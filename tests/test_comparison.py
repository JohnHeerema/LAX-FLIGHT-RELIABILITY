"""Hand-calculated reversals, independent SQL, and matrix covariance checks."""

import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from scripts.compare_departure_windows import analyze, prepare, sql_check


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / "analysis/morning_evening_protocol.json").read_text())


def records(specifications):
    """Tuples contain destination ID, window, number of flights, and disruptions."""
    rows = []
    for destination, window, flights, disruptions in specifications:
        for index in range(flights):
            date = pd.Timestamp("2025-01-01") + pd.Timedelta(days=index % 28)
            rows.append({
                "Origin": "LAX", "Year": 2025, "Month": 1,
                "FlightDate": date.strftime("%Y-%m-%d"), "DayOfWeek": date.dayofweek + 1,
                "Reporting_Airline": "AS", "DOT_ID_Reporting_Airline": 19930,
                "DestAirportID": destination, "Dest": str(destination),
                "CRSDepTime": "0800" if window == "morning" else "1800",
                "Cancelled": 0, "Diverted": 0, "ArrDelay": 20.0 if index < disruptions else -5.0,
            })
    return pd.DataFrame(rows)


def reversal_frame():
    # Evening has a higher disruption rate within BOTH destinations, but flies
    # more often to the lower-risk destination. Raw rates therefore reverse.
    return prepare(records([
        (1, "morning", 20, 2), (1, "evening", 60, 9),
        (2, "morning", 60, 24), (2, "evening", 20, 10),
    ]), PROTOCOL)


class PreparationTests(unittest.TestCase):
    def test_window_boundaries_and_midnight_are_explicit(self):
        frame = records([(1, "morning", 10, 0)])
        frame["CRSDepTime"] = ["0559", "0600", "0959", "1000", "1659", "1700", "2059", "2100", "2400", "0000"]
        result = prepare(frame, PROTOCOL)
        self.assertEqual(result["Window"].tolist(), ["outside", "morning", "morning", "outside", "outside", "evening", "evening", "outside", "outside", "outside"])
        self.assertEqual(result.loc[8, "CRSDepTime"], "2400")

    def test_cancellations_and_diversions_are_disruptions_without_filling_arrivals(self):
        frame = records([(1, "morning", 5, 0)])
        frame.loc[0, ["Cancelled", "ArrDelay"]] = [1, None]
        frame.loc[1, ["Diverted", "ArrDelay"]] = [1, None]
        frame.loc[2, "ArrDelay"] = 14
        frame.loc[3, "ArrDelay"] = 15
        result = prepare(frame, PROTOCOL)
        self.assertEqual(result["Disrupted"].tolist(), [1, 1, 0, 1, 0])
        self.assertTrue(result.loc[:1, "ArrDelay"].isna().all())
        self.assertEqual(result.loc[4, "ArrDelay"], -5)

    def test_completed_missing_arrival_stops_instead_of_becoming_on_time(self):
        frame = records([(1, "morning", 1, 0)])
        frame.loc[0, "ArrDelay"] = None
        with self.assertRaisesRegex(ValueError, "Completed arrival delay is missing"):
            prepare(frame, PROTOCOL)

    def test_invalid_time_stops(self):
        frame = records([(1, "morning", 1, 0)])
        frame.loc[0, "CRSDepTime"] = "2461"
        with self.assertRaisesRegex(ValueError, "Invalid scheduled local"):
            prepare(frame, PROTOCOL)

    def test_weekday_must_agree_with_the_scheduled_date(self):
        frame = records([(1, "morning", 1, 0)])
        frame.loc[0, "DayOfWeek"] = 7
        with self.assertRaisesRegex(ValueError, "Weekday does not match"):
            prepare(frame, PROTOCOL)


class MatchingAndInferenceTests(unittest.TestCase):
    def test_common_mix_resolves_the_hand_calculated_reversal(self):
        result, pairs, _ = analyze(reversal_frame(), PROTOCOL)
        raw = result["unadjusted_retained"]
        self.assertAlmostEqual(raw["morning"]["rate"], 26 / 80)
        self.assertAlmostEqual(raw["evening"]["rate"], 19 / 80)
        self.assertLess(raw["evening"]["rate"], raw["morning"]["rate"])
        self.assertTrue(np.allclose(pairs["Weight"], [0.5, 0.5]))
        self.assertAlmostEqual(result["standardized"]["morning_rate"], 0.25)
        self.assertAlmostEqual(result["standardized"]["evening_rate"], 0.325)
        self.assertAlmostEqual(result["standardized"]["difference"], 0.075)

    def test_both_windows_must_meet_the_support_rule(self):
        frame = prepare(records([(1, "morning", 10, 1), (1, "evening", 10, 2),
                                 (2, "morning", 20, 2), (2, "evening", 9, 1)]), PROTOCOL)
        result, pairs, _ = analyze(frame, PROTOCOL)
        self.assertEqual(result["eligible_pairs"], 1)
        self.assertEqual(result["n_morning"], 10)
        self.assertEqual(pairs["DestAirportID"].tolist(), [1])
        self.assertEqual(len(frame), 49)

    def test_different_airlines_cannot_supply_each_others_missing_window(self):
        frame = records([(1, "morning", 20, 1), (1, "evening", 20, 2)])
        frame.loc[frame["CRSDepTime"].eq("1800"), "DOT_ID_Reporting_Airline"] = 1
        with self.assertRaisesRegex(ValueError, "No groups meet"):
            analyze(prepare(frame, PROTOCOL), PROTOCOL)

    def test_row_order_does_not_change_the_estimate_or_interval(self):
        frame = reversal_frame()
        original, _, _ = analyze(frame, PROTOCOL)
        shuffled, _, _ = analyze(frame.sample(frac=1, random_state=24), PROTOCOL)
        self.assertAlmostEqual(original["standardized"]["difference"], shuffled["standardized"]["difference"])
        self.assertAlmostEqual(original["interval"]["standard_error"], shuffled["interval"]["standard_error"])

    def test_interval_matches_a_separate_saturated_ols_matrix_calculation(self):
        result, pairs, matched = analyze(reversal_frame(), PROTOCOL)
        cell = matched["PairID"].to_numpy() * 2 + matched["Window"].eq("evening").astype(int).to_numpy()
        design = np.eye(2 * len(pairs))[cell]
        outcome = matched["Disrupted"].to_numpy()
        beta = np.linalg.lstsq(design, outcome, rcond=None)[0]
        residual = outcome - design @ beta
        contrast = np.empty(2 * len(pairs))
        contrast[0::2] = -pairs["Weight"].to_numpy()
        contrast[1::2] = pairs["Weight"].to_numpy()
        cluster = ((pd.to_datetime(matched["FlightDate"]) - pd.Timestamp(PROTOCOL["cluster_anchor"])).dt.days // 7).to_numpy()
        scores = np.vstack([design[cluster == group].T @ residual[cluster == group] for group in np.unique(cluster)])
        bread = np.linalg.inv(design.T @ design)
        g, n, k = len(scores), len(design), design.shape[1]
        covariance = (g / (g - 1) * (n - 1) / (n - k)) * bread @ (scores.T @ scores) @ bread
        expected_se = float(np.sqrt(contrast @ covariance @ contrast))
        self.assertAlmostEqual(float(contrast @ beta), result["standardized"]["difference"], places=12)
        self.assertAlmostEqual(expected_se, result["interval"]["standard_error"], places=12)

    def test_sql_recomputes_raw_windows_and_outcomes_independently(self):
        frame = reversal_frame()
        result, _, _ = analyze(frame, PROTOCOL)
        frame["Window"] = "outside"
        frame["Disrupted"] = 0
        sql = sql_check(frame, PROTOCOL, result)
        self.assertAlmostEqual(sql["morning_rate"], 0.25)
        self.assertAlmostEqual(sql["evening_rate"], 0.325)

    def test_larger_time_clusters_do_not_change_the_point_estimate(self):
        frame = reversal_frame()
        main, _, _ = analyze(frame, PROTOCOL)
        longer, _, _ = analyze(frame, PROTOCOL, cluster_days=14)
        self.assertEqual(main["standardized"], longer["standardized"])
        self.assertLess(longer["interval"]["clusters"], main["interval"]["clusters"])


if __name__ == "__main__":
    unittest.main()
