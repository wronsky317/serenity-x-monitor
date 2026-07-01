from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_x_archive_report.py"
SPEC = importlib.util.spec_from_file_location("build_x_archive_report", MODULE_PATH)
assert SPEC and SPEC.loader
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)


class BuildXArchiveReportTest(unittest.TestCase):
    def test_optimus_does_not_trigger_mu_memory_template(self) -> None:
        row = {
            "kind": "failed",
            "sortAt": "2026-06-28T09:32:04.000Z",
            "post": {
                "xPostId": "2071164721299112316",
                "canonicalUrl": "https://x.com/aleabitoreddit/status/2071164721299112316",
                "text": (
                    "Yup, Schaeffler $SHA0 is the ideal example for automotive players. "
                    "Then theres auto players like Nabtesco for joints. And then Sanhua "
                    "in China for $TSLA Optimus. Markets are focusing on immediate upside "
                    "from bottlenecks like memory or MLCC. I am sure we will see some "
                    "random Toto-HBM type surprise as different humanoid architecture evolve."
                ),
            },
            "failureReason": "FAILED · INVALID TICKERS SHA0.DE",
        }

        self.assertEqual(archive.row_theme(row), "EV")
        self.assertEqual(archive.zh_row_title(row), "机器人供应链与汽车零部件玩家的长期可选性")
        takeaway = archive.zh_row_takeaway(row)
        self.assertIn("机器人", takeaway)
        self.assertNotIn("Memory/HBM 结构性短缺继续被强化", takeaway)
        self.assertNotIn("MU、SK Hynix、Samsung", takeaway)

    def test_mu_ticker_still_triggers_memory_template(self) -> None:
        row = {
            "kind": "thesis",
            "sortAt": "2026-06-26T07:47:43.000Z",
            "post": {
                "canonicalUrl": "https://x.com/aleabitoreddit/status/example",
                "text": "Memory names from $MU to SK Hynix and Samsung are going brrrr from HBM demand.",
            },
        }

        self.assertEqual(archive.row_theme(row), "SEMIS")
        self.assertEqual(archive.zh_row_title(row), "AI memory/HBM 供需紧张继续强化")
        self.assertIn("Memory/HBM 结构性短缺继续被强化", archive.zh_row_takeaway(row))

    def test_robotics_text_overrides_bad_semis_portfolio_theme(self) -> None:
        row = {
            "kind": "thesis",
            "sortAt": "2026-06-29T09:54:58.000Z",
            "portfolio": {
                "theme": "SEMIS",
                "thesisHeadline": "Robotics adoption is reaching an inflection point",
                "topTickers": ["NVDA", "AMZN", "TSLA"],
            },
            "post": {
                "canonicalUrl": "https://x.com/aleabitoreddit/status/2071532870859149617",
                "text": (
                    "$GM cuts 1,000 workers and replaces them with 50 robots. "
                    "Reports also show GM is working on a deal with $NVDA on factory robotics. "
                    "Robotics/Humanoids are just pre-scale right now."
                ),
            },
        }

        self.assertEqual(archive.row_theme(row), "EV")
        self.assertIn("机器人 / EV 供应链", archive.zh_row_takeaway(row))

    def test_unimicron_and_samsung_lta_do_not_trigger_hbm_template(self) -> None:
        row = {
            "kind": "failed",
            "sortAt": "2026-07-01T04:40:02.000Z",
            "post": {
                "canonicalUrl": "https://x.com/aleabitoreddit/status/2072178393878290789",
                "text": (
                    "Older DDR4 Memory with CXL as memory expansion. "
                    "LTAs are being signed with MLCC after Samsung signed LTA with US big tech customer. "
                    "Major IC substrate suppliers include Unimicron, Kinsus, Nan Ya PCB. "
                    "Memory and IC packaging and testing capacity have both become bottlenecks."
                ),
            },
        }

        self.assertNotEqual(archive.zh_row_title(row), "AI memory/HBM 供需紧张继续强化")
        takeaway = archive.zh_row_takeaway(row)
        self.assertNotIn("MU、SK Hynix、Samsung", takeaway)


if __name__ == "__main__":
    unittest.main()
