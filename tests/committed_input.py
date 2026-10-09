from storyloop_harness.advanced import WorldEvent


def commit_player_input(store, game_id, event_id, text, target_ids=()):
    before = store.load(game_id)
    return store.commit(game_id, before.version,
        WorldEvent(event_id, "player_input", "player", None, before.tick + 1, (),
                   {"text": text, "channel": "speech", "target_ids": list(target_ids),
                    "before_tick": before.tick, "duration_ticks": 1, "duration": "brief"}), (), ())
