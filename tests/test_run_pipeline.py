from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_pipeline.py"
SPEC = importlib.util.spec_from_file_location("run_pipeline", MODULE_PATH)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


class RunPipelineTest(unittest.TestCase):
    def test_run_fetch_with_retries_eventually_succeeds(self) -> None:
        calls: list[list[str]] = []
        results = [
            subprocess.CompletedProcess(["fetch"], 1, stdout="", stderr="temporary"),
            subprocess.CompletedProcess(["fetch"], 0, stdout="/tmp/raw/run\n", stderr=""),
        ]

        def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            return results.pop(0)

        completed = pipeline.run_fetch_with_retries(
            ["fetch"],
            retry_schedule=[(0, 3)],
            runner=runner,
            sleeper=lambda _: None,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(len(calls), 2)

    def test_run_fetch_with_retries_stops_after_retry_schedule(self) -> None:
        calls = 0
        sleeps: list[float] = []

        def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
            nonlocal calls
            calls += 1
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="still failing")

        completed = pipeline.run_fetch_with_retries(
            ["fetch"],
            retry_schedule=[(20, 3), (60, 3), (120, 3)],
            runner=runner,
            sleeper=sleeps.append,
        )

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(calls, 10)
        self.assertEqual(sleeps, [20, 20, 20, 60, 60, 60, 120, 120, 120])

    def test_parse_retry_schedule(self) -> None:
        self.assertEqual(
            pipeline.parse_retry_schedule("20:3,60:3,120:3"),
            [(20.0, 3), (60.0, 3), (120.0, 3)],
        )

    def test_append_xhs_failure_notice_does_not_reuse_old_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "latest_summary.md"
            report.write_text("# Serenity 日报\n\n日报正文\n", encoding="utf-8")

            pipeline.append_xhs_failure_notice(str(report), "codex unavailable")

            text = report.read_text(encoding="utf-8")
            self.assertIn("本次小红书笔记生成失败，已拒绝复用旧稿。", text)
            self.assertIn("codex unavailable", text)


if __name__ == "__main__":
    unittest.main()
