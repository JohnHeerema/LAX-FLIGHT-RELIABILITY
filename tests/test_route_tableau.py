"""Check severity boundaries, cautious labels, and Tableau aggregation semantics."""

import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from scripts.route_severity import adjusted_interval, coverage_supported, direction_label, outcome_at_threshold, sql_route_check
from scripts.tableau_exports import pair_source, summary_sources


ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "analysis/route_severity_plan.json").read_text())["route_support"]


def synthetic_pairs(threshold):
    morning = [2, 24] if threshold == 15 else [1, 12]
    evening = [9, 10] if threshold == 15 else [3, 4]
    frame = pd.DataFrame({
        "PairID": [0, 1], "DOT_ID_Reporting_Airline": [1, 2], "DestAirportID": [11, 22],
        "Month": [1, 2], "n_morning": [20, 60], "n_evening": [60, 20], "PooledFlights": [80, 80],
        "disrupted_morning": morning, "disrupted_evening": evening,
        "late_completion_morning": morning, "late_completion_evening": evening,
        "cancelled_morning": [0, 0], "cancelled_evening": [0, 0],
        "diverted_morning": [0, 0], "diverted_evening": [0, 0],
        "Reporting_Airline": ["AA", "UA"], "Dest": ["AAA", "BBB"],
    })
    return frame


def labels():
    airlines = pd.DataFrame({"Airline Code": ["AA", "UA"], "Airline Name": ["American Airlines", "United Airlines"]})
    cities = pd.DataFrame({"Destination Airport ID": [11, 22], "Destination Code": ["AAA", "BBB"],
                           "Destination City": ["Alpha, CA", "Beta, NY"]})
    return airlines, cities


class SeverityAndSupportTests(unittest.TestCase):
    def test_hour_boundary_and_nonarrival_events_are_retained(self):
        frame = pd.DataFrame({"Cancelled": [0, 0, 1, 0, 0], "Diverted": [0, 0, 0, 1, 0],
                              "ArrDelay": [59, 60, None, None, -10],
                              "EventCancelled": [0, 0, 1, 0, 0], "EventDiverted": [0, 0, 0, 1, 0],
                              "EventLate": [1, 1, 0, 0, 0], "Disrupted": [1, 1, 1, 1, 0]})
        original = frame.copy(deep=True)
        result = outcome_at_threshold(frame, 60)
        self.assertEqual(result["Disrupted"].tolist(), [0, 1, 1, 1, 0])
        self.assertTrue(result.loc[[2, 3], "ArrDelay"].isna().all())
        pd.testing.assert_frame_equal(frame, original)

    def test_support_boundaries_apply_to_counts_months_and_weeks(self):
        self.assertTrue(coverage_supported(100, 100, 6, 20, POLICY))
        self.assertFalse(coverage_supported(99, 100, 6, 20, POLICY))
        self.assertFalse(coverage_supported(100, 99, 6, 20, POLICY))
        self.assertFalse(coverage_supported(100, 100, 5, 20, POLICY))
        self.assertFalse(coverage_supported(100, 100, 6, 19, POLICY))

    def test_adjustment_widens_the_interval_as_the_family_grows(self):
        low, high = adjusted_interval(0.1, 0.02, 10, 1)
        self.assertAlmostEqual(low, 0.0554372229607, places=10)
        self.assertAlmostEqual(high, 0.1445627770393, places=10)
        wider_low, wider_high = adjusted_interval(0.1, 0.02, 10, 10)
        self.assertLess(wider_low, low)
        self.assertGreater(wider_high, high)

    def test_empty_interval_family_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "family must contain"):
            adjusted_interval(0.1, 0.02, 10, 0)

    def test_limited_coverage_never_acquires_a_direction_label(self):
        self.assertEqual(direction_label(False, None, None), "Limited coverage")
        self.assertEqual(direction_label(False, 0.1, 0.2), "Limited coverage")

    def test_intervals_crossing_or_touching_zero_are_uncertain(self):
        self.assertEqual(direction_label(True, -0.1, 0.2), "Uncertain direction")
        self.assertEqual(direction_label(True, 0, 0.2), "Uncertain direction")
        self.assertEqual(direction_label(True, -0.2, 0), "Uncertain direction")
        self.assertEqual(direction_label(True, 0.1, 0.2), "Higher evening rate")
        self.assertEqual(direction_label(True, -0.2, -0.1), "Higher morning rate")

    def test_sql_hour_threshold_is_inclusive_and_keeps_cancellations(self):
        frame = pd.DataFrame({
            "DOT_ID_Reporting_Airline": [1] * 6, "DestAirportID": [11, 11, 11, 11, 22, 22],
            "Month": [1] * 6, "CRSDepTime": ["0800", "0900", "1800", "1900", "0800", "1800"],
            "Cancelled": [0, 0, 0, 1, 0, 0], "Diverted": [0, 0, 0, 0, 1, 0],
            "ArrDelay": [59, 60, 0, None, None, 60], "Origin": ["LAX"] * 6, "Year": [2025] * 6,
        })
        expected = [
            {"destination_id": 11, "destination_code": "AAA", "matched_groups": 1,
             "morning_flights": 2, "evening_flights": 2, "morning_rate": .5, "evening_rate": .5},
            {"destination_id": 22, "destination_code": "BBB", "matched_groups": 1,
             "morning_flights": 1, "evening_flights": 1, "morning_rate": 1, "evening_rate": 1},
        ]
        self.assertEqual(sql_route_check(frame, {"minimum_flights_per_window_per_stratum": 1}, expected, 60), 2)


class TableauSourceTests(unittest.TestCase):
    def setUp(self):
        airlines, cities = labels()
        self.pairs = {15: synthetic_pairs(15), 60: synthetic_pairs(60)}
        self.table = pair_source(self.pairs, airlines, cities)

    def test_two_thresholds_do_not_duplicate_pair_rows_or_flight_counts(self):
        self.assertEqual(len(self.table), 4)
        self.assertEqual(self.table["Scheduled Flights"].sum(), 160)
        self.assertFalse(self.table.duplicated(["Airline DOT ID", "Destination Airport ID", "Month", "Departure Window"]).any())

    def test_tableau_ratio_of_sums_reproduces_the_common_mix(self):
        expected = {"Morning": .25, "Evening": .325}
        for window, target in expected.items():
            group = self.table.loc[self.table["Departure Window"].eq(window)]
            result = group["Weighted Disruptions 15+"].sum() / group["Common Mix Denominator"].sum()
            self.assertAlmostEqual(result, target)
        morning = self.table.loc[self.table["Departure Window"].eq("Morning")]
        self.assertNotAlmostEqual(morning["Disruptions 15+"].sum() / morning["Scheduled Flights"].sum(), .25)

    def test_whole_destination_and_month_filters_preserve_the_intended_rates(self):
        alpha = self.table.loc[self.table["Destination Code"].eq("AAA")]
        beta = self.table.loc[self.table["Month"].eq("2025-02-01")]
        for table, expected in [(alpha, {"Morning": .1, "Evening": .15}),
                                (beta, {"Morning": .4, "Evening": .5})]:
            for window, target in expected.items():
                group = table.loc[table["Departure Window"].eq(window)]
                self.assertAlmostEqual(group["Weighted Disruptions 15+"].sum() / group["Common Mix Denominator"].sum(), target)

    def test_hour_threshold_has_its_own_weighted_numerator(self):
        for window in ["Morning", "Evening"]:
            group = self.table.loc[self.table["Departure Window"].eq(window)]
            self.assertAlmostEqual(group["Weighted Disruptions 60+"].sum() / group["Common Mix Denominator"].sum(), .125)
        self.assertTrue(self.table["Disruptions 60+"].le(self.table["Disruptions 15+"]).all())

    def test_mismatched_cohorts_cannot_be_exported_together(self):
        self.pairs[60].loc[0, "n_morning"] = 99
        airlines, cities = labels()
        with self.assertRaisesRegex(ValueError, "same export cohort"):
            pair_source(self.pairs, airlines, cities)

    def test_summary_rates_and_gaps_use_different_units_and_keep_limited_bounds_blank(self):
        point = {"morning_rate": .25, "evening_rate": .325, "difference": .075}
        interval = {"lower": .02, "upper": .13, "clusters": 5}
        components = {name: {"morning_rate": 0, "evening_rate": 0} for name in ["cancelled", "diverted"]}
        components["late_completion"] = point
        result = {"standardized": point, "interval": interval, "n_morning": 80, "n_evening": 80,
                  "eligible_pairs": 2, "components": components}
        route = {"destination_id": 11, "destination_code": "AAA", "threshold_minutes": 15,
                 "morning_flights": 20, "evening_flights": 60, "matched_groups": 1,
                 "matched_months": 1, "week_clusters": 5, "window_coverage": .5,
                 "coverage_supported": False, "pointwise_interval": None,
                 "adjusted_lower": None, "adjusted_upper": None,
                 "direction_label": "Limited coverage", "route_family_size": 2, **point}
        audit = {"overall": {"15": result, "60": result}, "destinations": [route],
                 "coverage": {"retained_fraction_of_window_flights": .5}}
        _, cities = labels()
        overall, routes = summary_sources(audit, cities.set_index("Destination Airport ID"))
        self.assertEqual(overall["Delay Threshold Minutes"].tolist(), [15, 60])
        self.assertAlmostEqual(overall.loc[0, "Morning Disruption Rate"], .25)
        self.assertAlmostEqual(overall.loc[0, "Gap pp"], 7.5)
        self.assertAlmostEqual(overall.loc[0, "Gap Interval Lower pp"], 2)
        self.assertAlmostEqual(overall.loc[0, "Gap Interval Upper pp"], 13)
        self.assertTrue(routes.loc[0, ["Gap Interval Lower pp", "Gap Interval Upper pp"]].isna().all())
        self.assertAlmostEqual(routes.loc[0, "Gap pp"], 7.5)
