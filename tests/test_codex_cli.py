from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "codex_cli.py"
SPEC = importlib.util.spec_from_file_location("codex_cli", MODULE_PATH)
assert SPEC and SPEC.loader
codex_cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(codex_cli)


class ResolveCodexCliTest(unittest.TestCase):
    def make_executable(self, directory: str, name: str = "codex") -> Path:
        path = Path(directory) / name
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o755)
        return path

    def test_explicit_override_takes_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            override = self.make_executable(tmp, "custom-codex")

            resolved = codex_cli.resolve_codex_cli(
                environ={"CODEX_BIN": str(override)},
                which=lambda _: "/unused/path",
                candidates=(),
            )

            self.assertEqual(resolved, override)

    def test_invalid_explicit_override_is_actionable(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "CODEX_BIN is not an executable"):
            codex_cli.resolve_codex_cli(
                environ={"CODEX_BIN": "/missing/codex"},
                which=lambda _: None,
                candidates=(),
            )

    def test_path_lookup_precedes_app_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            discovered = self.make_executable(tmp)

            resolved = codex_cli.resolve_codex_cli(
                environ={},
                which=lambda _: str(discovered),
                candidates=(Path("/unused/app/codex"),),
            )

            self.assertEqual(resolved, discovered)

    def test_app_fallback_works_when_cron_path_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundled = self.make_executable(tmp)

            resolved = codex_cli.resolve_codex_cli(
                environ={"PATH": "/usr/bin:/bin"},
                which=lambda _: None,
                candidates=(bundled,),
            )

            self.assertEqual(resolved, bundled)

    def test_failure_lists_checked_locations(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "/missing/app/codex"):
            codex_cli.resolve_codex_cli(
                environ={},
                which=lambda _: None,
                candidates=(Path("/missing/app/codex"),),
            )


if __name__ == "__main__":
    unittest.main()
