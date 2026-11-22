"""Verify native Tableau checkpoints: python -m scripts.inspect_tableau_workbook."""

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


def inspect_overview(root, source, sheets, dashboard, threshold_column, records, check):
    """Check the dashboard and live summary fields in authoring checkpoint 02."""
    by_name = {sheet.get("name"): sheet for sheet in sheets}
    gap = by_name["Gap Summary"]
    shared_views = root.findall("./shared-views/shared-view")
    check("One shared threshold filter targets the common data source", len(shared_views) == 1
          and shared_views[0].get("name") == source.get("name")
          and shared_views[0].find("./datasources/datasource").get("name") == source.get("name"))
    check("Both worksheets use the shared source and threshold slice", all(
        sheet.find("./table/view/datasources/datasource").get("name") == source.get("name")
        and threshold_column in [item.text for item in sheet.findall("./table/view/slices/column")]
        and not any("Delay Threshold Minutes" in item.get("column", "")
                    for item in sheet.findall("./table/view/filter")) for sheet in sheets))
    gap_title = "".join(gap.find("./layout-options/title/formatted-text").itertext())
    check("Gap title uses the shared live threshold field", "<" + threshold_column + ">" in gap_title)
    gap_fields = ["Gap pp", "Gap Interval Lower pp", "Gap Interval Upper pp"]
    qualified = {field: f"[{source.get('name')}].[min:{field}:qk]" for field in gap_fields}
    instances = {item.get("column"): item.get("derivation")
                 for item in gap.findall("./table/view/datasource-dependencies/column-instance")}
    check("Gap and both interval fields use MIN", all(instances.get(f"[{field}]") == "Min" for field in gap_fields))
    text_fields = [item.get("column") for item in gap.findall("./table/panes/pane/encodings/text")]
    check("Summary text uses exactly the three validated gap fields", len(text_fields) == 3
          and set(text_fields) == set(qualified.values()))
    formats = {item.get("field"): item.get("value")
               for item in gap.findall("./table/style/style-rule/format[@attr='text-format']")}
    check("All three effective gap formats are two-decimal numbers", all(
        formats.get(field) == "*0.00" for field in qualified.values()))
    label_node = gap.find("./table/panes/pane/customized-label/formatted-text")
    label = "".join(run.text or "" for run in label_node.findall("./run")) if label_node is not None else ""
    check("Summary label binds all three live values and percentage-point units", all(
        "<" + field + ">" in label for field in qualified.values())
        and "percentage points" in label and "95% model-based interval" in label)
    check("Gap summary is a text mark without row or column dimensions",
          gap.find("./table/panes/pane/mark").get("class") == "Text"
          and not gap.findtext("./table/rows") and not gap.findtext("./table/cols"))
    check("Overview dashboard has the expected name", dashboard.get("name") == "LAX Reliability Overview")
    size = dashboard.find("./size")
    check("Desktop dashboard has fixed 1100-by-650 dimensions", size is not None
          and size.get("sizing-mode") == "fixed"
          and all(size.get(key) == value for key, value in {
              "maxwidth": "1100", "minwidth": "1100", "maxheight": "650", "minheight": "650"}.items()))
    zones = dashboard.findall("./zones//zone")
    views = [zone for zone in zones if zone.get("name") in by_name and zone.get("type-v2") is None]
    check("Dashboard contains both verified worksheets", len(views) == 2
          and {zone.get("name") for zone in views} == set(by_name))
    check("Overall chart and gap card share a vertical container in reading order", any(
        [zone.get("name") for zone in parent.findall("./zone") if zone.get("type-v2") is None]
        == ["Overall Reliability", "Gap Summary"]
        for parent in zones if parent.get("type-v2") == "layout-flow" and parent.get("param") == "vert"))
    controls = [zone for zone in zones if zone.get("type-v2") == "filter"]
    check("Desktop dashboard exposes one single-choice threshold control with All hidden", len(controls) == 1
          and controls[0].get("param") == threshold_column
          and controls[0].get("mode") == "radiolist" and controls[0].get("show-all") == "false")
    check("Both desktop view zones remain inside the dashboard bounds", all(
        int(zone.get("x")) >= 0 and int(zone.get("y")) >= 0
        and int(zone.get("x")) + int(zone.get("w")) <= 100000
        and int(zone.get("y")) + int(zone.get("h")) <= 100000 for zone in views))
    text_examples = []
    for row in records:
        rendered = label
        for field, token in qualified.items():
            rendered = rendered.replace("<" + token + ">", f"{row[field]:.2f}")
        rendered = rendered.replace("Æ", "").strip()
        expected_text = (f"{row['Gap pp']:.2f} percentage points\nApprox. 95% model-based interval: "
                         f"{row['Gap Interval Lower pp']:.2f} to {row['Gap Interval Upper pp']:.2f} percentage points")
        check(f"Summary field bindings resolve correctly at {row['Delay Threshold Minutes']} minutes", rendered == expected_text)
        text_examples.append({"threshold_minutes": row["Delay Threshold Minutes"], "label": rendered})
    return {"worksheets": sorted(by_name), "dashboard": dashboard.get("name"),
            "dashboard_dimensions": {"width": 1100, "height": 650},
            "effective_gap_number_format": "0.00", "gap_field_default_format":
            source.find("./column[@name='[Gap pp]']").get("default-format"),
            "label_binding_examples": text_examples,
            "layout_scope": "Desktop layout checked; auto-generated phone layout has not been visually reviewed."}


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
        if len(hyper_names) == 2:
            from scripts.inspect_tableau_destination_dashboard import inspect as inspect_destination
            return inspect_destination(workbook, expected_csv,
                                       expected_csv.parent / "destination_comparison_2025.csv")
        check("Package contains one workbook and one data extract", len(xml_names) == len(hyper_names) == 1)
        root = ET.fromstring(package.read(xml_names[0]))
        sources = root.findall("./datasources/datasource")
        sheets = root.findall("./worksheets/worksheet")
        dashboards = root.findall("./dashboards/dashboard")
        checkpoint = "02" if dashboards else "01"
        if checkpoint == "01":
            check("Checkpoint contains one overall source and worksheet", len(sources) == len(sheets) == 1)
            source, sheet = sources[0], sheets[0]
        else:
            check("Dashboard checkpoint contains one overall source and two expected worksheets", len(sources) == len(dashboards) == 1
                  and len(sheets) == 2 and {item.get("name") for item in sheets} == {"Overall Reliability", "Gap Summary"})
            source = sources[0]
            sheet = next(item for item in sheets if item.get("name") == "Overall Reliability")
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
    threshold_scope = filters if checkpoint == "01" else root.findall("./shared-views/shared-view/filter")
    threshold_filters = [item for item in threshold_scope if "Delay Threshold Minutes" in item.get("column", "")]
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
    overview = inspect_overview(root, source, sheets, dashboards[0], threshold_filters[0].get("column"), records, check) if checkpoint == "02" else {}
    check("Inspection leaves the uploaded workbook unchanged", digest(workbook) == original_hash)

    result = {"checkpoint": checkpoint, "workbook_name": workbook.name, "workbook_sha256": original_hash,
            "reference_csv": "data/tableau/overall_comparison_2025.csv", "reference_csv_sha256": digest(expected_csv),
            "tableau_version": root.get("source-build"), "hyper_api_version": importlib.metadata.version("tableauhyperapi"),
            "worksheet": sheet.get("name"), "embedded_rows": len(rows), "embedded_columns": len(columns),
            "selected_threshold": int(selected.get("member")), "colors": colors,
            "results": [{key: row[key] for key in ["Delay Threshold Minutes", *rate_fields, "Gap pp",
                        "Gap Interval Lower pp", "Gap Interval Upper pp"]} for row in records],
            "checks": checks,
            "scope": "ZIP, workbook configuration, and direct SQL on embedded data; no fresh Tableau rendering. Screenshots and threshold switching were reviewed separately during authoring."}
    result.update(overview)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=WORKBOOK)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = inspect(arguments.workbook)
    output = arguments.output or ROOT / f"reports/tableau_checkpoint_{result['checkpoint']}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checks_passed": len(result["checks"]), "rows": result["embedded_rows"],
                      "columns": result["embedded_columns"], "worksheet": result["worksheet"]}))


if __name__ == "__main__":
    main()
