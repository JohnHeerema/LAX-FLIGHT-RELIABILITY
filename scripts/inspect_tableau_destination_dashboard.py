"""Audit checkpoint 03 using saved Tableau configuration and embedded-data SQL.

This is a configuration audit for this authored workbook, not a Tableau renderer
or a general interpreter for arbitrary Tableau calculations and filter syntax.
"""

from collections import Counter
import csv
import hashlib
import importlib.metadata
import math
from pathlib import Path
import tempfile
from xml.etree import ElementTree as ET
import zipfile

from tableauhyperapi import Connection, CreateMode, HyperProcess, Telemetry


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(node):
    return "" if node is None else "".join(run.text or "" for run in node.findall("./run")).replace("Æ", "").strip()


def inspect(workbook, expected_overall_csv, expected_destination_csv):
    checks = []

    def check(description, condition):
        if not condition:
            raise ValueError(description)
        checks.append({"check": description, "passed": True})

    original_hash = digest(workbook)
    with zipfile.ZipFile(workbook) as package:
        check("Packaged workbook ZIP integrity passes", package.testzip() is None)
        names = package.namelist()
        xml_names = [name for name in names if name.lower().endswith(".twb")]
        hyper_names = [name for name in names if name.lower().endswith(".hyper")]
        check("Package contains one workbook and two data extracts", len(xml_names) == 1 and len(hyper_names) == 2)
        root = ET.fromstring(package.read(xml_names[0]))
        sources = {source.get("caption"): source for source in root.findall("./datasources/datasource")}
        check("Both expected analysis sources are present", len(sources) == 2
              and set(sources) == {"overall_comparison_2025", "destination_comparison_2025"})
        overall, destination = (sources[name] for name in ["overall_comparison_2025", "destination_comparison_2025"])
        sheets = {sheet.get("name"): sheet for sheet in root.findall("./worksheets/worksheet")}
        check("All three expected worksheets are present", len(sheets) == 3
              and set(sheets) == {"Overall Reliability", "Gap Summary", "Destination Gaps"})
        bars, gap, routes = (sheets[name] for name in ["Overall Reliability", "Gap Summary", "Destination Gaps"])
        dashboards = root.findall("./dashboards/dashboard")
        check("One named overview dashboard is present", len(dashboards) == 1
              and dashboards[0].get("name") == "LAX Reliability Overview")
        dashboard = dashboards[0]

        def field(source, name, derivation="min", kind="qk"):
            return f"[{source.get('name')}].[{derivation}:{name}:{kind}]"

        threshold = field(overall, "Delay Threshold Minutes", "none", "ok")
        destination_threshold = field(destination, "Delay Threshold Minutes", "none", "ok")
        groups, selections = [], []
        for name, sheet in sheets.items():
            filters = [item for item in sheet.findall("./table/view/filter")
                       if "Delay Threshold Minutes" in item.get("column", "")]
            check(f"{name} has exactly one threshold filter without a conflicting local filter", len(filters) == 1)
            item = filters[0]
            member, target = item.find("./groupfilter"), item.find("./target")
            wanted_target = destination_threshold if name == "Destination Gaps" else threshold
            check(f"{name} maps the shared threshold to the correct source field",
                  item.get("column") == threshold and bool(item.get("filter-group"))
                  and target is not None and target.get("field") == wanted_target)
            check(f"{name} saves one valid threshold member", member is not None
                  and member.get("function") == "member" and member.get("member") in {"15", "60"})
            groups.append(item.get("filter-group"))
            selections.append(int(member.get("member")))
            slices = [item.text for item in sheet.findall("./table/view/slices/column")]
            check(f"{name} uses the shared threshold slice", threshold in slices
                  and destination_threshold not in slices)
            title = text(sheet.find("./layout-options/title/formatted-text"))
            check(f"{name} title binds the live shared threshold", "<" + threshold + ">" in title)
            primary = sheet.find("./table/view/datasources/datasource")
            check(f"{name} uses the correct primary data source", primary is not None
                  and primary.get("name") == (destination if name == "Destination Gaps" else overall).get("name"))
        check("All three threshold filters share one group and saved selection", len(set(groups)) == len(set(selections)) == 1)
        relations = root.findall("./datasource-relationships/datasource-relationship")
        mappings = relations[0].findall("./column-mapping/map") if len(relations) == 1 else []
        check("Cross-source relationship maps only the matching threshold fields", len(relations) == 1
              and relations[0].get("source") == overall.get("name")
              and relations[0].get("target") == destination.get("name") and len(mappings) == 1
              and mappings[0].get("key") == threshold and mappings[0].get("value") == destination_threshold)

        rate_fields = ["Morning Disruption Rate", "Evening Disruption Rate"]
        check("Rate fields use MIN and two-decimal percentage formats", all(
            (column := overall.find(f"./column[@name='[{name}]']")) is not None
            and column.get("aggregation") == "Min" and column.get("default-format") == "p0.00%"
            for name in rate_fields))
        measure_filters = [item for item in bars.findall("./table/view/filter") if ":Measure Names" in item.get("column", "")]
        displayed = [item.get("member", "").strip('"') for item in measure_filters[0].findall(".//groupfilter[@function='member']")] if len(measure_filters) == 1 else []
        check("Only the two MIN disruption rates appear as bars", len(displayed) == 2
              and set(displayed) == {field(overall, name) for name in rate_fields})
        check("Rate chart uses horizontal labeled bars", ":Measure Names" in bars.findtext("./table/rows", "")
              and "Multiple Values" in bars.findtext("./table/cols", "")
              and bars.find("./table/panes/pane/mark").get("class") == "Bar"
              and bars.find(".//format[@attr='mark-labels-show']").get("value") == "true")
        axis = bars.find("./table/style/style-rule[@element='axis']/encoding[@attr='space']")
        check("Rate axis spans 0-25 percent with 5-point ticks", axis is not None
              and axis.get("range-type") == "fixed" and float(axis.get("min")) == 0
              and float(axis.get("max")) == 0.25 and float(axis.get("major-spacing")) == 0.05)
        check("Rate axis displays percentages", bars.find("./table/style/style-rule/format[@attr='text-format']").get("value") == "p0%")
        color_maps = overall.findall("./style/style-rule/encoding[@attr='color']/map")
        colors = {name: item.get("to") for name in rate_fields for item in color_maps if name in "".join(item.itertext())}
        check("Morning stays orange and evening stays blue", colors == {
            "Morning Disruption Rate": "#f28e2b", "Evening Disruption Rate": "#4e79a7"})
        order = bars.findall("./table/view/manual-sort/dictionary/bucket")
        check("Morning precedes evening", len(order) == 2 and rate_fields[0] in order[0].text and rate_fields[1] in order[1].text)

        gap_fields = ["Gap pp", "Gap Interval Lower pp", "Gap Interval Upper pp"]
        instances = {item.get("column"): item.get("derivation") for item in gap.findall("./table/view/datasource-dependencies/column-instance")}
        check("Summary gap and bounds use MIN", all(instances.get(f"[{name}]") == "Min" for name in gap_fields))
        encoded = [item.get("column") for item in gap.findall("./table/panes/pane/encodings/text")]
        check("Summary text binds exactly the gap and two bounds", len(encoded) == 3 and set(encoded) == {field(overall, name) for name in gap_fields})
        formats = {item.get("field"): item.get("value") for item in gap.findall("./table/style/style-rule/format[@attr='text-format']")}
        check("Summary values have effective two-decimal number formats", all(formats.get(field(overall, name)) == "*0.00" for name in gap_fields))
        label = text(gap.find("./table/panes/pane/customized-label/formatted-text"))
        check("Summary label uses live values and percentage-point units", all("<" + field(overall, name) + ">" in label for name in gap_fields)
              and "percentage points" in label and "95% model-based interval" in label)
        check("Summary uses a text mark with no row or column dimensions", gap.find("./table/panes/pane/mark").get("class") == "Text"
              and not gap.findtext("./table/rows") and not gap.findtext("./table/cols"))

        code_field = field(destination, "Destination Code", "none", "nk")
        code_filters = [item for item in routes.findall("./table/view/filter") if item.get("column") == code_field]
        codes = [item.get("member").strip('"') for item in code_filters[0].findall(".//groupfilter[@function='member']")] if len(code_filters) == 1 else []
        check("Destination filter selects exactly eight distinct codes", len(codes) == len(set(codes)) == 8)
        lower, point = field(destination, "Gap Interval Lower pp"), field(destination, "Gap pp")
        width_columns = destination.findall("./column[@caption='Interval Width pp']")
        check("Interval width is upper minus lower", len(width_columns) == 1
              and width_columns[0].find("./calculation").get("formula").strip() == "[Gap Interval Upper pp] - [Gap Interval Lower pp]")
        width = field(destination, width_columns[0].get("name")[1:-1])
        instances = {item.get("name"): item.get("derivation") for item in routes.findall("./table/view/datasource-dependencies/column-instance")}
        check("Destination gap, lower bound, and width use MIN", all(instances.get(token.split("].", 1)[1]) == "Min" for token in [point, lower, width]))
        check("Destination rows and columns bind codes, lower bounds, and gaps", routes.findtext("./table/rows") == code_field
              and routes.findtext("./table/cols") == f"({lower} + {point})")
        axes = routes.findall("./table/style/style-rule[@element='axis']/encoding[@attr='space']")
        check("Destination dual axes are synchronized", len(axes) == 1 and axes[0].get("field") == point
              and axes[0].get("fold") == "true" and axes[0].get("synchronized") == "true")
        check("Destination axis uses percentage-point units and automatic range", not axes[0].get("range-type")
              and routes.find("./table/style/style-rule/format[@attr='title']").get("value") == "Evening − Morning (Percentage Points)"
              and routes.find("./table/style/style-rule/format[@attr='display']").get("value") == "false")
        panes = {pane.get("x-axis-name"): pane for pane in routes.findall("./table/panes/pane") if pane.get("x-axis-name")}
        check("Two rendered layers use gap dots and lower-bound interval starts", set(panes) == {point, lower}
              and panes[point].find("./mark").get("class") == "Circle" and panes[lower].find("./mark").get("class") == "GanttBar")
        evidence = field(destination, "Direction Evidence", "none", "nk")
        check("Dots encode direction evidence and intervals encode validated width", panes[point].find("./encodings/color").get("column") == evidence
              and panes[lower].find("./encodings/size").get("column") == width and panes[lower].find("./encodings/color") is None)
        interval_color = panes[lower].find(".//format[@attr='mark-color']").get("value")
        check("Intervals are light gray with labels hidden; dot labels are shown", interval_color == "#e6e6e6"
              and panes[lower].find(".//format[@attr='mark-labels-show']").get("value") == "false"
              and panes[point].find(".//format[@attr='mark-labels-show']").get("value") == "true")
        direction_maps = destination.findall(f"./style/style-rule/encoding[@field='{evidence.split('].', 1)[1]}']/map")
        direction_colors = {"".join(item.itertext()).strip().strip('"'): item.get("to") for item in direction_maps}
        check("Direction colors distinguish higher evening rates from uncertain direction", direction_colors == {
            "Higher evening rate": "#4e79a7", "Uncertain direction": "#8a8382"})
        check("Destination gap labels use numeric percentage points", destination.find("./column[@name='[Gap pp]']").get("default-format") == "*0.00")

        zones = dashboard.findall("./zones//zone")
        views = [zone for zone in zones if zone.get("name") in sheets and zone.get("type-v2") is None]
        check("Dashboard includes all three verified worksheet zones", len(views) == 3 and {zone.get("name") for zone in views} == set(sheets))
        check("Dashboard stacks the three views in reading order", any(
            [zone.get("name") for zone in parent.findall("./zone") if zone.get("type-v2") is None]
            == ["Overall Reliability", "Gap Summary", "Destination Gaps"]
            for parent in zones if parent.get("type-v2") == "layout-flow" and parent.get("param") == "vert"))
        check("Saved desktop dashboard uses automatic sizing", dashboard.find("./size").get("sizing-mode") == "automatic")
        check("Desktop view zones are within normalized dashboard bounds", all(
            int(zone.get("x")) >= 0 and int(zone.get("y")) >= 0
            and int(zone.get("x")) + int(zone.get("w")) <= 100000
            and int(zone.get("y")) + int(zone.get("h")) <= 100000 for zone in views))
        controls = [zone for zone in zones if zone.get("type-v2") == "filter"]
        check("Dashboard has one shared single-choice threshold control with All hidden", len(controls) == 1
              and controls[0].get("param") == threshold and controls[0].get("mode") == "radiolist" and controls[0].get("show-all") == "false")
        cards = [card for card in root.findall("./windows/window/cards//card") if card.get("type") == "filter" and "Delay Threshold Minutes" in card.get("param", "")]
        check("Authoring threshold card is also single choice with All hidden", len(cards) == 1
              and cards[0].get("mode") == "radiolist" and cards[0].get("show-all") == "false")
        legends = [zone for zone in zones if zone.get("type-v2") == "color"]
        check("Visible legend describes destination direction evidence", len(legends) == 1 and legends[0].get("param") == evidence)
        footers = [zone for zone in zones if zone.get("type-v2") == "text"]
        footer = text(footers[0].find("./formatted-text")) if len(footers) == 1 else ""
        check("Footer names the source, scope, coverage, limits, and methods link", all(part in footer for part in [
            "U.S. DOT/BTS Reporting Carrier On-Time Performance", "Domestic LAX departures, 2025", "57,464",
            "64.2%", "selected departure windows", "do not establish causal effects or predict future flights",
            "https://github.com/JohnHeerema/LAX-FLIGHT-RELIABILITY"]))
        check("Footer appears below the destination chart", len(footers) == 1
              and int(footers[0].get("y")) >= max(int(zone.get("y")) + int(zone.get("h")) for zone in views))

        datasets, sql_examples = {}, []
        specifications = [(overall, expected_overall_csv, 2, 19), (destination, expected_destination_csv, 92, 22)]
        with tempfile.TemporaryDirectory(prefix="lax-tableau-dashboard-") as directory:
            with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU, parameters={"log_config": "", "use_tcp_port": "auto"}) as hyper:
                for index, (source, reference_path, count, column_count) in enumerate(specifications):
                    caption = source.get("caption")
                    extract = source.find("./extract")
                    check(f"{caption} uses an enabled packaged extract", extract is not None and extract.get("enabled") == "true"
                          and extract.find("./connection").get("dbname") in hyper_names)
                    local = Path(directory) / f"extract_{index}.hyper"
                    local.write_bytes(package.read(extract.find("./connection").get("dbname")))
                    with reference_path.open(newline="", encoding="utf-8") as stream:
                        reader = csv.DictReader(stream)
                        expected_columns, expected_rows = reader.fieldnames, list(reader)
                    with Connection(hyper.endpoint, str(local), CreateMode.NONE) as connection:
                        tables = connection.catalog.get_table_names("Extract")
                        check(f"{caption} contains one analysis table", len(tables) == 1)
                        table = tables[0]
                        columns = [column.name.unescaped for column in connection.catalog.get_table_definition(table).columns]
                        records = [dict(zip(columns, row)) for row in connection.execute_list_query("SELECT * FROM " + str(table))]
                        check(f"{caption} schema matches all {column_count} validated CSV fields", columns == expected_columns and len(columns) == column_count)
                        key_fields = ["Delay Threshold Minutes"] + (["Destination Code"] if index else [])

                        def key(row):
                            return tuple(str(row[name]) for name in key_fields)

                        expected = {key(row): row for row in expected_rows}
                        check(f"{caption} contains exactly {count} unique expected rows", len(records) == len(expected_rows) == len(expected) == count
                              and len({key(row) for row in records}) == count and {key(row) for row in records} == set(expected))
                        for row in records:
                            for name, actual in row.items():
                                wanted = expected[key(row)][name]
                                if actual is None:
                                    matches = wanted == ""
                                elif isinstance(actual, bool):
                                    matches = wanted.lower() == str(actual).lower()
                                elif isinstance(actual, (int, float)):
                                    matches = math.isclose(actual, float(wanted), abs_tol=1e-12, rel_tol=0)
                                else:
                                    matches = actual == wanted
                                if not matches:
                                    raise ValueError(f"Extract differs from validated CSV: {caption}, {name}, {key(row)}")
                        check(f"{caption}: every embedded value matches its CSV (absolute numeric tolerance 1e-12)", True)
                        datasets[caption] = {"rows": records, "columns": columns, "sha256": digest(reference_path)}
                        if index:
                            literals = ", ".join("'" + code.replace("'", "''") + "'" for code in sorted(codes))
                            for threshold_value in [15, 60]:
                                result = connection.execute_list_query('SELECT "Destination Code", "Gap pp", "Gap Interval Lower pp", '
                                    '"Gap Interval Upper pp", "Gap Interval Upper pp" - "Gap Interval Lower pp", "Direction Evidence" FROM '
                                    + str(table) + f' WHERE "Delay Threshold Minutes" = {threshold_value} AND "Destination Code" IN ({literals}) ORDER BY "Destination Code"')
                                check(f"Embedded SQL returns eight complete dots and ranges at {threshold_value} minutes", len(result) == 8
                                      and all(row[2] is not None and row[3] is not None and row[2] <= row[1] <= row[3]
                                              and row[4] > 0 and math.isclose(row[2] + row[4], row[3], abs_tol=1e-12, rel_tol=0) for row in result))
                                sql_examples.append({"threshold_minutes": threshold_value, "direction_counts": dict(sorted(Counter(row[5] for row in result).items())),
                                    "destinations": [dict(zip(["code", "gap_pp", "lower_pp", "upper_pp", "width_pp", "direction_evidence"], row)) for row in result]})

    overall_rows = sorted(datasets["overall_comparison_2025"]["rows"], key=lambda row: row["Delay Threshold Minutes"])
    destination_rows = datasets["destination_comparison_2025"]["rows"]
    labels = []
    for row in overall_rows:
        rendered = label
        for name in gap_fields:
            rendered = rendered.replace("<" + field(overall, name) + ">", f"{row[name]:.2f}")
        expected_text = (f"{row['Gap pp']:.2f} percentage points\nApprox. 95% model-based interval: "
                         f"{row['Gap Interval Lower pp']:.2f} to {row['Gap Interval Upper pp']:.2f} percentage points")
        check(f"Summary label bindings resolve correctly at {row['Delay Threshold Minutes']} minutes", rendered == expected_text)
        labels.append({"threshold_minutes": row["Delay Threshold Minutes"], "label": rendered})
    for value in [15, 60]:
        ranked = sorted([row for row in destination_rows if row["Delay Threshold Minutes"] == value],
                        key=lambda row: (-(row["Morning Flights"] + row["Evening Flights"]), row["Destination Code"]))
        check(f"Displayed destinations are the eight largest matched-flight counts at {value} minutes", set(codes) == {row["Destination Code"] for row in ranked[:8]})
    visible = [row for row in destination_rows if row["Destination Code"] in codes]
    check("All 16 displayed comparisons have supported coverage and 62-comparison family intervals", all(row["Coverage Supported"] and row["Route Family Size"] == 62 for row in visible))
    check("Destination direction labels agree with the adjusted interval signs", all(
        row["Direction Evidence"] == ("Higher evening rate" if row["Gap Interval Lower pp"] > 0 else "Higher morning rate" if row["Gap Interval Upper pp"] < 0 else "Uncertain direction") for row in visible))
    check("Inspection leaves the uploaded workbook unchanged", digest(workbook) == original_hash)
    return {"checkpoint": "03", "workbook_name": workbook.name, "workbook_sha256": original_hash,
            "tableau_version": root.get("source-build"), "hyper_api_version": importlib.metadata.version("tableauhyperapi"),
            "worksheet": "Overall Reliability", "worksheets": sorted(sheets), "dashboard": dashboard.get("name"),
            "dashboard_sizing": "automatic", "selected_threshold": selections[0], "embedded_rows": 94,
            "embedded_columns": {name: len(data["columns"]) for name, data in datasets.items()}, "embedded_values_compared": 2062,
            "reference_csvs": [{"path": "data/tableau/" + name + ".csv", "sha256": data["sha256"], "rows": len(data["rows"]), "columns": len(data["columns"])} for name, data in datasets.items()],
            "colors": colors, "direction_colors": direction_colors, "interval_color": interval_color,
            "effective_gap_number_format": "0.00", "gap_field_default_format": overall.find("./column[@name='[Gap pp]']").get("default-format"),
            "results": [{name: row[name] for name in ["Delay Threshold Minutes", *rate_fields, *gap_fields]} for row in overall_rows],
            "label_binding_examples": labels, "destination_sql_examples": sql_examples, "footer": footer, "checks": checks,
            "scope": "ZIP, saved workbook configuration, field bindings, and direct SQL on both embedded extracts; no fresh Tableau rendering or automated UI switching. Author screenshots at both thresholds were reviewed separately.",
            "layout_scope": "Automatic desktop sizing and saved zone geometry checked. Arbitrary viewport sizes and the auto-generated phone layout have not received visual review."}
