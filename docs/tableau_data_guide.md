# Tableau dashboard/story data guide

The visualization platform is **Tableau**. Python and SQL supply validated data and documented calculations. The current [three-view checkpoint](../tableau/checkpoints/LAX_Flight_Reliability_Checkpoint_03.twbx) contains overall rates, a live gap/interval summary, and eight destination comparisons. One threshold selector controls all three views across two separate sources.

## First checkpoint: connect one small source

Download [overall_comparison_2025.csv](../data/tableau/overall_comparison_2025.csv). In Tableau Desktop or Tableau Public, choose **Connect → Text File**, select the CSV, and inspect the data-source preview.

Confirm that there are exactly **two rows** and that `Delay Threshold Minutes` contains **15** and **60**. Rate values are decimal fractions at this stage; formatting them as percentages happens when building the worksheet. Stop at this preview before building the first chart.

## Sources and row grains

Load these as separate sources; each has a different row grain.

| File | Grain | Intended use |
| --- | --- | --- |
| `overall_comparison_2025.csv` | One full-year threshold | Overall morning/evening comparison and headline gap |
| `destination_comparison_2025.csv` | One destination and threshold | Destination-level full-year comparisons, coverage, and uncertainty |
| `comparison_pairs_2025.csv` | One matched airline/destination/month/window | Correct common-mix point estimates after whole-month, airline, or destination filters |
| `data_dictionary.csv` | One field in a source | Field types, units, and aggregation reference; not a chart's fact table |

Both thresholds use the original matched cohort. A disruption includes cancellation or diversion, plus a completed arrival at least the selected number of minutes late. The threshold changes the definition of lateness, not which matched flights are retained.

## Units and aggregation

| Field | Display format | Meaning |
| --- | --- | --- |
| `Morning Disruption Rate`, `Evening Disruption Rate`, other rate fields | Percentage, two decimals | Stored as fractions: `0.119882…` displays as `11.99%` |
| `Gap pp` and interval fields ending in `pp` | Number, two decimals | Already in percentage points: `9.3676…` displays as `9.37` |
| `Window Coverage` | Percentage | Fraction of the selected departure-window flights retained in the comparison |
| `Delay Threshold Minutes` | Discrete dimension/filter | Select 15 or 60 before making a summary mark |

For overall summaries, filter to one threshold. For destination marks, include destination and select one threshold. Use **MIN** for a precomputed rate or gap at that single-row scope. Obtain an overall rate from the overall source, rather than averaging destination percentages. Counts in the summary sources also repeat across the two thresholds, so totals require a selected threshold.

## Filtered comparisons from the pair source

The pair source stores 15- and 60-minute outcomes in separate columns. Actual flight counts therefore appear once per group/window. `Weighted Disruptions` fields are standardization inputs; they are not literal observed event counts.

With `Departure Window` in the view, the 15-minute common-mix rate is:

```text
SUM([Weighted Disruptions 15+]) / SUM([Common Mix Denominator])
```

The corresponding 60-minute rate uses `Weighted Disruptions 60+` with the same denominator. A later threshold parameter can select between these two calculations.

Whole-month, airline, and destination filters preserve the matched group structure. `Month` is an ISO date for the first of the month. Summary intervals apply to their fixed full-year scopes; filtered pair-table rates do not inherit those intervals. Keep the fixed-scope summaries and filtered point-estimate views clearly labeled.

## Destination uncertainty

- `Coverage Supported` reflects the precommitted count, month, and week requirements. It is a support flag, not a promise of precision.
- `Direction Evidence` uses the more cautious adjusted interval. Include uncertain directions in the view; limited-coverage rows can be shown in a coverage table or labeled distinctly.
- `Gap Interval Lower pp` and `Gap Interval Upper pp` describe uncertainty in **evening minus morning**, rather than uncertainty for either rate bar.
- Destination gap bounds use the route-family adjustment; overall bounds are pointwise. `Interval Scope` records that distinction.
- Blank destination bounds indicate limited coverage, not zero-width uncertainty.

## Suggested story sequence

1. Show the overall 15-minute result, then switch to the 60-minute definition.
2. Compare destinations with counts, coverage, and gap intervals visible.
3. Explain which views use supported historical comparisons and which have limited evidence.
4. Link the source validation, methods, and reproducible GitHub analysis.

Use the author's selected colors consistently: **orange for morning (`#F28E2B`)** and **blue for evening (`#4E79A7`)**. Keep morning above evening. Label rates as historical 2025 observations and keep the departure windows visible. Causal effects, future guarantees, and cost savings are not established by these comparisons.

## Verified native workbook checkpoint

The [checkpoint 03 audit](../reports/tableau_checkpoint_03.md) compares every embedded value with both validated CSVs. The overall extract has two rows and 19 fields; the destination extract has 92 rows and 22 fields. All three worksheet titles insert the shared threshold value. The overall percentage axis remains fixed at 0–25%, with 5-percentage-point ticks. The saved workbook selects 60 minutes, and both thresholds are embedded.

The three worksheets are stacked in a desktop dashboard with automatic sizing and a source/methods footer. Gap and interval values use MIN and effective custom `0.00` number formats. This worksheet formatting overrides an inherited percentage default on the overall source's `Gap pp`; choose number formatting whenever reusing this field. Viewport and phone-layout reviews remain separate from the configuration audit.

### Shared threshold across sources

Keep the overall and destination CSVs as separate sources at their documented grains. Map **overall `Delay Threshold Minutes` → destination `Delay Threshold Minutes`** in the cross-source relationship and apply the existing shared filter to all three worksheets. In the saved checkpoint, each worksheet has one threshold filter in the same filter group; Destination Gaps targets the mapped destination field.

A separate local destination threshold filter can conflict with the shared selector. For example, shared 15 plus local 60 produces no destination rows. Remove that competing local filter and retain the shared mapping. Switching the filter scope to only **All Using This Data Source** does not cover a worksheet using the separate destination source. Verify the bars, summary, destination marks, and all titles at both 15 and 60 after changing filter scope.

### Destination marks and intervals

The eight displayed destinations are selected by matched flight count, not by the size of their gaps: DEN, DFW, HNL, LAS, PHX, SEA, SFO, and SMF. The same eight remain visible at both thresholds. The destination layer uses MIN(`Gap pp`) for dots on synchronized dual axes, MIN(`Gap Interval Lower pp`) for Gantt starts, and MIN of the following calculated field for Gantt size:

```text
[Gap Interval Upper pp] - [Gap Interval Lower pp]
```

Keep interval labels hidden and dot labels visible. Dots use blue for **Higher evening rate** and gray for **Uncertain direction**; intervals are light gray. These categories derive from adjusted bounds across all 62 supported destination/threshold comparisons, including comparisons outside the eight displayed destinations. An uncertain direction means the interval includes zero; it does not establish equal disruption rates. Blank bounds for limited-coverage destinations remain blank.

Official Tableau references: [Connect to a text file](https://help.tableau.com/current/pro/desktop/en-us/examples_text.htm) and [measure aggregation](https://help.tableau.com/current/pro/desktop/en-us/calculations_aggregation.htm).
