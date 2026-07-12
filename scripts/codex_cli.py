"""Resolve the Codex CLI across interactive shells and Hermes cron."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path


DEFAULT_CODEX_CANDIDATES = (
    Path("/Applications/ChatGPT.app/Contents/Resources/codex"),
    Path("/Applications/Codex.app/Contents/Resources/codex"),
)


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def resolve_codex_cli(
    *,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    candidates: Iterable[Path] = DEFAULT_CODEX_CANDIDATES,
) -> Path:
    env = os.environ if environ is None else environ
    override = env.get("CODEX_BIN", "").strip()
    if override:
        path = Path(override).expanduser()
        if _is_executable(path):
            return path
        raise FileNotFoundError(f"CODEX_BIN is not an executable file: {path}")

    discovered = which("codex")
    if discovered:
        path = Path(discovered).expanduser()
        if _is_executable(path):
            return path

    checked: list[str] = []
    for candidate in candidates:
        path = Path(candidate).expanduser()
        checked.append(str(path))
        if _is_executable(path):
            return path

    raise FileNotFoundError(
        "Codex CLI was not found. Set CODEX_BIN or install Codex in one of: "
        + ", ".join(checked)
    )
