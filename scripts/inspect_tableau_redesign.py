"""Audit the redesign against the verified final archive, without rendering Tableau."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET
import zipfile

from scripts.inspect_tableau_workbook import inspect as inspect_source
from scripts.redesign_tableau_workbook import ROOT, SOURCE, OUTPUT, NOTE, WIDTH, HEIGHT


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def semantic(node):
    if node is None:
        return None
    return (node.tag, tuple(sorted(node.attrib.items())), (node.text or "").strip(),
            tuple(semantic(child) for child in node))


def text(node):
    return "".join(run.text or "" for run in node.findall("./run")).replace("Æ", "").strip()


def inspect(workbook=OUTPUT):
    workbook = Path(workbook).resolve()
    baseline = inspect_source(SOURCE)
    pinned = json.loads((ROOT / "reports/tableau_final.json").read_text())
    checks = []

    def check(description, condition):
        if not condition:
            raise ValueError(description)
        checks.append({"check": description, "passed": True})

    check("Baseline final archive agrees with its pinned audit", baseline == pinned)
    before = digest(workbook)
    with zipfile.ZipFile(SOURCE) as original, zipfile.ZipFile(workbook) as redesigned:
        check("Redesigned package ZIP integrity passes", redesigned.testzip() is None)
        names = redesigned.namelist()
        xml = [name for name in names if name.endswith(".twb")]
        extracts = [name for name in names if name.endswith(".hyper")]
        check("Redesigned package contains one workbook and both extracts", len(xml) == 1 and len(extracts) == 2)
        check("Both redesigned extracts are byte-identical to the fully audited originals", set(extracts) == {
            name for name in original.namelist() if name.endswith(".hyper")}
              and all(redesigned.read(name) == original.read(name) for name in extracts))
        old = ET.fromstring(original.read(next(name for name in original.namelist() if name.endswith(".twb"))))
        new = ET.fromstring(redesigned.read(xml[0]))
    old_sheets = {s.get("name"): s for s in old.findall("./worksheets/worksheet")}
    check("Formatted text precedes layout and style children", all(
        list(parent)[0].tag == "formatted-text" for parent in new.iter()
        if parent.find("./formatted-text") is not None))
    sheets = {s.get("name"): s for s in new.findall("./worksheets/worksheet")}
    check("All three original worksheet identities remain", set(sheets) == set(old_sheets) and len(sheets) == 3)
    sources = {s.get("caption"): s for s in new.findall("./datasources/datasource")}
    old_sources = {s.get("caption"): s for s in old.findall("./datasources/datasource")}
    check("Source identities and physical data connections are unchanged", set(sources) == set(old_sources)
          and all(sources[name].get("name") == old_sources[name].get("name")
                  and all(semantic(sources[name].find(path)) == semantic(old_sources[name].find(path))
                          for path in ["./connection", "./extract", "./object-graph"]) for name in sources))
    check("Cross-source threshold relationship is unchanged", [semantic(x) for x in new.findall("./datasource-relationships/datasource-relationship")]
          == [semantic(x) for x in old.findall("./datasource-relationships/datasource-relationship")])
    for name, sheet in sheets.items():
        previous = old_sheets[name]
        check(f"{name}: comparison filters are unchanged", [semantic(f) for f in sheet.findall("./table/view/filter")]
              == [semantic(f) for f in previous.findall("./table/view/filter")])
        check(f"{name}: row and column field bindings are unchanged", all(sheet.findtext(path) == previous.findtext(path) for path in ["./table/rows", "./table/cols"]))
        instances = {i.get("name"): i.get("derivation") for i in sheet.findall("./table/view/datasource-dependencies/column-instance")}
        check(f"{name}: existing aggregation instances are unchanged", all(instances.get(i.get("name")) == i.get("derivation") for i in previous.findall("./table/view/datasource-dependencies/column-instance")))
        check(f"{name}: title retains the live shared threshold", "none:Delay Threshold Minutes:ok]>" in text(sheet.find("./layout-options/title/formatted-text")))
    def calculations(root):
        return {(column.get("name"), calculation.get("formula")) for column in root.findall(".//column") for calculation in column.findall("./calculation")}
    check("All analytical calculations remain unchanged", calculations(new) == calculations(old))
    for name in sources:
        check(f"{name}: original color mappings remain unchanged", semantic(sources[name].find("./style")) == semantic(old_sources[name].find("./style")))
    check("All explicit gap defaults use number formatting", all(c.get("default-format") == "*0.00" for c in new.findall(".//column[@name='[Gap pp]']")))
    bars, gap, routes = (sheets[n] for n in ["Overall Reliability", "Gap Summary", "Destination Gaps"])
    check("Overall bars retain their validated percentage axis", semantic(bars.find("./table/style/style-rule[@element='axis']/encoding")) == semantic(old_sheets["Overall Reliability"].find("./table/style/style-rule[@element='axis']/encoding")))
    check("Overall rate comparison explains the shared airline, destination, and month mix", "Compared using the same airline, destination, and month mix" in text(bars.find("./layout-options/title/formatted-text")))
    check("Gap card retains all three live text-field encodings", [semantic(x) for x in gap.findall("./table/panes/pane/encodings/text")] == [semantic(x) for x in old_sheets["Gap Summary"].findall("./table/panes/pane/encodings/text")])
    check("Gap and both bounds retain effective two-decimal numeric formats", all(x.get("value") == "*0.00" for x in gap.findall("./table/style/style-rule/format[@attr='text-format']")))
    label = text(gap.find("./table/panes/pane/customized-label/formatted-text"))
    examples = []
    overall = sources["overall_comparison_2025"]
    for result in baseline["results"]:
        rendered = label
        for name in ["Gap pp", "Gap Interval Lower pp", "Gap Interval Upper pp"]:
            rendered = rendered.replace(f"<[{overall.get('name')}].[min:{name}:qk]>", f"{result[name]:.2f}")
        expected = (f"{result['Gap pp']:.2f} more\nevening disruptions per 100\ncomparable flights\n\n"
                    f"Approx. 95% model interval: {result['Gap Interval Lower pp']:.2f} to {result['Gap Interval Upper pp']:.2f} per 100")
        check(f"Plain-language gap resolves correctly at {result['Delay Threshold Minutes']} minutes", rendered == expected)
        examples.append({"threshold_minutes": result["Delay Threshold Minutes"], "label": rendered})
    destination = sources["destination_comparison_2025"]
    with (ROOT / "data/tableau/destination_comparison_2025.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    expected_aliases = {'"'+r["Destination Code"]+'"': r["Destination City"].split(",")[0].replace("Dallas/Fort Worth", "Dallas / Fort Worth") + " (" + r["Destination Code"] + ")" for r in rows}
    aliases = {a.get("key"): a.get("value") for a in destination.findall("./column[@name='[Destination Code]']/aliases/alias")}
    check("Destination city labels agree with the pinned CSV without replacing raw codes", aliases == expected_aliases)
    sort = routes.find("./table/view/single-value-per-nest-shelf-sorts/single-value-per-nest-shelf-sort")
    check("Destination rows sort by descending MIN gap", sort.get("direction") == "DESC" and sort.get("measure-to-sort-by") == f"[{destination.get('name')}].[min:Gap pp:qk]")
    axes = routes.findall("./table/style/style-rule[@element='axis']/encoding")
    check("Both destination axes use one fixed -6 to 24 scale", len(axes) == 2 and all(a.get("range-type") == "fixed" and float(a.get("min")) == -6 and float(a.get("max")) == 24 for a in axes))
    point = f"[{destination.get('name')}].[min:Gap pp:qk]"
    check("Destination secondary axis stays synchronized", next(a for a in axes if a.get("field") == point).get("synchronized") == "true")
    codes = {r["code"] for r in baseline["destination_sql_examples"][0]["destinations"]}
    visible = [r for r in rows if r["Destination Code"] in codes]
    check("Fixed scale includes every displayed interval endpoint at both thresholds", all(-6 <= float(r["Gap Interval Lower pp"]) <= float(r["Gap pp"]) <= float(r["Gap Interval Upper pp"]) <= 24 for r in visible))
    for pane in routes.findall("./table/panes/pane"):
        previous = next(p for p in old_sheets["Destination Gaps"].findall("./table/panes/pane") if p.get("id") == pane.get("id"))
        check("Destination layer " + str(pane.get("id", "all")) + ": geometry and direction bindings stay unchanged", semantic(pane.find("./mark")) == semantic(previous.find("./mark")) and all(semantic(pane.find("./encodings/"+kind)) == semantic(previous.find("./encodings/"+kind)) for kind in ["size", "color"]))
    check("Detailed tooltip includes gap, bounds, rates, counts, and adjustment scope", all(
        "62 destination/cutoff comparisons" in text(p.find("./customized-tooltip/formatted-text")) and all(
            f"[min:{name}:qk]>" in text(p.find("./customized-tooltip/formatted-text"))
            for name in ["Gap pp", "Gap Interval Lower pp", "Gap Interval Upper pp", "Morning Disruption Rate", "Evening Disruption Rate", "Morning Flights", "Evening Flights"])
        for p in routes.findall("./table/panes/pane")))
    check("Stale worksheet annotations are removed", routes.find("./table/annotations") is None)
    dashboard = new.find("./dashboards/dashboard")
    check("Original dashboard name is retained", dashboard.get("name") == "LAX Reliability Overview")
    size = dashboard.find("./size")
    check("Desktop canvas is fixed at 1200 by 900", size.get("sizing-mode") == "fixed" and all(size.get(k) == str(v) for k,v in {"minwidth":WIDTH,"maxwidth":WIDTH,"minheight":HEIGHT,"maxheight":HEIGHT}.items()))
    zones = dashboard.findall("./zones/zone/zone")
    check("Every visible zone is inside the canvas", all(int(z.get("x")) >= 0 and int(z.get("y")) >= 0 and int(z.get("x"))+int(z.get("w")) <= 100000 and int(z.get("y"))+int(z.get("h")) <= 100000 for z in zones))
    rectangles = [(int(z.get("x")),int(z.get("y")),int(z.get("w")),int(z.get("h"))) for z in zones]
    check("Top-level content rectangles do not overlap", all(x+w <= xx or xx+ww <= x or y+h <= yy or yy+hh <= y for i,(x,y,w,h) in enumerate(rectangles) for xx,yy,ww,hh in rectangles[i+1:]))
    check("All three views remain visible in the dashboard", {z.get("name") for z in zones if z.get("type-v2") is None} == set(sheets))
    controls = [z for z in zones if z.get("type-v2") == "filter"]
    check("Shared threshold is a single-choice control with All hidden", len(controls) == 1 and controls[0].get("mode") == "radiolist" and controls[0].get("show-all") == "false")
    texts = [text(z.find("./formatted-text")) for z in zones if z.get("type-v2") == "text"]
    check("Interpretation and source/coverage notes remain visible", NOTE in texts and any("57,464" in t and "64.2%" in t and "do not establish causal effects" in t and "github.com/JohnHeerema/LAX-FLIGHT-RELIABILITY" in t for t in texts))
    check("All formatted text uses Arial", all(r.get("fontname") in {None,"Arial"} for r in new.findall(".//formatted-text/run")))
    check("Inspection leaves both workbooks unchanged", digest(workbook) == before and digest(SOURCE) == baseline["workbook_sha256"])
    return {"status":"candidate_not_published", "workbook":workbook.name, "workbook_sha256":before,
            "baseline_workbook_sha256":baseline["workbook_sha256"],"baseline_checks_passed":len(baseline["checks"]),
            "embedded_values_covered_by_byte_identity":baseline["embedded_values_compared"],"checks":checks,
            "gap_label_examples":examples,"scope":"The original archive is freshly audited with embedded SQL; both candidate extracts are byte-identical. Candidate configuration, field bindings, bounds, geometry, and formatted-text child order are checked. The initial candidate failed a native Tableau open with D2E8DA72 because formatted-text followed zone-style. That ordering is repaired; the corrected workbook has not yet been confirmed to open/render in Tableau. The supplied PNG is a data-driven layout preview, not a Tableau screenshot."}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook",type=Path,default=OUTPUT)
    args=parser.parse_args()
    audit=inspect(args.workbook)
    (ROOT/"reports/tableau_redesign.json").write_text(json.dumps(audit,indent=2)+"\n")
    print(json.dumps({"baseline_checks":audit["baseline_checks_passed"],"redesign_checks":len(audit["checks"]),"status":audit["status"]}))
