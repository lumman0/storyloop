import unittest
from unittest.mock import patch

from agentscope.message import AssistantMsg, ThinkingBlock, TextBlock, UserMsg

from storyloop_harness.agents.openai_formatter import ThinkingSafeOpenAIChatFormatter


class ThinkingFormatterTests(unittest.IsolatedAsyncioTestCase):
    async def test_thinking_is_not_sent_back_and_does_not_warn(self) -> None:
        assistant = AssistantMsg(name="npc", content=[
            ThinkingBlock(thinking="private reasoning"),
            TextBlock(text="你好"),
        ])
        original = list(assistant.content)

        with patch("agentscope.formatter._openai_formatter.logger.warning") as warning:
            formatted = await ThinkingSafeOpenAIChatFormatter().format([
                UserMsg(name="player", content="hi"), assistant,
            ])

        self.assertIn("你好", str(formatted))
        self.assertNotIn("private reasoning", str(formatted))
        self.assertEqual(assistant.content, original)
        warning.assert_not_called()


if __name__ == "__main__":
    unittest.main()
