# Published Tableau dashboard: desktop review

Reviewed **November 22, 2026**, in a signed-out Chrome desktop browser.

[Open LAX Flight Reliability | Morning vs. Evening (2025)](https://public.tableau.com/app/profile/john.heerema/viz/LAXFlightReliabilityMorningvs_Evening2025/LAXReliabilityOverview?publish=yes)

The published dashboard opens at **15 minutes**. A live selector change to **60 minutes** updates the overall rates, gap card, all three worksheet titles, destination dots, and interval ranges. All eight destinations remain visible. The review ended with the original 15-minute view restored and no marks selected.

## Displayed results

The displayed values agree with the rounded values in the validated [overall](../data/tableau/overall_comparison_2025.csv) and [destination](../data/tableau/destination_comparison_2025.csv) CSVs.

| Arrival-delay threshold, plus cancellations/diversions | Morning rate | Evening rate | Evening minus morning, pp | Approx. pointwise 95% model-based interval, pp |
| --- | ---: | ---: | ---: | --- |
| 15 minutes | 11.99% | 21.36% | 9.37 | 8.34–10.39 |
| 60 minutes | 4.42% | 8.01% | 3.59 | 2.96–4.23 |

| Destination | 15-minute gap, pp | 60-minute gap, pp | Direction at 15 minutes | Direction at 60 minutes |
| --- | ---: | ---: | --- | --- |
| DEN | 9.72 | 2.49 | Higher evening rate | Uncertain direction |
| DFW | 2.37 | -0.24 | Uncertain direction | Uncertain direction |
| HNL | 10.12 | 4.37 | Higher evening rate | Higher evening rate |
| LAS | 18.15 | 5.83 | Higher evening rate | Higher evening rate |
| PHX | 8.26 | 2.48 | Higher evening rate | Uncertain direction |
| SEA | 5.96 | 1.18 | Higher evening rate | Uncertain direction |
| SFO | 13.94 | 7.59 | Higher evening rate | Higher evening rate |
| SMF | 9.44 | 3.69 | Higher evening rate | Higher evening rate |

Destination uncertainty uses adjusted family intervals; the overall gap card uses pointwise intervals. The full methods, assumptions, cohort, and interpretation limits remain in the [primary comparison](morning_evening.md) and [exploratory extension](route_severity.md).

## Presentation checks

- The main chart titles now display in a readable sans serif font in the review browser, correcting the earlier serif substitution in the first two titles.
- Morning bars remain orange and evening bars blue, with full color visible after clearing selections. Destination direction colors update from seven blue/one gray at 15 minutes to four blue/four gray at 60 minutes.
- The overall axis displays percentage ticks from 0% to 25%.
- The destination axis reads **Evening − morning disruption rate gap (percentage points)** and fits in the reviewed desktop view.
- The added note is visible: **Positive values mean higher evening disruption rates; negative values mean higher morning rates. Gray dots indicate uncertain direction.**
- The source footer states the 2025 domestic LAX scope, 57,464 matched scheduled flights, 64.2% coverage of the selected departure windows, interpretation limits, and GitHub methods link.

## Archive and review scope

This review exercised the live public interface and compared displayed rounded values. The later [final packaged workbook](../tableau/LAX_Flight_Reliability_Final.twbx) is now archived unchanged from the author's upload. Its [final audit](tableau_final.md) directly queries both embedded Hyper extracts, compares every value with the validated CSVs, and verifies the saved presentation settings visible in this review. Both extracts are byte-identical to the earlier [checkpoint 03](tableau_checkpoint_03.md); all earlier checkpoint files and audits remain preserved.

The uploaded archive contains the reviewed presentation updates. This is a comparison of saved settings and observed public behavior, rather than proof of byte identity with a workbook downloaded from the Tableau server.

The review covers one desktop browser display. It does not certify arbitrary viewport sizes, mobile layouts, or accessibility compliance. Some presentation details remain small: the destination header is abbreviated, the explanatory note uses a serif font in this browser, and the interval lines are pale. The main titles, numeric labels, interpretation note, and source text were readable at the reviewed desktop size.
