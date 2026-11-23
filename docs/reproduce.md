# Reproduce the LAX Flight Reliability project

Use **Python 3.12** and run the commands from the repository root. The final workbook and compact exports are included in Git. Raw BTS archives and the full LAX extract are stored locally outside Git.

## Set up the environment

```bash
git clone https://github.com/JohnHeerema/LAX-FLIGHT-RELIABILITY.git
cd LAX-FLIGHT-RELIABILITY
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-tableau.txt
```

The activation command is for macOS/Linux. On Windows, use `.venv\Scripts\activate`. The optional `requirements-tableau.txt` installs the pinned official Tableau Hyper API needed for native workbook inspection.

## Choose a reproduction scope

- **Check the published archive:** Run the native-workbook inspection and tests below. This reads the packaged summary extracts and does not download the raw flight archives.
- **Rebuild the analysis:** Build the full-year extract, run the primary comparison, then run the destination/severity extension. The first build downloads about 355 MB of official monthly ZIPs. Cached archives support offline repetition.

## Inspect the native Tableau checkpoint

The [final three-view workbook](../tableau/LAX_Flight_Reliability_Final.twbx) contains the overall comparison, a live gap/interval card, and destination gaps with adjusted intervals. Its [audit](../reports/tableau_final.md) verifies both embedded datasets, cross-source filter mapping, live values, interval geometry, units, colors, the Arial title setting, interpretation note, and saved desktop layout. All **2,062 embedded values** agree with the validated CSVs. The earlier [single-worksheet](../reports/tableau_checkpoint_01.md), [two-view overview](../reports/tableau_checkpoint_02.md), and [three-view authoring](../reports/tableau_checkpoint_03.md) checkpoints remain available.

To repeat the latest inspection without downloading the raw flight archives:

```bash
python -m pip install -r requirements-tableau.txt
python -m scripts.inspect_tableau_workbook --workbook tableau/LAX_Flight_Reliability_Final.twbx
python -m unittest discover -s tests -p test_tableau_checkpoint.py -v
```

The command regenerates the [final JSON audit](../reports/tableau_final.json). The final filename selects the final-presentation checks automatically; use `--final` to enforce those checks on a renamed copy. Inspection queries temporary copies of the embedded extracts and leaves the packaged workbook unchanged. The [public desktop review](../reports/tableau_public_review.md) separately exercised live switching at both thresholds. The native desktop dashboard uses automatic sizing. Other viewport sizes and the auto-generated phone layout still need visual review.

Regression checks include the authoring bug where a shared 15-minute selection conflicted with a local 60-minute filter and removed the destination marks. The current workbook uses one shared threshold group mapped across the two sources, with no competing local threshold filter. Earlier checkpoints can be inspected by passing their paths to the same command.

## Build the full-year dataset

With the same environment and requirements, run from the repository root:

```bash
python -m scripts.build_year
```

The first run downloads about 355 MB of official monthly ZIPs. The files are read in chunks, and the combined LAX extract is saved locally as `data/interim/lax_2025.csv`. Source checksums, timestamps, and the extract checksum are recorded in the [year manifest](../data/manifests/year_2025.json).

To reproduce the build from cached archives:

```bash
python -m scripts.build_year --offline
```

The command regenerates the [validation report](../reports/year_2025.md), [JSON audit](../reports/year_2025.json), [monthly summary](../data/summary/2025_monthly.csv), and [carrier exposure table](../data/summary/2025_carrier_month_counts.csv). A [standalone SQL query](../sql/monthly_validation.sql) cross-checks monthly counts, and [documented DOT benchmarks](../data/reference/dot_2025_benchmarks.json) provide checks against published totals. A failed data or reconciliation check stops the build before published outputs are replaced.

## Reproduce the first comparison

After building the validated year extract, update the pinned requirements and run:

```bash
python -m pip install -r requirements.txt
python -m scripts.compare_departure_windows
python -m unittest discover -s tests -v
```

The analysis verifies the input checksum, applies the precommitted protocol, checks Python's primary result with separate SQL, and regenerates the [report](../reports/morning_evening.md), [JSON audit](../reports/morning_evening.json), [matched group table](../data/summary/morning_evening_pairs.csv), [monthly results](../data/summary/morning_evening_monthly.csv), [sensitivity results](../data/summary/morning_evening_sensitivity.csv), and standalone SVG figure.

## Prepare the Tableau sources

The [destination/severity follow-up](../reports/route_severity.md) compares the 15- and 60-minute definitions on the same matched flights and labels destination coverage and uncertainty. Its [plan](route_severity_plan.md) was committed before the extension estimates.

```bash
python -m scripts.route_severity
```

The command regenerates the [overall](../data/tableau/overall_comparison_2025.csv), [destination](../data/tableau/destination_comparison_2025.csv), and [pair-level](../data/tableau/comparison_pairs_2025.csv) CSVs, their [dictionary](../data/tableau/data_dictionary.csv), a [checksum manifest](../data/manifests/tableau_sources_2025.json), and the [follow-up audit](../reports/route_severity.json). The [Tableau guide](tableau_data_guide.md) starts with one small connection and documents the correct aggregation rules.

## Optional: reproduce the January pilot

With the environment above active, run:

```bash
python scripts/inspect_pilot.py
```

The script downloads the original 27 MB BTS ZIP, reads the national CSV in chunks, retains LAX departures, and writes a local extract to `data/interim/`. It regenerates the pilot report, JSON profile, and illustrative records. Original archives and full extracts stay outside Git; the [source manifest](../data/manifests/pilot_2025_01.json) records the download and checksum.

After the first download, repeat the inspection without network access:

```bash
python scripts/inspect_pilot.py --offline
```

Run the focused calendar, filtering, denominator, source-integrity, and reference-matching tests:

```bash
python -m unittest discover -s tests -v
```
