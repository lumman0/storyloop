import unittest

from story_harness.core.contracts import Effect, Snapshot, WorldEvent
from story_harness.core.state import apply_event


class ApplyEventTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = Snapshot(
            game_id="game-1",
            version=0,
            tick=3,
            data={"world": {"window": {"broken": False}}},
        )

    def test_applies_nested_effect_without_mutating_previous_snapshot(self) -> None:
        event = WorldEvent(
            event_id="break-window",
            kind="window_broken",
            actor_id="player",
            cause_id=None,
            tick=4,
            effects=(Effect(("world", "window", "broken"), True),),
        )

        updated = apply_event(self.snapshot, event)

        self.assertEqual(updated.version, 1)
        self.assertEqual(updated.tick, 4)
        self.assertTrue(updated.data["world"]["window"]["broken"])
        self.assertFalse(self.snapshot.data["world"]["window"]["broken"])

    def test_rejects_effect_target_that_does_not_exist(self) -> None:
        event = WorldEvent(
            event_id="invent-key",
            kind="key_appeared",
            actor_id="player",
            cause_id=None,
            tick=4,
            effects=(Effect(("world", "key", "found"), True),),
        )

        with self.assertRaises(ValueError):
            apply_event(self.snapshot, event)

    def test_rejects_event_before_current_tick(self) -> None:
        event = WorldEvent(
            event_id="late-event",
            kind="window_broken",
            actor_id="player",
            cause_id=None,
            tick=2,
            effects=(Effect(("world", "window", "broken"), True),),
        )

        with self.assertRaises(ValueError):
            apply_event(self.snapshot, event)


if __name__ == "__main__":
    unittest.main()
