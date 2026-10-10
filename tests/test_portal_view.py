import unittest

from storyloop_harness.advanced import Snapshot
from storyloop_platform.portal.presentation import campaign_interaction
from storyloop_platform.runtime.campaign import CampaignProgram


class PortalPresentationTests(unittest.TestCase):
    def test_message_gate_exposes_only_player_choices_and_recipient_eligibility(self):
        program = CampaignProgram.from_dict({
            "id": "show", "ticks_per_day": 1, "final_tick": 1,
            "steps": [
                {"id": "start", "at": 0, "kind": "choice", "prompt": "开始",
                 "options": [{"id": "go", "label": "出发"}]},
                {"id": "night", "at": 0, "kind": "message", "prompt": "写一封信",
                 "options": [{"id": "a", "label": "甲", "recipient": "a"},
                             {"id": "b", "label": "乙", "recipient": "b"},
                             {"id": "skip", "label": "不写"}],
                 "incoming": [{"actor": "a", "label": "甲", "text": "隐藏来信",
                               "min_affinity": 2}]},
                {"id": "end", "at": 1, "kind": "finale", "choice_key": "start",
                 "threshold": 1, "success_text": "结束", "other_text": "结束"},
            ],
        })
        snapshot = Snapshot("g", 0, 0, {"campaign": {"cursor": 1, "met": {"a": True, "b": False}}})

        interaction = campaign_interaction(program, snapshot, "night")

        self.assertEqual(interaction, {
            "id": "night", "kind": "message", "prompt": "写一封信",
            "options": [{"id": "a", "label": "甲", "enabled": True, "requires_text": True},
                        {"id": "b", "label": "乙", "enabled": False, "requires_text": True},
                        {"id": "skip", "label": "不写", "enabled": True, "requires_text": False}],
        })
        self.assertNotIn("隐藏来信", str(interaction))


if __name__ == "__main__":
    unittest.main()
