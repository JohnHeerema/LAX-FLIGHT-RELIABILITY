"""Build and validate the 2025 LAX dataset: python -m scripts.build_year.

Original archives and the combined extract are cached locally outside Git.
Use --offline after downloading to rebuild from the pinned source snapshots.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import json
from pathlib import Path
import sqlite3
import urllib.request
import zipfile

import pandas as pd

from scripts.inspect_pilot import COLUMNS, FLIGHT_KEY, ROOT, inspect, load_lax, require, sha256


YEAR = 2025
MONTHS = tuple(range(1, 13))
MANIFEST_NAME = "year_2025.json"


def archive_url(month):
    require(month in MONTHS, "Month must be an integer from 1 to 12.")
    return (
        "https://transtats.bts.gov/PREZIP/"
        f"On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{YEAR}_{month}.zip"
    )


def pinned_source(root, month):
    manifest = root / "data/manifests" / MANIFEST_NAME
    if manifest.exists():
        data = json.loads(manifest.read_text())
        require(data["year"] == YEAR, "Source manifest belongs to a different year.")
        matches = [source for source in data["sources"] if source["month"] == month]
        require(len(matches) == 1, f"Expected one pinned source for month {month}.")
        return matches[0]
    if month == 1:
        pilot = root / "data/manifests/pilot_2025_01.json"
        if pilot.exists():
            return json.loads(pilot.read_text())
    return None


def get_month_archive(root, month, offline=False):
    """Keep each source snapshot intact; stop if a recorded checksum changes."""
    url = archive_url(month)
    raw = root / "data/raw"
    raw.mkdir(parents=True, exist_ok=True)
    path = raw / url.rsplit("/", 1)[-1]
    receipt_path = raw / (path.name + ".receipt.json")
    pinned = pinned_source(root, month)
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    expected = pinned or receipt
    if expected:
        require(expected["source_url"] == url, f"Source URL mismatch for month {month}.")
        require(expected["archive_name"] == path.name, f"Archive name mismatch for month {month}.")

    if not path.exists():
        require(not offline, f"Missing cached archive for {YEAR}-{month:02d}; run without --offline.")
        request = urllib.request.Request(
            url, headers={"User-Agent": "LAX-Flight-Reliability/0.2 (public-data research)"}
        )
        partial = path.with_suffix(".zip.part")
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as output:
            last_modified = response.headers.get("Last-Modified")
            etag = response.headers.get("ETag")
            content_length = response.headers.get("Content-Length")
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                output.write(chunk)
        if content_length is not None:
            require(partial.stat().st_size == int(content_length), f"Incomplete download for month {month}.")
        with zipfile.ZipFile(partial) as archive:
            require(archive.testzip() is None, f"ZIP integrity failed for month {month}.")
        actual_hash = sha256(partial)
        if expected:
            require(actual_hash == expected["archive_sha256"],
                    f"Source checksum changed for {YEAR}-{month:02d}; review before processing.")
        partial.replace(path)
        receipt = {
            "source_url": url,
            "downloaded_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "archive_name": path.name,
            "archive_bytes": path.stat().st_size,
            "archive_sha256": actual_hash,
            "http_last_modified": last_modified,
            "http_etag": etag,
        }
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    expected = pinned or receipt
    require(expected is not None, f"Cached month {month} has no provenance; inspect it before use.")
    require(sha256(path) == expected["archive_sha256"],
            f"Cached source checksum changed for {YEAR}-{month:02d}; review before processing.")
    require(path.stat().st_size == expected["archive_bytes"], f"Cached byte count changed for month {month}.")
    return path, expected


def download_months(root=ROOT, offline=False):
    results = {}
    # Three independent downloads keep the work bounded and avoid excessive requests.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(get_month_archive, root, month, offline): month for month in MONTHS}
        for future in as_completed(futures):
            month = futures[future]
            results[month] = future.result()
            print(f"{YEAR}-{month:02d}: archive ready ({results[month][0].stat().st_size:,} bytes)", flush=True)
    return {month: results[month] for month in MONTHS}


def reconcile_benchmarks(national, monthly, reference):
    """Compare calculated values with separately published, explicitly scoped totals."""
    values = {
        "national_scheduled_flights": national["scheduled_flights"],
        "national_cancelled_flights": national["cancelled_flights"],
        "national_on_time_arrival_percent": 100 * national["on_time_arrivals"] / national["scheduled_flights"],
        "lax_december_scheduled_departures": monthly[12]["counts"]["scheduled_flights"],
    }
    identifiers = [item["id"] for item in reference["benchmarks"]]
    require(len(identifiers) == len(values) and set(identifiers) == set(values),
            "Expected exactly the four documented DOT benchmark comparisons.")
    results = []
    for item in reference["benchmarks"]:
        actual = values[item["id"]]
        if "round_decimals" in item:
            actual = round(actual, item["round_decimals"])
        results.append({**item, "observed": actual, "passed": actual == item["expected"]})
    require(all(item["passed"] for item in results),
            "Published DOT totals need review: " + ", ".join(item["id"] for item in results if not item["passed"]))
    return results


def validate_combination(frame, monthly, annual, sources, root=ROOT):
    """Check month coverage, shared identifiers, totals, and a separate SQL aggregation."""
    require(set(monthly) == set(MONTHS), "Expected exactly one validated profile for every month.")
    checks = []

    def check(name, condition):
        checks.append({"check": name, "passed": bool(condition)})

    check("All 12 months appear in combined records", set(frame["Month"].astype(int)) == set(MONTHS))
    check("Year values are consistently 2025", frame["Year"].eq(YEAR).all())
    check("LAX airport identifiers agree with the LAX code", frame["OriginAirportID"].eq(12892).all())
    check("Monthly counts reconcile to annual counts", all(
        sum(monthly[month]["counts"][key] for month in MONTHS) == value
        for key, value in annual["counts"].items()
    ))
    check("Twelve distinct source archives were used", len({item["archive_name"] for item in sources}) == 12)
    check("National source row counts reconcile", sum(item["source_rows"] for item in sources)
          == sum(item["national_counts"]["scheduled_flights"] for item in sources))

    with sqlite3.connect(":memory:") as connection:
        frame.to_sql("flights", connection, index=False)
        sql = (root / "sql/monthly_validation.sql").read_text()
        rows = pd.read_sql_query(sql, connection)
    sql_matches = set(rows["month"]) == set(MONTHS) and all(
        int(record[key]) == monthly[int(record["month"])]["counts"][key]
        for record in rows.to_dict("records") for key in rows.columns if key != "month"
    )
    check("Monthly Python counts match the separate SQL query", sql_matches)
    failures = [item["check"] for item in checks if not item["passed"]]
    require(not failures, "Combined data need review: " + "; ".join(failures))
    return checks


def write_report(root, result, manifest):
    annual = result["annual"]
    counts, metrics = annual["counts"], annual["metrics"]
    monthly_rows = "\n".join(
        f"| {item['period']} | {item['counts']['scheduled_flights']:,} | "
        f"{item['counts']['cancelled_flights']:,} | {item['counts']['diverted_flights']:,} | "
        f"{item['counts']['missing_arrival_delay_among_completed']} | {item['checks_passed']} / {item['checks_run']} |"
        for item in result["monthly"]
    )
    external_rows = "\n".join(
        f"| {item['label']} | {item['expected']:,} | {item['observed']:,} | "
        f"Table {item['table']}, p. {item['printed_page']} | PASS |"
        for item in result["published_reconciliation"]
    )
    combined_checks = "\n".join(f"| {item['check']} | PASS |" for item in result["combination_checks"])
    missing_rows = "\n".join(f"| {key} | {value:,} |" for key, value in annual["missing_values"].items() if value)
    megabytes = sum(item["archive_bytes"] for item in manifest["sources"]) / 1_000_000
    text = f"""# Full-year dataset validation: LAX, 2025

**Checkpoint complete:** All 12 monthly files and the combined LAX data passed validation. Four calculations match separately published DOT figures. Airline comparisons, uncertainty estimates, and recommendations are the next stage.

## What is ready

The national source files contain **{result['national_counts']['scheduled_flights']:,} reported scheduled flights**. Our origin filter retains **{counts['scheduled_flights']:,} LAX departures**, covering **all 365 days**, **{len(annual['reporting_airlines'])} reporting airline codes**, and **{annual['destination_airports']} destination airports**.

Each source ZIP is preserved with its download timestamp and SHA-256 checksum. The {megabytes:.1f} MB of compressed sources are read in chunks; the full national CSVs do not need to be extracted to disk. No LAX flight records were dropped, deduplicated, imputed, or capped.

| LAX outcome | Flights |
| --- | ---: |
| Completed without diversion | {counts['completed_nondiverted_flights']:,} |
| Canceled | {counts['cancelled_flights']:,} |
| Diverted | {counts['diverted_flights']:,} |
| **All scheduled flights** | **{counts['scheduled_flights']:,}** |

## Monthly coverage and validation

The same 18 record and calculation checks are applied to each month and to the combined year. They cover identifiers, calendar coverage, status flags, meaningful missingness, delay-field consistency, Python/SQL agreement, and a separate percentile calculation. Every source file also passes archive, schema, period, and checksum checks.

| Month | Scheduled LAX flights | Canceled | Diverted | Completed flights missing arrival delay | Checks passed |
| --- | ---: | ---: | ---: | ---: | ---: |
{monthly_rows}

The combined year also passes all {len(annual['checks'])} shared checks, including the proposed flight identifier's uniqueness across the entire dataset. See the [JSON validation record](year_2025.json) and [monthly summary CSV](../data/summary/2025_monthly.csv).

## Combination checks

| Check | Result |
| --- | --- |
{combined_checks}

The [standalone SQL query](../sql/monthly_validation.sql) recalculates monthly counts from raw outcome flags and delay minutes. Monthly totals are added to obtain annual totals. Rates are recalculated from their numerators and denominators, rather than averaging monthly percentages. The annual percentile is computed from all eligible arrival records, rather than averaging monthly percentiles.

## Reconciliation to the published DOT report

Reference: [Air Travel Consumer Report, February 2026]({result['reference_document']['source_url']}). The [benchmark file](../data/reference/dot_2025_benchmarks.json) records the manually transcribed values, table/page locations, coverage, and PDF checksum.

| Matching-scope check | Published | Calculated | Location | Result |
| --- | ---: | ---: | --- | --- |
{external_rows}

The first three comparisons use the **national reporting operating-carrier** population. The last checks our **December LAX origin filter**, using the report's DEP count rather than its ARR count. They are not marketing-carrier network totals.

DOT's national on-time percentage uses all scheduled flights. Our project's arrival-delay rate uses eligible completed, nondiverted arrivals. Those different denominators mean one is not simply the complement of the other. Matching published aggregates strengthens the ingestion checks; it does not establish that every individual record is error-free.

## Missing values were retained and checked

All **{counts['missing_arrival_delay']:,}** missing ordinary arrival-delay values belong to canceled or diverted flights: **{counts['cancelled_flights']:,} + {counts['diverted_flights']:,}**. **{counts['missing_arrival_delay_among_completed']} completed, nondiverted flights** are missing ordinary arrival delay.

There are also **{counts['cancelled_with_recorded_departure_time']} canceled records with a departure time recorded**. The explicit outcome flags determine completion status. A timestamp alone is insufficient.

| Selected field with missing values | Records |
| --- | ---: |
{missing_rows}

The missing cancellation-code and delay-cause patterns agree with eligibility in every month. All remaining values are retained in the local extract. Handling follows the [documented rules](../docs/data_handling.md).

## Baseline measures, before comparisons

| Measure | Calculation or population | Full-year value |
| --- | --- | ---: |
| Cancellation rate | {counts['cancelled_flights']:,} / {counts['scheduled_flights']:,} scheduled flights | {metrics['cancellation_rate']:.2%} |
| Diversion rate | {counts['diverted_flights']:,} / {counts['scheduled_flights']:,} scheduled flights | {metrics['diversion_rate']:.2%} |
| Arrival delay rate | {counts['arrivals_delayed_15_plus']:,} / {counts['arrival_delay_eligible_flights']:,} eligible arrivals | {metrics['arrival_delay_rate']:.2%} |
| 90th percentile of minutes late | All {counts['arrival_delay_eligible_flights']:,} eligible arrivals, early arrivals set to zero | {metrics['p90_arrival_delay_minutes']:g} minutes |

These are descriptive dataset totals, not estimates of an airline's causal effect or recommendations about a future flight.

## Coverage matters before ranking airlines

The [carrier-by-month exposure table](../data/summary/2025_carrier_month_counts.csv) shows how many flights support each carrier's observations. Some reporting carriers have few LAX flights or months with none. We will compare destination, period, and scheduled-time mix and report uncertainty before interpreting carrier differences.

Carrier codes remain as reported in the source. The DOT reference also notes the Alaska/Hawaiian operating-certificate change in late 2025; interpretation of those labels requires care rather than automatic consolidation.

## Reproduce this checkpoint

With Python 3.12 and the pinned requirements installed, run from the repository root:

```bash
python -m scripts.build_year
```

This downloads missing monthly ZIPs, checks each file against its pinned snapshot, validates each month and the combined year, performs the published-total comparisons, and regenerates the report, JSON audit, source manifest, summary CSVs, and local full extract. Three concurrent downloads bound request volume. Once cached:

```bash
python -m scripts.build_year --offline
```

The combined extract is `data/interim/lax_2025.csv`, outside Git. Its SHA-256 checksum and column list are in the [year manifest](../data/manifests/year_2025.json). Published outputs are written after validation succeeds. Future source revisions require explicit review; a checksum mismatch stops the build.

The January-only command still reproduces its original pilot outputs. The original archives and the local full extract are preserved separately from the compact files published in this repository.

**Next checkpoint:** define the first fair comparison and examine the results with sample sizes and uncertainty.
"""
    (root / "reports/year_2025.md").write_text(text, encoding="utf-8", newline="\n")


def run(root=ROOT, offline=False):
    archives = download_months(root, offline=offline)
    frames, sources, monthly = [], [], {}
    national = {"scheduled_flights": 0, "cancelled_flights": 0, "diverted_flights": 0, "on_time_arrivals": 0}
    national_airlines = set()
    receipt_keys = [
        "source_url", "downloaded_at_utc", "archive_name", "archive_bytes", "archive_sha256",
        "http_last_modified", "http_etag",
    ]
    for month in MONTHS:
        path, receipt = archives[month]
        frame, info = load_lax(path, year=YEAR, month=month, include_national=True)
        profile = inspect(frame, year=YEAR, month=month)
        monthly[month] = profile
        frames.append(frame)
        source = {key: receipt.get(key) for key in receipt_keys}
        source.update({key: value for key, value in info.items() if key != "selected_columns"})
        sources.append({"month": month, "lax_rows": len(frame), **source})
        for key in national:
            national[key] += info["national_counts"][key]
        national_airlines.update(info["national_reporting_airlines"])
        print(f"{YEAR}-{month:02d}: {len(frame):,} LAX flights; {len(profile['checks'])} checks passed", flush=True)

    combined = pd.concat(frames, ignore_index=True)
    annual = inspect(combined, year=YEAR, month=None)
    checks = validate_combination(combined, monthly, annual, sources, root=root)
    reference = json.loads((root / "data/reference/dot_2025_benchmarks.json").read_text())
    reconciliation = reconcile_benchmarks(national, monthly, reference)
    month_records = [{
        "period": profile["period"], "counts": profile["counts"], "metrics": profile["metrics"],
        "reporting_airlines": profile["reporting_airlines"],
        "destination_airports": profile["destination_airports"],
        "checks_run": len(profile["checks"]),
        "checks_passed": sum(item["passed"] for item in profile["checks"]),
    } for profile in monthly.values()]
    result = {
        "year": YEAR, "annual": annual, "monthly": month_records,
        "national_counts": national, "national_reporting_airlines": sorted(national_airlines),
        "combination_checks": checks, "reference_document": reference["document"],
        "published_reconciliation": reconciliation,
    }

    # All validation gates above must pass before published outputs are replaced.
    for directory in ["data/interim", "data/manifests", "data/summary", "reports"]:
        (root / directory).mkdir(parents=True, exist_ok=True)
    extract = root / "data/interim/lax_2025.csv"
    combined.to_csv(extract, index=False, float_format="%g", lineterminator="\n")
    manifest = {
        "year": YEAR, "origin": "LAX", "selected_columns": COLUMNS,
        "proposed_flight_key": FLIGHT_KEY, "sources": sources,
        "derived_extract": {"path": "data/interim/lax_2025.csv", "rows": len(combined),
                            "bytes": extract.stat().st_size, "sha256": sha256(extract)},
    }
    monthly_table = pd.DataFrame([{
        "month": record["period"], **record["counts"], **record["metrics"],
        "checks_passed": record["checks_passed"],
    } for record in month_records])
    monthly_table.to_csv(root / "data/summary/2025_monthly.csv", index=False, lineterminator="\n")
    coverage = combined.groupby(["Month", "Reporting_Airline"]).size().unstack(fill_value=0)
    coverage.index = [f"{YEAR}-{month:02d}" for month in coverage.index]
    coverage.index.name = "month"
    coverage.to_csv(root / "data/summary/2025_carrier_month_counts.csv", lineterminator="\n")
    (root / "data/manifests" / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", newline="\n")
    (root / "reports/year_2025.json").write_text(json.dumps(result, indent=2) + "\n", newline="\n")
    write_report(root, result, manifest)
    print(json.dumps({"lax_counts": annual["counts"], "combination_checks": len(checks),
                      "published_checks_passed": len(reconciliation), "report": "reports/year_2025.md"}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Use cached ZIPs without network requests.")
    args = parser.parse_args()
    run(offline=args.offline)
