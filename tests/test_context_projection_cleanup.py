import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from storyloop_platform.portal.http_api import create_app

from storyloop_harness.advanced import PendingWork
from storyloop_platform.adapters.runtime_config import HarnessConfig
from test_turn_failure_contract import portal, ROOT


def test_only_active_routes_and_runtime_limits_are_required(tmp_path):
    raw = json.loads((ROOT / 'config/local.json').read_text(encoding='utf-8'))
    raw['models']['tasks'] = {task: 'deepseek-v4.1-flash' for task in
                              ('single_turn', 'narration', 'followup_actions')}
    raw['runtime'].pop('main_max_iters', None)
    raw['runtime'].pop('npc_max_iters', None)
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(raw), encoding='utf-8')
    config = HarnessConfig.load(path)
    assert config.model_name('single_turn') == 'deepseek-v4.1-flash'
    assert not hasattr(config.runtime, 'npc_max_iters')


@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('due_tick', [0, 100])
def test_obsolete_work_rejected_before_model_world_or_billing(portal, monkeypatch, stream, due_tick):
    token = portal.register('reader', 'password-123')['token']
    game_id = asyncio.run(portal.create_save(token, 'npc-chat'))['game_id']
    before = portal.store.load(game_id)
    work = PendingWork('obsolete', 'npc_reply', due_tick, 10, None,
                       {'actor_id': 'dockhand', 'player_message': 'hello'})
    portal.store.commit(game_id, before.version, None, (), (work,))
    snapshot = portal.store.load(game_id)
    queued = portal.store.pending_work(game_id)
    observations = portal.store.observations_for(game_id, 'player')
    ledger = portal.credit_ledger(token)
    def forbidden(*args, **kwargs):
        raise AssertionError('obsolete saves must fail before model or billing work')
    monkeypatch.setattr(type(portal.config), 'create_model', forbidden)
    monkeypatch.setattr(portal.billing, 'require_credit', forbidden)
    with TestClient(create_app(portal), base_url='http://127.0.0.1') as client:
        response = client.post(f'/v1/saves/{game_id}/turns' + ('/stream' if stream else ''),
            headers={'Authorization': f'Bearer {token}'},
            json={'text': 'hello', 'request_id': 'obsolete'})
        payload = ([json.loads(line[6:]) for line in response.text.splitlines()
                    if line.startswith('data: ')][-1] if stream else response.json())
        assert 'new game' in str(payload)
    assert portal.store.load(game_id) == snapshot
    assert portal.store.pending_work(game_id) == queued
    assert portal.store.observations_for(game_id, 'player') == observations
    assert portal.credit_ledger(token) == ledger
    assert portal.turn_settlements.get(game_id, 'obsolete', 'hello') is None



def test_current_http_turn_uses_scene_projection_and_settles_once_with_only_active_routes(portal, monkeypatch):
    from dataclasses import replace
    from types import SimpleNamespace
    from storyloop_harness.agents.scene_turn import SingleSceneGenerator
    from storyloop_platform.portal.billing import record_model_usage
    from test_single_call import a_turn, FakeGenerator

    portal.config = replace(portal.config, task_models={task: 'deepseek-v4.1-flash'
        for task in ('single_turn', 'narration', 'followup_actions')})
    generator = FakeGenerator(a_turn())
    async def generate(_self, game_id, context):
        record_model_usage('deepseek-v4.1-flash', 'single_turn',
                           SimpleNamespace(input_tokens=100, output_tokens=50, metadata={}))
        return await generator.generate(game_id, context)
    monkeypatch.setattr(SingleSceneGenerator, 'generate', generate)
    token = portal.register('scene-reader', 'password-123')['token']
    game_id = asyncio.run(portal.create_save(token, 'npc-chat'))['game_id']
    with TestClient(create_app(portal), base_url='http://127.0.0.1') as client:
        args = dict(headers={'Authorization': f'Bearer {token}'},
                    json={'text': 'hello', 'request_id': 'scene-one'})
        first = client.post(f'/v1/saves/{game_id}/turns', **args)
        replay = client.post(f'/v1/saves/{game_id}/turns', **args)
        assert first.status_code == replay.status_code == 200
        assert first.json() == replay.json()
        assert first.json()['billing']['input_tokens'] == 100
    assert generator.calls == 1
    assert 'npc_contexts' in generator.requests[0]
    assert portal.store.event_exists(game_id, 'portal-scene-one:input:reply:dockhand:spoken')
    assert len([entry for entry in portal.credit_ledger(token) if entry['kind'] == 'turn']) == 1
