"""Follow up the first comparison and prepare Tableau: python -m scripts.route_severity."""

import json
import sqlite3
import subprocess

import numpy as np
import pandas as pd
from scipy.stats import t

from scripts.compare_departure_windows import analyze, calculate, clustered_interval, point_estimates
from scripts.inspect_pilot import ROOT, require, sha256


PLAN_PATH = "analysis/route_severity_plan.json"


def outcome_at_threshold(frame, threshold):
    """Change the late-arrival threshold without removing cancellations or diversions."""
    require(threshold > 0, "The delay threshold must be positive.")
    result = frame.copy()
    completed = result["Cancelled"].eq(0) & result["Diverted"].eq(0)
    result["EventLate"] = (completed & result["ArrDelay"].ge(threshold)).astype(int)
    result["Disrupted"] = result[["EventCancelled", "EventDiverted", "EventLate"]].sum(axis=1)
    return result


def coverage_supported(morning, evening, months, weeks, policy):
    return (morning >= policy["minimum_flights_each_window"]
            and evening >= policy["minimum_flights_each_window"]
            and months >= policy["minimum_months"] and weeks >= policy["minimum_week_clusters"])


def adjusted_interval(point, standard_error, degrees_of_freedom, family_size, alpha=0.05):
    require(family_size >= 1, "An interval family must contain a comparison.")
    critical = float(t.ppf(1 - alpha / (2 * family_size), df=degrees_of_freedom))
    return point - critical * standard_error, point + critical * standard_error


def direction_label(supported, lower, upper):
    if not supported:
        return "Limited coverage"
    if lower > 0:
        return "Higher evening rate"
    if upper < 0:
        return "Higher morning rate"
    return "Uncertain direction"


def destination_records(frame, pairs, matched, protocol, plan, threshold):
    records = []
    all_windows = frame.loc[frame["Window"].isin(["morning", "evening"])].groupby("DestAirportID").size()
    for destination, group in pairs.groupby("DestAirportID", sort=True):
        group = group.copy()
        group["Weight"] = group["PooledFlights"] / group["PooledFlights"].sum()
        flights = matched.loc[matched["DestAirportID"].eq(destination)]
        dates = pd.to_datetime(flights["FlightDate"])
        weeks = int(((dates - pd.Timestamp(protocol["cluster_anchor"])).dt.days // 7).nunique())
        nm, ne = int(group["n_morning"].sum()), int(group["n_evening"].sum())
        months = int(group["Month"].nunique())
        supported = coverage_supported(nm, ne, months, weeks, plan["route_support"])
        interval = clustered_interval(group, flights, protocol) if supported else None
        record = {
            "destination_id": int(destination), "destination_code": str(flights["Dest"].iloc[0]),
            "threshold_minutes": threshold, "morning_flights": nm, "evening_flights": ne,
            "matched_groups": len(group), "matched_months": months, "week_clusters": weeks,
            "window_coverage": (nm + ne) / int(all_windows.loc[destination]),
            "coverage_supported": bool(supported),
            **point_estimates(group)["disrupted"], "pointwise_interval": interval,
        }
        records.append(record)
    return records


def sql_route_check(frame, protocol, records, threshold, root=ROOT):
    columns = ["DOT_ID_Reporting_Airline", "DestAirportID", "Month", "CRSDepTime",
               "Cancelled", "Diverted", "ArrDelay", "Origin", "Year"]
    with sqlite3.connect(":memory:") as connection:
        frame[columns].to_sql("flights", connection, index=False)
        sql = (root / "sql/route_severity.sql").read_text()
        rows = pd.read_sql_query(sql, connection, params={
            "threshold": threshold, "minimum": protocol["minimum_flights_per_window_per_stratum"]})
    expected = {item["destination_id"]: item for item in records}
    require(set(rows["DestAirportID"]) == set(expected), "SQL destination coverage differs.")
    for row in rows.to_dict("records"):
        reference = expected[row["DestAirportID"]]
        for column, key in [("groups", "matched_groups"), ("morning_flights", "morning_flights"),
                            ("evening_flights", "evening_flights"), ("morning_rate", "morning_rate"),
                            ("evening_rate", "evening_rate")]:
            require(np.isclose(row[column], reference[key], atol=1e-12, rtol=0),
                    f"SQL destination calculation differs for {reference['destination_code']} at {threshold} minutes.")
    return len(rows)


def compute(root=ROOT):
    plan = json.loads((root / PLAN_PATH).read_text())
    protocol, base_frame, _, _, _, previous = calculate(root)
    require(previous["input_sha256"] == plan["input_sha256"], "Follow-up input changed.")
    original = json.loads((root / "reports/morning_evening.json").read_text())
    results, pairs_by_threshold, matches_by_threshold, routes = {}, {}, {}, []
    checks = []

    def check(name, condition):
        checks.append({"check": name, "passed": bool(condition)})

    baseline_keys = None
    baseline_event = None
    for threshold in plan["threshold_minutes"]:
        frame = outcome_at_threshold(base_frame, threshold)
        result, pairs, matched = analyze(frame, protocol)
        keys = pairs[protocol["strata"] + ["n_morning", "n_evening", "PooledFlights"]]
        if baseline_keys is None:
            baseline_keys = keys
            baseline_event = frame["Disrupted"]
        else:
            check("Both thresholds use identical matched groups and flight counts", keys.equals(baseline_keys))
            check("The 60-minute outcome is a subset of the 15-minute outcome", frame["Disrupted"].le(baseline_event).all())
        if threshold == 15:
            check("The original overall 15-minute point estimates are reproduced", all(
                np.isclose(result["standardized"][key], original["primary"]["standardized"][key], atol=1e-12, rtol=0)
                for key in ["morning_rate", "evening_rate", "difference"]))
        records = destination_records(frame, pairs, matched, protocol, plan, threshold)
        checked = sql_route_check(frame, protocol, records, threshold, root)
        check(f"SQL independently reproduces all {checked} destinations at {threshold} minutes", checked == len(records))
        weights = [item["morning_flights"] + item["evening_flights"] for item in records]
        check(f"Destination common-mix rates reconcile to the overall {threshold}-minute rates", all(
            np.isclose(np.average([item[key] for item in records], weights=weights),
                       result["standardized"][key], atol=1e-12, rtol=0)
            for key in ["morning_rate", "evening_rate", "difference"]))
        results[threshold], pairs_by_threshold[threshold], matches_by_threshold[threshold] = result, pairs, matched
        routes.extend(records)

    supported_destinations = {item["destination_id"] for item in routes if item["coverage_supported"]}
    family_size = len(supported_destinations) * len(plan["threshold_minutes"])
    for record in routes:
        if record["coverage_supported"]:
            interval = record["pointwise_interval"]
            lower, upper = adjusted_interval(record["difference"], interval["standard_error"],
                                             interval["degrees_of_freedom"], family_size, plan["route_family_alpha"])
        else:
            lower, upper = None, None
        record["adjusted_lower"], record["adjusted_upper"] = lower, upper
        record["direction_label"] = direction_label(record["coverage_supported"], lower, upper)
        record["route_family_size"] = family_size
    check("Coverage rules select the same destinations at both thresholds", all(
        {item["destination_id"] for item in routes if item["threshold_minutes"] == threshold and item["coverage_supported"]}
        == supported_destinations for threshold in plan["threshold_minutes"]))
    require(all(item["passed"] for item in checks), "Follow-up checks need review.")
    plan_commit = subprocess.check_output(["git", "log", "-1", "--format=%H", "--", PLAN_PATH], cwd=root, text=True).strip()
    audit = {"plan_version": plan["version"], "plan_commit": plan_commit, "plan_sha256": sha256(root / PLAN_PATH),
             "input_sha256": previous["input_sha256"], "coverage": previous["coverage"],
             "overall": {str(key): value for key, value in results.items()}, "destinations": routes,
             "route_family_size": family_size, "supported_destinations": len(supported_destinations),
             "checks": checks}
    return plan, protocol, base_frame, pairs_by_threshold, matches_by_threshold, audit


def write_report(root, audit, tables):
    overall = tables["overall_comparison_2025.csv"]
    destinations = tables["destination_comparison_2025.csv"]
    global_rows = "\n".join(
        f"| {int(row['Delay Threshold Minutes'])} minutes | {row['Morning Disruption Rate']:.2%} | "
        f"{row['Evening Disruption Rate']:.2%} | {row['Gap pp']:+.2f} | "
        f"{row['Gap Interval Lower pp']:+.2f} to {row['Gap Interval Upper pp']:+.2f} |"
        for row in overall.to_dict("records")
    )
    labels = ["Higher evening rate", "Higher morning rate", "Uncertain direction", "Limited coverage"]
    evidence_rows = []
    for threshold in [15, 60]:
        counts = destinations.loc[destinations["Delay Threshold Minutes"].eq(threshold), "Direction Evidence"].value_counts()
        evidence_rows.append(f"| {threshold} minutes | " + " | ".join(str(int(counts.get(label, 0))) for label in labels) + " |")
    low = destinations.loc[destinations["Delay Threshold Minutes"].eq(15)].set_index("Destination Airport ID")
    examples = destinations.loc[destinations["Delay Threshold Minutes"].eq(60)].copy()
    examples["Flights"] = examples["Morning Flights"] + examples["Evening Flights"]
    examples = examples.sort_values(["Flights", "Destination Code"], ascending=[False, True]).head(8)
    example_rows = []
    for row in examples.to_dict("records"):
        bounds = (f"{row['Gap Interval Lower pp']:+.2f} to {row['Gap Interval Upper pp']:+.2f}"
                  if row["Coverage Supported"] else "Not displayed")
        gap15 = low.loc[row["Destination Airport ID"], "Gap pp"]
        example_rows.append(f"| {row['Destination Code']} — {row['Destination City']} | {row['Flights']:,} | "
                            f"{gap15:+.2f} | {row['Gap pp']:+.2f} | {bounds} | {row['Direction Evidence']} |")
    checks = "\n".join(f"| {item['check']} | PASS |" for item in audit["checks"] + audit["tableau_validation"])
    hour = overall.loc[overall["Delay Threshold Minutes"].eq(60)].iloc[0]
    plan_url = "https://github.com/JohnHeerema/LAX-FLIGHT-RELIABILITY/commit/" + audit["plan_commit"]
    text = f"""# Destination differences, one-hour delays, and Tableau inputs

**Follow-up finding:** With the same matched flights and common airline/destination/month mix, the 60-minute disruption rate is **{hour['Morning Disruption Rate']:.2%} for morning** and **{hour['Evening Disruption Rate']:.2%} for evening** departures. The evening-minus-morning difference is **{hour['Gap pp']:.2f} percentage points**, with an approximate pointwise 95% weekly-cluster interval of **{hour['Gap Interval Lower pp']:.2f} to {hour['Gap Interval Upper pp']:.2f} points**.

This is an exploratory extension after the first overall 15-minute result. The [follow-up plan](../docs/route_severity_plan.md) was [committed before estimating these extension results]({plan_url}). The original protocol and result are preserved. Final dashboard/story visualizations will be authored in **Tableau** using the validated CSV sources below.

## The stricter threshold changes the outcome, not the cohort

Both definitions count a cancellation or diversion as a disruption. For a completed, nondiverted flight, the arrival must be at least 15 or 60 minutes late respectively. No missing arrival value is replaced with zero.

Both comparisons contain **{audit['coverage']['retained_flights']:,} scheduled flights** in the same **706 airline/destination/month groups**, using the original 06:00–09:59 and 17:00–20:59 scheduled local departure windows. They cover **{audit['coverage']['retained_fraction_of_window_flights']:.1%} of flights in those windows**, rather than every LAX flight.

| Arrival-delay threshold, plus cancellations/diversions | Morning | Evening | Difference, pp | Approx. pointwise 95% interval, pp |
| --- | ---: | ---: | ---: | --- |
{global_rows}

The gap is smaller under the one-hour definition, while remaining positive in this matched historical comparison. This suggests the first result is not solely about delays shorter than an hour. It does not identify a causal effect, estimate trip-specific costs, or predict future operations. The 60-minute comparison is exploratory; its interval does not acquire confirmatory status by reusing the original data.

## Destination coverage and more cautious directional labels

There are **46 matched destinations**. **{audit['supported_destinations']}** meet the follow-up display-support rules: at least 100 flights in each window, six months, and 20 weekly clusters. The remaining destinations retain descriptive rates and counts, with **Limited coverage** labels and blank displayed intervals.

For supported destinations, the direction labels use approximate Bonferroni-adjusted intervals across **{audit['route_family_size']} destination/threshold comparisons**. This makes the intervals wider when many destinations are inspected. It does not remove the assumptions of the conditional weekly variance model or establish causal relationships.

| Threshold | Higher evening rate | Higher morning rate | Uncertain direction | Limited coverage |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(evidence_rows)}

An uncertain interval is not evidence of equal reliability. A limited-coverage label is not a recommendation. These destination labels should not be replaced by a blanket statement about all routes.

## Examples selected by exposure, not outcome

These are the eight destinations with the largest retained flight counts, as specified in advance. Positive gaps indicate higher evening disruption rates; negative gaps indicate higher morning point estimates. The interval shown is the more cautious route interval for the 60-minute definition.

| Destination | Retained flights | Gap at 15 min, pp | Gap at 60 min, pp | Adjusted 60-min interval, pp | 60-min direction evidence |
| --- | ---: | ---: | ---: | --- | --- |
{chr(10).join(example_rows)}

The [complete destination source](../data/tableau/destination_comparison_2025.csv) includes all destinations, both thresholds, coverage, pointwise bounds on supported routes, adjusted bounds, and direction labels. Overall results still include every originally matched destination; the stricter destination display rules do not redefine the overall cohort.

## Tableau sources ready for authoring

| Source | Rows | One row represents |
| --- | ---: | --- |
| [Overall comparison](../data/tableau/overall_comparison_2025.csv) | {len(overall):,} | One delay threshold for the full-year matched cohort |
| [Destination comparison](../data/tableau/destination_comparison_2025.csv) | {len(destinations):,} | One destination and threshold |
| [Comparison pairs](../data/tableau/comparison_pairs_2025.csv) | {len(tables['comparison_pairs_2025.csv']):,} | One matched airline/destination/month/window, with both thresholds as columns |
| [Field dictionary](../data/tableau/data_dictionary.csv) | {len(tables['data_dictionary.csv']):,} | One source field and its units/aggregation guidance |

The [Tableau data guide](../docs/tableau_data_guide.md) explains which source to use, the ratio-of-sums needed for filtered comparisons, and the distinction between percent rates and percentage-point gaps. The [export manifest](../data/manifests/tableau_sources_2025.json) records file checksums and row counts.

The first authoring checkpoint is deliberately small: connect the **overall comparison** CSV as a text file and verify its two rows, for thresholds 15 and 60. The Tableau workbook and its visual checks are the next stage.

## Checks and provenance

The original extract checksum is unchanged. SQL independently reconstructs time windows, matched groups, and every destination's point estimates at both thresholds. Destination common-mix rates reconcile to their overall rates when weighted by retained pooled flights.

The CSV files are read back after writing. The exact ratio-of-sums intended for Tableau reproduces the global results, all destination results, and the earlier month-by-month results. Keys are unique, the higher-threshold counts are nested, rates use fractions, gaps use percentage points, and limited-coverage bounds remain blank.

| Check | Result |
| --- | --- |
{checks}

Airport-city labels come from `DestCityName` in the pinned BTS monthly files, with a [lookup provenance record](../data/reference/destination_labels_2025.json). Reporting operating-carrier names come from the DOT report appendix. Names and codes remain in their historical 2025 reporting scope, including separate Alaska and Hawaiian labels.

The [machine-readable audit](route_severity.json) records the plan commit, input checksum, full-precision results, coverage, and checks. Reproduce this checkpoint with `python -m scripts.route_severity` after building the validated year extract. Cached, checked lookup tables avoid rereading the source archives on subsequent runs.
"""
    (root / "reports/route_severity.md").write_text(text, encoding="utf-8", newline="\n")


def run(root=ROOT):
    from scripts.tableau_exports import write_sources
    plan, protocol, frame, pairs, matches, audit = compute(root)
    tables, checks = write_sources(audit, pairs, frame, root)
    audit["tableau_validation"] = checks
    (root / "reports/route_severity.json").write_text(json.dumps(audit, indent=2) + "\n", newline="\n")
    write_report(root, audit, tables)
    print(json.dumps({"overall": {key: value["standardized"] for key, value in audit["overall"].items()},
                      "supported_destinations": audit["supported_destinations"],
                      "route_family_size": audit["route_family_size"],
                      "tableau_rows": {name: len(table) for name, table in tables.items()},
                      "validation_checks": len(audit["checks"]) + len(checks)}, indent=2))
    return audit


if __name__ == "__main__":
    run()
