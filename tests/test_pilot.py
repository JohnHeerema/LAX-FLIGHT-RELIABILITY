"""Small, hand-calculated cases for denominator and source-integrity errors."""

import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from scripts.inspect_pilot import SOURCE_URL, get_archive, summarize


class PilotTests(unittest.TestCase):
    def setUp(self):
        # Four completed flights, one cancellation, and one diversion.
        self.frame = pd.DataFrame({
            "Cancelled": [0, 0, 0, 0, 1, 0],
            "Diverted": [0, 0, 0, 0, 0, 1],
            "ArrDelay": [-7, 14, 15, 60, None, None],
            "ArrDelayMinutes": [0, 14, 15, 60, None, None],
            "DepTime": ["0800", "0900", "1000", "1100", "1200", "1300"],
        })

    def test_rates_use_their_own_denominators_and_include_exactly_15_minutes(self):
        counts, metrics = summarize(self.frame)
        self.assertEqual(counts["scheduled_flights"], 6)
        self.assertEqual(counts["arrival_delay_eligible_flights"], 4)
        self.assertEqual(counts["arrivals_delayed_15_plus"], 2)
        self.assertEqual(metrics["cancellation_rate"], 1 / 6)
        self.assertEqual(metrics["diversion_rate"], 1 / 6)
        self.assertEqual(metrics["arrival_delay_rate"], 2 / 4)
        self.assertAlmostEqual(metrics["p90_arrival_delay_minutes"], 46.5)

    def test_cancellation_with_a_departure_time_is_still_a_cancellation(self):
        counts, _ = summarize(self.frame)
        self.assertEqual(counts["cancelled_with_recorded_departure_time"], 1)
        self.assertEqual(counts["completed_nondiverted_flights"], 4)

    def test_missing_completed_arrival_is_reported_and_excluded_from_delay_denominator(self):
        self.frame.loc[3, ["ArrDelay", "ArrDelayMinutes"]] = None
        counts, metrics = summarize(self.frame)
        self.assertEqual(counts["missing_arrival_delay_among_completed"], 1)
        self.assertEqual(counts["arrival_delay_eligible_flights"], 3)
        self.assertEqual(metrics["arrival_delay_rate"], 1 / 3)

    def test_all_cancelled_group_has_unknown_arrival_metrics_rather_than_zero(self):
        counts, metrics = summarize(self.frame.loc[[4]])
        self.assertEqual(counts["arrival_delay_eligible_flights"], 0)
        self.assertEqual(metrics["cancellation_rate"], 1)
        self.assertIsNone(metrics["arrival_delay_rate"])
        self.assertIsNone(metrics["p90_arrival_delay_minutes"])

    def test_summarizing_does_not_fill_or_change_source_values(self):
        original = self.frame.copy(deep=True)
        summarize(self.frame)
        pd.testing.assert_frame_equal(self.frame, original)

    def test_offline_mode_requires_a_cached_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "No cached archive"):
                get_archive(Path(directory), offline=True)

    def test_altered_source_snapshot_stops_before_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data/raw").mkdir(parents=True)
            (root / "data/manifests").mkdir(parents=True)
            (root / "data/raw" / SOURCE_URL.rsplit("/", 1)[-1]).write_bytes(b"altered snapshot")
            (root / "data/manifests/pilot_2025_01.json").write_text(
                json.dumps({"archive_sha256": "original recorded hash"})
            )
            with self.assertRaisesRegex(ValueError, "Source checksum differs"):
                get_archive(root, offline=True)


if __name__ == "__main__":
    unittest.main()
