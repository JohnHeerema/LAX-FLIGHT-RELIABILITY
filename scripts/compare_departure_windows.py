"""Compare morning/evening reliability: python -m scripts.compare_departure_windows."""

import json
from pathlib import Path
import sqlite3
import subprocess

import numpy as np
import pandas as pd
from scipy.stats import t

from scripts.inspect_pilot import ROOT, TEXT_COLUMNS, require, sha256


PROTOCOL_PATH = "analysis/morning_evening_protocol.json"
COMPONENTS = {"disrupted": "Disrupted", "cancelled": "EventCancelled",
              "diverted": "EventDiverted", "late_completion": "EventLate"}


def prepare(frame, protocol):
    """Keep raw arrival blanks; derive outcome indicators and scheduled time windows."""
    frame = frame.copy().reset_index(drop=True)
    require(frame["Origin"].eq(protocol["origin"]).all(), "Unexpected origin in comparison data.")
    require(frame["Year"].eq(protocol["year"]).all(), "Unexpected year in comparison data.")
    dates = pd.to_datetime(frame["FlightDate"], format="%Y-%m-%d", errors="raise")
    require((dates.notna() & dates.dt.year.eq(protocol["year"])).all(), "Unexpected flight date.")
    require(dates.dt.month.eq(frame["Month"]).all(), "Month does not match the flight date.")
    require((dates.dt.dayofweek + 1).eq(frame["DayOfWeek"]).all(), "Weekday does not match the flight date.")
    flags = frame[["Cancelled", "Diverted"]]
    require(flags.isin([0, 1]).all().all(), "Outcome flags must be complete and binary.")
    require(not flags.sum(axis=1).gt(1).any(), "Cancellation and diversion flags overlap.")
    completed = frame["Cancelled"].eq(0) & frame["Diverted"].eq(0)
    require(frame.loc[completed, "ArrDelay"].notna().all(), "Completed arrival delay is missing.")
    require(np.isfinite(frame.loc[completed, "ArrDelay"]).all(), "Completed arrival delay is not finite.")

    codes = frame["CRSDepTime"].astype("string")
    valid = codes.str.fullmatch(r"(?:[01][0-9]|2[0-3])[0-5][0-9]|2400")
    require(valid.fillna(False).all(), "Invalid scheduled local HHMM code.")
    minute = (codes.str[:2].astype(int) * 60 + codes.str[2:].astype(int)) % (24 * 60)
    frame["Window"] = "outside"
    for name, window in protocol["windows"].items():
        frame.loc[minute.ge(window["start_minute"]) & minute.lt(window["end_minute"]), "Window"] = name

    frame["EventCancelled"] = frame["Cancelled"].eq(1).astype(int)
    frame["EventDiverted"] = frame["Diverted"].eq(1).astype(int)
    frame["EventLate"] = (completed & frame["ArrDelay"].ge(15)).astype(int)
    frame["Disrupted"] = frame[["EventCancelled", "EventDiverted", "EventLate"]].sum(axis=1)
    require(frame["Disrupted"].isin([0, 1]).all(), "Disruption components must be mutually exclusive.")
    return frame


def matched_pairs(frame, strata, minimum):
    """Retain supported comparisons and use exactly the same weights for both windows."""
    require(minimum >= 1, "The support threshold must be positive.")
    require(frame[strata].notna().all().all(), "A comparison identifier is missing.")
    selected = frame.loc[frame["Window"].isin(["morning", "evening"])]
    aggregates = {"n": ("Disrupted", "size")}
    aggregates.update({name: (column, "sum") for name, column in COMPONENTS.items()})
    grouped = selected.groupby(strata + ["Window"], sort=True).agg(**aggregates).reset_index()
    tables = []
    for window in ["morning", "evening"]:
        table = grouped.loc[grouped["Window"].eq(window)].drop(columns="Window")
        tables.append(table.rename(columns={name: name + "_" + window for name in aggregates}))
    pairs = tables[0].merge(tables[1], on=strata, how="outer", validate="one_to_one")
    count_columns = [column for column in pairs.columns if column not in strata]
    pairs[count_columns] = pairs[count_columns].fillna(0).astype(int)
    pairs = pairs.loc[pairs["n_morning"].ge(minimum) & pairs["n_evening"].ge(minimum)].copy()
    require(not pairs.empty, "No groups meet the support rule in both windows.")
    pairs = pairs.sort_values(strata, kind="stable").reset_index(drop=True)
    pairs["PairID"] = np.arange(len(pairs))
    pairs["PooledFlights"] = pairs["n_morning"] + pairs["n_evening"]
    pairs["Weight"] = pairs["PooledFlights"] / pairs["PooledFlights"].sum()
    for window in ["morning", "evening"]:
        pairs["rate_" + window] = pairs["disrupted_" + window] / pairs["n_" + window]
    matched = selected.merge(pairs[strata + ["PairID", "Weight"]], on=strata, how="inner", validate="many_to_one")
    return pairs, matched


def point_estimates(pairs):
    results = {}
    for name in COMPONENTS:
        morning = float(np.dot(pairs["Weight"], pairs[name + "_morning"] / pairs["n_morning"]))
        evening = float(np.dot(pairs["Weight"], pairs[name + "_evening"] / pairs["n_evening"]))
        results[name] = {"morning_rate": morning, "evening_rate": evening, "difference": evening - morning}
    return results


def clustered_interval(pairs, matched, protocol, cluster_days=7):
    """Scalar CR1 sandwich for the contrast of saturated group/window means."""
    lookup = pairs.set_index("PairID")
    ids = matched["PairID"].to_numpy()
    evening = matched["Window"].eq("evening").to_numpy()
    count = np.where(evening, lookup.loc[ids, "n_evening"], lookup.loc[ids, "n_morning"])
    mean = np.where(evening, lookup.loc[ids, "rate_evening"], lookup.loc[ids, "rate_morning"])
    weight = lookup.loc[ids, "Weight"].to_numpy()
    contribution = np.where(evening, 1.0, -1.0) * weight * (matched["Disrupted"].to_numpy() - mean) / count
    require(np.isclose(contribution.sum(), 0, atol=1e-12), "Residual contrast contributions do not sum to zero.")
    dates = pd.to_datetime(matched["FlightDate"], format="%Y-%m-%d")
    groups = ((dates - pd.Timestamp(protocol["cluster_anchor"])).dt.days // cluster_days).to_numpy()
    labels, inverse = np.unique(groups, return_inverse=True)
    totals = np.bincount(inverse, weights=contribution)
    g, n, k = len(labels), len(matched), 2 * len(pairs)
    require(g >= 2 and n > k, "Not enough clusters or residual degrees of freedom for an interval.")
    correction = g / (g - 1) * (n - 1) / (n - k)
    standard_error = float(np.sqrt(correction * np.dot(totals, totals)))
    difference = point_estimates(pairs)["disrupted"]["difference"]
    critical = float(t.ppf(0.5 + protocol["confidence_level"] / 2, df=g - 1))
    return {"lower": difference - critical * standard_error, "upper": difference + critical * standard_error,
            "standard_error": standard_error, "clusters": g, "cluster_days": cluster_days,
            "residual_parameters": k, "correction": correction, "degrees_of_freedom": g - 1}


def summarize_window(frame):
    return {window: {"scheduled_flights": int(frame["Window"].eq(window).sum()),
                     "disruptions": int(frame.loc[frame["Window"].eq(window), "Disrupted"].sum()),
                     "rate": float(frame.loc[frame["Window"].eq(window), "Disrupted"].mean())}
            for window in ["morning", "evening"]}


def analyze(frame, protocol, minimum=None, add_weekday=False, cluster_days=None):
    strata = list(protocol["strata"]) + (["DayOfWeek"] if add_weekday else [])
    minimum = minimum if minimum is not None else protocol["minimum_flights_per_window_per_stratum"]
    cluster_days = cluster_days if cluster_days is not None else protocol["primary_cluster_days"]
    pairs, matched = matched_pairs(frame, strata, minimum)
    components = point_estimates(pairs)
    result = {
        "strata": strata, "minimum": minimum, "eligible_pairs": len(pairs),
        "n_morning": int(pairs["n_morning"].sum()), "n_evening": int(pairs["n_evening"].sum()),
        "components": components, "standardized": components["disrupted"],
        "interval": clustered_interval(pairs, matched, protocol, cluster_days),
        "unadjusted_retained": summarize_window(matched),
    }
    return result, pairs, matched


def sql_check(frame, protocol, result, root=ROOT):
    with sqlite3.connect(":memory:") as connection:
        # Read the raw fields; the SQL assigns windows and outcomes independently.
        columns = ["DOT_ID_Reporting_Airline", "DestAirportID", "Month", "CRSDepTime",
                   "Cancelled", "Diverted", "ArrDelay", "Origin", "Year"]
        frame[columns].to_sql("flights", connection, index=False)
        sql = (root / "sql/morning_evening.sql").read_text()
        row = pd.read_sql_query(sql, connection, params={"minimum": result["minimum"]}).iloc[0]
    expected = {"eligible_pairs": result["eligible_pairs"], "n_morning": result["n_morning"],
                "n_evening": result["n_evening"],
                "disrupted_morning": result["unadjusted_retained"]["morning"]["disruptions"],
                "disrupted_evening": result["unadjusted_retained"]["evening"]["disruptions"],
                "morning_rate": result["standardized"]["morning_rate"],
                "evening_rate": result["standardized"]["evening_rate"]}
    require(all(np.isclose(float(row[key]), value, atol=1e-12, rtol=0) for key, value in expected.items()),
            "Independent SQL comparison does not match Python.")
    return {key: float(row[key]) for key in expected}


def monthly_comparison(pairs):
    records = []
    for month, group in pairs.groupby("Month", sort=True):
        group = group.copy()
        group["Weight"] = group["PooledFlights"] / group["PooledFlights"].sum()
        record = {"month": f"2025-{int(month):02d}", "eligible_pairs": len(group),
                  "pooled_flights": int(group["PooledFlights"].sum()), **point_estimates(group)["disrupted"]}
        records.append(record)
    return pd.DataFrame(records)


def validation_checks(result, pairs, matched, monthly, sensitivities):
    checks = []

    def check(name, value):
        checks.append({"check": name, "passed": bool(value)})

    check("Common group weights are positive and sum to one", pairs["Weight"].gt(0).all() and np.isclose(pairs["Weight"].sum(), 1))
    check("Both windows meet the predeclared support rule",
          pairs[["n_morning", "n_evening"]].ge(result["minimum"]).all().all())
    check("Retained flight counts reconcile", len(matched) == result["n_morning"] + result["n_evening"])
    for window in ["morning", "evening"]:
        component_sum = sum(result["components"][name][window + "_rate"] for name in ["cancelled", "diverted", "late_completion"])
        check(window.title() + " disruption components reconcile", np.isclose(component_sum, result["standardized"][window + "_rate"]))
    check("All 12 months support the primary comparison", len(monthly) == 12)
    for value in ["morning_rate", "evening_rate", "difference"]:
        combined = np.average(monthly[value], weights=monthly["pooled_flights"])
        check("Monthly " + value + " reconciles to the annual contrast", np.isclose(combined, result["standardized"][value]))
    longer = next(item for item in sensitivities if item["id"] == "two_week_clusters")
    check("Longer clustering changes uncertainty, not the primary point estimate",
          longer["eligible_pairs"] == result["eligible_pairs"]
          and np.isclose(longer["standardized"]["difference"], result["standardized"]["difference"]))
    require(all(item["passed"] for item in checks), "Comparison validation needs review.")
    return checks


def calculate(root=ROOT):
    protocol = json.loads((root / PROTOCOL_PATH).read_text())
    manifest = json.loads((root / protocol["input_manifest"]).read_text())
    extract = root / protocol["input_extract"]
    require(extract.exists(), "Build the validated year extract first: python -m scripts.build_year")
    digest = sha256(extract)
    require(digest == protocol["input_sha256"] == manifest["derived_extract"]["sha256"],
            "The comparison input differs from the protocol's validated snapshot.")
    frame = pd.read_csv(extract, dtype={name: "string" for name in TEXT_COLUMNS})
    require(len(frame) == manifest["derived_extract"]["rows"], "Input row count changed.")
    frame = prepare(frame, protocol)
    primary, pairs, matched = analyze(frame, protocol)
    independent = sql_check(frame, protocol, primary, root=root)
    sensitivities = []
    for specification in protocol["sensitivity_checks"]:
        result, _, _ = analyze(frame, protocol, minimum=specification["minimum"],
                               add_weekday=specification["add_weekday"],
                               cluster_days=specification["cluster_days"])
        sensitivities.append({"id": specification["id"], **result})
    monthly = monthly_comparison(pairs)
    checks = validation_checks(primary, pairs, matched, monthly, sensitivities)
    all_windows = summarize_window(frame)
    coverage = {
        "source_flights": len(frame),
        "outside_windows": int(frame["Window"].eq("outside").sum()),
        "all_window_flights": sum(item["scheduled_flights"] for item in all_windows.values()),
        "retained_flights": len(matched),
        "retained_fraction_of_window_flights": len(matched) / sum(item["scheduled_flights"] for item in all_windows.values()),
        "excluded_window_flights": sum(item["scheduled_flights"] for item in all_windows.values()) - len(matched),
        "matched_reporting_airline_codes": sorted(matched["Reporting_Airline"].unique().tolist()),
        "matched_destination_airports": int(matched["DestAirportID"].nunique()),
    }
    for item in sensitivities:
        item["retained_fraction_of_window_flights"] = (item["n_morning"] + item["n_evening"]) / coverage["all_window_flights"]
    try:
        protocol_commit = subprocess.check_output(
            ["git", "log", "-1", "--format=%H", "--", PROTOCOL_PATH], cwd=root, text=True,
            stderr=subprocess.DEVNULL,
        ).strip() or None
    except (FileNotFoundError, subprocess.CalledProcessError):
        protocol_commit = None
    audit = {
        "protocol_version": protocol["version"], "protocol_sha256": sha256(root / PROTOCOL_PATH),
        "protocol_commit": protocol_commit, "input_sha256": digest, "coverage": coverage,
        "unadjusted_all_windows": all_windows, "primary": primary,
        "sensitivities": sensitivities, "monthly": monthly.to_dict("records"),
        "validation": checks, "sql_cross_check": independent,
    }
    return protocol, frame, pairs, matched, monthly, audit


def make_figure(root, monthly, audit):
    """Produce a standalone vector figure and a local PNG for visual inspection."""
    import calendar
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none",
                         "svg.hashsalt": "lax-morning-evening-v1", "axes.unicode_minus": False})
    primary = audit["primary"]
    rates, interval = primary["standardized"], primary["interval"]
    navy, muted, morning, evening = "#173042", "#5B6D7B", "#317F8C", "#C45F42"
    background, grid = "#F8FAFB", "#DFE6EB"
    fig = plt.figure(figsize=(12.2, 8.8), facecolor=background)
    direction = "more" if rates["difference"] >= 0 else "fewer"
    fig.text(.065, .953, f"Evening departures had {direction} disruptions", fontsize=23, weight="bold", color=navy)
    fig.text(.065, .913, "Same airline, destination and month mix  |  LAX, 2025", fontsize=11.5, color=muted)
    fig.text(.065, .842, f"{rates['difference'] * 100:+.2f} percentage points", fontsize=27, weight="bold", color=evening)
    fig.text(.065, .801, f"Approx. 95% week-cluster interval: {interval['lower'] * 100:+.2f} to {interval['upper'] * 100:+.2f} points", fontsize=11.5, color=muted)

    ax = fig.add_axes([.105, .255, .345, .43], facecolor=background)
    values = [100 * rates["morning_rate"], 100 * rates["evening_rate"]]
    ax.barh([1, 0], values, color=[morning, evening], height=.45, zorder=3)
    ax.set_yticks([1, 0], ["Morning\n6–10 a.m.", "Evening\n5–9 p.m."], color=navy, fontsize=11)
    maximum = np.ceil((max(values) + 5) / 10) * 10
    ax.set_xlim(0, maximum)
    ax.set_ylim(-.55, 1.55)
    ax.set_xticks(np.arange(0, maximum + .1, 10))
    ax.set_xlabel("Percent of scheduled flights", color=muted, fontsize=10.5, labelpad=10)
    ax.set_title("Common-mix disruption rate", loc="left", fontsize=13, color=navy, pad=16, weight="bold")
    ax.grid(axis="x", color=grid, zorder=0)
    ax.tick_params(axis="both", length=0, colors=muted, labelsize=10.5)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for y, value in zip([1, 0], values):
        ax.text(value + .6, y, f"{value:.2f}%", va="center", fontsize=13.5, weight="bold", color=navy)
    fig.text(.105, .165, f"{primary['n_morning']:,} morning · {primary['n_evening']:,} evening flights", color=muted, fontsize=10)

    ax2 = fig.add_axes([.60, .237, .325, .478], facecolor=background)
    gaps = monthly["difference"].to_numpy() * 100
    ys = np.arange(len(monthly))
    ax2.hlines(ys, 0, gaps, color="#E2B7A9", linewidth=2, zorder=2)
    ax2.scatter(gaps, ys, color=evening, s=38, zorder=3)
    labels = [calendar.month_abbr[int(value[-2:])] for value in monthly["month"]]
    ax2.set_yticks(ys, labels, color=navy, fontsize=10)
    ax2.invert_yaxis()
    ax2.set_xlim(min(0, gaps.min() - 2), max(5, gaps.max() + 3))
    ax2.axvline(0, color="#A8B7C2", linewidth=1)
    ax2.grid(axis="x", color=grid, zorder=0)
    ax2.set_xlabel("Evening minus morning, percentage points", fontsize=10.5, color=muted, labelpad=10)
    ax2.set_title("Direction across the year", loc="left", fontsize=13, weight="bold", color=navy, pad=14)
    ax2.tick_params(axis="both", length=0, colors=muted, labelsize=10)
    for spine in ax2.spines.values():
        spine.set_visible(False)
    for y, gap in zip(ys, gaps):
        ax2.text(gap + .45, y, f"{gap:+.1f}", va="center", color=navy, fontsize=9.5)

    coverage = audit["coverage"]
    fig.text(.065, .108, "Disruption = canceled, diverted, or arrived 15+ minutes late.", fontsize=10, color=navy)
    fig.text(.065, .076, f"{coverage['retained_flights']:,} matched flights · {primary['eligible_pairs']:,} comparison groups · {coverage['retained_fraction_of_window_flights']:.1%} of flights in the two windows.", fontsize=9.5, color=muted)
    fig.text(.065, .043, "Historical association, not a causal estimate or future-flight prediction. Monthly points are descriptive.", fontsize=9.5, color=muted)
    (root / "reports/figures").mkdir(parents=True, exist_ok=True)
    fig.savefig(root / "reports/figures/morning_evening.svg", metadata={"Date": None, "Creator": "LAX Flight Reliability"}, facecolor=background)
    fig.savefig(root / "data/interim/morning_evening_preview.png", dpi=150, metadata={"Software": "LAX Flight Reliability"}, facecolor=background)
    plt.close(fig)


def write_report(root, audit):
    primary, coverage = audit["primary"], audit["coverage"]
    point, interval = primary["standardized"], primary["interval"]
    all_raw, retained_raw = audit["unadjusted_all_windows"], primary["unadjusted_retained"]
    rows = []
    for label, values in [("All flights in the two windows, unadjusted", all_raw),
                          ("Retained comparable flights, unadjusted", retained_raw)]:
        m, e = values["morning"]["rate"], values["evening"]["rate"]
        rows.append(f"| {label} | {m:.2%} | {e:.2%} | {(e-m)*100:+.2f} points |")
    rows.append(f"| **Retained flights, common airline/destination/month mix** | **{point['morning_rate']:.2%}** | **{point['evening_rate']:.2%}** | **{point['difference']*100:+.2f} points** |")
    comparison_table = "\n".join(rows)
    components = "\n".join(
        f"| {label} | {primary['components'][key]['morning_rate']:.2%} | {primary['components'][key]['evening_rate']:.2%} | {primary['components'][key]['difference']*100:+.2f} points |"
        for key, label in [("cancelled", "Canceled"), ("diverted", "Diverted"), ("late_completion", "Completed arrival 15+ minutes late")]
    )
    names = {"minimum_5": "Minimum 5 per window", "minimum_20": "Minimum 20 per window",
             "match_weekday": "Also match weekday; minimum 3", "two_week_clusters": "Primary groups, two-week uncertainty clusters"}
    sensitivity_rows = "\n".join(
        f"| {names[item['id']]} | {item['n_morning']+item['n_evening']:,} | {item['retained_fraction_of_window_flights']:.1%} | "
        f"{item['standardized']['difference']*100:+.2f} | {item['interval']['lower']*100:+.2f} to {item['interval']['upper']*100:+.2f} |"
        for item in audit["sensitivities"]
    )
    month_rows = "\n".join(
        f"| {item['month']} | {item['morning_rate']:.2%} | {item['evening_rate']:.2%} | {item['difference']*100:+.2f} points | {item['pooled_flights']:,} |"
        for item in audit["monthly"]
    )
    positives = sum(item["difference"] > 0 for item in audit["monthly"])
    direction = "higher" if point["difference"] > 0 else "lower"
    protocol_link = ("https://github.com/JohnHeerema/LAX-FLIGHT-RELIABILITY/commit/" + audit["protocol_commit"]
                     if audit["protocol_commit"] else "../docs/morning_evening_plan.md")
    checks = "\n".join(f"| {item['check']} | PASS |" for item in audit["validation"])
    content = f"""# Morning and evening departures: the same airline, destination and month mix

**Finding:** Among the supported comparisons, evening flights had a **{abs(point['difference'])*100:.2f}-percentage-point {direction} arrival-disruption rate**. The common-mix rates were **{point['morning_rate']:.2%} in the morning** and **{point['evening_rate']:.2%} in the evening**. The approximate 95% week-cluster interval for evening minus morning is **{interval['lower']*100:+.2f} to {interval['upper']*100:+.2f} points**.

This is a historical association in the covered 2025 flights. The interval is conditional on the comparison design and its dependence assumptions, not a prediction interval for a future flight.

For scale, the standardized gap corresponds to about **{abs(point['difference'])*1000:.0f} more disruptions per 1,000 scheduled flights** at that common mix.

![Common-mix disruption rates and monthly gaps](figures/morning_evening.svg)

## What was compared

Morning means scheduled departure **06:00–09:59**, and evening means **17:00–20:59**, in LAX local time. A disruption is a **cancellation, diversion, or completed arrival at least 15 minutes late**. Its denominator includes all scheduled flights in the selected group; ordinary arrival-delay blanks are preserved.

Each comparison group uses the **same reporting operating-carrier DOT ID, destination airport ID, and month**, with at least 10 morning and 10 evening flights. We calculate both window rates inside each group, then give both windows the same weights based on that group's combined scheduled flights. This creates a common airline/destination/month mix.

The [analysis plan](../docs/morning_evening_plan.md) and [executable protocol](../analysis/morning_evening_protocol.json) were [committed before the outcome comparisons were calculated]({protocol_link}). The primary specification was kept after inspecting its results.

## How much of the dataset supports this comparison?

| Coverage step | Flights |
| --- | ---: |
| Full validated LAX dataset | {coverage['source_flights']:,} |
| Scheduled outside the two selected windows | {coverage['outside_windows']:,} |
| All flights inside the two windows | {coverage['all_window_flights']:,} |
| Inside the windows but without supported comparisons | {coverage['excluded_window_flights']:,} |
| **Retained in the primary comparison** | **{coverage['retained_flights']:,}** |

The retained flights comprise **{primary['n_morning']:,} morning** and **{primary['n_evening']:,} evening** departures, across **{primary['eligible_pairs']:,} airline/destination/month groups**, **{len(coverage['matched_reporting_airline_codes'])} reporting airline codes**, and **{coverage['matched_destination_airports']} destinations**. They represent **{coverage['retained_fraction_of_window_flights']:.1%} of flights in the selected windows**. These exclusions concern this comparison only; the full dataset remains intact.

The remaining windows or routes may have a different relationship. The result should not be described as the difference for every LAX flight or every destination.

## Raw and common-mix comparisons

| Comparison | Morning | Evening | Evening minus morning |
| --- | ---: | ---: | ---: |
{comparison_table}

The change between the first two rows reflects which flights have supported counterparts. The change between the second and third rows is the reweighting to a common airline/destination/month mix. Those are separate steps; the entire change from the first to the third row should not be attributed to adjustment alone.

## What drives the gap?

These are common-mix component rates **per scheduled flight**, using the same groups and weights as the main result.

| Component | Morning | Evening | Evening minus morning |
| --- | ---: | ---: | ---: |
{components}

The observed difference is dominated by late completed arrivals; the cancellation component is much smaller. Diversion rates differ in the opposite direction. These components add to the composite before rounding. They describe observed rates, without establishing equivalence or statistical differences for each component individually.

The earlier conditional arrival-delay measure in the dataset report has a different denominator: completed, nondiverted arrivals. The component above instead divides late completed arrivals by all scheduled flights, so it can add correctly to cancellations and diversions.

## Does the pattern depend on one month?

The evening-minus-morning common-mix difference is positive in **{positives} of {len(audit['monthly'])} months**. Each month uses its own supported groups and common weights.

| Month | Morning | Evening | Difference | Retained flights |
| --- | ---: | ---: | ---: | ---: |
{month_rows}

Monthly points are descriptive; they do not constitute 12 separately confirmed causal effects. The annual result uses pooled-flight weights across months, rather than an unweighted average of monthly rates or gaps.

## Sensitivity checks specified in advance

| Specification | Retained flights | Share of window flights | Gap, points | Approx. 95% interval, points |
| --- | ---: | ---: | ---: | --- |
{sensitivity_rows}

The weekday check compares flights with matching scheduled weekdays as well as airline, destination, and month. The support checks change the comparison population; the two-week check keeps the primary population and point estimate, changing the uncertainty calculation only. All specified results are shown, without choosing a replacement main result after seeing them.

## How uncertainty was calculated

The primary interval groups residual contributions by **{interval['clusters']} calendar-week clusters**, allowing flights in a week to share operational conditions. It uses a CR1 finite-sample correction and a Student t critical value with **{interval['degrees_of_freedom']} degrees of freedom**. It treats the observed group weights and comparison design as fixed. The exact scalar calculation and correction are explained in the [plan](../docs/morning_evening_plan.md).

The dataset contains the recorded flights for 2025. The interval concerns an approximate model of operational variability; the observed historical rates themselves are known for this dataset. Independence across weekly clusters is assumed. The two-week sensitivity considers longer shared conditions but does not prove that all remaining dependence is absent. Unmeasured differences can still explain part of the association.

## Checks supporting this result

The input matches the validated extract checksum. A [separate SQL query](../sql/morning_evening.sql) reassigns time windows from raw HHMM codes, rebuilds the composite from raw outcome fields, and recalculates grouping, counts, and common-mix rates. Its point estimates agree with Python to an absolute tolerance of 1e-12.

Focused tests include a hand-calculated reversal of raw versus common-mix rates, a separate saturated-regression matrix covariance calculation, time-window boundaries, support rules, preserved missing arrivals, and an SQL check that ignores Python's derived outcome and window labels.

| Analysis check | Result |
| --- | --- |
{checks}

The [JSON audit](morning_evening.json) stores full-precision results, input/protocol checksums, the protocol commit, coverage, sensitivities, and validation. The [matched group table](../data/summary/morning_evening_pairs.csv) supports numerical review; small groups in that file are not standalone route recommendations.

## What a planner can use, and what remains unknown

The comparison supports treating departure time as a useful historical reliability consideration when evaluating otherwise practical options. It supports reviewing morning availability for a time-sensitive trip while still checking the particular airline, route, weekday, price, and current schedule. It does not establish that moving a flight's departure time would itself cause the observed improvement.

This analysis does not identify the operational mechanism, estimate financial savings, guarantee future performance, or establish a preferred time for every route. A route-specific view and a simple dashboard are the next steps toward a usable planning tool.

## Reproduce the analysis

Install the pinned requirements and build the validated year extract, then run:

```bash
python -m scripts.compare_departure_windows
python -m unittest discover -s tests -v
```

The command needs only the cached validated LAX extract. It checks the input checksum and regenerates the report, numerical audit, matched groups, monthly/sensitivity CSVs, and standalone SVG. The PNG under `data/interim/` is a local preview for figure review.
"""
    (root / "reports/morning_evening.md").write_text(content, encoding="utf-8", newline="\n")


def run(root=ROOT):
    protocol, frame, pairs, matched, monthly, audit = calculate(root)
    for directory in ["data/summary", "reports/figures", "data/interim"]:
        (root / directory).mkdir(parents=True, exist_ok=True)
    labels = frame.groupby(protocol["strata"], as_index=False).agg(
        Reporting_Airline=("Reporting_Airline", "first"), Dest=("Dest", "first"))
    export_pairs = pairs.merge(labels, on=protocol["strata"], how="left", validate="one_to_one")
    export_pairs.to_csv(root / "data/summary/morning_evening_pairs.csv", index=False, lineterminator="\n")
    monthly.to_csv(root / "data/summary/morning_evening_monthly.csv", index=False, lineterminator="\n")
    sensitivity = pd.DataFrame([{
        "specification": item["id"], "eligible_pairs": item["eligible_pairs"],
        "retained_flights": item["n_morning"] + item["n_evening"],
        "coverage": item["retained_fraction_of_window_flights"], **item["standardized"],
        "interval_lower": item["interval"]["lower"], "interval_upper": item["interval"]["upper"],
        "cluster_days": item["interval"]["cluster_days"], "clusters": item["interval"]["clusters"],
    } for item in audit["sensitivities"]])
    sensitivity.to_csv(root / "data/summary/morning_evening_sensitivity.csv", index=False, lineterminator="\n")
    (root / "reports/morning_evening.json").write_text(json.dumps(audit, indent=2) + "\n", newline="\n")
    write_report(root, audit)
    make_figure(root, monthly, audit)
    print(json.dumps({"coverage": audit["coverage"], "standardized": audit["primary"]["standardized"],
                      "interval": audit["primary"]["interval"], "analysis_checks": len(audit["validation"]),
                      "report": "reports/morning_evening.md"}, indent=2))
    return audit


if __name__ == "__main__":
    run()
