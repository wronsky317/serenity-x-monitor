from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "hermes_daily_archive.py"
SPEC = importlib.util.spec_from_file_location("hermes_daily_archive", MODULE_PATH)
assert SPEC and SPEC.loader
daily = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(daily)


class HermesDailyArchiveTest(unittest.TestCase):
    def test_parse_args_accepts_skip_xhs_note(self) -> None:
        args = daily.parse_args(["--skip-xhs-note"])

        self.assertTrue(args.skip_xhs_note)

    def test_report_path_for_run_requires_current_run_report(self) -> None:
        raw_run = "/Users/wronsky/Documents/codes/serenity-x-monitor/raw/20260704T120000Z"
        outputs = {
            "report": "/Users/wronsky/Documents/codes/serenity-x-monitor/reports/20260704T120000Z_report.md",
            "latest": "/Users/wronsky/Documents/codes/serenity-x-monitor/reports/latest_summary.md",
        }

        self.assertEqual(daily.report_path_for_run(outputs, raw_run), outputs["report"])

    def test_report_path_for_run_rejects_latest_only_fallback(self) -> None:
        raw_run = "/Users/wronsky/Documents/codes/serenity-x-monitor/raw/20260704T120000Z"
        outputs = {
            "latest": "/Users/wronsky/Documents/codes/serenity-x-monitor/reports/latest_summary.md",
        }

        self.assertEqual(daily.report_path_for_run(outputs, raw_run), "")

    def test_report_path_for_run_rejects_report_from_other_run(self) -> None:
        raw_run = "/Users/wronsky/Documents/codes/serenity-x-monitor/raw/20260704T120000Z"
        outputs = {
            "report": "/Users/wronsky/Documents/codes/serenity-x-monitor/reports/20260703T120000Z_report.md",
            "latest": "/Users/wronsky/Documents/codes/serenity-x-monitor/reports/latest_summary.md",
        }

        self.assertEqual(daily.report_path_for_run(outputs, raw_run), "")

    def test_xhs_path_for_run_requires_current_run(self) -> None:
        raw_run = "/tmp/raw/20260711T131512Z"
        outputs = {"xhs": "/tmp/reports/20260711T131512Z_xhs.md"}

        self.assertEqual(daily.xhs_path_for_run(outputs, raw_run), outputs["xhs"])
        self.assertEqual(
            daily.xhs_path_for_run({"xhs": "/tmp/reports/older_xhs.md"}, raw_run),
            "",
        )


if __name__ == "__main__":
    unittest.main()
