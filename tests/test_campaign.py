import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from story_harness.adapters.store import SQLiteGameStore
from story_harness.core.contracts import Effect, PendingWork, Snapshot, WorldEvent
from story_harness.runtime.campaign import CampaignProgram, CampaignSession
from story_harness.runtime.runner import TurnRunner
from story_harness.runtime.schedule import scenario_cue


class FakeReact:
    def __init__(self, store):
        self.store = store
        self.calls = []

    async def run_turn(self, game_id, text, turn_id):
        self.calls.append(text)
        before = self.store.load(game_id)
        after = self.store.commit(game_id, before.version,
                                  WorldEvent(f"{turn_id}:input", "player_input", "player", None, before.tick + 1, (),
                                             {"text": text, "target_ids": ["m1"]}), (), ())
        return SimpleNamespace(narration="对话完成", decision=SimpleNamespace(intent="speech", target_ids=["m1"]), snapshot=after)


def program():
    return CampaignProgram.from_dict({
        "id": "test-show", "ticks_per_day": 2, "final_tick": 4,
        "steps": [
            {"id": "arrival", "at": 0, "kind": "choice", "prompt": "选行李牌",
             "options": [{"id": "m1", "label": "甲"}, {"id": "m2", "label": "乙"}]},
            {"id": "opening", "at": 0, "kind": "scene", "text": "节目开始",
             "observations": [{"recipient": "m1", "text": "甲知道的事"}]},
            {"id": "message", "at": 1, "kind": "message", "prompt": "发送心动留言",
             "options": [{"id": "m1", "label": "甲", "recipient": "m1", "affinity": {"m1": 2}},
                         {"id": "m2", "label": "乙", "recipient": "m2"},
                         {"id": "skip", "label": "不发"}],
             "incoming": [{"actor": "m1", "label": "甲", "text": "今天和你聊天很开心。", "min_affinity": 2}]},
            {"id": "reveal", "at": 2, "kind": "scene", "text": "愿望卡揭晓：",
             "reveal_answers": ["arrival"]},
            {"id": "final_choice", "at": 3, "kind": "choice", "prompt": "最终选择",
             "options": [{"id": "m1", "label": "甲"}, {"id": "solo", "label": "独自离开"}]},
            {"id": "ending", "at": 4, "kind": "finale", "choice_key": "final_choice",
             "threshold": 2, "success_text": "双向选择", "other_text": "独自离开",
             "rejected_text": "对方没有做出相同选择。",
             "bonus_choice_key": "arrival", "bonus_text": "最初的行李牌也选中了他。"},
        ],
    })


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = SQLiteGameStore(str(Path(self.directory.name) / "game.sqlite3"))
        self.program = program()
        self.store.create_game(Snapshot("g", 0, 0, {
            "scenario": {"id": "test-show", "version": "1"},
            "actors": {"player": {"location": "villa"}, "m1": {"location": "villa"},
                       "m2": {"location": "villa"}},
            "campaign": self.program.initial_state(["m1", "m2"]),
        }))
        self.react = FakeReact(self.store)
        self.session = CampaignSession(self.store, self.program, self.react)

    def tearDown(self):
        self.directory.cleanup()

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_gate_blocks_react_and_scheduled_scene_advances_once(self):
        start = self.run_async(self.session.start("g"))
        self.assertEqual(start.gate_id, "arrival")
        self.assertEqual(start.segments[-1].kind, "prompt")
        blocked = self.run_async(self.session.submit("g", "随便聊聊", "t0"))
        self.assertEqual(blocked.gate_id, "arrival")
        self.assertEqual(self.react.calls, [])
        chosen = self.run_async(self.session.submit("g", "/choose m1", "t1"))
        self.assertIn("节目开始", chosen.text)
        self.assertEqual([part.kind for part in chosen.segments], ["narration", "scene"])
        self.assertEqual(self.store.load("g").data["campaign"]["choices"]["arrival"], "m1")
        self.assertEqual(len(self.store.observations_for("g", "m1")), 1)
        self.assertEqual(self.store.observations_for("g", "m2"), [])
        self.run_async(self.session.start("g"))
        self.assertEqual(len(self.store.observations_for("g", "m1")), 1)

    def test_chat_advances_clock_and_private_message_is_recipient_scoped(self):
        self.run_async(self.session.start("g"))
        self.run_async(self.session.submit("g", "/choose m1", "t1"))
        result = self.run_async(self.session.submit("g", "和甲聊天", "t2"))
        self.assertEqual(result.gate_id, "message")
        self.assertEqual(result.snapshot.tick, 1)
        self.assertTrue(result.snapshot.data["campaign"]["met"]["m1"])
        result = self.run_async(self.session.submit("g", "/choose m1 今晚很开心", "t3"))
        self.assertEqual(result.snapshot.data["campaign"]["messages"]["message"], "今晚很开心")
        self.assertEqual(result.snapshot.data["campaign"]["affinity"]["m1"], 4)
        self.assertTrue(any(o.channel == "private_message" and "今晚很开心" in o.content
                            for o in self.store.observations_for("g", "m1")))
        self.assertFalse(any("今晚很开心" in o.content for o in self.store.observations_for("g", "m2")))
        self.assertTrue(any("今晚很开心" in o.content for o in self.store.observations_for("g", "player")))
        self.assertIn("今天和你聊天很开心", result.text)
        self.assertEqual(result.snapshot.data["campaign"]["incoming"]["message"], ["m1"])
        self.assertTrue(any(o.channel == "outgoing_message" for o in self.store.observations_for("g", "m1")))
        self.assertFalse(any("今天和你聊天很开心" in o.content for o in self.store.observations_for("g", "m2")))
        self.assertRaises(ValueError, lambda: self.run_async(self.session.submit("g", "/choose m2", "t3-repeat")))

    def test_finale_depends_on_player_choice_and_affinity(self):
        self.run_async(self.session.start("g"))
        self.run_async(self.session.submit("g", "/choose m1", "t1"))
        self.run_async(self.session.submit("g", "和甲聊天", "t2"))
        self.run_async(self.session.submit("g", "/choose m1 今晚很开心", "t3"))
        self.run_async(self.session.submit("g", "/next", "t4"))
        result = self.run_async(self.session.submit("g", "/next", "t5"))
        self.assertEqual(result.gate_id, "final_choice")
        self.run_async(self.session.submit("g", "/choose m1", "t6"))
        result = self.run_async(self.session.submit("g", "/next", "t7"))
        self.assertTrue(result.complete)
        self.assertEqual(result.snapshot.data["campaign"]["ending"], "paired:m1")
        self.assertIn("双向选择", result.text)
        self.assertIn("最初的行李牌也选中了他", result.text)

    def test_choice_records_players_own_words(self):
        self.run_async(self.session.start("g"))
        result = self.run_async(self.session.submit("g", "/choose m1 我想慢慢认识你", "own-words"))
        self.assertEqual(result.snapshot.data["campaign"]["answers"]["arrival"], "我想慢慢认识你")
        self.run_async(self.session.submit("g", "/next", "reveal-1"))
        result = self.run_async(self.session.submit("g", "/choose skip", "reveal-2"))
        result = self.run_async(self.session.submit("g", "/next", "reveal-3"))
        self.assertIn("我想慢慢认识你", result.text)

    def test_choice_can_mark_a_date_partner_met(self):
        dated = CampaignProgram.from_dict({
            "id": "date", "ticks_per_day": 2, "final_tick": 2,
            "steps": [
                {"id": "date", "at": 0, "kind": "choice", "prompt": "选择约会对象",
                 "options": [{"id": "m2", "label": "乙", "meet": "m2", "affinity": {"m2": 2}}]},
                {"id": "end_choice", "at": 1, "kind": "choice", "prompt": "最终选择",
                 "options": [{"id": "m2", "label": "乙"}]},
                {"id": "end", "at": 2, "kind": "finale", "choice_key": "end_choice",
                 "threshold": 2, "success_text": "牵手", "other_text": "离开"},
            ],
        })
        self.store.create_game(Snapshot("date", 0, 0, {
            "scenario": {"id": "date", "version": "1"},
            "actors": {"player": {"location": "villa"}, "m2": {"location": "villa"}},
            "campaign": dated.initial_state(["m2"]),
        }))
        session = CampaignSession(self.store, dated)
        self.run_async(session.start("date"))
        result = self.run_async(session.submit("date", "/choose m2", "date-1"))
        self.assertTrue(result.snapshot.data["campaign"]["met"]["m2"])
        self.assertEqual(result.snapshot.data["campaign"]["affinity"]["m2"], 2)
        self.assertTrue(any("约会" in item.content for item in self.store.observations_for("date", "m2")))
        self.assertTrue(any("乙" in item.content for item in self.store.observations_for("date", "player")))

    def test_campaign_turns_emit_session_scoped_steps(self):
        calls = []

        class Span:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def update(self, **kwargs):
                calls.append(("update", kwargs))

            def metric(self, name, value):
                calls.append(("metric", name, value))

        class Telemetry:
            capture_content = False

            def span(self, name, metadata, **kwargs):
                calls.append(("span", name, metadata, kwargs))
                return Span()

        session = CampaignSession(self.store, self.program, self.react, telemetry=Telemetry())
        self.run_async(session.start("g"))
        self.run_async(session.submit("g", "/choose m1", "trace-choice"))
        roots = [call for call in calls if call[0] == "span" and call[1] in {"campaign-start", "campaign-turn"}]
        self.assertEqual([call[3]["session_id"] for call in roots], ["test-show:g", "test-show:g"])
        self.assertTrue(any(call[:2] == ("span", "campaign-step") for call in calls))
        self.assertTrue(any(call[:2] == ("span", "campaign-choice") for call in calls))

    def test_inspection_does_not_raise_affinity_even_if_target_was_proposed(self):
        class InspectReact(FakeReact):
            async def run_turn(self, game_id, text, turn_id):
                result = await super().run_turn(game_id, text, turn_id)
                result.decision.intent = "inspect"
                return result

        session = CampaignSession(self.store, self.program, InspectReact(self.store))
        self.run_async(session.start("g"))
        self.run_async(session.submit("g", "/choose m1", "inspect-gate"))
        result = self.run_async(session.submit("g", "看看周围", "inspect-turn"))
        self.assertFalse(result.snapshot.data["campaign"]["met"]["m1"])
        self.assertEqual(result.snapshot.data["campaign"]["affinity"]["m1"], 0)

    def test_unreciprocated_final_choice_has_distinct_narration(self):
        self.run_async(self.session.start("g"))
        self.run_async(self.session.submit("g", "/choose m1", "rejected-1"))
        self.run_async(self.session.submit("g", "/next", "rejected-2"))
        self.run_async(self.session.submit("g", "/choose skip", "rejected-3"))
        self.run_async(self.session.submit("g", "/next", "rejected-4"))
        self.run_async(self.session.submit("g", "/next", "rejected-5"))
        self.run_async(self.session.submit("g", "/choose m1", "rejected-6"))
        result = self.run_async(self.session.submit("g", "/next", "rejected-7"))
        self.assertEqual(result.snapshot.data["campaign"]["ending"], "solo")
        self.assertIn("对方没有做出相同选择", result.text)

    def test_campaign_refuses_game_from_another_scenario(self):
        self.store.create_game(Snapshot("foreign", 0, 0, {
            "scenario": {"id": "other-show", "version": "1"},
            "actors": {"player": {"location": "villa"}},
            "campaign": self.program.initial_state(["m1"]),
        }))
        with self.assertRaisesRegex(ValueError, "scenario"):
            self.run_async(self.session.start("foreign"))
        self.assertEqual(self.store.load("foreign").version, 0)

    def test_program_requires_one_terminal_finale_at_final_tick(self):
        base = {"id": "broken", "ticks_per_day": 2, "final_tick": 2,
                "steps": [{"id": "scene", "at": 0, "kind": "scene", "text": "开始"}]}
        with self.assertRaisesRegex(ValueError, "finale"):
            CampaignProgram.from_dict(base)
        base["steps"].append({"id": "ending", "at": 1, "kind": "finale",
                              "choice_key": "choice", "threshold": 1,
                              "success_text": "好", "other_text": "结束"})
        with self.assertRaisesRegex(ValueError, "finale"):
            CampaignProgram.from_dict(base)

    def test_program_requires_finale_narration_fields(self):
        raw = {"id": "broken", "ticks_per_day": 2, "final_tick": 1,
               "steps": [
                   {"id": "choice", "at": 0, "kind": "choice", "prompt": "选择",
                    "options": [{"id": "solo", "label": "独自"}]},
                   {"id": "end", "at": 1, "kind": "finale", "choice_key": "choice",
                    "threshold": 1, "other_text": "结束"},
               ]}
        with self.assertRaisesRegex(ValueError, "finale.*text"):
            CampaignProgram.from_dict(raw)
        raw["steps"][1]["success_text"] = "牵手"
        raw["steps"][1].pop("other_text")
        with self.assertRaisesRegex(ValueError, "finale.*text"):
            CampaignProgram.from_dict(raw)

    def test_day_updates_when_schedule_has_no_scene_for_that_day(self):
        sparse = CampaignProgram.from_dict({
            "id": "sparse", "ticks_per_day": 2, "final_tick": 6,
            "steps": [
                {"id": "opening", "at": 0, "kind": "choice", "prompt": "开始",
                 "options": [{"id": "solo", "label": "独自"}]},
                {"id": "ending", "at": 6, "kind": "finale", "choice_key": "opening",
                 "threshold": 1, "success_text": "好", "other_text": "结束"},
            ],
        })
        self.store.create_game(Snapshot("sparse", 0, 0, {
            "scenario": {"id": "sparse", "version": "1"},
            "actors": {"player": {"location": "villa"}},
            "campaign": sparse.initial_state([]),
        }))
        session = CampaignSession(self.store, sparse)
        self.run_async(session.start("sparse"))
        self.run_async(session.submit("sparse", "/choose solo", "sparse-0"))
        self.run_async(session.submit("sparse", "/next", "sparse-1"))
        result = self.run_async(session.submit("sparse", "/next", "sparse-2"))
        self.assertEqual(result.snapshot.tick, 2)
        self.assertEqual(result.snapshot.data["campaign"]["day"], 2)

    def test_next_drains_due_world_work_before_campaign_gate(self):
        class QueueReact(FakeReact):
            async def run_ready_work(self, game_id):
                return await TurnRunner(self.store, {"scenario_cue": scenario_cue}, 8).run_async(game_id)

        cue = PendingWork("weather-cue", "scenario_cue", 1, 10, None, {
            "event_kind": "weather_changed", "summary": "雪停了",
            "effects": [{"path": ["world", "weather"], "value": "clear"}],
            "location": "villa", "sensory": "雪停了，天空变亮。",
        })
        self.store.create_game(Snapshot("queue", 0, 0, {
            "scenario": {"id": "test-show", "version": "1"},
            "world": {"weather": "snow"},
            "actors": {"player": {"location": "villa"}, "m1": {"location": "villa"}},
            "campaign": self.program.initial_state(["m1"]),
        }), (cue,))
        session = CampaignSession(self.store, self.program, QueueReact(self.store))
        self.run_async(session.start("queue"))
        self.run_async(session.submit("queue", "/choose m1", "queue-choice"))
        result = self.run_async(session.submit("queue", "/next", "queue-next"))
        self.assertEqual(result.gate_id, "message")
        self.assertEqual(result.snapshot.data["world"]["weather"], "clear")
        self.assertEqual(self.store.pending_work("queue"), [])
        self.assertIn("雪停了，天空变亮", result.text)

    def test_react_turn_drains_work_left_by_its_step_budget_before_campaign_gate(self):
        cue = PendingWork("chat-cue", "scenario_cue", 1, 10, None, {
            "event_kind": "weather_changed", "summary": "雪停了",
            "effects": [{"path": ["world", "weather"], "value": "clear"}],
            "location": "villa", "sensory": "雪停了，天空变亮。",
        })

        class BudgetReact(FakeReact):
            async def run_turn(self, game_id, text, turn_id):
                result = await super().run_turn(game_id, text, turn_id)
                self.store.commit(game_id, result.snapshot.version, None, (), (cue,))
                return result

            async def run_ready_work(self, game_id):
                return await TurnRunner(self.store, {"scenario_cue": scenario_cue}, 8).run_async(game_id)

        self.store.create_game(Snapshot("chat-queue", 0, 0, {
            "scenario": {"id": "test-show", "version": "1"},
            "world": {"weather": "snow"},
            "actors": {"player": {"location": "villa"}, "m1": {"location": "villa"}},
            "campaign": self.program.initial_state(["m1"]),
        }))
        session = CampaignSession(self.store, self.program, BudgetReact(self.store))
        self.run_async(session.start("chat-queue"))
        self.run_async(session.submit("chat-queue", "/choose m1", "chat-choice"))
        result = self.run_async(session.submit("chat-queue", "你好", "chat-turn"))
        self.assertEqual(result.snapshot.data["world"]["weather"], "clear")
        self.assertEqual(result.gate_id, "message")
        self.assertIn("雪停了，天空变亮", result.text)

    def test_retrying_same_choice_or_next_id_does_not_apply_it_twice(self):
        self.run_async(self.session.start("g"))
        first = self.run_async(self.session.submit("g", "/choose m1", "same-choice"))
        self.assertEqual(self.store.completed_turn_count("g"), 1)
        repeated = self.run_async(self.session.submit("g", "/choose m1", "same-choice"))
        self.assertEqual(repeated.snapshot.version, first.snapshot.version)
        self.assertEqual(self.store.completed_turn_count("g"), 1)
        next_turn = self.run_async(self.session.submit("g", "/next", "same-next"))
        repeated_next = self.run_async(self.session.submit("g", "/next", "same-next"))
        self.assertEqual(next_turn.snapshot.tick, 1)
        self.assertEqual(repeated_next.snapshot.tick, 1)
        self.assertEqual(self.store.completed_turn_count("g"), 2)

    def test_completed_turn_keeps_player_output_for_restart(self):
        self.run_async(self.session.start("g"))
        result = self.run_async(self.session.submit("g", "/choose m1", "campaign-turn-0"))
        details = self.store.event_details("g", "campaign-turn-0:completed")
        self.assertEqual(details["display_text"], result.text)
        self.assertIn("节目开始", details["display_text"])

    def test_same_turn_id_with_different_input_is_rejected(self):
        self.run_async(self.session.start("g"))
        self.run_async(self.session.submit("g", "/choose m1", "same-id"))
        with self.assertRaisesRegex(ValueError, "different input"):
            self.run_async(self.session.submit("g", "/choose m2", "same-id"))
        self.assertEqual(self.store.completed_turn_count("g"), 1)

    def test_incomplete_choice_can_be_recovered_before_next_prompt(self):
        self.run_async(self.session.start("g"))
        before = self.store.load("g")
        self.store.commit("g", before.version,
                          WorldEvent("campaign-turn-0:choice", "campaign_choice", "player", None, 0,
                                     (Effect(("campaign", "cursor"), 1),
                                      Effect(("campaign", "choices", "arrival"), "m1")),
                                     {"request_text": "/choose m1", "option_id": "m1"}), (), ())
        with self.assertRaisesRegex(ValueError, "different input"):
            self.run_async(self.session.submit("g", "/choose m2", "campaign-turn-0"))
        recovered = self.run_async(self.session.recover_turn("g", "campaign-turn-0"))
        self.assertIsNotNone(recovered)
        self.assertEqual(self.store.completed_turn_count("g"), 1)
        self.assertIn("节目开始", recovered.text)
        next_turn = self.run_async(self.session.submit("g", "/next", "campaign-turn-1"))
        self.assertEqual(next_turn.snapshot.tick, 1)

    def test_future_slow_npc_work_is_rejected_before_next_commits_clock(self):
        self.run_async(self.session.start("g"))
        self.run_async(self.session.submit("g", "/choose m1", "opening-choice"))
        before = self.store.load("g")
        self.store.commit("g", before.version, None, (), (PendingWork(
            "late-slow-reply", "npc_reply", 1, 10, None,
            {"actor_id": "m1", "player_message": "你好", "duration_ticks": 2},
        ),))

        with self.assertRaisesRegex(ValueError, "campaign.*duration_ticks"):
            self.run_async(self.session.submit("g", "/next", "next-turn"))
        self.assertEqual(self.store.load("g").tick, 0)
        self.assertFalse(self.store.event_exists("g", "next-turn:advance"))

    def test_retry_reconciles_committed_speech_without_repeat_model_call(self):
        self.run_async(self.session.start("g"))
        self.run_async(self.session.submit("g", "/choose m1", "first-choice"))
        before = self.store.load("g")
        self.store.commit("g", before.version,
                          WorldEvent("recover:input", "player_input", "player", None, 1, (),
                                     {"text": "hi", "target_ids": ["m1"], "channel": "speech"}), (), ())
        result = self.run_async(self.session.submit("g", "hi", "recover"))
        self.assertEqual(self.react.calls, [])
        self.assertEqual(result.snapshot.data["campaign"]["affinity"]["m1"], 1)
        self.assertEqual(result.gate_id, "message")
        repeated = self.run_async(self.session.submit("g", "hi", "recover"))
        self.assertEqual(repeated.snapshot.data["campaign"]["affinity"]["m1"], 1)

    def test_restart_reconciles_speech_committed_before_affinity(self):
        self.run_async(self.session.start("g"))
        self.run_async(self.session.submit("g", "/choose m1", "opening-choice"))
        before = self.store.load("g")
        self.store.commit("g", before.version,
                          WorldEvent("unfinished:input", "player_input", "player", None, 1, (),
                                     {"text": "hi", "target_ids": ["m1"], "channel": "speech"}), (), ())
        resumed = CampaignSession(self.store, self.program, self.react)
        result = self.run_async(resumed.start("g"))
        self.assertEqual(result.snapshot.data["campaign"]["affinity"]["m1"], 1)
        self.assertTrue(result.snapshot.data["campaign"]["met"]["m1"])


if __name__ == "__main__":
    unittest.main()
