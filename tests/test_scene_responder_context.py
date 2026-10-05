"""Source-driven responders need their own projected role and history."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from story_harness.adapters.store import SQLiteGameStore
from story_harness.agents.scene_turn import SceneContextProjector, SceneTurn
from story_harness.core.contracts import Observation, WorldEvent
from story_harness.runtime.agent_context import estimate_tokens
from story_harness.runtime.single_call import SingleCallGameSession
from story_harness.world.scenario import ScenarioPackage
from story_harness.world.story_blueprint import StoryBlueprint
from story_harness.world.worldbook import Worldbook, WorldbookEntry


ROOT = Path(__file__).resolve().parents[1]


def source_package():
    base = ScenarioPackage.load(ROOT / "examples/freeform")
    state = deepcopy(base.initial_state)
    names = {"dockhand": "Dockhand", "vendor": "Vendor", "guard": "Guard", "guide": "Guide"}
    for actor_id in names:
        state["actors"][actor_id] = {"location": "harbor_square"}
    cards = tuple((actor_id, f"{actor_id}_card") for actor_id in names)
    book = Worldbook(base.package_id, base.version, [
        WorldbookEntry(card, f"{names[actor_id]} knows only their own harbor experiences. " * 8,
                       "actor", frozenset({actor_id}), "card")
        for actor_id, card in cards
    ])
    blueprint = StoryBlueprint.model_validate({
        "source_document": "Synthetic harbor story",
        "opening_focus": "Four workers share a public harbor scene.",
        "setup": {"player_options": [{"id": "random", "label": "Visitor", "guidance": "Visitor",
                                     "source_ref": "Source"}],
                  "tone_options": [{"id": "slow", "label": "Slow", "guidance": "Patient",
                                   "source_ref": "Source"}]},
        "facts": [{"id": "harbor", "text": "Visitors arrive by boat.",
                   "source_ref": "Source", "visibility": "public"}],
    })
    return replace(base, initial_state=state, actor_cards=cards, actor_names=names,
                   worldbook=book, story_blueprint=blueprint, initial_work=(),
                   presentation_mode="interactive")


class SceneResponderContextTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = SQLiteGameStore(str(Path(temp.name) / "game.sqlite3"))
        self.package = source_package()
        self.package.seed_game(self.store, "game")
        self.projector = SceneContextProjector(self.store, self.package)

    def test_four_person_source_scene_only_allows_projected_responders(self):
        context = self.projector.project(self.store.load("game"), "Hello everyone")
        self.assertEqual(len(context.nearby_actor_ids), 4)
        projected = tuple(item["id"] for item in context.request["npc_contexts"])
        self.assertEqual(context.request["candidate_responders"], list(projected))
        self.assertEqual(context.focus_actor_ids, projected)
        self.assertEqual(len(projected), 3)

    def test_explicitly_named_fourth_actor_gets_their_own_role_and_history(self):
        snapshot = self.store.load("game")
        self.store.commit("game", snapshot.version,
            WorldEvent("guide-secret", "private_fact", None, None, 0, ()),
            (Observation("guide-secret:seen", "guide-secret", "guide", "private_message",
                         "Guide privately saw the missing boat.", 0),), ())
        context = self.projector.project(self.store.load("game"), "Guide, what did you see?")
        self.assertEqual(context.focus_actor_ids[0], "guide")
        own = context.request["npc_contexts"][0]
        self.assertIn("Guide", own["role_card"])
        self.assertIn("missing boat", str(own["own_history"]))
        self.assertNotIn("missing boat", str(context.request["npc_contexts"][1:]))

    def test_unprojected_actor_is_removed_from_replies_targets_and_memories(self):
        before = self.store.load("game")
        context = self.projector.project(before, "Hello everyone")
        plan = SceneTurn.model_validate({
            "decision": {"intent": "speech", "target_ids": ["dockhand", "guide"]},
            "prose": "Dockhand and Guide greet you.",
            "replies": [{"actor_id": actor_id, "speech": "Welcome."}
                        for actor_id in ("dockhand", "guide")],
            "memories": [{"actor_id": actor_id, "fact": "Greeted the visitor."}
                         for actor_id in ("dockhand", "guide")],
        })
        session = SingleCallGameSession(self.store, self.package, None, self.projector)
        validated = session._validate_plan(before, plan, context.focus_actor_ids,
                                           context.nearby_actor_ids)
        self.assertEqual([item.actor_id for item in validated.replies], ["dockhand"])
        self.assertEqual(validated.decision.target_ids, ["dockhand"])
        self.assertEqual([item.actor_id for item in validated.memories], ["dockhand"])

    def test_empty_generated_card_falls_back_to_authored_role(self):
        before = self.store.load("game")
        before.data["actor_profiles"] = {"guide": {"role_card": "   "}}
        context = self.projector.project(before, "Guide, hello")
        self.assertTrue(context.request["npc_contexts"][0]["role_card"].strip())

    def test_source_mention_does_not_expand_responders_beyond_present_cast(self):
        before = self.store.load("game")
        before.data["actors"]["guide"]["location"] = "another_room"
        context = self.projector.project(before, "Guide, hello")
        self.assertNotIn("guide", context.focus_actor_ids)
        self.assertNotIn("guide", context.request["candidate_responders"])

    def test_budget_exhaustion_cannot_erase_all_responder_role_cards(self):
        before = self.store.load("game")
        minimal = deepcopy(self.projector.project(before, "").request)
        minimal["public_setting"] = []
        for item in minimal["npc_contexts"]:
            item["role_card"] = ""
        # Fill the real estimator's 4,800-token budget with mandatory envelope
        # and player text: the old loop can only fit by emptying every role card.
        remaining = 4800 - estimate_tokens(json.dumps(minimal, ensure_ascii=False))
        constrained = SceneContextProjector(self.store, self.package, context_window_tokens=1024)
        with self.assertRaisesRegex(ValueError, "responder role"):
            constrained.project(before, "x" * remaining)
