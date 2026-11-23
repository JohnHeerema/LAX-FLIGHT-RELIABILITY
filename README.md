# LAX Flight Reliability

**A data analysis portfolio project by John Heerema · Python, SQL, and Tableau**

[Explore the interactive dashboard](https://public.tableau.com/app/profile/john.heerema/viz/LAXFlightReliabilityMorningvs_Evening2025/LAXReliabilityOverview?publish=yes) · [Read the analysis](reports/morning_evening.md) · [Download the final Tableau workbook](tableau/LAX_Flight_Reliability_Final.twbx)

**On this branch:** an [unpublished dashboard redesign candidate](docs/dashboard_redesign.md), with an editable workbook, previews for both cutoffs, and 48 configuration checks. Its native Tableau rendering still needs to be checked; the public link above remains the existing version.

An analysis of **190,472 reported domestic LAX departures in 2025**, asking whether morning and evening flights had different disruption rates after comparing the same airline, destination, and month mix. The result is a published Tableau dashboard backed by reproducible analysis and documented checks.

## Main findings

**Evening departures had higher disruption rates in the matched historical comparison.**

| Arrival-delay threshold | Morning | Evening | Evening minus morning | Approx. 95% model-based interval for the gap |
| --- | ---: | ---: | ---: | --- |
| 15 minutes — primary analysis | 11.99% | 21.36% | **9.37 percentage points** | 8.34–10.39 percentage points |
| 60 minutes — exploratory follow-up | 4.42% | 8.01% | **3.59 percentage points** | 2.96–4.23 percentage points |

Both definitions also count cancellations and diversions as disruptions. Both use the same **57,464 matched scheduled flights**, covering **64.2% of flights in the selected departure windows**.

At the 15-minute threshold, the gap corresponds to approximately **9 additional disruptions per 100 comparable evening departures relative to morning departures**. Positive gaps also appeared in all 12 descriptive monthly comparisons. These are historical associations; the project does not establish a causal departure-time effect or forecast future flights.

![Common-mix disruption rates and monthly gaps](reports/figures/morning_evening.svg)

## Question and approach

**Were morning departures more reliable after accounting for the airline, destination, and month mix?**

Different flight mixes can affect a simple morning-versus-evening average. This project makes the comparison within supported groups and applies the same mix to both windows:

1. **Define the windows:** scheduled departures at 06:00–09:59 and 17:00–20:59, in LAX local time.
2. **Retain comparable groups:** the same reporting operating-carrier DOT ID, destination airport ID, and month, with at least 10 scheduled flights in each window. The primary comparison retains 706 groups.
3. **Standardize the mix:** calculate rates within each group, then weight both windows by the group's combined scheduled flight count.
4. **Assess uncertainty and robustness:** use approximate weekly-cluster intervals, examine predeclared sensitivity checks, and extend to the 60-minute definition and destination comparisons.

The [primary plan](docs/morning_evening_plan.md) was committed before calculating its outcome comparisons. The destination/severity follow-up is exploratory; its [separate plan](docs/route_severity_plan.md) was committed before estimating the extension results. Destination intervals account for 62 supported destination/threshold comparisons.

The dashboard shows overall rates, the gap and its interval, and eight destinations selected by matched flight count. It supports a historical reliability review for travelers and operations planners.

## Skills demonstrated

| Area | Evidence in the project |
| --- | --- |
| Python and data quality | Chunked ingestion of official monthly files; checks for schema, dates, duplicate identifiers, outcome flags, and missing values. [Dataset validation](reports/year_2025.md) |
| SQL verification | Separate queries reconstruct time windows, outcomes, matched cohorts, and weighted point estimates. [SQL queries](sql) |
| Statistical comparison | Common-mix standardization, weekly-cluster uncertainty, sensitivity checks, and adjusted destination intervals. [Analysis](reports/morning_evening.md) |
| Tableau | Separate source grains, a shared 15/60-minute filter, live field inserts, correct percentage-point units, and synchronized dot/interval views. [Data guide](docs/tableau_data_guide.md) |
| Reproducibility | Pinned dependencies, source manifests and checksums, frozen analysis plans, tests, and packaged-workbook audits. [Reproduction guide](docs/reproduce.md) |

## Validation and deliverables

- **Source data:** all 12 months and the full year pass the recorded data checks; four calculations match published DOT benchmarks. [Validation report](reports/year_2025.md)
- **Analysis:** independent SQL point estimates agree with Python within an absolute tolerance of 1e-12. [Primary checks](reports/morning_evening.md#checks-supporting-this-result) · [Extension checks](reports/route_severity.md#checks-and-provenance)
- **Tableau archive:** all 2,062 embedded values match the validated CSVs; the final archive passes 82 data/configuration checks. The final validation records 61 passing project tests. [Final audit](reports/tableau_final.md)
- **Published interface:** both threshold states, displayed results, dynamic titles, colors, and notes were checked in a signed-out desktop browser. [Desktop review](reports/tableau_public_review.md)

The [Tableau-ready CSVs and dictionary](data/tableau), [full destination/severity report](reports/route_severity.md), and [earlier workbook checkpoints](tableau/checkpoints) are included for further inspection.

## Reproduce

Use Python 3.12. From the repository root, check the packaged data and run the tests without downloading the raw flight archives:

```bash
python -m pip install -r requirements.txt -r requirements-tableau.txt
python -m unittest discover -s tests -v
python -m scripts.inspect_tableau_workbook --workbook tableau/LAX_Flight_Reliability_Final.twbx
```

The [full reproduction guide](docs/reproduce.md) covers environment setup, the BTS download/build, primary analysis, Tableau-source exports, and offline repetition. Raw archives and the full flight-level extract remain outside Git; manifests preserve their provenance.

## Source and limits

Source: [U.S. DOT/BTS Reporting Carrier On-Time Performance](https://www.transtats.bts.gov/TableInfo.asp?QO_fu146_anzr=b0-gvzr&gnoyr_VQ=FGJ), January–December 2025, reported domestic flights scheduled to depart LAX.

The matched result covers supported comparisons within the selected windows. Other flights and routes may differ, and unmeasured factors can still affect the association. The intervals describe conditional model-based operational variability; they are not future-flight prediction intervals. The desktop dashboard was reviewed; mobile layouts and full accessibility compliance remain outside that review.

## Authorship and AI assistance

Created by **John Heerema** with AI assistance for code drafting, debugging, analysis ideas, and explanations. Published findings trace to source data, executed Python/SQL checks, and documented limitations.

Project code uses the [MIT License](LICENSE). BTS remains the source of the flight data.
