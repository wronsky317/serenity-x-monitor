from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from PIL import Image


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "render_report_long_image.py"
SPEC = importlib.util.spec_from_file_location("render_report_long_image", MODULE_PATH)
assert SPEC and SPEC.loader
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


class RenderReportLongImageTest(unittest.TestCase):
    def test_renders_complete_markdown_to_long_png(self) -> None:
        markdown = "# 日报\n\n## 核心总结\n\n正文内容。\n\n- 风险提示：不构成投资建议。\n"
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.png"
            size = renderer.render(markdown, output)
            with Image.open(output) as image:
                self.assertEqual(image.size, size)
                self.assertGreaterEqual(image.width, renderer.WIDTH)
                self.assertGreater(image.height, 300)

    def test_blocks_preserve_headings_and_bullets(self) -> None:
        result = renderer.blocks("# 标题\n\n## 分节\n\n- 条目\n")

        self.assertEqual(result, [("h1", "标题"), ("h2", "分节"), ("bullet", "• 条目")])


if __name__ == "__main__":
    unittest.main()
