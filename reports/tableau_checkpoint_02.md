# Tableau checkpoint 02: interactive overview verified

The [native overview workbook](../tableau/checkpoints/LAX_Flight_Reliability_Checkpoint_02.twbx) passes **39 data and configuration checks**. It combines **Overall Reliability** and **Gap Summary** in the **LAX Reliability Overview** dashboard. One shared threshold selector controls the rate bars, both titles, and the gap/interval card.

## Verified data and labels

The packaged Hyper extract contains **two rows and 19 fields**. Every value agrees with the [validated overall CSV](../data/tableau/overall_comparison_2025.csv), with an absolute numeric tolerance of 1e-12 for floating-point conversion.

| Arrival-delay threshold, plus cancellations/diversions | Morning | Evening | Evening-minus-morning gap, pp | Approx. pointwise 95% weekly-cluster interval, pp |
| --- | ---: | ---: | ---: | --- |
| 15 | 11.99% | 21.36% | 9.37 | 8.34–10.39 |
| 60 | 4.42% | 8.01% | 3.59 | 2.96–4.23 |

These are the fixed full-year matched comparisons of **57,464 scheduled flights**. The intervals describe conditional model-based uncertainty in the gap. They are not future-flight predictions or evidence of a causal departure-time effect. See the [primary analysis](morning_evening.md) and [exploratory extension](route_severity.md) for the cohort, model assumptions, and limitations.

All three summary values are live MIN field inserts. The inspector resolves the stored label bindings against both threshold rows and verifies the resulting text. It does not infer valid bindings merely from a screenshot with the expected numbers.

## Saved dashboard configuration

The saved threshold is **60 minutes**. The desktop layout is fixed at **1100 by 650 pixels**, with the rate chart above the summary card in a vertical container. The desktop selector uses single-choice radio buttons with All hidden. Both source worksheets reference the same data source and shared threshold filter, without conflicting local threshold filters.

The bars retain orange for morning (`#F28E2B`) and blue for evening (`#4E79A7`), and the common percentage axis spans 0–25%. The three gap/interval fields have effective custom `0.00` formats and show percentage-point units. `Gap pp` still has an inherited percentage default at the data-source level; the saved worksheet explicitly overrides it. Further uses of that field should use number formatting, as documented in the [data guide](../docs/tableau_data_guide.md).

| Check | Result |
| --- | --- |
| Packaged workbook ZIP integrity passes | PASS |
| Package contains one workbook and one data extract | PASS |
| Dashboard checkpoint contains one overall source and two expected worksheets | PASS |
| Active data extract is included inside the package | PASS |
| Extract contains one analysis table | PASS |
| All 19 extract fields match the validated CSV schema | PASS |
| Extract contains exactly the 15- and 60-minute rows | PASS |
| Reference CSV contains exactly one row per threshold | PASS |
| Every extracted value agrees with the validated CSV (absolute numeric tolerance 1e-12) | PASS |
| Threshold is a dimension | PASS |
| One threshold filter is present | PASS |
| Saved filter selects one valid threshold | PASS |
| Threshold control is single choice with All hidden | PASS |
| Title uses the live threshold field | PASS |
| Morning Disruption Rate defaults to MIN and two-decimal percentage formatting | PASS |
| Evening Disruption Rate defaults to MIN and two-decimal percentage formatting | PASS |
| Only the two MIN disruption rates appear as bars | PASS |
| View uses horizontal bars with visible labels | PASS |
| Axis is fixed at 0-25 percent with 5-point ticks | PASS |
| Numeric axis displays percentages | PASS |
| Colors preserve morning orange and evening blue | PASS |
| Morning precedes evening | PASS |
| One shared threshold filter targets the common data source | PASS |
| Both worksheets use the shared source and threshold slice | PASS |
| Gap title uses the shared live threshold field | PASS |
| Gap and both interval fields use MIN | PASS |
| Summary text uses exactly the three validated gap fields | PASS |
| All three effective gap formats are two-decimal numbers | PASS |
| Summary label binds all three live values and percentage-point units | PASS |
| Gap summary is a text mark without row or column dimensions | PASS |
| Overview dashboard has the expected name | PASS |
| Desktop dashboard has fixed 1100-by-650 dimensions | PASS |
| Dashboard contains both verified worksheets | PASS |
| Overall chart and gap card share a vertical container in reading order | PASS |
| Desktop dashboard exposes one single-choice threshold control with All hidden | PASS |
| Both desktop view zones remain inside the dashboard bounds | PASS |
| Summary field bindings resolve correctly at 15 minutes | PASS |
| Summary field bindings resolve correctly at 60 minutes | PASS |
| Inspection leaves the uploaded workbook unchanged | PASS |

## Reproduce this checkpoint audit

```bash
python -m pip install -r requirements-tableau.txt
python -m scripts.inspect_tableau_workbook --workbook tableau/checkpoints/LAX_Flight_Reliability_Checkpoint_02.twbx
python -m unittest discover -s tests -p test_tableau_checkpoint.py -v
```

The [inspection script](../scripts/inspect_tableau_workbook.py) queries a temporary extract copy through the [official Tableau Hyper API](https://tableau.github.io/hyper-db/docs/guides/hyper_file/read/). It leaves both checkpoint workbooks unchanged and regenerates the [JSON audit](tableau_checkpoint_02.json). Repeated inspection produces identical results, and the earlier checkpoint 01 audit remains byte-identical.

Four additional temporary fault cases exercise failures relevant to this dashboard: a missing shared threshold filter, a manually typed interval bound, a percentage-formatted gap, and a multiple-choice dashboard control. The two earlier fault checks remain in the same [test module](../tests/test_tableau_checkpoint.py).

The audit verifies embedded data, saved configuration, and simple field bindings. It does not launch Tableau for a new render or automate live clicks. The author's supplied screenshots show the 15-minute gap card and 60-minute combined dashboard; switching was confirmed during authoring. The auto-generated phone layout has not received a visual review. Destination views, sources/methods context in the dashboard, and final layout review remain ahead.

Workbook SHA-256: `3ed598a53ea5463ca4d35a05294e917ceb1ee85fcc47b4b470a9cd43d4093052`.

Validated CSV SHA-256: `a74ec9a683282e353f9ef84046f23233155bebe83b06cae67318b49fe440c96a`.
