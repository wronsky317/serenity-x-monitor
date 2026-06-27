#!/usr/bin/env python3
"""Send plain text to a Feishu chat using the local Codex Feishu bridge config."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


BRIDGE_DIR = Path("/Users/wronsky/.codex/feishu-bridge")
BRIDGE_MODULE = BRIDGE_DIR / "feishu_codex_bridge.py"
DEFAULT_ENV_FILE = BRIDGE_DIR / ".env"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("feishu_codex_bridge", BRIDGE_MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Feishu bridge module: {BRIDGE_MODULE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description="Send text to a Feishu chat.")
    parser.add_argument("--chat-id", required=True, help="Feishu chat_id / open_chat_id.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="Bridge .env path.")
    parser.add_argument("--text", help="Text to send. Reads stdin when omitted.")
    parser.add_argument("--file", help="Read text from a UTF-8 file.")
    parser.add_argument("--title", default="", help="Optional title prepended to the message.")
    args = parser.parse_args()

    if args.file:
        text = Path(args.file).expanduser().read_text(encoding="utf-8")
    else:
        text = args.text if args.text is not None else sys.stdin.read()
    text = text.strip()
    if not text:
        raise SystemExit("No text to send.")

    if args.title:
        text = f"{args.title.strip()}\n\n{text}"

    bridge = load_bridge_module()
    bridge.load_dotenv(Path(args.env_file).expanduser())
    cfg = bridge.Config.from_env()
    sender = bridge.FeishuSender(cfg, bridge.TokenCache(cfg))
    sender.send_text(args.chat_id, text)
    print(f"sent {len(text)} chars to {args.chat_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
