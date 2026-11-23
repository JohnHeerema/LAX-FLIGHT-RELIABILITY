"""Create a presentation-only Tableau redesign from the verified final archive.

The embedded extracts, comparison filters, and analysis calculations are kept.
This edits the native XML; opening/rendering in Tableau is a separate check.
"""

from copy import deepcopy
import csv
import hashlib
from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET

ET.register_namespace("user", "http://www.tableausoftware.com/xml/user")


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tableau/LAX_Flight_Reliability_Final.twbx"
OUTPUT = ROOT / "tableau/LAX_Flight_Reliability_Redesigned.twbx"
WIDTH, HEIGHT = 1200, 900
NAVY, MUTED, BLUE = "#183247", "#566779", "#4e79a7"
NOTE = ("Positive = higher evening disruption rate.  0 = no estimated gap.  Negative = higher morning rate.\n"
        "Blue dots: interval above zero.  Gray dots: interval includes zero, so direction is uncertain.")


def run(parent, value, size=11, color=NAVY, bold=False):
    attributes = {"fontname": "Arial", "fontsize": str(size), "fontcolor": color, "fontalignment": "0"}
    if bold:
        attributes["bold"] = "true"
    ET.SubElement(parent, "run", attributes).text = value


def formatted(parent, entries):
    node = parent.find("./formatted-text")
    if node is not None:
        parent.remove(node)
    node = ET.SubElement(parent, "formatted-text")
    for value, size, color, bold in entries:
        run(node, value, size, color, bold)
    return node


def style(parent, element, attr, value, **attributes):
    rule = parent.find(f"./style-rule[@element='{element}']")
    if rule is None:
        rule = ET.SubElement(parent, "style-rule", element=element)
    item = next((x for x in rule.findall("./format") if x.get("attr") == attr
                 and all(x.get(k) == v for k, v in attributes.items())), None)
    if item is None:
        item = ET.SubElement(rule, "format", attr=attr, **attributes)
    item.set("value", str(value))


def make():
    with zipfile.ZipFile(SOURCE) as package:
        source_name = next(n for n in package.namelist() if n.endswith(".twb"))
        root = ET.fromstring(package.read(source_name))
        sources = {x.get("caption"): x for x in root.findall("./datasources/datasource")}
        overall, destination = sources["overall_comparison_2025"], sources["destination_comparison_2025"]
        sheets = {x.get("name"): x for x in root.findall("./worksheets/worksheet")}
        bars, gap, routes = (sheets[n] for n in ["Overall Reliability", "Gap Summary", "Destination Gaps"])

        def field(source, name, derivation="min", kind="qk"):
            return f"[{source.get('name')}].[{derivation}:{name}:{kind}]"

        threshold = "<" + field(overall, "Delay Threshold Minutes", "none", "ok") + ">"
        for column in root.findall(".//column[@name='[Gap pp]']"):
            column.set("default-format", "*0.00")
        for column in root.findall(".//column[@name='[Delay Threshold Minutes]']"):
            column.set("caption", "Arrival delay cutoff (minutes)")
        for column in root.findall(".//column[@name='[Direction Evidence]']"):
            column.set("caption", "Direction of the gap")

        formatted(bars.find("./layout-options/title"), [
            ("Disrupted flights\n", 16, NAVY, True),
            (f"Canceled, diverted, or arrival ≥{threshold} minutes late\n", 10, MUTED, False),
            ("Compared using the same airline, destination, and month mix", 9, MUTED, False)])
        formatted(gap.find("./layout-options/title"), [
            ("The evening gap\n", 16, NAVY, True),
            (f"{threshold}-minute arrival-delay cutoff", 10, MUTED, False)])
        formatted(routes.find("./layout-options/title"), [
            ("Where is the evening gap largest?\n", 16, NAVY, True),
            (f"{threshold}-minute cutoff · Eight destinations with the most matched flights\n", 10, MUTED, False),
            ("Dots: estimates · Lines: approximate 95% adjusted model intervals", 10, MUTED, False)])

        tokens = {n: "<" + field(overall, n) + ">" for n in ["Gap pp", "Gap Interval Lower pp", "Gap Interval Upper pp"]}
        formatted(gap.find("./table/panes/pane/customized-label"), [
            (tokens["Gap pp"], 32, BLUE, True),
            (" more\n", 21, BLUE, True),
            ("evening disruptions per 100\ncomparable flights\n\n", 14, NAVY, False),
            (f"Approx. 95% model interval: {tokens['Gap Interval Lower pp']} to {tokens['Gap Interval Upper pp']} per 100", 10, MUTED, False)])

        with (ROOT / "data/tableau/destination_comparison_2025.csv").open(newline="") as stream:
            destinations = {r["Destination Code"]: r["Destination City"].split(",")[0].replace("Dallas/Fort Worth", "Dallas / Fort Worth") for r in csv.DictReader(stream)}
        column = destination.find("./column[@name='[Destination Code]']")
        if column is None:
            column = ET.Element("column", datatype="string", name="[Destination Code]", role="dimension", type="nominal")
            destination.insert(list(destination).index(destination.findall("./column")[-1]) + 1, column)
        column.set("caption", "Destination")
        aliases = column.find("./aliases")
        if aliases is not None:
            column.remove(aliases)
        aliases = ET.SubElement(column, "aliases")
        for code, city in sorted(destinations.items()):
            ET.SubElement(aliases, "alias", key='"' + code + '"', value=f"{city} ({code})")
        dependency = routes.find(f"./table/view/datasource-dependencies[@datasource='{destination.get('name')}']")
        old_column = dependency.find("./column[@name='[Destination Code]']")
        position = list(dependency).index(old_column)
        dependency.remove(old_column)
        dependency.insert(position, deepcopy(column))
        sort = routes.find("./table/view/single-value-per-nest-shelf-sorts/single-value-per-nest-shelf-sort")
        sort.set("direction", "DESC")
        sort.set("measure-to-sort-by", field(destination, "Gap pp"))
        axis = routes.find("./table/style/style-rule[@element='axis']/encoding")
        axis.attrib.update({"range-type": "fixed", "min": "-6", "max": "24", "major-origin": "0", "major-spacing": "5"})
        primary_axis = deepcopy(axis)
        primary_axis.set("field", field(destination, "Gap Interval Lower pp"))
        primary_axis.attrib.pop("fold", None)
        primary_axis.attrib.pop("synchronized", None)
        routes.find("./table/style/style-rule[@element='axis']").insert(0, primary_axis)
        title = routes.find("./table/style/style-rule/format[@attr='title']")
        title.set("value", "Evening minus morning gap (percentage points)")
        style(routes.find("./table/style"), "header", "width-header", "210")
        for annotations in routes.findall("./table/annotations"):
            routes.find("./table").remove(annotations)

        def tooltip_field(name, datatype="real", percentage=False):
            col = dependency.find(f"./column[@name='[{name}]']")
            if col is None:
                col = ET.Element("column", datatype=datatype, name=f"[{name}]", role="measure", type="quantitative")
                dependency.insert(list(dependency).index(dependency.find("./column-instance")), col)
            col.set("aggregation", "Min")
            col.set("default-format", "p0.00%" if percentage else ("*#,##0" if datatype == "integer" else "*0.00"))
            instance_name = f"[min:{name}:qk]"
            if dependency.find(f"./column-instance[@name='{instance_name}']") is None:
                ET.SubElement(dependency, "column-instance", column=f"[{name}]", derivation="Min", name=instance_name, pivot="key", type="quantitative")
            return field(destination, name)

        fields = {n: tooltip_field(n, "integer" if n.endswith("Flights") else "real", n.endswith("Rate")) for n in [
            "Gap pp", "Gap Interval Lower pp", "Gap Interval Upper pp", "Morning Disruption Rate", "Evening Disruption Rate", "Morning Flights", "Evening Flights"]}
        tooltip = ("<" + field(destination, "Destination Code", "none", "nk") + ">\n"
                   "Evening minus morning: <" + fields["Gap pp"] + "> percentage points\n"
                   "Approx. 95% adjusted interval: <" + fields["Gap Interval Lower pp"] + "> to <" + fields["Gap Interval Upper pp"] + "> points\n"
                   "Morning disruption rate: <" + fields["Morning Disruption Rate"] + ">\n"
                   "Evening disruption rate: <" + fields["Evening Disruption Rate"] + ">\n"
                   "Matched flights: <" + fields["Morning Flights"] + "> morning; <" + fields["Evening Flights"] + "> evening\n"
                   "Intervals adjusted across 62 destination/cutoff comparisons.\nHistorical association; not a future-flight forecast.")
        for pane in routes.findall("./table/panes/pane"):
            encodings = pane.find("./encodings")
            for token in fields.values():
                if not any(x.get("column") == token for x in encodings.findall("./tooltip")):
                    ET.SubElement(encodings, "tooltip", column=token)
            custom = pane.find("./customized-tooltip")
            if custom is None:
                custom = ET.Element("customized-tooltip")
                pane.insert(list(pane).index(pane.find("./style")), custom)
            formatted(custom, [(tooltip, 10, NAVY, False)])
            if pane.find("./mark").get("class") == "GanttBar":
                style(pane.find("./style"), "mark", "mark-color", "#9aa8b8")
                style(pane.find("./style"), "mark", "size", "0.18")
            elif pane.get("x-axis-name"):
                style(pane.find("./style"), "mark", "size", "0.55")

        dashboard = root.find("./dashboards/dashboard")
        old_zones = {x.get("id"): deepcopy(x) for x in dashboard.findall("./zones//zone")}
        size = dashboard.find("./size")
        size.attrib.clear()
        size.attrib.update({"sizing-mode": "fixed", "minwidth": str(WIDTH), "maxwidth": str(WIDTH), "minheight": str(HEIGHT), "maxheight": str(HEIGHT)})
        for device in dashboard.findall("./devicelayouts"):
            dashboard.remove(device)
        zones = dashboard.find("./zones")
        zones.clear()

        def rect(zone, x, y, w, h):
            zone.attrib.update({"x": str(round(x / WIDTH * 100000)), "y": str(round(y / HEIGHT * 100000)),
                                "w": str(round(w / WIDTH * 100000)), "h": str(round(h / HEIGHT * 100000))})

        container = ET.SubElement(zones, "zone", id="4", **{"type-v2": "layout-basic"})
        rect(container, 0, 0, WIDTH, HEIGHT)

        def place(identifier, rectangle, background="white", border=False):
            zone = deepcopy(old_zones[identifier])
            zone.set("is-floating", "true")
            rect(zone, *rectangle)
            for cached in zone.findall("./layout-cache"):
                zone.remove(cached)
            zs = zone.find("./zone-style")
            if zs is None:
                zs = ET.SubElement(zone, "zone-style")
            zs.clear()
            for attr, value in [("margin", "0"), ("padding", "12" if border else "0"), ("background-color", background),
                                ("border-style", "solid" if border else "none"), ("border-width", "1" if border else "0"), ("border-color", "#dce3eb")]:
                ET.SubElement(zs, "format", attr=attr, value=value)
            container.append(zone)
            return zone

        header = ET.SubElement(container, "zone", id="26", **{"type-v2": "text", "is-floating": "true"})
        rect(header, 24, 18, 910, 78)
        formatted(header, [("LAX flights: morning vs. evening\n", 23, NAVY, True),
                           ("2025 domestic departures · Morning 06:00–09:59 · Evening 17:00–20:59 · LAX local time", 11, MUTED, False)])
        place("8", (980, 16, 196, 86))
        place("5", (24, 112, 690, 215), border=True)
        place("10", (738, 112, 438, 215), background="#f1f6fc", border=True)
        place("15", (24, 348, 1152, 400), border=True)
        note = place("22", (24, 770, 826, 55))
        formatted(note, [(NOTE, 10, MUTED, False)])
        place("16", (878, 762, 298, 65))
        footer = place("17", (24, 832, 1152, 62))
        for item in footer.findall("./formatted-text/run"):
            item.set("fontname", "Arial")
            item.set("fontsize", "9")
            item.set("fontcolor", MUTED)
        dashboard.find("./style").append(ET.Element("style-rule", element="dashboard"))
        style(dashboard.find("./style"), "dashboard", "background-color", "#ffffff")
        for cached in root.findall("./thumbnails"):
            root.remove(cached)
        for active in root.findall("./windows/window[@class='dashboard']/active"):
            active.set("id", "4")
        ET.indent(root, space="  ")
        xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as target:
            for info in package.infolist():
                if info.filename == source_name:
                    workbook_info = deepcopy(info)
                    workbook_info.filename = "LAX_Flight_Reliability_Redesigned.twb"
                    workbook_info.orig_filename = workbook_info.filename
                    target.writestr(workbook_info, xml)
                else:
                    target.writestr(info, package.read(info.filename))
    print(f"Created {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size:,} bytes)")
    print("SHA256", hashlib.sha256(OUTPUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    make()
