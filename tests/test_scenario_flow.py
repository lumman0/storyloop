import tempfile
import unittest
from pathlib import Path

from storyloop_harness.core.contracts import Effect, PendingWork, Snapshot, WorldEvent
from storyloop_harness.runtime.player_input import submit_player_input
from storyloop_harness.runtime.runner import TurnRunner, WorkResult
from storyloop_harness.world.scenario import ScenarioPackage
from storyloop_harness.runtime.schedule import advance_time, scenario_cue
from storyloop_platform.adapters.store import SQLiteGameStore


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class ScenarioFlowTests(unittest.TestCase):
    def test_background_cue_accepts_declared_prior_phases(self) -> None:
        state = {"world": {"phase": "preparing"}, "actors": {"player": {"location": "villa"}}}
        work = PendingWork("meal-ready", "scenario_cue", 3, 10, None, {
            "event_kind": "meal_served", "summary": "晚餐摆上桌",
            "when_path": ["world", "phase"],
            "when_values": ["not_started", "planning", "preparing", "cooking"],
            "effect_path": ["world", "phase"], "effect_value": "served",
            "location": "villa", "sensory": "大家把晚餐端上桌。",
        })
        result = scenario_cue(Snapshot("game", 0, 3, state), work)

        self.assertEqual(result.event.effects[0].value, "served")

    def test_both_packages_advance_background_during_play(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "games.sqlite3"))
            for name, expected in (("freeform", "open"), ("scheduled", "handoff")):
                package = ScenarioPackage.load(EXAMPLES / name)
                game_id = name
                package.seed_game(store, game_id)
                self.assertEqual(TurnRunner(store, {"scenario_cue": scenario_cue}, 4).run(game_id).processed_work_ids, ())
                advance_time(store, game_id, 4, f"{name}:time-4")
                result = TurnRunner(store, {"scenario_cue": scenario_cue}, 4).run(game_id)
                self.assertEqual(len(result.processed_work_ids), 1)
                self.assertEqual(result.snapshot.tick // package.ticks_per_day + 1, 2)
                self.assertEqual(result.snapshot.data["world"]["market_phase" if name == "freeform" else "segment"], expected)
                actor_id = "dockhand" if name == "freeform" else "engineer"
                self.assertEqual(len(store.observations_for(game_id, actor_id)), 1)
                if name == "scheduled":
                    self.assertEqual(result.snapshot.data["plot"]["mission_phase"], "handoff_day")
                else:
                    self.assertEqual(result.snapshot.data["plot"]["market_day"], "first_day")

    def test_cue_is_consumed_without_forcing_a_stale_plot_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "games.sqlite3"))
            ScenarioPackage.load(EXAMPLES / "scheduled").seed_game(store, "game")
            store.commit(
                "game", 0,
                WorldEvent("player-changed-plan", "plan_changed", "player", None, 4,
                           (Effect(("world", "segment"), "private_trip"),)),
                (), (),
            )

            result = TurnRunner(store, {"scenario_cue": scenario_cue}, 4).run("game")

            self.assertEqual(result.processed_work_ids, ("relay-shift-handoff",))
            self.assertEqual(result.snapshot.data["world"]["segment"], "private_trip")
            self.assertEqual(result.snapshot.version, 1)

    def test_time_cannot_move_backward(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "games.sqlite3"))
            ScenarioPackage.load(EXAMPLES / "freeform").seed_game(store, "game")
            advance_time(store, "game", 2, "time-2")
            with self.assertRaisesRegex(ValueError, "backward"):
                advance_time(store, "game", 1, "time-1")

    def test_chat_turns_release_background_cue_before_npc_reply(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "games.sqlite3"))
            ScenarioPackage.load(EXAMPLES / "freeform").seed_game(store, "game")
            runner = TurnRunner(
                store,
                {"scenario_cue": scenario_cue, "npc_reply": lambda snapshot, work: WorkResult(None, (), ())},
                3,
            )
            for index in range(1, 4):
                submit_player_input(store, "game", f"input-{index}", "聊聊天", ("dockhand",))
                runner.run("game")
            submit_player_input(store, "game", "input-4", "再聊一会", ("dockhand",))

            result = runner.run("game")

            self.assertEqual(result.snapshot.tick, 4)
            self.assertEqual(result.processed_work_ids[0], "harbor-opening-cue")
            self.assertEqual(result.snapshot.data["world"]["market_phase"], "open")


if __name__ == "__main__":
    unittest.main()
