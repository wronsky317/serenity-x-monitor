from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "publish_xhs_ai.py"
SPEC = importlib.util.spec_from_file_location("publish_xhs_ai", MODULE_PATH)
assert SPEC and SPEC.loader
publish_xhs_ai = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish_xhs_ai)


class FakeLocator:
    def __init__(self, *, count=1, wait_error=None):
        self._count = count
        self._wait_error = wait_error
        self.clicked = 0
        self.evaluated = []
        self.first = self
        self.last = self

    async def count(self):
        return self._count

    async def wait_for(self, **_kwargs):
        if self._wait_error:
            raise self._wait_error

    async def click(self, **_kwargs):
        self.clicked += 1

    async def evaluate(self, expression):
        self.evaluated.append(expression)

    def locator(self, _selector):
        return self

    def filter(self, **_kwargs):
        return self


class FakeKeyboard:
    def __init__(self):
        self.events = []

    async def press(self, value):
        self.events.append(("press", value))

    async def insert_text(self, value):
        self.events.append(("insert", value))

    async def type(self, value, **_kwargs):
        self.events.append(("type", value))


class FakePage:
    def __init__(self, *, topic_wait_error=None):
        self.editor = FakeLocator()
        self.topic = FakeLocator(wait_error=topic_wait_error)
        self.keyboard = FakeKeyboard()

    def locator(self, selector):
        if selector == "#creator-editor-topic-container":
            return self.topic
        return self.editor

    async def wait_for_timeout(self, _milliseconds):
        return None


class PublishXhsAiTest(unittest.IsolatedAsyncioTestCase):
    async def test_topics_are_selected_from_suggestions(self):
        page = FakePage()

        await publish_xhs_ai.append_linked_topics(page, ["AI", "白毛女神", "长期主义"])

        self.assertEqual(page.topic.clicked, 3)
        self.assertEqual(len(page.editor.evaluated), 1)
        self.assertIn("range.collapse(false)", page.editor.evaluated[0])
        self.assertNotIn(("press", "End"), page.keyboard.events)
        self.assertEqual(
            [event for event in page.keyboard.events if event[0] == "type"],
            [("type", "AI"), ("type", "白毛女神"), ("type", "长期主义")],
        )

    async def test_missing_topic_suggestion_aborts_instead_of_plain_text_fallback(self):
        page = FakePage(topic_wait_error=TimeoutError("no suggestions"))

        with self.assertRaisesRegex(RuntimeError, "suggestion-not-selected:长期主义"):
            await publish_xhs_ai.append_linked_topics(page, ["长期主义"])

        self.assertEqual(page.topic.clicked, 0)

    async def test_publisher_prepares_plain_body_then_adds_linked_topics(self):
        calls = {}

        class FakePoster:
            def __init__(self):
                self.page = object()

            async def initialize(self):
                return None

            async def post_article(self, title, content, images, auto_publish):
                calls["post"] = (title, content, images, auto_publish)
                return True

            async def cleanup(self):
                calls["cleaned"] = True

        module = types.ModuleType("src.core.write_xiaohongshu")
        module.XiaohongshuPoster = FakePoster
        payload = {
            "title": "【财经】0714 今日标题",
            "content": "完整正文",
            "images": ["cover.png", "report.png"],
            "tags": ["AI", "白毛女神", "长期主义"],
        }

        with patch.dict(sys.modules, {"src.core.write_xiaohongshu": module}), \
             patch.object(publish_xhs_ai, "append_linked_topics", new=AsyncMock()) as append, \
             patch.object(publish_xhs_ai, "publish_prepared_article", new=AsyncMock(return_value=True)) as publish:
            result = await publish_xhs_ai.publish_with_xhs_ai(payload)

        self.assertTrue(result)
        self.assertEqual(calls["post"], (payload["title"], "完整正文", payload["images"], False))
        append.assert_awaited_once_with(unittest.mock.ANY, payload["tags"])
        publish.assert_awaited_once_with(unittest.mock.ANY, payload["title"])
        self.assertTrue(calls["cleaned"])


if __name__ == "__main__":
    unittest.main()
