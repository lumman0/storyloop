"""Character histories remain bounded, recipient-scoped data after restart."""
import json

from storyloop_harness.advanced import Observation, WorldEvent, estimate_tokens
from storyloop_harness.testing import project_scene_request
from storyloop_platform.adapters.store import SQLiteGameStore
from scenario_fixtures import source_package


def test_character_history_budget_and_visibility_survive_sql_restart(tmp_path):
    path = str(tmp_path / 'world.sqlite3')
    store = SQLiteGameStore(path)
    package = source_package()
    package.seed_game(store, 'save-a')
    package.seed_game(store, 'save-b')
    for index in range(18):
        before = store.load('save-a')
        event_id = f'private-{index}'
        store.commit('save-a', before.version,
            WorldEvent(event_id, 'private_fact', None, None, before.tick, ()),
            (Observation(event_id + ':seen', event_id, 'guide', 'private_message',
                         f'Guide secret {index}: ' + 'quiet harbor recollection ' * 50, before.tick),), ())
    def project(database, game):
        return project_scene_request(database, package, game, 'Guide, what do you remember?',
                                     context_window_tokens=7200)
    first = project(store, 'save-a')
    assert estimate_tokens(json.dumps(first, ensure_ascii=False)) <= 4800
    own = next(item for item in first['npc_contexts'] if item['id'] == 'guide')
    assert 'Guide secret 17' in str(own['own_history'])
    assert 'Guide secret' not in str(first['player_history'])
    assert all('Guide secret' not in str(item['own_history'])
               for item in first['npc_contexts'] if item['id'] != 'guide')
    reopened = SQLiteGameStore(path)
    assert project(reopened, 'save-a') == first
    assert 'Guide secret' not in str(project(reopened, 'save-b'))
