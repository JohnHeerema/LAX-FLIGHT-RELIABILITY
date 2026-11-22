"""Failure checks for the optional native Tableau workbook inspection."""

import importlib.util
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
