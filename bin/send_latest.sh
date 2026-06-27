#!/usr/bin/env bash
set -euo pipefail

/Users/wronsky/.codex/feishu-bridge/.venv/bin/python \
  /Users/wronsky/Documents/codes/serenity-x-monitor/scripts/send_feishu_text.py \
  --chat-id "${FEISHU_CHAT_ID:?Set FEISHU_CHAT_ID first}" \
  --title "Serenity 日报" \
  --file /Users/wronsky/Documents/codes/serenity-x-monitor/reports/latest_summary.md
