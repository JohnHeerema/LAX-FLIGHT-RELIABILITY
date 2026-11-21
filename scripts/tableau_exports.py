"""Build Tableau sources with explicit grains and validated ratio-of-sums inputs."""

import json
import zipfile

import numpy as np
import pandas as pd

from scripts.build_year import get_month_archive
from scripts.inspect_pilot import ROOT, require, sha256


def destination_labels(root=ROOT):
    path = root / "data/reference/destination_labels_2025.csv"
    metadata = path.with_suffix(".json")
    source_manifest = root / "data/manifests/year_2025.json"
    source_hash = sha256(source_manifest)
    if path.exists():
        require(metadata.exists(), "Destination labels have no provenance record.")
        reference = json.loads(metadata.read_text())
        require(reference["source_manifest_sha256"] == source_hash and reference["csv_sha256"] == sha256(path),
                "Destination labels differ from their recorded source snapshot.")
        return pd.read_csv(path)

    parts = []
    for month in range(1, 13):
        archive_path, source = get_month_archive(root, month, offline=True)
        with zipfile.ZipFile(archive_path) as archive:
            member = source.get("csv_member") or next(name for name in archive.namelist() if name.endswith(".csv"))
            with archive.open(member) as stream:
                for chunk in pd.read_csv(stream, usecols=["Origin", "DestAirportID", "Dest", "DestCityName"], chunksize=100_000):
                    parts.append(chunk.loc[chunk["Origin"].eq("LAX"), ["DestAirportID", "Dest", "DestCityName"]].drop_duplicates())
        print(f"Destination labels checked against {month:02d}/2025 source", flush=True)
    labels = pd.concat(parts, ignore_index=True).drop_duplicates().sort_values("DestAirportID").reset_index(drop=True)
    require(not labels["DestAirportID"].duplicated().any(), "A destination ID has conflicting display labels.")
    require(labels.notna().all().all(), "A destination display label is missing.")
    labels = labels.rename(columns={"DestAirportID": "Destination Airport ID", "Dest": "Destination Code", "DestCityName": "Destination City"})
    labels.to_csv(path, index=False, lineterminator="\n")
    reference = {"source_manifest": "data/manifests/year_2025.json", "source_manifest_sha256": source_hash,
                 "filter": "Origin == LAX, all 12 pinned monthly archives",
                 "source_columns": ["DestAirportID", "Dest", "DestCityName"],
                 "rows": len(labels), "csv_sha256": sha256(path)}
    metadata.write_text(json.dumps(reference, indent=2) + "\n", newline="\n")
    return labels


def pair_source(pairs_by_threshold, airline_labels, destination_lookup):
    """One row per group/window; two thresholds are columns, not duplicate rows."""
    base, higher = pairs_by_threshold[15], pairs_by_threshold[60]
    require(base[["PairID", "DOT_ID_Reporting_Airline", "DestAirportID", "Month", "n_morning", "n_evening"]].equals(
        higher[["PairID", "DOT_ID_Reporting_Airline", "DestAirportID", "Month", "n_morning", "n_evening"]]),
        "Thresholds do not share the same export cohort.")
    airline_names = airline_labels.set_index("Airline Code")["Airline Name"].to_dict()
    cities = destination_lookup.set_index("Destination Airport ID")["Destination City"].to_dict()
    records = []
    for index, row in base.iterrows():
        hi = higher.iloc[index]
        for order, window in enumerate(["morning", "evening"], start=1):
            n = int(row["n_" + window])
            pooled = int(row["PooledFlights"])
            factor = pooled / n
            record = {
                "Month": f"2025-{int(row['Month']):02d}-01",
                "Airline DOT ID": int(row["DOT_ID_Reporting_Airline"]),
                "Airline Code": row["Reporting_Airline"], "Airline Name": airline_names[row["Reporting_Airline"]],
                "Destination Airport ID": int(row["DestAirportID"]), "Destination Code": row["Dest"],
                "Destination City": cities[int(row["DestAirportID"])],
                "Departure Window": window.title(), "Window Order": order,
                "Scheduled Flights": n, "Cancelled Flights": int(row["cancelled_" + window]),
                "Diverted Flights": int(row["diverted_" + window]),
                "Disruptions 15+": int(row["disrupted_" + window]),
                "Disruptions 60+": int(hi["disrupted_" + window]),
                "Late Arrivals 15+": int(row["late_completion_" + window]),
                "Late Arrivals 60+": int(hi["late_completion_" + window]),
                "Common Mix Denominator": pooled,
                "Weighted Disruptions 15+": float(row["disrupted_" + window] * factor),
                "Weighted Disruptions 60+": float(hi["disrupted_" + window] * factor),
                "Weighted Cancellations": float(row["cancelled_" + window] * factor),
                "Weighted Diversions": float(row["diverted_" + window] * factor),
            }
            records.append(record)
    return pd.DataFrame(records)


def summary_sources(audit, lookup):
    global_rows = []
    for threshold, result in sorted(audit["overall"].items(), key=lambda item: int(item[0])):
        point, interval = result["standardized"], result["interval"]
        row = {"Delay Threshold Minutes": int(threshold), "Morning Disruption Rate": point["morning_rate"],
               "Evening Disruption Rate": point["evening_rate"], "Gap pp": point["difference"] * 100,
               "Gap Interval Lower pp": interval["lower"] * 100, "Gap Interval Upper pp": interval["upper"] * 100,
               "Morning Flights": result["n_morning"], "Evening Flights": result["n_evening"],
               "Matched Groups": result["eligible_pairs"], "Window Coverage": audit["coverage"]["retained_fraction_of_window_flights"],
               "Week Clusters": interval["clusters"], "Comparison Period": "Calendar year 2025",
               "Interval Scope": "Approximate 95% pointwise, weekly clustered"}
        for component, label in [("cancelled", "Cancellation"), ("diverted", "Diversion"), ("late_completion", "Late Arrival")]:
            for window in ["morning", "evening"]:
                row[window.title() + " " + label + " Rate"] = result["components"][component][window + "_rate"]
        global_rows.append(row)
    route_rows = []
    for item in audit["destinations"]:
        supported = item["coverage_supported"]
        interval = item["pointwise_interval"]
        route_rows.append({
            "Destination Airport ID": item["destination_id"], "Destination Code": item["destination_code"],
            "Destination City": lookup.loc[item["destination_id"], "Destination City"],
            "Delay Threshold Minutes": item["threshold_minutes"], "Morning Disruption Rate": item["morning_rate"],
            "Evening Disruption Rate": item["evening_rate"], "Gap pp": item["difference"] * 100,
            "Gap Interval Lower pp": item["adjusted_lower"] * 100 if supported else None,
            "Gap Interval Upper pp": item["adjusted_upper"] * 100 if supported else None,
            "Pointwise Lower pp": interval["lower"] * 100 if supported else None,
            "Pointwise Upper pp": interval["upper"] * 100 if supported else None,
            "Morning Flights": item["morning_flights"], "Evening Flights": item["evening_flights"],
            "Matched Groups": item["matched_groups"], "Matched Months": item["matched_months"],
            "Week Clusters": item["week_clusters"], "Window Coverage": item["window_coverage"],
            "Coverage Supported": supported, "Direction Evidence": item["direction_label"],
            "Route Family Size": item["route_family_size"], "Comparison Period": "Calendar year 2025",
            "Interval Scope": "Approximate 95% family intervals, Bonferroni, weekly clustered",
        })
    routes = pd.DataFrame(route_rows).sort_values(["Destination Code", "Delay Threshold Minutes"]).reset_index(drop=True)
    return pd.DataFrame(global_rows), routes


def export_dictionary(tables):
    rows = []
    for source, frame in tables.items():
        pairs = source.startswith("comparison_pairs")
        for column in frame.columns:
            dtype = "Text / dimension"
            units = "Label"
            advice = "Use as a dimension or filter."
            meaning = column
            if column == "Month":
                dtype, units, advice = "Date", "First day of calendar month", "Whole-month filters preserve the matched groups."
            elif column == "Delay Threshold Minutes":
                dtype, units, advice = "Integer / dimension", "Minutes", "Select exactly one threshold before building summary marks."
            elif column.endswith("Rate") or column == "Window Coverage":
                dtype, units = "Decimal", "Fraction 0-1; display as Percentage"
                advice = "MIN at the documented summary row grain; never sum or average destinations to obtain an overall rate."
            elif "pp" in column:
                dtype, units = "Decimal", "Percentage points; display as Number"
                advice = "MIN at the documented summary row grain. Bounds apply to the gap, not either window's rate."
            elif column.startswith("Weighted ") or column == "Common Mix Denominator":
                dtype, units = "Decimal", "Standardization input, not an observed event count"
                advice = "SUM within each departure window; divide weighted event sums by common-mix denominator sums."
            elif column == "Coverage Supported":
                dtype, units, advice = "Boolean", "True / False", "Default destination direction views to supported rows; retain limited rows for coverage context."
            elif pd.api.types.is_numeric_dtype(frame[column]):
                dtype, units = "Integer", "Count or identifier"
                advice = "SUM counts only in the pair source; summary counts require one threshold and one scope."
                if column.endswith("ID") or column in ["Window Order", "Route Family Size"]:
                    advice = "Use as a dimension or sort field; do not total identifiers or family sizes."
            if pairs and column in ["Disruptions 15+", "Disruptions 60+", "Late Arrivals 15+", "Late Arrivals 60+", "Scheduled Flights", "Cancelled Flights", "Diverted Flights"]:
                meaning += " (observed count; use weighted inputs for common-mix rates)"
            if "pp" in column and ("Interval" in column or "Pointwise" in column):
                meaning += "; full-year model-based gap uncertainty; blank for limited destination coverage"
            rows.append({"Source File": source, "Field": column, "Data Type": dtype, "Units": units,
                         "Meaning": meaning, "Aggregation Guidance": advice})
    return pd.DataFrame(rows)


def validate_exports(overall, routes, pair_table, audit, root=ROOT):
    checks = []

    def check(name, condition):
        checks.append({"check": name, "passed": bool(condition)})

    check("Overall rows are unique by threshold", not overall["Delay Threshold Minutes"].duplicated().any() and len(overall) == 2)
    check("Destination rows are unique by destination and threshold", not routes.duplicated(["Destination Airport ID", "Delay Threshold Minutes"]).any())
    keys = ["Airline DOT ID", "Destination Airport ID", "Month", "Departure Window"]
    check("Pair rows have one unique group/window key", not pair_table.duplicated(keys).any())
    check("Pair counts do not duplicate thresholds", int(pair_table["Scheduled Flights"].sum()) == audit["coverage"]["retained_flights"])
    check("Display labels are complete", pair_table[["Airline Name", "Destination City", "Destination Code"]].notna().all().all())
    check("Higher-threshold event counts are nested", pair_table["Disruptions 60+"].le(pair_table["Disruptions 15+"]).all())
    check("Rate fields are fractions, not percentage-point values", all(
        table[column].between(0, 1).all() for table in [overall, routes]
        for column in table if column.endswith("Rate") or column == "Window Coverage"))
    check("Gap fields use percentage-point units", all(
        np.isclose(table["Gap pp"], 100 * (table["Evening Disruption Rate"] - table["Morning Disruption Rate"]),
                   atol=1e-12, rtol=0).all() for table in [overall, routes]))
    limited = routes.loc[~routes["Coverage Supported"]]
    check("Limited coverage retains points but suppresses intervals", limited["Gap pp"].notna().all()
          and limited[["Gap Interval Lower pp", "Gap Interval Upper pp", "Pointwise Lower pp", "Pointwise Upper pp"]].isna().all().all())
    for threshold in [15, 60]:
        for window in ["Morning", "Evening"]:
            selected = pair_table.loc[pair_table["Departure Window"].eq(window)]
            rate = selected[f"Weighted Disruptions {threshold}+"].sum() / selected["Common Mix Denominator"].sum()
            expected = overall.loc[overall["Delay Threshold Minutes"].eq(threshold), window + " Disruption Rate"].iloc[0]
            check(f"Tableau ratio-of-sums reproduces overall {window.lower()} at {threshold} minutes", np.isclose(rate, expected, atol=1e-12, rtol=0))
        for item in routes.loc[routes["Delay Threshold Minutes"].eq(threshold)].to_dict("records"):
            selected = pair_table.loc[pair_table["Destination Airport ID"].eq(item["Destination Airport ID"])]
            for window in ["Morning", "Evening"]:
                group = selected.loc[selected["Departure Window"].eq(window)]
                rate = group[f"Weighted Disruptions {threshold}+"].sum() / group["Common Mix Denominator"].sum()
                require(np.isclose(rate, item[window + " Disruption Rate"], atol=1e-12, rtol=0), "A filtered destination export does not reproduce its common-mix rate.")
        check(f"Every destination filter reproduces both {threshold}-minute rates", True)
    original_months = pd.read_csv(root / "data/summary/morning_evening_monthly.csv")
    for item in original_months.to_dict("records"):
        selected = pair_table.loc[pair_table["Month"].eq(item["month"] + "-01")]
        for window in ["Morning", "Evening"]:
            group = selected.loc[selected["Departure Window"].eq(window)]
            rate = group["Weighted Disruptions 15+"].sum() / group["Common Mix Denominator"].sum()
            require(np.isclose(rate, item[window.lower() + "_rate"], atol=1e-12, rtol=0), "A month filter does not reproduce the validated comparison.")
    check("Whole-month filters reproduce the original monthly comparisons", True)
    require(all(item["passed"] for item in checks), "Tableau export checks need review.")
    return checks


def write_sources(audit, pairs_by_threshold, frame, root=ROOT):
    labels = destination_labels(root)
    airlines = pd.read_csv(root / "data/reference/airline_labels_2025.csv")
    require(not airlines["Airline Code"].duplicated().any(), "Airline display codes must be unique.")
    parent = json.loads((root / "analysis/morning_evening_protocol.json").read_text())
    group_labels = frame.groupby(parent["strata"], as_index=False).agg(Reporting_Airline=("Reporting_Airline", "first"), Dest=("Dest", "first"))
    enriched = {threshold: pairs.merge(group_labels, on=parent["strata"], how="left", validate="one_to_one")
                for threshold, pairs in pairs_by_threshold.items()}
    pair_table = pair_source(enriched, airlines, labels)
    overall, routes = summary_sources(audit, labels.set_index("Destination Airport ID"))
    directory = root / "data/tableau"
    directory.mkdir(parents=True, exist_ok=True)
    tables = {"overall_comparison_2025.csv": overall, "destination_comparison_2025.csv": routes,
              "comparison_pairs_2025.csv": pair_table}
    dictionary = export_dictionary(tables)
    tables["data_dictionary.csv"] = dictionary
    for name, table in tables.items():
        table.to_csv(directory / name, index=False, lineterminator="\n")
    # Validate the actual text files, including parsed numbers and empty bounds.
    parsed = {name: pd.read_csv(directory / name) for name in tables}
    checks = validate_exports(parsed["overall_comparison_2025.csv"], parsed["destination_comparison_2025.csv"],
                              parsed["comparison_pairs_2025.csv"], audit, root)
    manifest = {"input_sha256": audit["input_sha256"], "followup_plan_commit": audit["plan_commit"],
                "visualization_platform": "Tableau", "files": [{"path": "data/tableau/" + name,
                "rows": len(table), "columns": len(table.columns), "sha256": sha256(directory / name)}
                for name, table in tables.items()], "validation": checks}
    (root / "data/manifests/tableau_sources_2025.json").write_text(json.dumps(manifest, indent=2) + "\n", newline="\n")
    return parsed, checks
