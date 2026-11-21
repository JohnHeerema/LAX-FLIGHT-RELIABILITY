# First comparison: morning and evening departures

**Protocol version 1.0.** This plan is committed before calculating morning/evening outcome comparisons. It specifies an observational analysis of the validated 2025 records; it is not an external preregistration or a randomized experiment.

## The question and the outcome

Within comparable airline, destination, and month groups, how much does the frequency of an **arrival disruption** differ between morning and evening departures?

For this comparison, a disruption is a flight that was **canceled, diverted, or arrived at least 15 minutes late**. The denominator is all scheduled flights in the selected comparison group. Canceled and diverted flights retain their missing ordinary arrival-delay values; the explicit outcome flags identify their disruption status.

This adds an explicitly defined composite outcome for this analysis. It does not change the existing cancellation, diversion, conditional arrival-delay, or percentile definitions in the data-handling rules. Its three components will also be shown separately per scheduled flight.

## Choices fixed before seeing this comparison's results

| Decision | Primary specification |
| --- | --- |
| Source | Validated full-year LAX extract, verified against its recorded checksum |
| Morning window | Scheduled local departure from 06:00 up to, but not including, 10:00 |
| Evening window | Scheduled local departure from 17:00 up to, but not including, 21:00 |
| Comparison group | Same reporting operating-carrier DOT ID, destination airport ID, and calendar month |
| Minimum support | At least 10 morning and 10 evening scheduled flights within a group |
| Common group weight | Total morning-plus-evening flights within that retained group, divided by the total across retained groups |
| Main result | Evening disruption rate minus morning disruption rate, expressed in percentage points |
| Uncertainty | Approximate 95% interval with calendar-week clustering |

The windows have equal duration and represent useful morning/evening options. The minimum count is a transparent support rule, not a guarantee of precision. Flights outside these windows or without supported comparisons remain in the full dataset. Their exclusion applies only to this particular analysis and will be counted explicitly.

Scheduled HHMM codes remain intact. For assigning time windows only, `2400` is treated as midnight and falls outside both windows. No cross-airport clock subtraction or inferred arrival timestamp is used.

## How the comparison will be made

1. Label the two scheduled departure windows and determine each flight's disruption status from the raw outcome fields.
2. Form airline/destination/month groups and retain those meeting the support rule in both windows.
3. Calculate morning and evening disruption rates separately within each retained group.
4. Give both windows the same set of group weights. Add the weighted rates to obtain two rates for the same airline/destination/month mix.
5. Subtract morning from evening and show component rates, coverage, and month-specific differences.

This avoids comparing one window's route and airline mix directly with another window's different mix. It does not account for every difference between those flights.

## Uncertainty and its assumptions

These are the recorded 2025 flights, so the observed counts and rates are descriptive totals for that dataset. The interval is a **conditional model-based approximation** to variability in the comparison under changing operational conditions. It is not uncertainty about whether the observed count was calculated correctly, and it is not a prediction interval for a future flight.

Flights in the same week may share weather and network disruptions. We therefore sum residual contributions within calendar weeks, rather than treating every flight as an independent observation. Weeks are seven-day blocks anchored on Monday, December 30, 2024. Correlation within a week is allowed; independence between weeks is an assumption, not an established fact.

For the calculation, let each retained airline/destination/month group have two outcome means and one common weight. The per-flight contribution is the common weight times its outcome residual divided by that window's group size, with a positive sign for evening and negative for morning. Sum those contributions within each week and square and sum the weekly totals. Multiply by the CR1 correction:

$$
\frac{G}{G-1}\frac{N-1}{N-K}
$$

Here, `G` is the number of observed calendar-week clusters, `N` is the number of retained flights, and `K` is twice the number of retained groups, corresponding to a separate mean for each group/window cell. The interval uses a Student t critical value with `G - 1` degrees of freedom. Group weights and the observed comparison design are treated as fixed.

Unmeasured confounding and dependence extending beyond a week are not eliminated by this interval. Longer time clusters and weekday matching are included as sensitivity checks. Thin groups, overlapping conditions, and the single-year scope still limit generalization.

## Sensitivity checks to publish regardless of direction

| Check | Change from the primary specification |
| --- | --- |
| Minimum 5 | Require at least 5 flights per window within a group |
| Minimum 20 | Require at least 20 flights per window within a group |
| Match weekday | Add scheduled-flight day of week to the grouping, with at least 3 flights in each window; verify it against the flight date |
| Two-week clusters | Keep the primary groups and weights; use 14-day clusters for the uncertainty interval |

The thresholds change which comparisons are supported; their coverage must be reported. The primary specification remains the main result even if a sensitivity produces a more attractive answer.

## Validation and interpretation

- Recalculate the primary grouping, counts, window assignment, and common-weight rates with a separate SQL query.
- Test window boundaries, cancellation handling, minimum support, and a synthetic example in which raw and common-mix comparisons reverse direction.
- Check the uncertainty calculation against a separate matrix implementation of a saturated group/window regression on synthetic records.
- Verify that component disruption rates add to the composite, group weights sum to one, and monthly results reconcile to the annual common-mix result.
- Rerun the analysis and verify stable numerical outputs and figures.

The result will describe an association within supported historical options. It will not show that changing departure time alone causes an improvement. Price, schedule availability, destination, weekday, weather, aircraft routing, and other operational differences can matter. A travel recommendation must remain conditional on practical constraints and future uncertainty.

The executable choices are recorded in the [protocol JSON](../analysis/morning_evening_protocol.json).

Method references:

- Cameron, A. C., & Miller, D. L. (2015). [A practitioner's guide to cluster-robust inference](https://escholarship.org/uc/item/1jq5d0pq). *Journal of Human Resources, 50*(2), 317–372.
- [Official statsmodels cluster covariance implementation](https://www.statsmodels.org/stable/_modules/statsmodels/stats/sandwich_covariance.html).
- [SciPy Student t distribution documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.t.html).
