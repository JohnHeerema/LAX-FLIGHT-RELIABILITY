"""Failure checks for the optional native Tableau workbook inspection."""

import importlib.util
import csv
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET
import zipfile


HAS_HYPER = importlib.util.find_spec("tableauhyperapi") is not None
if HAS_HYPER:
    from scripts.inspect_tableau_workbook import ROOT, SOURCE, WORKBOOK, inspect


@unittest.skipUnless(HAS_HYPER, "Install requirements-tableau.txt to inspect native Tableau data")
class TableauCheckpointFailureTests(unittest.TestCase):
    def test_multiple_choice_threshold_control_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="lax-tableau-test-") as directory:
            altered = Path(directory) / "multiple-choice.twbx"
            with zipfile.ZipFile(WORKBOOK) as source, zipfile.ZipFile(altered, "w", zipfile.ZIP_DEFLATED) as target:
                for info in source.infolist():
                    content = source.read(info.filename)
                    if info.filename.endswith(".twb"):
                        root = ET.fromstring(content)
                        root.find("./windows/window/cards//card[@type='filter']").set("mode", "checklist")
                        content = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                    target.writestr(info, content)
            with self.assertRaisesRegex(ValueError, "single choice"):
                inspect(altered)

    def test_changed_source_rate_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="lax-tableau-test-") as directory:
            altered = Path(directory) / "wrong-rate.csv"
            content = SOURCE.read_text(encoding="utf-8")
            original = "0.0441568323388093"
            self.assertIn(original, content)
            altered.write_text(content.replace(original, "0.5000000000000000"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Extract differs from validated CSV: Morning Disruption Rate at 60 minutes"):
                inspect(WORKBOOK, altered)


@unittest.skipUnless(HAS_HYPER, "Install requirements-tableau.txt to inspect native Tableau data")
class TableauDashboardFailureTests(unittest.TestCase):
    def reject_altered_dashboard(self, change, message):
        workbook = ROOT / "tableau/checkpoints/LAX_Flight_Reliability_Checkpoint_02.twbx"
        with tempfile.TemporaryDirectory(prefix="lax-dashboard-test-") as directory:
            altered = Path(directory) / "altered.twbx"
            with zipfile.ZipFile(workbook) as source, zipfile.ZipFile(altered, "w", zipfile.ZIP_DEFLATED) as target:
                for info in source.infolist():
                    content = source.read(info.filename)
                    if info.filename.endswith(".twb"):
                        root = ET.fromstring(content)
                        change(root)
                        content = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                    target.writestr(info, content)
            with self.assertRaisesRegex(ValueError, message):
                inspect(altered)

    def test_missing_shared_filter_is_rejected(self):
        def change(root):
            shared = root.find("./shared-views/shared-view")
            shared.remove(shared.find("./filter"))
        self.reject_altered_dashboard(change, "One threshold filter is present")

    def test_static_interval_bound_is_rejected(self):
        def change(root):
            source = root.find("./datasources/datasource").get("name")
            token = f"<[{source}].[min:Gap Interval Upper pp:qk]>"
            for run in root.findall("./worksheets/worksheet[@name='Gap Summary']//customized-label/formatted-text/run"):
                run.text = (run.text or "").replace(token, "4.23")
        self.reject_altered_dashboard(change, "Summary label binds all three live values")

    def test_percentage_format_on_gap_is_rejected(self):
        def change(root):
            for item in root.findall("./worksheets/worksheet[@name='Gap Summary']/table/style/style-rule/format"):
                if "[min:Gap pp:qk]" in item.get("field", ""):
                    item.set("value", "p0.00%")
        self.reject_altered_dashboard(change, "All three effective gap formats are two-decimal numbers")

    def test_multiple_choice_dashboard_control_is_rejected(self):
        def change(root):
            root.find("./dashboards/dashboard/zones//zone[@type-v2='filter']").set("mode", "checklist")
        self.reject_altered_dashboard(change, "Desktop dashboard exposes one single-choice threshold control")


@unittest.skipUnless(HAS_HYPER, "Install requirements-tableau.txt to inspect native Tableau data")
class TableauDestinationDashboardFailureTests(unittest.TestCase):
    def reject_altered_dashboard(self, change, message):
        workbook = ROOT / "tableau/checkpoints/LAX_Flight_Reliability_Checkpoint_03.twbx"
        with tempfile.TemporaryDirectory(prefix="lax-destinations-test-") as directory:
            altered = Path(directory) / "altered.twbx"
            with zipfile.ZipFile(workbook) as source, zipfile.ZipFile(altered, "w", zipfile.ZIP_DEFLATED) as target:
                for info in source.infolist():
                    content = source.read(info.filename)
                    if info.filename.endswith(".twb"):
                        root = ET.fromstring(content)
                        change(root)
                        content = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                    target.writestr(info, content)
            with self.assertRaisesRegex(ValueError, message):
                inspect(altered)

    def test_conflicting_local_threshold_is_rejected(self):
        """The actual authoring bug: shared 15 AND local 60 erased the view."""
        def change(root):
            for item in root.findall("./worksheets/worksheet/table/view/filter"):
                if "Delay Threshold Minutes" in item.get("column", ""):
                    item.find("./groupfilter").set("member", "15")
            view = root.find("./worksheets/worksheet[@name='Destination Gaps']/table/view")
            shared = next(item for item in view.findall("./filter") if "Delay Threshold Minutes" in item.get("column", ""))
            local = deepcopy(shared)
            local.attrib.pop("filter-group")
            local.set("column", local.find("./target").get("field"))
            local.remove(local.find("./target"))
            local.find("./groupfilter").set("member", "60")
            view.append(local)
        self.reject_altered_dashboard(change, "exactly one threshold filter without a conflicting local filter")

    def test_wrong_cross_source_mapping_is_rejected(self):
        def change(root):
            mapping = root.find("./datasource-relationships/datasource-relationship/column-mapping/map")
            mapping.set("value", mapping.get("value").replace("Delay Threshold Minutes", "Destination Code"))
        self.reject_altered_dashboard(change, "Cross-source relationship maps only the matching threshold fields")

    def test_wrong_interval_width_is_rejected(self):
        def change(root):
            root.find("./datasources/datasource/column[@caption='Interval Width pp']/calculation").set(
                "formula", "[Gap Interval Upper pp] + [Gap Interval Lower pp]")
        self.reject_altered_dashboard(change, "Interval width is upper minus lower")

    def test_unsynchronized_axes_are_rejected(self):
        def change(root):
            root.find("./worksheets/worksheet[@name='Destination Gaps']/table/style/style-rule/encoding").set("synchronized", "false")
        self.reject_altered_dashboard(change, "Destination dual axes are synchronized")

    def test_changed_destination_reference_value_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="lax-destination-data-test-") as directory:
            overall = Path(directory) / SOURCE.name
            overall.write_bytes(SOURCE.read_bytes())
            destination = Path(directory) / "destination_comparison_2025.csv"
            with (SOURCE.parent / destination.name).open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                columns, rows = reader.fieldnames, list(reader)
            next(row for row in rows if row["Destination Code"] == "SFO" and row["Delay Threshold Minutes"] == "60")["Gap pp"] = "99.0"
            with destination.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, "Extract differs from validated CSV: destination_comparison_2025, Gap pp"):
                inspect(ROOT / "tableau/checkpoints/LAX_Flight_Reliability_Checkpoint_03.twbx", overall)
