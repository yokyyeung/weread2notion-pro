import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from heatmap import generate_heatmap, heatmap_years


class HeatmapTests(unittest.TestCase):
    def test_old_year_range_rolls_forward(self):
        self.assertEqual(heatmap_years("2018-2024", 2026), "2018-2026")
        self.assertEqual(heatmap_years("2018-2024", 2027), "2018-2027")
        self.assertEqual(heatmap_years("", 2026), "2026")
        self.assertEqual(heatmap_years("all", 2026), "all")

    def test_reversed_year_range_is_rejected(self):
        with self.assertRaises(ValueError):
            heatmap_years("2026-2018", 2026)

    def test_api_error_does_not_render(self):
        api = Mock()
        api.get_api_data.return_value = {"errcode": -2010}
        with patch("heatmap.subprocess.run") as run:
            with self.assertRaisesRegex(RuntimeError, "WEREAD_COOKIE"):
                generate_heatmap(api, [])
            run.assert_not_called()

    def test_renderer_success_without_svg_is_failure(self):
        api = Mock()
        api.get_api_data.return_value = {"readTimes": {}}
        with tempfile.TemporaryDirectory() as directory:
            old = os.getcwd()
            try:
                os.chdir(directory)
                with patch("heatmap.subprocess.run"):
                    with self.assertRaisesRegex(RuntimeError, "SVG"):
                        generate_heatmap(api, [])
            finally:
                os.chdir(old)

    def test_real_renderer_writes_2025_and_2026_reading_data(self):
        api = Mock()
        api.get_api_data.return_value = {
            "readTimes": {"1735660800": 3600, "1767196800": 7200}
        }
        with tempfile.TemporaryDirectory() as directory:
            old = os.getcwd()
            try:
                os.chdir(directory)
                with patch.dict(os.environ, {
                    "YEAR": "2025-2026",
                    "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
                }):
                    generate_heatmap(api, ["--me", "Offline regression", "--track-color", "#ACE7AE"])
                svg = Path("OUT_FOLDER/weread.svg")
                root = ET.parse(svg).getroot()
                titles = {node.text for node in root.iter("{http://www.w3.org/2000/svg}title")}
                self.assertTrue("2025-01-01 1小时" in titles)
                self.assertTrue("2026-01-01 2小时" in titles)
                self.assertFalse(Path("OUT_FOLDER/json.svg").exists())
                self.assertEqual(list(Path("OUT_FOLDER").iterdir()), [svg])
            finally:
                os.chdir(old)


if __name__ == "__main__":
    unittest.main()
