# Destination differences, one-hour delays, and Tableau inputs

**Follow-up finding:** With the same matched flights and common airline/destination/month mix, the 60-minute disruption rate is **4.42% for morning** and **8.01% for evening** departures. The evening-minus-morning difference is **3.59 percentage points**, with an approximate pointwise 95% weekly-cluster interval of **2.96 to 4.23 points**.

This is an exploratory extension after the first overall 15-minute result. The [follow-up plan](../docs/route_severity_plan.md) was [committed before estimating these extension results](https://github.com/JohnHeerema/LAX-FLIGHT-RELIABILITY/commit/70e67397c463a17dc376261a3027e20579afae4d). The original protocol and result are preserved. Final dashboard/story visualizations will be authored in **Tableau** using the validated CSV sources below.

## The stricter threshold changes the outcome, not the cohort

Both definitions count a cancellation or diversion as a disruption. For a completed, nondiverted flight, the arrival must be at least 15 or 60 minutes late respectively. No missing arrival value is replaced with zero.

Both comparisons contain **57,464 scheduled flights** in the same **706 airline/destination/month groups**, using the original 06:00–09:59 and 17:00–20:59 scheduled local departure windows. They cover **64.2% of flights in those windows**, rather than every LAX flight.

| Arrival-delay threshold, plus cancellations/diversions | Morning | Evening | Difference, pp | Approx. pointwise 95% interval, pp |
| --- | ---: | ---: | ---: | --- |
| 15 minutes | 11.99% | 21.36% | +9.37 | +8.34 to +10.39 |
| 60 minutes | 4.42% | 8.01% | +3.59 | +2.96 to +4.23 |

The gap is smaller under the one-hour definition, while remaining positive in this matched historical comparison. This suggests the first result is not solely about delays shorter than an hour. It does not identify a causal effect, estimate trip-specific costs, or predict future operations. The 60-minute comparison is exploratory; its interval does not acquire confirmatory status by reusing the original data.

## Destination coverage and more cautious directional labels

There are **46 matched destinations**. **31** meet the follow-up display-support rules: at least 100 flights in each window, six months, and 20 weekly clusters. The remaining destinations retain descriptive rates and counts, with **Limited coverage** labels and blank displayed intervals.

For supported destinations, the direction labels use approximate Bonferroni-adjusted intervals across **62 destination/threshold comparisons**. This makes the intervals wider when many destinations are inspected. It does not remove the assumptions of the conditional weekly variance model or establish causal relationships.

| Threshold | Higher evening rate | Higher morning rate | Uncertain direction | Limited coverage |
| --- | ---: | ---: | ---: | ---: |
| 15 minutes | 20 | 0 | 11 | 15 |
| 60 minutes | 11 | 0 | 20 | 15 |

An uncertain interval is not evidence of equal reliability. A limited-coverage label is not a recommendation. These destination labels should not be replaced by a blanket statement about all routes.

## Examples selected by exposure, not outcome

These are the eight destinations with the largest retained flight counts, as specified in advance. Positive gaps indicate higher evening disruption rates; negative gaps indicate higher morning point estimates. The interval shown is the more cautious route interval for the 60-minute definition.

| Destination | Retained flights | Gap at 15 min, pp | Gap at 60 min, pp | Adjusted 60-min interval, pp | 60-min direction evidence |
| --- | ---: | ---: | ---: | --- | --- |
| SFO — San Francisco, CA | 5,068 | +13.94 | +7.59 | +4.37 to +10.81 | Higher evening rate |
| LAS — Las Vegas, NV | 3,800 | +18.15 | +5.83 | +2.03 to +9.62 | Higher evening rate |
| HNL — Honolulu, HI | 3,407 | +10.12 | +4.37 | +1.72 to +7.02 | Higher evening rate |
| SEA — Seattle, WA | 3,363 | +5.96 | +1.18 | -1.15 to +3.51 | Uncertain direction |
| PHX — Phoenix, AZ | 3,135 | +8.26 | +2.48 | -0.61 to +5.57 | Uncertain direction |
| DEN — Denver, CO | 2,995 | +9.72 | +2.49 | -0.46 to +5.45 | Uncertain direction |
| SMF — Sacramento, CA | 2,847 | +9.44 | +3.69 | +1.20 to +6.19 | Higher evening rate |
| DFW — Dallas/Fort Worth, TX | 2,630 | +2.37 | -0.24 | -4.60 to +4.12 | Uncertain direction |

The [complete destination source](../data/tableau/destination_comparison_2025.csv) includes all destinations, both thresholds, coverage, pointwise bounds on supported routes, adjusted bounds, and direction labels. Overall results still include every originally matched destination; the stricter destination display rules do not redefine the overall cohort.

## Tableau sources ready for authoring

| Source | Rows | One row represents |
| --- | ---: | --- |
| [Overall comparison](../data/tableau/overall_comparison_2025.csv) | 2 | One delay threshold for the full-year matched cohort |
| [Destination comparison](../data/tableau/destination_comparison_2025.csv) | 92 | One destination and threshold |
| [Comparison pairs](../data/tableau/comparison_pairs_2025.csv) | 1,412 | One matched airline/destination/month/window, with both thresholds as columns |
| [Field dictionary](../data/tableau/data_dictionary.csv) | 62 | One source field and its units/aggregation guidance |

The [Tableau data guide](../docs/tableau_data_guide.md) explains which source to use, the ratio-of-sums needed for filtered comparisons, and the distinction between percent rates and percentage-point gaps. The [export manifest](../data/manifests/tableau_sources_2025.json) records file checksums and row counts.

The first authoring checkpoint is deliberately small: connect the **overall comparison** CSV as a text file and verify its two rows, for thresholds 15 and 60. The Tableau workbook and its visual checks are the next stage.

## Checks and provenance

The original extract checksum is unchanged. SQL independently reconstructs time windows, matched groups, and every destination's point estimates at both thresholds. Destination common-mix rates reconcile to their overall rates when weighted by retained pooled flights.

The CSV files are read back after writing. The exact ratio-of-sums intended for Tableau reproduces the global results, all destination results, and the earlier month-by-month results. Keys are unique, the higher-threshold counts are nested, rates use fractions, gaps use percentage points, and limited-coverage bounds remain blank.

| Check | Result |
| --- | --- |
| The original overall 15-minute point estimates are reproduced | PASS |
| SQL independently reproduces all 46 destinations at 15 minutes | PASS |
| Destination common-mix rates reconcile to the overall 15-minute rates | PASS |
| Both thresholds use identical matched groups and flight counts | PASS |
| The 60-minute outcome is a subset of the 15-minute outcome | PASS |
| SQL independently reproduces all 46 destinations at 60 minutes | PASS |
| Destination common-mix rates reconcile to the overall 60-minute rates | PASS |
| Coverage rules select the same destinations at both thresholds | PASS |
| Overall rows are unique by threshold | PASS |
| Destination rows are unique by destination and threshold | PASS |
| Pair rows have one unique group/window key | PASS |
| Pair counts do not duplicate thresholds | PASS |
| Display labels are complete | PASS |
| Higher-threshold event counts are nested | PASS |
| Rate fields are fractions, not percentage-point values | PASS |
| Gap fields use percentage-point units | PASS |
| Limited coverage retains points but suppresses intervals | PASS |
| Tableau ratio-of-sums reproduces overall morning at 15 minutes | PASS |
| Tableau ratio-of-sums reproduces overall evening at 15 minutes | PASS |
| Every destination filter reproduces both 15-minute rates | PASS |
| Tableau ratio-of-sums reproduces overall morning at 60 minutes | PASS |
| Tableau ratio-of-sums reproduces overall evening at 60 minutes | PASS |
| Every destination filter reproduces both 60-minute rates | PASS |
| Whole-month filters reproduce the original monthly comparisons | PASS |

Airport-city labels come from `DestCityName` in the pinned BTS monthly files, with a [lookup provenance record](../data/reference/destination_labels_2025.json). Reporting operating-carrier names come from the DOT report appendix. Names and codes remain in their historical 2025 reporting scope, including separate Alaska and Hawaiian labels.

The [machine-readable audit](route_severity.json) records the plan commit, input checksum, full-precision results, coverage, and checks. Reproduce this checkpoint with `python -m scripts.route_severity` after building the validated year extract. Cached, checked lookup tables avoid rereading the source archives on subsequent runs.
