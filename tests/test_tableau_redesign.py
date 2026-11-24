"""Guard the candidate's data identity, filter semantics, and interval visibility."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET
import zipfile

from scripts.redesign_tableau_workbook import formatted, MUTED


class FormattedTextOrderTests(unittest.TestCase):
    def test_insert_and_replacement_keep_text_before_zone_style(self):
        for existing in [False, True]:
            with self.subTest(existing_text=existing):
                parent = ET.Element("zone")
                if existing:
                    ET.SubElement(parent, "formatted-text")
                style = ET.SubElement(parent, "zone-style")
                formatted(parent, [("Updated note", 10, MUTED, False)])
                self.assertEqual([child.tag for child in parent], ["formatted-text", "zone-style"])
                self.assertIs(parent[1], style)
                self.assertEqual(parent.findtext("./formatted-text/run"), "Updated note")


HAS_HYPER=importlib.util.find_spec("tableauhyperapi") is not None
if HAS_HYPER:
    from scripts.inspect_tableau_redesign import inspect
    from scripts.redesign_tableau_workbook import OUTPUT


@unittest.skipUnless(HAS_HYPER,"Install requirements-tableau.txt")
class RedesignFailureTests(unittest.TestCase):
    def altered(self, directory, change):
        output=Path(directory)/"altered.twbx"
        with zipfile.ZipFile(OUTPUT) as source, zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                content=source.read(info.filename)
                if info.filename.endswith('.twb'):
                    root=ET.fromstring(content);change(root);content=ET.tostring(root,encoding='utf-8',xml_declaration=True)
                target.writestr(info,content)
        return output

    def test_conflicting_threshold_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            def change(root):
                node=root.find("./worksheets/worksheet[@name='Destination Gaps']/table/view/filter/groupfilter")
                node.set('member','60')
            with self.assertRaisesRegex(ValueError,'comparison filters are unchanged'):
                inspect(self.altered(directory,change))

    def test_text_after_zone_style_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            def change(root):
                node = root.find("./dashboards/dashboard/zones/zone/zone[@id='22']")
                label = node.find("./formatted-text")
                node.remove(label)
                node.append(label)
            with self.assertRaisesRegex(ValueError, "Formatted text precedes"):
                inspect(self.altered(directory, change))

    def test_scale_that_clips_intervals_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            def change(root):
                for node in root.findall("./worksheets/worksheet[@name='Destination Gaps']/table/style/style-rule[@element='axis']/encoding"):
                    node.set('max','10')
            with self.assertRaisesRegex(ValueError,'fixed -6 to 24 scale'):
                inspect(self.altered(directory,change))

    def test_changed_embedded_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'altered-data.twbx'
            with zipfile.ZipFile(OUTPUT) as source, zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as target:
                changed=False
                for info in source.infolist():
                    data=source.read(info.filename)
                    if info.filename.endswith('.hyper') and not changed:
                        data=data[:-1]+bytes([data[-1]^1]);changed=True
                    target.writestr(info,data)
            with self.assertRaisesRegex(ValueError,'byte-identical to the fully audited originals'):
                inspect(output)
