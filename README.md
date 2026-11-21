# LAX Flight Reliability

**A data analysis project by John Heerema**

For a given destination, how does flight reliability vary by airline, departure time, and season—and which patterns are dependable enough to inform planning?

**Status:** The full-year 2025 dataset is built and validated. Comparative analysis and the dashboard are the next stage.

**Dataset checkpoint:** [190,472 LAX departures across all 365 days](reports/year_2025.md), with 12 reporting airline codes and 105 destination airports. Every month and the combined year pass the record checks. Four comparisons match published DOT figures, including national annual totals and December LAX departures.

**First checkpoint:** Read the [January pilot inspection](reports/pilot_2025_01.md) and explore [12 example flight records](data/samples/lax_2025_01_examples.csv). The pilot preserves cancellations and diversions and checks Python calculations against SQL. These are one-month observations; full-year recommendations will follow validated analysis.

**Data rules:** [How records, missing values, and metric denominators will be handled](docs/data_handling.md). These rules were documented before downloading the remaining months.

## Purpose

Help travelers and operations planners understand historical disruption risk when comparing flights from Los Angeles International Airport (LAX).

The project connects logistics planning with data analysis: define a useful question, check the evidence, compare realistic options, and explain the tradeoffs.

## Data and scope

| Item | Planned scope |
| --- | --- |
| Source | U.S. Department of Transportation, Bureau of Transportation Statistics (BTS) |
| Dataset | Reporting Carrier On-Time Performance (1987–present) |
| Period | January 1–December 31, 2025 |
| Flights | Reported nonstop domestic flights scheduled to depart LAX |
| Unit of analysis | One reported scheduled flight occurrence, including cancellations and diversions |
| Comparisons | Destination, reporting airline, scheduled departure time, and month |

BTS reporting coverage determines which carriers and flights appear. This analysis describes the selected dataset; it does not cover international flights or every airline.

Source documentation:

- [Dataset overview](https://www.transtats.bts.gov/TableInfo.asp?QO_fu146_anzr=b0-gvzr&gnoyr_VQ=FGJ)
- [Field definitions](https://www.transtats.bts.gov/Fields.asp?gnoyr_VQ=FGJ)
- [BTS explanation of on-time performance](https://www.bts.gov/explore-topics-and-geography/topics/airline-time-performance-and-causes-flight-delays)

## Planned measures

| Measure | Definition |
| --- | --- |
| Flight count | Number of reported scheduled flights in the selected group |
| Cancellation rate | Canceled flights divided by all reported scheduled flights in that group |
| Diversion rate | Diverted flights divided by all reported scheduled flights in that group |
| Arrival delay rate | Flights arriving at least 15 minutes late divided by completed, nondiverted flights with a recorded arrival delay |
| 90th percentile arrival delay | A measure of longer delays: the value at or below which 90% of eligible arrival-delay observations fall; early arrivals count as zero minutes late |

Arrival-delay measures exclude canceled and diverted flights. Their rates will be shown alongside arrival delays, and missing arrival records will be reported separately. Each result will state its sample size and denominator.

These definitions have been checked on each month and on the full-year dataset. Any later changes will be documented before interpreting comparisons.

## How results will be validated

- Check the downloaded months, date range, LAX filter, required columns, and possible duplicate flight records.
- Inspect missing values and investigate unusual records before deciding how to handle them.
- Keep cancellations and diversions visible rather than replacing missing arrival times with zero.
- Compare airlines serving the same destination and comparable periods; examine differences in departure-time mix.
- Show flight counts and uncertainty so small samples do not dominate rankings.
- Check whether patterns persist across months. If a predictive model is added, evaluate it on later dates kept separate from model development.
- Reconcile selected results with BTS summaries using matching coverage and metric definitions, and explain any differences.
- Preserve source references, download dates, and runnable analysis so results can be reproduced.

Historical patterns describe associations. They do not establish that changing an airline or departure time causes an improvement, and they do not guarantee future flight performance.

## Roadmap

- [x] Create the repository and define the project.
- [x] Download one month as a pilot and inspect the records.
- [x] Document data-handling rules before extending to the full year.
- [x] Build and validate the full-year LAX dataset.
- [ ] Analyze reliability and investigate competing explanations.
- [ ] Build an interactive dashboard and a concise findings report.
- [ ] Add reproduction instructions and complete the final review.

## Planned deliverables

- Documented Python and SQL analysis.
- A data dictionary and a report of data-quality checks.
- An interactive dashboard for comparing historical reliability.
- A short report with supported recommendations and limitations.
- Instructions for reproducing the published results.

## Run the January pilot

Use Python 3.12. From a local copy of this repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/inspect_pilot.py
```

The activation command above is for macOS/Linux. On Windows, activate the environment with `.venv\Scripts\activate`.

The script downloads the original 27 MB BTS ZIP, reads the national CSV in chunks, retains LAX departures, and writes a local extract to `data/interim/`. It regenerates the pilot report, JSON profile, and illustrative records. Original archives and full extracts stay outside Git; the [source manifest](data/manifests/pilot_2025_01.json) records the download and checksum.

After the first download, repeat the inspection without network access:

```bash
python scripts/inspect_pilot.py --offline
```

Run the focused calendar, filtering, denominator, source-integrity, and reference-matching tests:

```bash
python -m unittest discover -s tests -v
```

## Build the full-year dataset

With the same environment and requirements, run from the repository root:

```bash
python -m scripts.build_year
```

The first run downloads about 355 MB of official monthly ZIPs. The files are read in chunks, and the combined LAX extract is saved locally as `data/interim/lax_2025.csv`. Source checksums, timestamps, and the extract checksum are recorded in the [year manifest](data/manifests/year_2025.json).

To reproduce the build from cached archives:

```bash
python -m scripts.build_year --offline
```

The command regenerates the [validation report](reports/year_2025.md), [JSON audit](reports/year_2025.json), [monthly summary](data/summary/2025_monthly.csv), and [carrier exposure table](data/summary/2025_carrier_month_counts.csv). A [standalone SQL query](sql/monthly_validation.sql) cross-checks monthly counts, and [documented DOT benchmarks](data/reference/dot_2025_benchmarks.json) provide checks against published totals. A failed data or reconciliation check stops the build before published outputs are replaced.

## AI assistance

AI assists with code drafting, debugging, analysis ideas, and explanations. Every published finding must trace to source data, executed code, and documented checks. Methods and conclusions will be reviewed as the project develops.

## License

Project code is available under the [MIT License](LICENSE). BTS remains the source of the flight data; this project does not relicense the source data.
