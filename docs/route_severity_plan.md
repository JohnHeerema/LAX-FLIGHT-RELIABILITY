# Destination and delay-severity follow-up

This is a follow-up prompted by the first overall 15-minute comparison. It uses the same historical data and is exploratory. The choices below are committed before computing this extension's destination summaries and 60-minute comparison; the first protocol and result remain unchanged.

## Questions and fixed choices

- Does the morning/evening difference persist when a late arrival must be at least 60 minutes late?
- How does the pattern vary by destination, and where is coverage too limited for a dependable directional label?
- Which compact, validated tables will support a Tableau dashboard or story?

Use the original morning/evening windows, airline/destination/month groups, minimum 10 flights per window per group, pooled common weights, and weekly conditional CR1 variance. Compare two outcomes: canceled, diverted, or completed arrival at least **15** minutes late; and the same definition with **60** minutes. The matched flights and groups must be identical for both thresholds.

## Destination coverage and uncertainty

A destination is eligible for a directional summary only if its retained comparisons cover at least **100 flights in each window**, **6 months**, and **20 observed weekly clusters**. These are support rules rather than guarantees of precision. Preserve every matched destination's point estimates and counts, including those with limited coverage.

Because many destinations and two thresholds are examined, use a more cautious interval for directional labels. The family consists of both thresholds for every coverage-supported destination. With `M` comparisons, use the existing standard error and a Student t critical value at `1 - 0.05 / (2M)`. This is a Bonferroni adjustment. Its coverage is approximate because the underlying weekly variance model is approximate.

Label a supported result **Higher evening rate** only when this interval lies entirely above zero, **Higher morning rate** only when it lies entirely below zero, and **Uncertain direction** when it crosses zero. Label all unsupported results **Limited coverage** and leave displayed intervals blank. Pointwise intervals may be retained for audit on supported routes, but the direction label uses the adjusted interval.

The overall 60-minute result is an exploratory, pointwise comparison with the original cohort. It does not acquire the original analysis's primary status. Report both thresholds and all destinations, including opposite-direction or uncertain results. Illustrative examples are the eight destinations with the largest retained flight counts, independent of their outcome rates.

## Tableau deliverables

Prepare three CSV sources with readable field names and documented row grains:

| Source | One row represents | Use |
| --- | --- | --- |
| Overall comparison | One threshold for the full-year matched cohort | First two-bar comparison and headline difference |
| Destination comparison | One destination and threshold | Route comparison, coverage, and uncertainty |
| Comparison pairs | One matched airline/destination/month/window | Valid common-mix point estimates after whole-month, airline, or destination filters |

Rates are fractions from 0 to 1; differences and interval bounds are percentage points. Overall and destination summary rates are precomputed and cannot be added or averaged to obtain a different overall estimate. The pair source supplies weighted event numerators and a common-mix denominator; Tableau must divide their sums within each departure window.

The pair source stores the two outcomes in separate columns, so selecting a threshold does not duplicate flight counts. Its allowed filters preserve whole matched groups. Full-year summary intervals do not apply to arbitrary filtered views.

Final dashboard/story visualizations will be authored in Tableau. This checkpoint prepares its evidence and input tables; it does not publish a Tableau workbook.

## Validation

- Reproduce the existing 15-minute result and preserve the original input checksum.
- Verify that 60-minute outcomes are a subset of 15-minute outcomes, with identical matching and weights.
- Independently recalculate global and destination results with SQL at both thresholds.
- Reconcile pooled-weight destination results to each overall rate.
- Read the exported CSVs back and reproduce global, destination, and monthly rates using the exact ratio-of-sums intended for Tableau.
- Check unique row keys, nonmissing labels, rate units, limited-coverage blanks, and the adjusted directional labels.
- Rerun and verify identical published outputs.

The executable policy is in [route_severity_plan.json](../analysis/route_severity_plan.json). Historical associations and conditional intervals do not establish causal effects or predict an individual future flight.

The interval adjustment follows [NIST's explanation of Bonferroni intervals](https://www.itl.nist.gov/div898/handbook/prc/section4/prc473.htm), applied here to the approximate conditional intervals already used in the project. Airline display names in [the lookup CSV](../data/reference/airline_labels_2025.csv) are transcribed from the reporting-carrier appendix on printed page 38 of the [February 2026 DOT report](https://www.transportation.gov/sites/dot.gov/files/2026-03/February%20%202026%20ATCR.pdf).
