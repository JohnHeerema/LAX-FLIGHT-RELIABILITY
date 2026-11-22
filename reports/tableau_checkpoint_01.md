# Tableau checkpoint 01: overall comparison verified

The [native packaged workbook](../tableau/checkpoints/LAX_Flight_Reliability_Checkpoint_01.twbx) passes **23 data and configuration checks**. It contains one interactive worksheet, **Overall Reliability**, with the 15/60-minute selector, a live threshold in the title, and the author's chosen morning-orange/evening-blue colors.

## Data inside the workbook

The workbook includes a Hyper extract containing **two rows and 19 columns**. Direct SQL reads of every value agree with the [validated overall CSV](../data/tableau/overall_comparison_2025.csv), using an absolute numeric tolerance of 1e-12 for floating-point conversion. No flight-archive download is required to reproduce this checkpoint audit.

| Arrival-delay threshold, plus cancellations/diversions | Morning | Evening | Evening-minus-morning gap, pp | Approx. pointwise 95% weekly-cluster interval, pp |
| --- | ---: | ---: | ---: | --- |
| 15 | 11.99% | 21.36% | 9.37 | 8.34–10.39 |
| 60 | 4.42% | 8.01% | 3.59 | 2.96–4.23 |

The gap and interval fields are verified inside the extract and are ready for the next worksheet; they are not yet displayed in this workbook. These describe the fixed full-year matched cohort of **57,464 flights**, not arbitrary filtered route/month views. The uncertainty model and historical-association limits are explained in the [analysis](morning_evening.md) and [follow-up](route_severity.md).

## Saved settings

The saved threshold is **60 minutes**. The control uses round single-choice buttons and hides All. Both bars use MIN on their precomputed rate fields. The shared axis runs from 0% to 25%, with five-percentage-point ticks; rate labels retain two decimal places. Morning appears first, in orange (`#F28E2B`); evening follows in blue (`#4E79A7`).

| Check | Result |
| --- | --- |
| Packaged workbook ZIP integrity passes | PASS |
| Package contains one workbook and one data extract | PASS |
| Checkpoint contains one overall source and worksheet | PASS |
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
| Inspection leaves the uploaded workbook unchanged | PASS |

## Reproduce the inspection

```bash
python -m pip install -r requirements-tableau.txt
python -m scripts.inspect_tableau_workbook
python -m unittest discover -s tests -p test_tableau_checkpoint.py -v
```

The [inspection script](../scripts/inspect_tableau_workbook.py) reads the workbook configuration and queries a temporary copy of the embedded extract with the [official Tableau Hyper API](https://tableau.github.io/hyper-db/docs/guides/hyper_file/read/). Usage-data reporting is disabled. The package itself is unchanged. A repeat run produces the same [JSON audit](tableau_checkpoint_01.json).

Two [temporary fault cases](../tests/test_tableau_checkpoint.py) were also checked: a multiple-choice threshold control is rejected, and a mismatched source rate is rejected. These check that inspection failures are surfaced rather than recorded as passes.

The inspection verifies stored data and configuration; it does not launch Tableau for a fresh render. Screenshots were reviewed separately during authoring, and the author confirmed switching between thresholds. The final dashboard/story and its end-to-end visual review remain ahead.

Workbook SHA-256: `1ee7ac498319e2a98d11d98e3f3254897d1cf7a4b8e6c5c820bd6c1d02c44933`.

Validated CSV SHA-256: `a74ec9a683282e353f9ef84046f23233155bebe83b06cae67318b49fe440c96a`.
