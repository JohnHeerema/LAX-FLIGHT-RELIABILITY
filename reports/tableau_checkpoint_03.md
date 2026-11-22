# Tableau checkpoint 03: three-view dashboard verified

The [packaged workbook](../tableau/checkpoints/LAX_Flight_Reliability_Checkpoint_03.twbx) passes **76 data and configuration checks**. The dashboard combines Overall Reliability, Gap Summary, and Destination Gaps, with one shared 15/60-minute selector and a source/methods footer. The uploaded workbook is archived unchanged.

## Embedded data

Every value in both packaged Hyper extracts agrees with the validated CSVs: **2,062 values**, using absolute numeric tolerance 1e-12 and exact string, boolean, and blank-value matching.

| Source | Rows | Fields | Grain |
| --- | ---: | ---: | --- |
| [Overall](../data/tableau/overall_comparison_2025.csv) | 2 | 19 | Full-year threshold |
| [Destination](../data/tableau/destination_comparison_2025.csv) | 92 | 22 | Destination and threshold |

| Delay threshold, plus cancellations/diversions | Morning | Evening | Gap, pp | Approx. pointwise 95% model-based interval, pp |
| --- | ---: | ---: | ---: | --- |
| 15 minutes | 11.99% | 21.36% | 9.37 | 8.34–10.39 |
| 60 minutes | 4.42% | 8.01% | 3.59 | 2.96–4.23 |

Both definitions use the same 57,464 matched scheduled flights: 64.2% of reported flights in the selected departure windows. The gap card uses three live MIN field inserts, with effective `0.00` number formats and percentage-point units. The overall source still inherits a percentage default for `Gap pp`; the saved worksheet overrides it. Reuse that field with number formatting.

## Filter and destination verification

All three worksheets have one threshold filter in the same shared group. The overall threshold maps to the destination threshold through one cross-source relationship. There is no competing local destination threshold filter. Each title uses the shared live threshold field.

The earlier authoring defect combined a shared 15-minute filter with a separate local 60-minute filter, leaving Destination Gaps empty. A regression test recreates that conflict and requires the inspector to reject it. Other temporary fault tests reject an incorrect relationship mapping, upper-plus-lower interval width, unsynchronized axes, and a changed destination reference value.

Direct SQL on the embedded destination extract returns eight complete dots and intervals at each threshold. The selected destinations are the eight largest matched-flight counts, chosen without ranking their outcome gaps. All have supported coverage, and their bounds retain the Bonferroni adjustment across **62** supported destination/threshold comparisons. Gantt starts are lower bounds, sizes are upper minus lower, and the circle and Gantt axes are synchronized.

| Threshold | Higher evening rate | Uncertain direction | Destinations shown |
| --- | ---: | ---: | ---: |
| 15 minutes | 7 | 1 | 8 |
| 60 minutes | 4 | 4 | 8 |

The [JSON audit](tableau_checkpoint_03.json) records every displayed gap, bound, interval width, and direction label at both thresholds. Uncertain direction means the adjusted interval includes zero; it does not establish equality. Overall intervals are pointwise, while destination intervals use the family adjustment. These conditional model intervals describe historical comparisons, not causal effects or future-flight forecasts. See the [primary analysis](morning_evening.md), [exploratory extension](route_severity.md), and [data guide](../docs/tableau_data_guide.md).

## Saved presentation and audit limits

The workbook saves the **60-minute** selection and uses **automatic desktop sizing**. Three vertically stacked view zones and the footer follow the intended reading order. The rate axis is fixed at 0–25%; destination axes use an automatic range. Morning remains orange (`#F28E2B`) and evening blue (`#4E79A7`). Destination dots use blue for higher evening rates and gray (`#8A8382`) for uncertain directions; intervals are light gray (`#E6E6E6`). The footer gives the BTS source, 2025 domestic LAX scope, sample size, window coverage, interpretation limits, and GitHub methods link.

The audit checks ZIP integrity, saved configuration, simple field bindings, and direct embedded-data SQL. It does not launch Tableau, render a new dashboard, or automate selector clicks. Author screenshots at 15 and 60 minutes were reviewed separately during authoring; the saved gap-card thumbnail is readable. Arbitrary viewport sizes, full color-contrast accessibility, and the auto-generated phone layout have not received visual review. The pale interval lines should also be checked at the published display size.

## Reproduce

```bash
python -m pip install -r requirements-tableau.txt
python -m scripts.inspect_tableau_workbook --workbook tableau/checkpoints/LAX_Flight_Reliability_Checkpoint_03.twbx
python -m unittest discover -s tests -p test_tableau_checkpoint.py -v
```

Inspection reads temporary extract copies through the [official Tableau Hyper API](https://tableau.github.io/hyper-db/docs/guides/hyper_file/read/). The [entry point](../scripts/inspect_tableau_workbook.py) dispatches this two-source workbook to the [destination-dashboard inspector](../scripts/inspect_tableau_destination_dashboard.py). Earlier checkpoint files and audits remain unchanged.

Workbook SHA-256: `3661489e52ec6ceeb6cb5ed6d6d0df70b07da486092886f0d3d102fcdadc141a`.

Validated `overall_comparison_2025.csv` SHA-256: `a74ec9a683282e353f9ef84046f23233155bebe83b06cae67318b49fe440c96a`.

Validated `destination_comparison_2025.csv` SHA-256: `b738b9b81f9bf368681804ebff611dbbcf9aa17ff5b641dcd9f54d3b77fd5b33`.

