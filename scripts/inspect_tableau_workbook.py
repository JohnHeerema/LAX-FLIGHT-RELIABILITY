"""Verify the first Tableau checkpoint: python -m scripts.inspect_tableau_workbook."""

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import tempfile
from xml.etree import ElementTree as ET
import zipfile

from tableauhyperapi import Connection, CreateMode, HyperProcess, Telemetry


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "tableau/checkpoints/LAX_Flight_Reliability_Checkpoint_01.twbx"
SOURCE = ROOT / "data/tableau/overall_comparison_2025.csv"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(workbook=WORKBOOK, expected_csv=SOURCE):
    """Read a temporary extract copy; leave the supplied workbook unchanged."""
    checks = []

    def check(description, condition):
        if not condition:
            raise ValueError(description)
        checks.append({"check": description, "passed": True})

    original_hash = digest(workbook)
    with expected_csv.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        expected_columns = reader.fieldnames
        expected_rows = list(reader)
    with zipfile.ZipFile(workbook) as package:
        check("Packaged workbook ZIP integrity passes", package.testzip() is None)
        names = package.namelist()
        xml_names = [name for name in names if name.lower().endswith(".twb")]
        hyper_names = [name for name in names if name.lower().endswith(".hyper")]
        check("Package contains one workbook and one data extract", len(xml_names) == len(hyper_names) == 1)
        root = ET.fromstring(package.read(xml_names[0]))
        sources = root.findall("./datasources/datasource")
        sheets = root.findall("./worksheets/worksheet")
        check("Checkpoint contains one overall source and worksheet", len(sources) == len(sheets) == 1)
        source, sheet = sources[0], sheets[0]
        extract = source.find("./extract")
        check("Active data extract is included inside the package", extract is not None
              and extract.get("enabled") == "true"
              and extract.find("./connection").get("dbname") == hyper_names[0])
        with tempfile.TemporaryDirectory(prefix="lax-tableau-check-") as directory:
            local_extract = Path(directory) / "checkpoint.hyper"
            local_extract.write_bytes(package.read(hyper_names[0]))
            with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
                              parameters={"log_config": "", "use_tcp_port": "auto"}) as hyper:
                with Connection(hyper.endpoint, str(local_extract), CreateMode.NONE) as connection:
                    tables = connection.catalog.get_table_names("Extract")
                    check("Extract contains one analysis table", len(tables) == 1)
                    table = tables[0]
                    columns = [column.name.unescaped for column in connection.catalog.get_table_definition(table).columns]
                    rows = connection.execute_list_query('SELECT * FROM ' + str(table) + ' ORDER BY "Delay Threshold Minutes"')

    check("All 19 extract fields match the validated CSV schema", columns == expected_columns and len(columns) == 19)
    records = [dict(zip(columns, row)) for row in rows]
    check("Extract contains exactly the 15- and 60-minute rows", len(records) == 2
          and [row["Delay Threshold Minutes"] for row in records] == [15, 60])
    expected = {int(row["Delay Threshold Minutes"]): row for row in expected_rows}
    check("Reference CSV contains exactly one row per threshold", len(expected_rows) == len(expected) == 2
          and set(expected) == {15, 60})
    for row in records:
        reference = expected[row["Delay Threshold Minutes"]]
        for field, actual in row.items():
            wanted = reference[field]
            matches = (math.isclose(actual, float(wanted), abs_tol=1e-12, rel_tol=0)
                       if isinstance(actual, (int, float)) else actual == wanted)
            if not matches:
                raise ValueError(f"Extract differs from validated CSV: {field} at {row['Delay Threshold Minutes']} minutes")
    check("Every extracted value agrees with the validated CSV (absolute numeric tolerance 1e-12)", True)

    threshold = source.find("./column[@name='[Delay Threshold Minutes]']")
    check("Threshold is a dimension", threshold is not None and threshold.get("role") == "dimension")
    filters = sheet.findall("./table/view/filter")
    threshold_filters = [item for item in filters if "Delay Threshold Minutes" in item.get("column", "")]
    check("One threshold filter is present", len(threshold_filters) == 1)
    selected = threshold_filters[0].find("./groupfilter")
    check("Saved filter selects one valid threshold", selected is not None and selected.get("function") == "member"
          and selected.get("member") in {"15", "60"})
    cards = [card for card in root.findall("./windows/window/cards//card")
             if card.get("type") == "filter" and "Delay Threshold Minutes" in card.get("param", "")]
    check("Threshold control is single choice with All hidden", len(cards) == 1
          and cards[0].get("mode") in {"radiolist", "singledropdown"} and cards[0].get("show-all") == "false")
    title = "".join(sheet.find("./layout-options/title/formatted-text").itertext())
    check("Title uses the live threshold field", "<" + threshold_filters[0].get("column") + ">" in title)

    rate_fields = ["Morning Disruption Rate", "Evening Disruption Rate"]
    for field in rate_fields:
        column = source.find(f"./column[@name='[{field}]']")
        check(f"{field} defaults to MIN and two-decimal percentage formatting",
              column is not None and column.get("aggregation") == "Min" and column.get("default-format") == "p0.00%")
    measure_filter = next(item for item in filters if ":Measure Names" in item.get("column", ""))
    displayed = [item.get("member", "") for item in measure_filter.findall(".//groupfilter[@function='member']")]
    check("Only the two MIN disruption rates appear as bars", len(displayed) == 2
          and all(any("[min:" + field + ":qk]" in item for item in displayed) for field in rate_fields))
    check("View uses horizontal bars with visible labels", ":Measure Names" in sheet.findtext("./table/rows", "")
          and "Multiple Values" in sheet.findtext("./table/cols", "")
          and sheet.find("./table/panes/pane/mark").get("class") == "Bar"
          and any(item.get("value") == "true" for item in sheet.findall(".//format[@attr='mark-labels-show']")))
    axis = sheet.find("./table/style/style-rule[@element='axis']/encoding[@attr='space']")
    check("Axis is fixed at 0-25 percent with 5-point ticks", axis is not None
          and axis.get("range-type") == "fixed" and float(axis.get("min")) == 0
          and float(axis.get("max")) == 0.25 and float(axis.get("major-spacing")) == 0.05)
    check("Numeric axis displays percentages", any(item.get("value") == "p0%"
          for item in sheet.findall("./table/style/style-rule/format[@attr='text-format']")))
    color_maps = source.findall("./style/style-rule/encoding[@attr='color']/map")
    colors = {field: item.get("to") for field in rate_fields for item in color_maps
              if field in "".join(item.itertext())}
    check("Colors preserve morning orange and evening blue", colors == {
        "Morning Disruption Rate": "#f28e2b", "Evening Disruption Rate": "#4e79a7"})
    order = sheet.findall("./table/view/manual-sort/dictionary/bucket")
    check("Morning precedes evening", len(order) == 2 and "Morning Disruption Rate" in order[0].text
          and "Evening Disruption Rate" in order[1].text)
    check("Inspection leaves the uploaded workbook unchanged", digest(workbook) == original_hash)

    return {"checkpoint": "01", "workbook_name": workbook.name, "workbook_sha256": original_hash,
            "reference_csv": "data/tableau/overall_comparison_2025.csv", "reference_csv_sha256": digest(expected_csv),
            "tableau_version": root.get("source-build"), "hyper_api_version": importlib.metadata.version("tableauhyperapi"),
            "worksheet": sheet.get("name"), "embedded_rows": len(rows), "embedded_columns": len(columns),
            "selected_threshold": int(selected.get("member")), "colors": colors,
            "results": [{key: row[key] for key in ["Delay Threshold Minutes", *rate_fields, "Gap pp",
                        "Gap Interval Lower pp", "Gap Interval Upper pp"]} for row in records],
            "checks": checks,
            "scope": "ZIP, workbook configuration, and direct SQL on embedded data; no fresh Tableau rendering. Screenshots and threshold switching were reviewed separately during authoring."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=WORKBOOK)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/tableau_checkpoint_01.json")
    arguments = parser.parse_args()
    result = inspect(arguments.workbook)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checks_passed": len(result["checks"]), "rows": result["embedded_rows"],
                      "columns": result["embedded_columns"], "worksheet": result["worksheet"]}))


if __name__ == "__main__":
    main()
