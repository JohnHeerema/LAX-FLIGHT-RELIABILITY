"""Exercise calendar boundaries, airport filtering, SQL, and reference safeguards."""

import calendar
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import pandas as pd

from scripts.build_year import archive_url, get_month_archive, reconcile_benchmarks, validate_combination
from scripts.inspect_pilot import COLUMNS, inspect, load_lax


ROOT = Path(__file__).resolve().parents[1]


def month_records(month):
    """One valid, on-time LAX flight per calendar day; fields are synthetic."""
    records = []
    for day in range(1, calendar.monthrange(2025, month)[1] + 1):
        date = pd.Timestamp(year=2025, month=month, day=day)
        row = {name: float("nan") for name in COLUMNS}
        row.update({
            "Year": 2025, "Month": month, "DayOfWeek": date.dayofweek + 1,
            "FlightDate": date.strftime("%Y-%m-%d"), "Reporting_Airline": "AS",
            "DOT_ID_Reporting_Airline": 19930, "Flight_Number_Reporting_Airline": "0001",
            "Origin": "LAX", "OriginAirportID": 12892, "Dest": "SFO", "DestAirportID": 14771,
            "CRSDepTime": "0005", "DepTimeBlk": "0001-0559", "DepTime": "0005",
            "DepDelay": 0.0, "DepDel15": 0.0, "ArrDelay": -5.0, "ArrDelayMinutes": 0.0,
            "ArrDel15": 0.0, "Cancelled": 0.0, "CancellationCode": None,
            "Diverted": 0.0, "Flights": 1.0, "Distance": 337.0,
        })
        records.append(row)
    return pd.DataFrame(records, columns=COLUMNS)


class CalendarAndSourceTests(unittest.TestCase):
    def test_february_uses_28_days_instead_of_januarys_calendar(self):
        profile = inspect(month_records(2), year=2025, month=2)
        self.assertEqual(profile["period"], "2025-02")
        self.assertEqual(profile["counts"]["scheduled_flights"], 28)

    def test_missing_day_stops_validation(self):
        with self.assertRaisesRegex(ValueError, "All 28 February dates"):
            inspect(month_records(2).iloc[:-1], year=2025, month=2)

    def test_duplicate_key_is_flagged_instead_of_silently_dropped(self):
        frame = month_records(2)
        frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "No duplicate proposed flight keys"):
            inspect(frame, year=2025, month=2)
        self.assertEqual(len(frame), 29)

    def test_invalid_status_flag_stops_validation(self):
        frame = month_records(2)
        frame.loc[0, "Cancelled"] = 2
        with self.assertRaisesRegex(ValueError, "flags are complete and binary"):
            inspect(frame, year=2025, month=2)

    def test_midnight_code_stays_text(self):
        frame = month_records(2)
        frame.loc[0, "CRSDepTime"] = "2400"
        inspect(frame, year=2025, month=2)
        self.assertEqual(frame.loc[0, "CRSDepTime"], "2400")

    def test_invalid_local_time_stops_validation(self):
        frame = month_records(2)
        frame.loc[0, "CRSDepTime"] = "2461"
        with self.assertRaisesRegex(ValueError, "valid local HHMM"):
            inspect(frame, year=2025, month=2)

    def test_source_month_is_checked_before_filtering_airports(self):
        frame = month_records(1).iloc[[0]]
        frame.loc[:, "Origin"] = "JFK"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrong_month.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("flights.csv", frame.to_csv(index=False))
            with self.assertRaisesRegex(ValueError, "different year or month"):
                load_lax(path, year=2025, month=2)

    def test_only_origin_lax_is_retained_and_leading_zeros_survive(self):
        frame = month_records(2).iloc[:4].copy()
        frame.loc[1, ["Origin", "OriginAirportID", "Dest", "DestAirportID"]] = ["JFK", 12478, "LAX", 12892]
        frame.loc[2, ["Cancelled", "ArrDelay", "ArrDelayMinutes", "ArrDel15"]] = [1, None, None, None]
        frame.loc[3, ["ArrDelay", "ArrDelayMinutes", "ArrDel15"]] = [15, 15, 1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "flights.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("flights.csv", frame.to_csv(index=False))
            selected, info = load_lax(path, year=2025, month=2, include_national=True)
        self.assertEqual(info["source_rows"], 4)
        self.assertEqual(len(selected), 3)
        self.assertEqual(selected.loc[0, "CRSDepTime"], "0005")
        self.assertEqual(selected.loc[0, "Flight_Number_Reporting_Airline"], "0001")
        self.assertEqual(info["national_counts"], {
            "scheduled_flights": 4, "cancelled_flights": 1,
            "diverted_flights": 0, "on_time_arrivals": 2,
        })

    def test_offline_mode_does_not_fetch_missing_month(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Missing cached archive"):
                get_month_archive(Path(directory), 2, offline=True)

    def test_cached_month_checksum_mismatch_stops_before_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data/raw").mkdir(parents=True)
            (root / "data/manifests").mkdir(parents=True)
            name = archive_url(2).rsplit("/", 1)[-1]
            (root / "data/raw" / name).write_bytes(b"changed archive")
            manifest = {"year": 2025, "sources": [{
                "month": 2, "source_url": archive_url(2), "archive_name": name,
                "archive_bytes": 15, "archive_sha256": hashlib.sha256(b"original archive").hexdigest(),
            }]}
            (root / "data/manifests/year_2025.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "Cached source checksum changed"):
                get_month_archive(root, 2, offline=True)


class CombinationAndReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames = {month: month_records(month) for month in range(1, 13)}
        cls.monthly = {month: inspect(frame, month=month) for month, frame in cls.frames.items()}
        cls.combined = pd.concat(cls.frames.values(), ignore_index=True)
        cls.annual = inspect(cls.combined, month=None)
        cls.sources = [{"archive_name": f"month_{month}.zip", "source_rows": len(frame),
                        "national_counts": {"scheduled_flights": len(frame)}}
                       for month, frame in cls.frames.items()]

    def test_combined_calendar_and_sql_reconcile(self):
        self.assertEqual(self.annual["counts"]["scheduled_flights"], 365)
        checks = validate_combination(self.combined, self.monthly, self.annual, self.sources)
        self.assertTrue(all(check["passed"] for check in checks))

    def test_missing_month_cannot_pass_combination(self):
        months = {month: profile for month, profile in self.monthly.items() if month != 12}
        with self.assertRaisesRegex(ValueError, "every month"):
            validate_combination(self.combined, months, self.annual, self.sources)

    def test_changed_monthly_total_is_caught(self):
        months = json.loads(json.dumps(self.monthly))
        months = {int(month): profile for month, profile in months.items()}
        months[2]["counts"]["scheduled_flights"] += 1
        with self.assertRaisesRegex(ValueError, "Monthly counts reconcile"):
            validate_combination(self.combined, months, self.annual, self.sources)

    def test_published_count_mismatch_stops_build(self):
        reference = json.loads((ROOT / "data/reference/dot_2025_benchmarks.json").read_text())
        monthly = {12: {"counts": {"scheduled_flights": 16050}}}
        national = {"scheduled_flights": 7001619, "cancelled_flights": 102875, "on_time_arrivals": 5344846}
        with self.assertRaisesRegex(ValueError, "national_cancelled_flights"):
            reconcile_benchmarks(national, monthly, reference)

    def test_published_percent_matches_only_at_documented_precision(self):
        reference = json.loads((ROOT / "data/reference/dot_2025_benchmarks.json").read_text())
        monthly = {12: {"counts": {"scheduled_flights": 16050}}}
        national = {"scheduled_flights": 7001619, "cancelled_flights": 102876, "on_time_arrivals": 5344846}
        results = reconcile_benchmarks(national, monthly, reference)
        self.assertEqual(results[2]["observed"], 76.34)
        self.assertTrue(all(item["passed"] for item in results))

    def test_empty_benchmark_list_is_not_treated_as_success(self):
        monthly = {12: {"counts": {"scheduled_flights": 1}}}
        national = {"scheduled_flights": 1, "cancelled_flights": 0, "on_time_arrivals": 1}
        with self.assertRaisesRegex(ValueError, "four documented DOT"):
            reconcile_benchmarks(national, monthly, {"benchmarks": []})


if __name__ == "__main__":
    unittest.main()
