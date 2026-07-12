from __future__ import annotations

import importlib.util
import json
import socket
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "publish_xhs.py"
SPEC = importlib.util.spec_from_file_location("publish_xhs", MODULE_PATH)
assert SPEC and SPEC.loader
publish_xhs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish_xhs)

NOTE = """# 小红书笔记

## 短标题候选

1. 第一标题
2. CPO主线的关键验证点（推荐）

## 正文

这是正文。

## 话题

#光通信 #CPO #人工智能 #半导体 #科技投资 #产业趋势 #基本面研究 #投资逻辑 #风险管理 #市场观察
"""


class PublishXhsTest(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path, Path]:
        run_id = "20260711T131512Z"
        raw_run = root / "raw" / run_id
        raw_run.mkdir(parents=True)
        xhs_file = root / "reports" / f"{run_id}_xhs.md"
        xhs_file.parent.mkdir()
        xhs_file.write_text(NOTE, encoding="utf-8")
        image = root / "pic.png"
        image.write_bytes(b"png")
        return xhs_file, raw_run, image

    def test_build_payload_uses_recommended_title_and_fixed_final_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xhs_file, raw_run, image = self.fixture(Path(tmp))
            payload, fingerprint = publish_xhs.build_payload(
                xhs_file=xhs_file,
                raw_run=raw_run,
                images=[image],
                published_at=datetime(2026, 7, 12, 21, 15),
            )
        self.assertEqual(payload["title"], "【财经】0712 CPO主线的关键验证点")
        self.assertEqual(payload["content"], "这是正文。")
        self.assertEqual(payload["tags"][-2:], ["白毛女神", "长期主义"])
        self.assertEqual(len(payload["tags"]), 10)
        self.assertEqual(len(fingerprint), 64)

    def test_rejects_xhs_file_from_another_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xhs_file, raw_run, image = self.fixture(Path(tmp))
            other = xhs_file.with_name("other_xhs.md")
            other.write_text(NOTE, encoding="utf-8")
            with self.assertRaisesRegex(publish_xhs.PublishError, "does-not-match"):
                publish_xhs.build_payload(
                    xhs_file=other,
                    raw_run=raw_run,
                    images=[image],
                    published_at=datetime(2026, 7, 12),
                )

    def test_long_recommended_title_is_rejected_without_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xhs_file, raw_run, image = self.fixture(Path(tmp))
            xhs_file.write_text(
                NOTE.replace("CPO主线的关键验证点", "这是一个明显超过平台限制的推荐标题"),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(publish_xhs.PublishError, "title-too-long"):
                publish_xhs.build_payload(
                    xhs_file=xhs_file,
                    raw_run=raw_run,
                    images=[image],
                    published_at=datetime(2026, 7, 12),
                )

    def test_dry_run_never_calls_publish(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xhs_file, raw_run, image = self.fixture(root)
            with mock.patch.object(publish_xhs, "publish") as publish:
                exit_code = publish_xhs.main([
                    "--xhs-file", str(xhs_file), "--raw-run", str(raw_run),
                    "--image", str(image), "--state-file", str(root / "state.json"),
                    "--dry-run",
                ])
        self.assertEqual(exit_code, 0)
        publish.assert_not_called()

    def test_successful_publish_is_skipped_on_second_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xhs_file, raw_run, image = self.fixture(root)
            state_file = root / "state.json"
            args = [
                "--xhs-file", str(xhs_file), "--raw-run", str(raw_run),
                "--image", str(image), "--state-file", str(state_file),
                "--confirm-publish",
            ]
            with mock.patch.object(
                publish_xhs,
                "publish",
                return_value={"success": True, "data": {"status": "published"}},
            ) as publish:
                self.assertEqual(publish_xhs.main(args), 0)
                self.assertEqual(publish_xhs.main(args), 0)
            history = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(publish.call_count, 1)
        self.assertEqual(len(history["published"]), 1)

    def test_socket_timeout_is_reported_as_publish_error(self) -> None:
        with mock.patch.object(publish_xhs.request, "urlopen", side_effect=socket.timeout("slow")):
            with self.assertRaisesRegex(publish_xhs.PublishError, "service-request-failed"):
                publish_xhs.request_json("http://127.0.0.1:18060", "/api/v1/login/status")


if __name__ == "__main__":
    unittest.main()
