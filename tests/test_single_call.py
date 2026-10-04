"""Focused contract checks for the default one-call story engine."""

import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from story_harness.adapters.store import SQLiteGameStore
from story_harness.agents.scene_turn import SceneContextProjector, SceneTurn
from story_harness.agents.scene_messages import MessageScene
from story_harness.core.contracts import Observation, WorldEvent
from story_harness.core.open_actions import parse_mutable_fields, validate_open_effects
from story_harness.core.contracts import Effect
from story_harness.agents.action_advisor import ActionOption
from story_harness.runtime.campaign import CampaignProgram, CampaignSession
from story_harness.runtime.single_call import SingleCallGameSession
from story_harness.runtime.story_clock import StoryClock
from story_harness.world.scenario import ScenarioPackage
from story_harness.world.worldbook import Worldbook, WorldbookEntry


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "freeform"


class FakeGenerator:
    def __init__(self, turn: dict) -> None:
        self.turn = turn
        self.calls = 0
        self.requests = []

    async def generate(self, game_id, context):
        self.calls += 1
        self.requests.append(context.request)
        return SceneTurn.model_validate(self.turn)


def a_turn(**changes):
    result = {
        "decision": {"intent": "speech", "target_ids": ["dockhand"]},
        "prose": "你听见码头工放下缆绳。",
        "replies": [{"actor_id": "dockhand", "speech": "今天有船靠岸。"}],
        "options": [
            {"label": "询问船期", "input": "我问码头工下一班船几点到。"},
            {"label": "看看告示", "input": "我走到告示板前查看。"},
            {"label": "沿岸走走", "input": "我沿着码头走一段。"},
        ],
    }
    result.update(changes)
    return result


class SingleCallTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = SQLiteGameStore(str(Path(temp.name) / "game.sqlite3"))
        self.package = replace(ScenarioPackage.load(EXAMPLE), presentation_mode="novel")
        self.package.seed_game(self.store, "game")

    def session(self, generator, program=None):
        clock = StoryClock(8, overnight_requires_rest=True)
        projector = SceneContextProjector(self.store, self.package,
                                          clock=clock, program=program)
        return SingleCallGameSession(self.store, self.package, generator, projector,
                                     clock=clock)

    async def test_one_call_persists_npc_context_and_replay_uses_saved_plan(self):
        generator = FakeGenerator(a_turn())
        session = self.session(generator)

        first = await session.run_turn("game", "早上好", "turn-1")
        replay = await session.run_turn("game", "早上好", "turn-1")

        self.assertEqual(generator.calls, 1)
        self.assertEqual(first.narration, replay.narration)
        self.assertEqual([item.kind for item in first.segments], ["scene"])
        self.assertTrue(self.store.event_exists("game", "turn-1:input:reply:dockhand:spoken"))
        own_context = self.store.agent_context_entries("game", "dockhand")
        self.assertTrue(any("今天有船靠岸" in item.content for item in own_context))
        self.assertFalse(any(item.channel == "shared_experience" for item in own_context))
        self.assertEqual(len(session.proposed_options("game", "turn-1")), 3)

    async def test_notable_shared_moment_enters_only_participant_context(self):
        generator = FakeGenerator(a_turn(
            decision={"intent": "action", "target_ids": ["dockhand"]},
            prose="你和码头工一起把木箱搬到岸边，放下时相视一笑。",
            action={"status": "occurred", "player_result": "木箱搬到了岸边",
                    "sensory": "两人共同搬动木箱", "effects": []},
            memories=[
                {"actor_id": "dockhand", "fact": "第一天和玩家共同搬动木箱，放下时相视一笑。"},
                {"actor_id": "unknown", "fact": "没有在场的人不应获得这段经历。"},
            ],
        ))
        session = self.session(generator)

        first = await session.run_turn("game", "我和码头工一起搬木箱", "turn-1")
        await session.run_turn("game", "我和码头工一起搬木箱", "turn-1")

        memories = [item for item in self.store.observations_for("game", "dockhand")
                    if item.channel == "shared_experience"]
        self.assertEqual([item.content for item in memories],
                         ["第一天和玩家共同搬动木箱，放下时相视一笑。"])
        self.assertFalse(any(item.channel == "shared_experience"
                             for item in self.store.observations_for("game", "player")))
        self.assertTrue(any(item.channel == "shared_experience"
                            for item in self.store.agent_context_entries("game", "dockhand")))
        self.assertEqual(generator.calls, 1)
        self.assertEqual([item.kind for item in first.segments], ["scene"])

        unseen = FakeGenerator(a_turn(
            decision={"intent": "action", "target_ids": ["dockhand"]},
            prose="你独自走到岸边，放下随身的包。",
            action={"status": "occurred", "player_result": "你放下了包",
                    "sensory": "玩家放下随身的包", "effects": []},
            memories=[{"actor_id": "dockhand", "fact": "码头工夸奖了玩家的包。"}],
        ))
        await self.session(unseen).run_turn("game", "我独自到岸边放下包", "turn-2")
        self.assertEqual(len([item for item in self.store.observations_for("game", "dockhand")
                              if item.channel == "shared_experience"]), 1)

    async def test_interactive_mode_keeps_npc_reply_as_separate_visible_segment(self):
        package = replace(self.package, presentation_mode="interactive")
        generator = FakeGenerator(a_turn())
        clock = StoryClock(8, overnight_requires_rest=True)
        session = SingleCallGameSession(
            self.store, package, generator,
            SceneContextProjector(self.store, package, clock=clock), clock=clock,
        )

        outcome = await session.run_turn("game", "早上好", "turn-1")

        self.assertEqual([item.kind for item in outcome.segments], ["scene", "dialogue"])
        self.assertEqual(outcome.segments[1].speaker_id, "dockhand")
        self.assertEqual(generator.calls, 1)

    async def test_actor_contexts_stay_separate_and_room_speech_is_observed(self):
        state = deepcopy(self.package.initial_state)
        state["actors"]["vendor"] = {"location": "harbor_square"}
        book = Worldbook(self.package.package_id, self.package.version,
                         [*self.package.worldbook._entries.values(),
                          WorldbookEntry("vendor_card", "摊主只知道自己的经历。", "actor",
                                         frozenset({"vendor"}), "card")])
        package = replace(self.package, initial_state=state,
                          actor_cards=(*self.package.actor_cards, ("vendor", "vendor_card")),
                          actor_names={**self.package.actor_names, "vendor": "摊主"},
                          worldbook=book)
        package.seed_game(self.store, "second")
        snapshot = self.store.load("second")
        self.store.commit("second", snapshot.version,
                          WorldEvent("vendor-secret", "private_fact", None, None, 0, ()),
                          (Observation("vendor-secret:seen", "vendor-secret", "vendor",
                                       "private_message", "只属于摊主的秘密", 0),), ())
        generator = FakeGenerator(a_turn(decision={"intent": "speech",
                                                  "target_ids": ["dockhand"],
                                                  "audience": "room"}))
        clock = StoryClock(8, overnight_requires_rest=True)
        session = SingleCallGameSession(
            self.store, package, generator,
            SceneContextProjector(self.store, package, clock=clock), clock=clock,
        )

        await session.run_turn("second", "大家好", "turn-1")

        request = generator.requests[0]
        self.assertNotIn("只属于摊主的秘密", str(request["player_history"]))
        dockhand_context = next(item for item in request["npc_contexts"]
                                if item["id"] == "dockhand")
        self.assertNotIn("只属于摊主的秘密", str(dockhand_context))
        self.assertTrue(any(item.content == "大家好"
                            for item in self.store.observations_for("second", "vendor")))
        self.assertTrue(any("码头工对玩家说" in item.content
                            for item in self.store.observations_for("second", "vendor")))

    async def test_invalid_action_effect_cannot_change_world(self):
        generator = FakeGenerator(a_turn(
            decision={"intent": "action", "target_ids": ["dockhand"]},
            action={"status": "occurred", "player_result": "窗户碎了",
                    "sensory": "玩家打破窗户", "effects": [
                        {"path": ["world", "shop_window", "broken"], "value": True}]},
        ))
        session = self.session(generator)

        result = await session.run_turn("game", "打破窗户", "turn-1")

        self.assertFalse(result.snapshot.data["world"]["shop_window"]["broken"])
        self.assertEqual(self.store.event_details("game", "turn-1:action")["outcome"], "attempted")
        self.assertEqual(generator.calls, 1)

    async def test_completed_activity_does_not_refill_old_scene_options(self):
        generator = FakeGenerator(a_turn(options=[]))
        session = self.session(generator)
        await session.run_turn("game", "我开始备菜", "turn-1")
        old_lead = ActionOption(label="开始备菜", input="我开始备菜。")

        self.assertEqual(session.proposed_options("game", "turn-1", (old_lead,)), ())

    async def test_projector_includes_player_identity_and_public_rules(self):
        book = Worldbook(self.package.package_id, self.package.version,
                         [*self.package.worldbook._entries.values(),
                          WorldbookEntry("filming_rule", "第一天只公布名字。", "public",
                                         frozenset(), "rule")])
        state = deepcopy(self.package.initial_state)
        state["player_profile"] = {"name": "林晚"}
        package = replace(self.package, worldbook=book, initial_state=state)
        package.seed_game(self.store, "profile-game")
        before = self.store.load("profile-game")
        self.store.commit("profile-game", before.version,
                          WorldEvent("recent-scene", "scene", None, None, 0, ()),
                          (Observation("recent-scene:player", "recent-scene", "player",
                                       "scene", "上午的光照在窗外雪坡上。", 0),), ())

        context = SceneContextProjector(self.store, package).project(
            self.store.load("profile-game"), "你好")

        self.assertEqual(context.request["player_profile"]["name"], "林晚")
        self.assertIn("第一天只公布名字。", context.request["public_rules"])
        self.assertIn("室内光线", context.request["avoid_repeated_scenery"])


    async def test_campaign_skips_second_presentation_call_for_free_action(self):
        program = CampaignProgram.from_dict({
            "id": self.package.package_id, "ticks_per_day": 4, "final_tick": 4,
            "steps": [
                {"id": "arrival", "at": 0, "kind": "scene", "text": "来到港口。"},
                {"id": "choice", "at": 2, "kind": "choice", "prompt": "找谁？",
                 "options": [{"id": "dockhand", "label": "码头工"}]},
                {"id": "end", "at": 4, "kind": "finale", "choice_key": "choice",
                 "threshold": 0, "success_text": "结束", "other_text": "结束"},
            ],
        })
        before = self.store.load("game")
        state = deepcopy(before.data)
        state["campaign"] = program.initial_state(["dockhand"])
        self.store.create_game(replace(before, game_id="campaign", data=state))
        generator = FakeGenerator(a_turn())
        clock = StoryClock(8, overnight_requires_rest=True)
        react = SingleCallGameSession(
            self.store, self.package, generator,
            SceneContextProjector(self.store, self.package, clock=clock, program=program),
            clock=clock,
        )

        class ForbiddenPresenter:
            async def present(self, context):
                raise AssertionError("ordinary turn must not call a second model")

        campaign = CampaignSession(self.store, program, react, turns_per_story_tick=1,
                                   novel_presenter=ForbiddenPresenter(),
                                   skip_react_presentation=True)
        await campaign.start("campaign", present_opening=False)
        outcome = await campaign.submit("campaign", "你好", "turn-1")

        self.assertEqual(generator.calls, 1)
        self.assertIn("码头工", outcome.text)
        self.assertFalse(any(item.kind == "time" for item in outcome.segments))

    async def test_message_gate_uses_one_batch_writer_and_saves_recipient_memory(self):
        program = CampaignProgram.from_dict({
            "id": self.package.package_id, "ticks_per_day": 4, "final_tick": 4,
            "steps": [
                {"id": "intro", "at": 0, "kind": "scene", "text": "夜里收到愿望卡。"},
                {"id": "partner", "at": 0, "kind": "choice", "prompt": "认识谁？",
                 "options": [{"id": "dockhand", "label": "码头工", "meet": "dockhand"}]},
                {"id": "message", "at": 0, "kind": "message", "prompt": "给谁留言？",
                 "options": [{"id": "dockhand", "label": "码头工", "recipient": "dockhand"}],
                 "incoming": [{"actor": "dockhand", "label": "码头工", "text": "剧本备用短信",
                               "min_affinity": 0}]},
                {"id": "end", "at": 4, "kind": "finale", "choice_key": "partner",
                 "threshold": 0, "success_text": "结束", "other_text": "结束"},
            ],
        })
        before = self.store.load("game")
        state = deepcopy(before.data)
        state["campaign"] = program.initial_state(["dockhand"])
        self.store.create_game(replace(before, game_id="message-game", data=state))

        class BatchWriter:
            def __init__(self):
                self.calls = []

            async def write(self, game_id, senders, recipient, player_note, fallback):
                self.calls.append((senders, recipient, player_note))
                return MessageScene("夜色里，留言送了出去。", {"dockhand": "我也想再聊聊。"})

        writer = BatchWriter()
        campaign = CampaignSession(self.store, program,
                                   turns_per_story_tick=1,
                                   message_batch_writer=writer,
                                   skip_react_presentation=True)
        await campaign.start("message-game", present_opening=False)
        await campaign.submit("message-game", "/choose dockhand", "partner-turn")
        outcome = await campaign.submit("message-game", "/choose dockhand 你好", "message-turn")

        self.assertEqual(writer.calls, [(('dockhand',), 'dockhand', '你好')])
        self.assertIn("我也想再聊聊", outcome.text)
        self.assertTrue(any(item.content == "你好" for item in
                            self.store.observations_for("message-game", "dockhand")))


class ActivityTransitionTests(unittest.TestCase):
    def test_declared_activity_rejects_skipping_stages(self):
        state = {"world": {"meal_phase": "preparing"}}
        fields = parse_mutable_fields([{
            "path": ["world", "meal_phase"],
            "values": ["preparing", "cooking", "served"],
            "transitions": [
                {"from": "preparing", "to": ["cooking"]},
                {"from": "cooking", "to": ["served"]},
            ],
        }], state)

        self.assertEqual(fields[0].next_values("preparing"), ("cooking",))
        validate_open_effects((Effect(("world", "meal_phase"), "cooking"),), fields, state)
        with self.assertRaises(ValueError):
            validate_open_effects((Effect(("world", "meal_phase"), "served"),), fields, state)


if __name__ == "__main__":
    unittest.main()
