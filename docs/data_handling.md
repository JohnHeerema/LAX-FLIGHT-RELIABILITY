# Data-handling rules — version 1

**Checkpoint:** Rules documented after inspecting January 2025 and before downloading the remaining months. They have now been applied to each month and the combined year; see the [full-year validation report](../reports/year_2025.md).

We define these rules before comparing airlines or departure times so an attractive result does not determine how we handle inconvenient records.

## Six rules to understand first

| Rule | What we will do | Why it matters |
| --- | --- | --- |
| Preserve the source | Keep the original archive and record its URL, download time, and SHA-256 checksum. | We can identify the exact snapshot behind a result. |
| Keep every in-scope flight | Include reported domestic flights scheduled to depart LAX, including cancellations and diversions. | Removing disrupted flights would hide part of reliability. |
| Preserve meaningful blanks | Leave ordinary arrival delay missing for canceled or diverted flights. | Missing arrival delay does not mean zero delay. |
| Respect early arrivals | Keep negative signed delays; use zero only when expressing an observed early arrival as minutes late. | An observed early arrival and an unobserved ordinary arrival are different outcomes. |
| Use the right denominator | Use all scheduled flights for cancellation and diversion rates; eligible completed arrivals for arrival-delay measures. | Different questions require different comparison groups. |
| Investigate anomalies | Flag duplicate identifiers, invalid flags, unexpected missing values, and unusual measurements before changing records. | Automatic deletion or replacement can create misleading results. |

## Scope and one row of data

The target dataset covers January 1–December 31, 2025, with `Origin == 'LAX'`, from the BTS **Reporting Carrier On-Time Performance** table. One row represents one reported scheduled nonstop flight occurrence.

We retain the table's reporting operating-carrier identity. We do not silently combine regional carriers with the airline brands on tickets or mix this table with the separate Marketing Carrier dataset. Source coverage is not a census of every airline or international flight.

The proposed flight identifier consists of:

- `FlightDate`
- `DOT_ID_Reporting_Airline`
- `Flight_Number_Reporting_Airline`
- `OriginAirportID`
- `DestAirportID`
- `CRSDepTime`

These fields are present and unique in the validated full-year dataset. A repeated identifier in a future source revision triggers review; it does not authorize keeping the first row and discarding the rest.

## Classify outcomes using flags

| Outcome | Rule |
| --- | --- |
| Canceled | `Cancelled == 1` |
| Diverted | `Diverted == 1` |
| Completed without diversion | `Cancelled == 0` and `Diverted == 0` |

Both flags must be present and equal to 0 or 1. A record with both flags equal to 1 requires review before classification. The outcome counts must reconcile to all in-scope scheduled flights.

A recorded departure time does not override these flags. January contains 11 canceled flights with a departure time recorded.

## Missing values and unusual measurements

| Field or situation | Handling rule |
| --- | --- |
| Ordinary `ArrDelay` is blank for a canceled or diverted flight | Preserve the blank; retain the flight in its outcome group. Diverted-arrival measurements use separate BTS fields. |
| Ordinary arrival delay is missing for a completed, nondiverted flight | Flag and investigate. Do not replace it with zero; pause affected comparisons until reviewed. Report the number of records without usable arrival delay. |
| `CancellationCode` is blank for a flight that was not canceled | Treat this as expected in the January pilot; check the pattern again in later months. |
| Cause-of-delay fields are blank outside qualifying delayed arrivals | Preserve the blanks and check them against eligibility before interpreting cause information. Do not infer that a blank means a measured zero. |
| Signed `ArrDelay` is negative | Retain it as an early arrival. |
| A delay is unusually large | Retain and flag it for review. Do not trim, cap, or delete it simply because it changes an average. |
| A required date, identifier, or status flag is missing or invalid | Stop the affected validation and investigate the source record. Do not silently infer a replacement. |
| The CSV has an empty trailing header field | Select named columns explicitly; the empty field is not a flight attribute. |

Raw values remain available. Any later correction or exclusion must state the reason and the number of affected records. We do not apply blanket row deletion or blanket zero-filling.

## Metric definitions

An **eligible arrival** is a completed, nondiverted flight with a valid recorded arrival delay. We check agreement between `ArrDelay`, `ArrDelayMinutes`, and `ArrDel15` before using them.

| Measure | Numerator or values | Denominator or population |
| --- | --- | --- |
| Flight count | In-scope scheduled flight records | Selected group |
| Cancellation rate | Canceled flights | All in-scope scheduled flights in that group |
| Diversion rate | Diverted flights | All in-scope scheduled flights in that group |
| Arrival delay rate | Eligible arrivals with `ArrDelay >= 15` | All eligible arrivals in that group |
| 90th percentile of minutes late | Observed `ArrDelayMinutes`, with early arrivals equal to zero | All eligible arrivals, using linear interpolation |

Exactly 15 minutes late qualifies as delayed. Percentile calculations include eligible on-time arrivals, not just delayed arrivals. A group with no eligible arrivals has an unknown arrival-delay rate and percentile, rather than zero.

### January example

| Calculation | Result |
| --- | ---: |
| Cancellation rate: 158 / 15,157 scheduled flights | 1.04% |
| Diversion rate: 41 / 15,157 scheduled flights | 0.27% |
| Arrival delay rate: 1,934 / 14,958 eligible arrivals | 12.93% |
| Missing ordinary arrival delays: 158 canceled + 41 diverted | 199 records |

These numbers come from the [pilot inspection](../reports/pilot_2025_01.md) and [machine-readable profile](../reports/pilot_2025_01.json). The denominator and missingness rules are covered by the existing [focused tests](../tests/test_pilot.py).

## Outcome added for the first comparison

The [morning/evening protocol](morning_evening_plan.md), committed before estimating that comparison, adds an **arrival-disruption** outcome: a cancellation, diversion, or completed arrival at least 15 minutes late. Its denominator is all scheduled flights in the selected comparison group. The three components are also reported separately per scheduled flight, so their rates add to the composite.

This is an analysis-specific addition. It preserves the earlier metric definitions and leaves ordinary arrival-delay blanks intact. It does not reinterpret a canceled flight as having an observed zero-minute arrival delay.

## Dates and times

Preserve flight numbers, airline codes, and local HHMM time codes as text. Keep scheduled and actual values distinct. The pilot accepts valid HHMM codes and the special `2400` representation; the original code remains intact. Any later conversion of that value must be documented and tested before creating time buckets or timestamps.

Use the supplied BTS delay-minute fields. Do not subtract origin and destination HHMM codes: they are local clock times and can cross time zones or midnight. Comparisons of departure options will use scheduled departure information.

## Checks required before extending the analysis

- Record one source snapshot per month, including the exact archive checksum. A changed checksum stops processing for review.
- Verify every file's stated month, valid flight dates, required columns, and archive integrity.
- Verify all 12 months and the expected calendar coverage in the combined LAX data.
- Recheck identifiers, outcome flags, missingness patterns, and metric consistency for each month and the combined dataset.
- Reconcile monthly counts and the combined counts. Recalculate selected measures with separate Python and SQL logic.
- Check selected totals against published BTS summaries using matching carrier coverage, flight direction, period, and denominator definitions.

The 18 shared checks passed for every month and the combined year. Seven combination checks and four comparisons with published DOT figures also passed. Matching Python and SQL calculations verifies logic on the same records; published aggregates provide an additional comparison, without establishing that each individual source record is error-free.

## Interpretation and changes

Airline comparisons will account for destination, period, and departure-time mix and will display sample sizes and uncertainty. January alone cannot support seasonal conclusions or full-year airline rankings. Historical associations do not establish causal effects or guarantee future reliability.

If later evidence requires a rule change, record the reason, affected records, and effect on the results in version control. Updated rules and analysis must stay consistent.

Source meanings follow the [BTS field definitions](https://www.transtats.bts.gov/Fields.asp?gnoyr_VQ=FGJ) and [BTS explanation of on-time performance](https://www.bts.gov/explore-topics-and-geography/topics/airline-time-performance-and-causes-flight-delays).
