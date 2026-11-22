# Final Tableau workbook: verified archive

The [final packaged workbook](../tableau/LAX_Flight_Reliability_Final.twbx) passes **82 data and configuration checks**. It is archived byte-for-byte from the author's uploaded `LAX_Flight_Reliability_Final.twbx`; inspection reads temporary extract copies and leaves the archive unchanged.

[Open the live dashboard](https://public.tableau.com/app/profile/john.heerema/viz/LAXFlightReliabilityMorningvs_Evening2025/LAXReliabilityOverview?publish=yes) · [Read the public desktop review](tableau_public_review.md) · [Machine-readable final audit](tableau_final.json)

## Data and saved results

Every one of the **2,062 embedded values** agrees with the validated CSVs. The overall extract has two rows and 19 fields; the destination extract has 92 rows and 22 fields. Numeric conversion uses absolute tolerance 1e-12; strings, booleans, and missing bounds are compared exactly.

Both embedded Hyper files are byte-identical to those in [checkpoint 03](tableau_checkpoint_03.md). The final presentation changes do not alter the data or the analytical results.

| Arrival-delay threshold, plus cancellations/diversions | Morning | Evening | Gap, pp | Approx. pointwise 95% model-based interval, pp |
| --- | ---: | ---: | ---: | --- |
| 15 minutes | 11.99% | 21.36% | 9.37 | 8.34–10.39 |
| 60 minutes | 4.42% | 8.01% | 3.59 | 2.96–4.23 |

The comparison retains 57,464 matched scheduled flights, or 64.2% of reported flights in the selected departure windows. These are historical common-mix comparisons. They do not establish causal effects or forecast future flights. The [primary report](morning_evening.md) and [exploratory extension](route_severity.md) document the assumptions, coverage, and model-based intervals.

## Final presentation checks

- The saved opening selection is **15 minutes**. All three views use one shared threshold group with the proper mapping across the separate overall and destination sources; no competing local threshold filter remains.
- All three titles use a live threshold field and inherit the workbook's **Arial** title setting without conflicting title-run overrides.
- Rate bars retain orange for morning and blue for evening, visible labels, and a fixed 0–25% percentage axis.
- The gap card uses live MIN inserts for the estimate and both bounds. Effective `0.00` formats display percentage points correctly, overriding an inherited percentage default in the overall source.
- The destination axis reads **Evening − morning disruption rate gap (percentage points)**. Dual axes are synchronized; Gantt starts use lower bounds and widths use upper minus lower. Both threshold states yield eight complete dots and ranges in direct embedded SQL.
- The displayed destinations are the eight largest matched-flight counts. All have supported coverage and adjusted intervals from the 62-comparison family. Direction labels agree with the adjusted bounds.
- The exact interpretation note is **Positive values mean higher evening disruption rates; negative values mean higher morning rates. Gray dots indicate uncertain direction.** It follows the destination view and precedes the source footer; both text zones are within the saved dashboard bounds.
- The source footer contains the BTS source, 2025 domestic LAX scope, cohort size, window coverage, interpretation limits, and GitHub methods link. The saved desktop dashboard uses automatic sizing.

## Validation and scope

The project test suite passes **61 tests**. Two final-stage failure cases verify that an earlier checkpoint cannot pass as the final presentation and that reversing the direction explanation is rejected. Existing checks for cross-source filter conflicts, incorrect data, interval widths, synchronized axes, percentage-point formats, and live field inserts remain in place.

Repeated inspection produces the same final JSON audit. The three earlier packaged checkpoints and their machine-readable audits remain unchanged and reproduce byte-identical audit outputs.

This native audit verifies ZIP integrity, saved configuration, simple field bindings, and embedded data. It does not render a new Tableau dashboard. The [public desktop review](tableau_public_review.md) separately checks the main title rendering, labels, notes, displayed rounded results, and live 15/60 switching. The uploaded workbook's saved settings agree with those observed presentation updates; byte identity with a server-downloaded workbook has not been established. Other viewport sizes, mobile layout, and full accessibility compliance are outside this review.

## Reproduce

```bash
python -m pip install -r requirements.txt -r requirements-tableau.txt
python -m scripts.inspect_tableau_workbook --workbook tableau/LAX_Flight_Reliability_Final.twbx
python -m unittest discover -s tests -v
```

The named final workbook automatically selects the final audit profile and writes `reports/tableau_final.json`. For a renamed copy, add `--final` to enforce the same final-presentation requirements. Earlier checkpoint paths retain their original inspection behavior and report filenames.

The inspector uses the optional pinned Tableau Hyper API dependency in [requirements-tableau.txt](../requirements-tableau.txt), through the [entry point](../scripts/inspect_tableau_workbook.py) and [two-source inspector](../scripts/inspect_tableau_destination_dashboard.py). See the [data guide](../docs/tableau_data_guide.md) for source grains and aggregation rules.

## File fingerprints

Workbook SHA-256: `9c8650d76736c74eab711730f3216d1656153dfd486079836d3d2fa7c6142562`.

Validated `overall_comparison_2025.csv` SHA-256: `a74ec9a683282e353f9ef84046f23233155bebe83b06cae67318b49fe440c96a`.

Validated `destination_comparison_2025.csv` SHA-256: `b738b9b81f9bf368681804ebff611dbbcf9aa17ff5b641dcd9f54d3b77fd5b33`.

Embedded `overall_comparison_2025` Hyper SHA-256: `5dd973cdd1338fef91534baf0f2f095ef7aafcb9d8c046700767c647b0e48cd6`.

Embedded `destination_comparison_2025` Hyper SHA-256: `fb602d166f616163c602f5e409d0ca00f5da3f459422878073e244849a906e51`.

