"""Download and inspect January 2025 BTS data without dropping LAX flights.

Run from the repository root: python scripts/inspect_pilot.py
Use --offline to reuse the source archive without a network request.
"""

import argparse
import calendar
import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import urllib.request
import zipfile

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PERIOD = "2025_01"
SOURCE_URL = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2025_1.zip"
)
COLUMNS = [
    "Year", "Month", "DayOfWeek", "FlightDate", "Reporting_Airline",
    "DOT_ID_Reporting_Airline", "Flight_Number_Reporting_Airline",
    "Origin", "OriginAirportID", "Dest", "DestAirportID", "CRSDepTime",
    "DepTimeBlk", "DepTime", "DepDelay", "DepDel15", "ArrDelay",
    "ArrDelayMinutes", "ArrDel15", "Cancelled", "CancellationCode",
    "Diverted", "Flights", "Distance", "CarrierDelay", "WeatherDelay",
    "NASDelay", "SecurityDelay", "LateAircraftDelay",
]
TEXT_COLUMNS = [
    "FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline",
    "Origin", "Dest", "CRSDepTime", "DepTimeBlk", "DepTime", "CancellationCode",
]
FLIGHT_KEY = [
    "FlightDate", "DOT_ID_Reporting_Airline", "Flight_Number_Reporting_Airline",
    "OriginAirportID", "DestAirportID", "CRSDepTime",
]


def require(condition, message):
    """Stop with a useful error if an assumption about the data is violated."""
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_archive(root, offline=False):
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    path = raw / SOURCE_URL.rsplit("/", 1)[-1]
    receipt_path = raw / "download_receipt.json"
    manifest_path = root / "data" / "manifests" / f"pilot_{PERIOD}.json"
    baseline = json.loads(manifest_path.read_text()) if manifest_path.exists() else None

    if not path.exists():
        require(not offline, "No cached archive. Run once without --offline to download it.")
        request = urllib.request.Request(
            SOURCE_URL, headers={"User-Agent": "LAX-Flight-Reliability/0.1 (public-data research)"}
        )
        partial = path.with_suffix(".zip.part")
        with urllib.request.urlopen(request, timeout=45) as response, partial.open("wb") as output:
            headers = dict(response.headers)
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                output.write(chunk)
        with zipfile.ZipFile(partial) as archive:
            require(archive.testzip() is None, "Downloaded archive failed its ZIP integrity check.")
        partial.replace(path)
        receipt = {
            "source_url": SOURCE_URL,
            "downloaded_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "archive_name": path.name,
            "archive_bytes": path.stat().st_size,
            "archive_sha256": sha256(path),
            "http_last_modified": headers.get("Last-Modified"),
            "http_etag": headers.get("ETag"),
        }
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    actual_hash = sha256(path)
    if baseline:
        require(actual_hash == baseline["archive_sha256"],
                "Source checksum differs from our recorded snapshot. Review the change before proceeding.")
        return path, baseline

    require(receipt_path.exists(), "The source download receipt is missing.")
    receipt = json.loads(receipt_path.read_text())
    require(actual_hash == receipt["archive_sha256"], "Cached archive differs from its download receipt.")
    require(receipt["source_url"] == SOURCE_URL, "Download receipt names a different source.")
    return path, receipt


def load_lax(archive_path, year=2025, month=1, include_national=False):
    """Read the national CSV in chunks and retain only flights originating at LAX."""
    parts = []
    source_rows = 0
    national = {"scheduled_flights": 0, "cancelled_flights": 0, "diverted_flights": 0, "on_time_arrivals": 0}
    national_airlines = set()
    with zipfile.ZipFile(archive_path) as archive:
        require(archive.testzip() is None, "Source archive failed its ZIP integrity check.")
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        require(len(names) == 1, "Expected exactly one CSV in the archive.")
        member = names[0]
        with archive.open(member) as stream:
            header = next(csv.reader(io.TextIOWrapper(stream, encoding="utf-8-sig")))
        require(set(COLUMNS).issubset(header), "Source CSV is missing a required column.")
        with archive.open(member) as stream:
            reader = pd.read_csv(
                stream, usecols=COLUMNS, dtype={name: "string" for name in TEXT_COLUMNS},
                chunksize=100_000,
            )
            for chunk in reader:
                require(((chunk["Year"] == year) & (chunk["Month"] == month)).all(),
                        "Source CSV includes a different year or month.")
                dates = pd.to_datetime(chunk["FlightDate"], format="%Y-%m-%d", errors="raise")
                require((dates.notna() & dates.dt.year.eq(year) & dates.dt.month.eq(month)).all(),
                        f"Source flight dates do not match {year}-{month:02d}.")
                source_rows += len(chunk)
                if include_national:
                    national["scheduled_flights"] += len(chunk)
                    national["cancelled_flights"] += int(chunk["Cancelled"].eq(1).sum())
                    national["diverted_flights"] += int(chunk["Diverted"].eq(1).sum())
                    national["on_time_arrivals"] += int((
                        chunk["Cancelled"].eq(0) & chunk["Diverted"].eq(0)
                        & chunk["ArrDelay"].lt(15)
                    ).sum())
                    national_airlines.update(chunk["Reporting_Airline"].dropna().tolist())
                parts.append(chunk.loc[chunk["Origin"].eq("LAX"), COLUMNS].copy())
    require(bool(parts), "Source CSV contains no records.")
    frame = pd.concat(parts, ignore_index=True)
    require(not frame.empty, "No LAX flights found in the source CSV.")
    info = {
        "csv_member": member,
        "csv_uncompressed_bytes": archive.getinfo(member).file_size,
        "source_rows": source_rows,
        "source_named_columns": sum(bool(name) for name in header),
        "source_blank_header_columns": sum(not name for name in header),
        "selected_columns": COLUMNS,
    }
    if include_national:
        info["national_counts"] = national
        info["national_reporting_airlines"] = sorted(national_airlines)
    return frame, info


def summarize(frame):
    """Use explicit denominators; a blank arrival delay is never filled with zero."""
    completed = frame["Cancelled"].eq(0) & frame["Diverted"].eq(0)
    eligible = completed & frame["ArrDelay"].notna()
    total = len(frame)
    n_eligible = int(eligible.sum())
    delayed = int(frame.loc[eligible, "ArrDelay"].ge(15).sum())
    counts = {
        "scheduled_flights": total,
        "cancelled_flights": int(frame["Cancelled"].eq(1).sum()),
        "diverted_flights": int(frame["Diverted"].eq(1).sum()),
        "completed_nondiverted_flights": int(completed.sum()),
        "arrival_delay_eligible_flights": n_eligible,
        "arrivals_delayed_15_plus": delayed,
        "missing_arrival_delay": int(frame["ArrDelay"].isna().sum()),
        "missing_arrival_delay_among_completed": int((completed & frame["ArrDelay"].isna()).sum()),
        "cancelled_with_recorded_departure_time": int(
            (frame["Cancelled"].eq(1) & frame["DepTime"].notna()).sum()
        ),
    }
    metrics = {
        "cancellation_rate": counts["cancelled_flights"] / total if total else None,
        "diversion_rate": counts["diverted_flights"] / total if total else None,
        "arrival_delay_rate": delayed / n_eligible if n_eligible else None,
        "p90_arrival_delay_minutes": (
            float(frame.loc[eligible, "ArrDelayMinutes"].quantile(0.9, interpolation="linear"))
            if n_eligible else None
        ),
    }
    return counts, metrics


def inspect(frame, year=2025, month=1):
    checks = []

    def check(name, condition):
        checks.append({"check": name, "passed": bool(condition)})

    completed = frame["Cancelled"].eq(0) & frame["Diverted"].eq(0)
    eligible = completed & frame["ArrDelay"].notna()
    counts, metrics = summarize(frame)
    check("Only LAX origins", frame["Origin"].eq("LAX").all())
    if month is None:
        expected_dates = set(pd.date_range(f"{year}-01-01", f"{year}-12-31").strftime("%Y-%m-%d"))
        date_label = f"All {len(expected_dates)} calendar dates are represented"
        period = str(year)
    else:
        days = calendar.monthrange(year, month)[1]
        expected_dates = {f"{year}-{month:02d}-{day:02d}" for day in range(1, days + 1)}
        date_label = f"All {days} {calendar.month_name[month]} dates are represented"
        period = f"{year}-{month:02d}"
    check(date_label, set(frame["FlightDate"]) == expected_dates)
    check("Flight identifiers are present", frame[FLIGHT_KEY].notna().all().all())
    check("No duplicate proposed flight keys", not frame.duplicated(FLIGHT_KEY).any())
    check("Each record represents one flight", frame["Flights"].eq(1).all())
    check("Cancellation and diversion flags are complete and binary",
          frame[["Cancelled", "Diverted"]].isin([0, 1]).all().all())
    check("Cancellation and diversion flags do not overlap",
          not (frame["Cancelled"].eq(1) & frame["Diverted"].eq(1)).any())
    valid_time = frame["CRSDepTime"].str.fullmatch(r"(?:[01][0-9]|2[0-3])[0-5][0-9]|2400")
    check("Scheduled departure times are valid local HHMM codes", valid_time.fillna(False).all())
    check("Completed flights have arrival-delay values", frame.loc[completed, "ArrDelay"].notna().all())
    check("Canceled and diverted records have no ordinary arrival delay",
          frame.loc[~completed, "ArrDelay"].isna().all())
    check("Eligible arrival-delay fields are finite",
          np.isfinite(frame.loc[eligible, ["ArrDelay", "ArrDelayMinutes", "ArrDel15"]]).all().all())
    check("15-minute delay flags agree with delay minutes",
          frame.loc[eligible, "ArrDel15"].eq(frame.loc[eligible, "ArrDelay"].ge(15).astype(int)).all())
    check("Early arrivals become zero only in the minutes-late field",
          frame.loc[eligible, "ArrDelayMinutes"].eq(frame.loc[eligible, "ArrDelay"].clip(lower=0)).all())
    check("Cancellation codes agree with cancellation flags",
          frame.loc[frame["Cancelled"].eq(1), "CancellationCode"].isin(list("ABCD")).all()
          and frame.loc[frame["Cancelled"].eq(0), "CancellationCode"].isna().all())
    causes = ["CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay"]
    check("Cause fields are populated for qualifying delayed arrivals",
          frame[causes].notna().eq(eligible & frame["ArrDelay"].ge(15), axis=0).all().all())
    check("Outcome counts reconcile to all scheduled flights",
          counts["cancelled_flights"] + counts["diverted_flights"]
          + counts["completed_nondiverted_flights"] == len(frame))

    # SQL counts the same raw records with a separate implementation of the rules.
    with sqlite3.connect(":memory:") as connection:
        frame.to_sql("flights", connection, index=False)
        sql_counts = connection.execute("""
            SELECT COUNT(*),
                   SUM(CASE WHEN Cancelled = 1 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN Diverted = 1 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN Cancelled = 0 AND Diverted = 0
                                 AND ArrDelay IS NOT NULL THEN 1 ELSE 0 END),
                   SUM(CASE WHEN Cancelled = 0 AND Diverted = 0
                                 AND ArrDelay >= 15 THEN 1 ELSE 0 END)
            FROM flights
        """).fetchone()
    expected = tuple(counts[key] for key in [
        "scheduled_flights", "cancelled_flights", "diverted_flights",
        "arrival_delay_eligible_flights", "arrivals_delayed_15_plus",
    ])
    check("Python counts match a separate SQL calculation", sql_counts == expected)
    values = frame.loc[eligible, "ArrDelay"].clip(lower=0).tolist()
    check("P90 matches Python statistics with inclusive interpolation",
          len(values) >= 2 and np.isclose(
              statistics.quantiles(values, n=10, method="inclusive")[8],
              metrics["p90_arrival_delay_minutes"],
          ))
    failures = [item["check"] for item in checks if not item["passed"]]
    require(not failures, "Flight-data checks need review: " + "; ".join(failures))
    return {
        "period": period, "origin": "LAX", "counts": counts, "metrics": metrics,
        "date_min": frame["FlightDate"].min(), "date_max": frame["FlightDate"].max(),
        "reporting_airlines": sorted(frame["Reporting_Airline"].unique().tolist()),
        "destination_airports": int(frame["Dest"].nunique()),
        "missing_values": {name: int(value) for name, value in frame.isna().sum().items()},
        "checks": checks,
        "environment": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__},
    }


def sample_records(frame):
    """Choose examples of each outcome for learning, not for estimating rates."""
    complete = frame["Cancelled"].eq(0) & frame["Diverted"].eq(0)
    groups = [
        ("on_time", complete & frame["ArrDelay"].lt(15)),
        ("delayed_15_plus", complete & frame["ArrDelay"].ge(15)),
        ("cancelled", frame["Cancelled"].eq(1)),
        ("diverted", frame["Diverted"].eq(1)),
    ]
    selected = [
        frame.loc[mask].sort_values(FLIGHT_KEY).head(3).assign(example_outcome=label)
        for label, mask in groups
    ]
    columns = [
        "example_outcome", "FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline",
        "Origin", "Dest", "CRSDepTime", "ArrDelay", "ArrDel15", "Cancelled", "Diverted", "CancellationCode",
    ]
    return pd.concat(selected, ignore_index=True)[columns]


def write_report(root, profile, manifest):
    counts, metrics = profile["counts"], profile["metrics"]
    checks = "\n".join(f"| {item['check']} | PASS |" for item in profile["checks"])
    missing = "\n".join(f"| {name} | {value:,} |" for name, value in profile["missing_values"].items())
    n = counts["scheduled_flights"]
    eligible = counts["arrival_delay_eligible_flights"]
    content = f"""# January 2025 pilot: inspecting the evidence

**Checkpoint:** {len(profile['checks'])} LAX data and calculation checks passed. This is a one-month inspection, not a full-year reliability assessment.

## What we downloaded

The official [BTS monthly archive]({SOURCE_URL}) contains **{manifest['source_rows']:,} reported U.S. flight records**. Filtering on `Origin == 'LAX'` retains **{n:,} scheduled flights** across all 31 days of January, **{len(profile['reporting_airlines'])} reporting airlines**, and **{profile['destination_airports']} destination airports**.

A **row** represents one reported scheduled flight occurrence. A **column** describes one property, such as the flight date, destination, or cancellation flag. Flights arriving at LAX from somewhere else are outside this project's scope.

The CSV has {manifest['source_named_columns']} named columns and {manifest['source_blank_header_columns']} empty trailing header field. The script reads {len(COLUMNS)} explicitly named columns in chunks. It preserves local HHMM times and flight numbers as text, so leading zeros remain intact. The empty trailing field is not a flight attribute and is not selected.

## The flight records reconcile

| Outcome | Reported flights |
| --- | ---: |
| Completed without diversion | {counts['completed_nondiverted_flights']:,} |
| Canceled | {counts['cancelled_flights']:,} |
| Diverted | {counts['diverted_flights']:,} |
| **All scheduled flights** | **{n:,}** |

The three outcome groups do not overlap, and their counts sum to all scheduled flights. No LAX records were dropped or deduplicated.

## What missing values mean here

There are **{counts['missing_arrival_delay']} missing ordinary arrival-delay values**. All belong to canceled or diverted flights; **{counts['missing_arrival_delay_among_completed']} completed, nondiverted flights** are missing that value.

These are meaningful missing values. We preserve them and use explicit outcome flags rather than replacing them with zero or dropping the whole record. BTS has separate fields for diverted-flight arrivals; ordinary `ArrDelay` does not describe those outcomes.

Another useful detail: **{counts['cancelled_with_recorded_departure_time']} canceled records still have a departure time**. A populated departure field does not establish successful completion. We use the `Cancelled` and `Diverted` flags to classify outcomes.

`CancellationCode` is populated for canceled records. The cause-of-delay fields are populated for qualifying delayed arrivals; blanks outside that group are not automatically evidence of a broken dataset. These patterns will be checked again during full-year validation.

## Metric definitions tested on this month

| Measure | Calculation | Pilot value |
| --- | --- | ---: |
| Cancellation rate | {counts['cancelled_flights']:,} / {n:,} scheduled flights | {metrics['cancellation_rate']:.2%} |
| Diversion rate | {counts['diverted_flights']:,} / {n:,} scheduled flights | {metrics['diversion_rate']:.2%} |
| Arrival delay rate | {counts['arrivals_delayed_15_plus']:,} arrivals at least 15 minutes late / {eligible:,} eligible arrivals | {metrics['arrival_delay_rate']:.2%} |
| 90th percentile of minutes late | {eligible:,} eligible arrivals; early arrivals count as zero | {metrics['p90_arrival_delay_minutes']:g} minutes |

The arrival-delay denominator contains completed, nondiverted flights with a recorded arrival delay. The 90th percentile uses linear interpolation. These describe different parts of reliability and should be read together.

## Validation results

The source CSV also passed archive-integrity, required-column, and January year/month/date checks before the LAX inspection. The file checksum matches the recorded source snapshot.

| LAX check | Result |
| --- | --- |
{checks}

Python and SQL operate on the same source records. Their agreement checks calculation logic; it is not independent confirmation that BTS captured every relevant flight. Reconciliation to published BTS summaries with matching coverage remains a later checkpoint.

## Learn from individual records

Open the [12 example records](../data/samples/lax_2025_01_examples.csv). Three examples were selected from each outcome group to make the fields easier to understand. This is an illustrative sample, not a representative estimate of outcome frequencies. Empty CSV cells remain empty.

| Field | Meaning |
| --- | --- |
| `FlightDate` | Scheduled flight date |
| `Reporting_Airline` | Reporting operating-carrier code, not necessarily the brand on a ticket |
| `CRSDepTime` | Scheduled departure in local HHMM format |
| `ArrDelay` | Minutes relative to scheduled arrival; negative values mean early arrival |
| `ArrDel15` | 1 for arrival at least 15 minutes late; 0 otherwise, where recorded |
| `Cancelled` / `Diverted` | Explicit outcome flags: 1 means yes |
| `CancellationCode` | Reported cancellation reason, when applicable |

Field meanings follow the [BTS data dictionary](https://www.transtats.bts.gov/Fields.asp?gnoyr_VQ=FGJ).

## Reproduce this checkpoint

Tested with Python {profile['environment']['python']}, pandas {profile['environment']['pandas']}, and NumPy {profile['environment']['numpy']}.

From the repository root, install `requirements.txt` and run `python scripts/inspect_pilot.py`. This downloads the original ZIP if it is missing, verifies its checksum, saves the LAX extract locally, and regenerates this report, its JSON profile, and the example records. Run `python scripts/inspect_pilot.py --offline` to use the cached archive.

The original ZIP and full LAX extract are excluded from Git. Their source, original download timestamp, checksum, and file dimensions are recorded in the [source manifest](../data/manifests/pilot_2025_01.json). If the remote archive changes, the script stops for review rather than silently substituting a new snapshot.

## Limits and next checkpoint

January was selected as the first calendar month before comparing outcomes. This month alone cannot establish seasonal patterns, rank airlines fairly, support causal claims, or predict future reliability. Reporting coverage is limited to the selected BTS table, and the proposed flight identifier has only been checked on this pilot.

**Next checkpoint:** review individual records and agree on the full-year data-handling rules before extending the pipeline.
"""
    (root / "reports" / f"pilot_{PERIOD}.md").write_text(content, encoding="utf-8")


def run(root=ROOT, offline=False):
    archive_path, provenance = get_archive(root, offline=offline)
    frame, source_info = load_lax(archive_path)
    profile = inspect(frame)
    manifest = {**provenance, **source_info}
    for directory in ["data/manifests", "data/interim", "data/samples", "reports"]:
        (root / directory).mkdir(parents=True, exist_ok=True)
    (root / "data/manifests" / f"pilot_{PERIOD}.json").write_text(json.dumps(manifest, indent=2) + "\n")
    frame.to_csv(root / "data/interim" / f"lax_{PERIOD}.csv", index=False, float_format="%g")
    (root / "reports" / f"pilot_{PERIOD}.json").write_text(json.dumps(profile, indent=2) + "\n")
    sample_records(frame).to_csv(root / "data/samples/lax_2025_01_examples.csv", index=False, float_format="%g")
    write_report(root, profile, manifest)
    print(json.dumps({"counts": profile["counts"], "metrics": profile["metrics"],
                      "checks_passed": len(profile["checks"]),
                      "report": f"reports/pilot_{PERIOD}.md"}, indent=2))
    return profile


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Use the cached source ZIP without a network request.")
    args = parser.parse_args()
    run(offline=args.offline)
