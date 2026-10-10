"""SQL portal execution must cross the supported harness facade."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from storyloop_harness import TurnEngine, TurnInput
from storyloop_harness.testing import OfflineModel
from storyloop_harness.usage import collect_usage, record_model_usage, ModelUsage
from test_turn_failure_contract import portal


class PricedOfflineModel(OfflineModel):
    async def __call__(self, *args, **kwargs):
        with collect_usage():
            response = await super().__call__(*args, **kwargs)
        record_model_usage('qwen3.8-flash', 'single_turn',
                           SimpleNamespace(input_tokens=1000, output_tokens=500))
        return response


def test_sql_portal_calls_public_engine_and_settles_returned_usage_once(portal, monkeypatch):
    portal.gameplay.factory.offline_models.model = PricedOfflineModel()
    calls = []
    run = TurnEngine.run_turn

    async def observed(self, turn, **kwargs):
        assert isinstance(turn, TurnInput)
        calls.append(turn)
        result = await run(self, turn, **kwargs)
        # Settlement must consume the returned contract, not a nested collector.
        return replace(result, model_usage=(ModelUsage('qwen3.8-flash', 'single_turn', 1234, 567),))

    monkeypatch.setattr(TurnEngine, 'run_turn', observed)
    token = portal.register('reader', 'password-123')['token']
    game = asyncio.run(portal.create_save(token, 'npc-chat'))['game_id']
    before = portal.gameplay.store.load(game)
    response = asyncio.run(portal.turn(token, game, 'Hello', 'public-turn'))
    assert len(calls) == 1
    assert response['body'].strip()
    assert portal.gameplay.store.load(game).version > before.version
    assert portal.gameplay.store.event_exists(game, 'portal-public-turn:input')
    assert response['billing']['input_tokens'] == 1234
    assert response['billing']['output_tokens'] == 567
    assert asyncio.run(portal.turn(token, game, 'Hello', 'public-turn')) == response
    assert len(calls) == 1
    assert len([row for row in portal.credit_ledger(token) if row['kind'] == 'turn']) == 1


@pytest.mark.parametrize('missing_usage', [False, True])
def test_sql_portal_model_failure_keeps_world_and_wallet(portal, monkeypatch, missing_usage):
    class FailedModel:
        async def __call__(self, *a, **k):
            if missing_usage:
                record_model_usage('qwen3.8-flash', 'single_turn', None)
            raise RuntimeError('offline model failed')
    portal.gameplay.factory.offline_models.model = FailedModel()
    token = portal.register('reader', 'password-123')['token']
    game = asyncio.run(portal.create_save(token, 'npc-chat'))['game_id']
    before, wallet = portal.gameplay.store.load(game), portal.wallet(token)
    with pytest.raises(RuntimeError, match='usage|failed'):
        asyncio.run(portal.turn(token, game, 'Hello', 'failed-turn'))
    assert portal.gameplay.store.load(game) == before
    assert portal.wallet(token) == wallet


@pytest.fixture
def campaign_portal(portal, tmp_path, monkeypatch):
    import json
    import shutil
    from test_turn_failure_contract import ROOT
    from storyloop_platform.portal.catalog import GameCatalog
    from storyloop_platform.runtime.campaign import CampaignProgram
    package_path = tmp_path / 'campaign'
    shutil.copytree(ROOT / 'examples/freeform', package_path)
    manifest_path = package_path / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    program = {'id': manifest['id'], 'ticks_per_day': manifest['ticks_per_day'], 'final_tick': 4,
               'steps': [
                   {'id': 'arrival', 'at': 0, 'kind': 'scene', 'text': 'A quiet harbor.'},
                   {'id': 'choice', 'at': 3, 'kind': 'choice', 'prompt': 'Who?',
                    'options': [{'id': 'dockhand', 'label': 'Dockhand'}]},
                   {'id': 'ending', 'at': 4, 'kind': 'finale', 'choice_key': 'choice',
                    'threshold': 0, 'success_text': 'Done', 'other_text': 'Done'}]}
    manifest['initial_state']['campaign'] = CampaignProgram.from_dict(program).initial_state(['dockhand'])
    manifest['authored_prologue'] = 'A quiet harbor.'
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    (package_path / 'campaign.json').write_text(json.dumps(program), encoding='utf-8')
    catalog = tmp_path / 'catalog.json'
    catalog.write_text(json.dumps({'games': [{'id': 'campaign', 'title': 'Campaign',
                       'mode': 'campaign', 'package': 'campaign'}]}), encoding='utf-8')
    portal.gameplay.game_access.catalog = GameCatalog.load(catalog)
    portal.gameplay.factory.offline_models.model = PricedOfflineModel()
    return portal


@pytest.mark.parametrize('player_text, expected_tokens', [('Hello', 1000), ('/next', 222)])
def test_campaign_bills_engine_or_product_presentation_usage(campaign_portal, monkeypatch,
                                                            player_text, expected_tokens):
    portal = campaign_portal
    class Presenter:
        async def present(self, context):
            record_model_usage('qwen3.8-flash', 'narration',
                               SimpleNamespace(input_tokens=222, output_tokens=33))
            return 'The harbor settles into the afternoon.'
    portal.gameplay.factory.presenter = Presenter()
    token = portal.register('reader', 'password-123')['token']
    game = asyncio.run(portal.create_save(token, 'campaign'))['game_id']
    result = asyncio.run(portal.turn(token, game, player_text, 'campaign-turn'))
    assert result['billing']['input_tokens'] == expected_tokens
    assert asyncio.run(portal.turn(token, game, player_text, 'campaign-turn')) == result
    assert len([row for row in portal.credit_ledger(token) if row['kind'] == 'turn']) == 1


def test_campaign_missing_product_usage_stays_unbilled(campaign_portal, monkeypatch):
    portal = campaign_portal
    class Presenter:
        async def present(self, context):
            record_model_usage('qwen3.8-flash', 'narration', None)
    portal.gameplay.factory.presenter = Presenter()
    token = portal.register('reader', 'password-123')['token']
    game = asyncio.run(portal.create_save(token, 'campaign'))['game_id']
    wallet = portal.wallet(token)
    with pytest.raises(RuntimeError, match='usage'):
        asyncio.run(portal.turn(token, game, '/next', 'missing-usage'))
    assert portal.wallet(token) == wallet
    with pytest.raises(ValueError, match='恢复'):
        asyncio.run(portal.turn(token, game, '/next', 'missing-usage'))


def test_sql_store_preserves_public_commit_version_contract(portal):
    from storyloop_harness import GameStore, ScenarioPackage
    from storyloop_harness.advanced import WorldEvent
    from test_turn_failure_contract import ROOT
    store: GameStore = portal.gameplay.store
    package = ScenarioPackage.load(ROOT / 'examples/freeform')
    package.seed_game(store, 'versions')
    before = store.load('versions')
    event = WorldEvent('first', 'test', None, None, before.tick, ())
    after = store.commit('versions', before.version, event, (), ())
    with pytest.raises(ValueError, match='version'):
        store.commit('versions', before.version, replace(event, event_id='stale'), (), ())
    assert store.load('versions') == after
    assert not store.event_exists('versions', 'stale')


def test_product_and_engine_usage_are_merged_once(portal, monkeypatch):
    from storyloop_platform.runtime.guidance import GuidanceAdvisor
    portal.gameplay.factory.offline_models.model = PricedOfflineModel()
    token = portal.register('reader', 'password-123')['token']
    game = asyncio.run(portal.create_save(token, 'npc-chat'))['game_id']
    advise = GuidanceAdvisor.advise
    async def metered_guidance(self, *args, **kwargs):
        result = await advise(self, *args, **kwargs)
        record_model_usage('qwen3.8-flash', 'guidance',
                           SimpleNamespace(input_tokens=11, output_tokens=7))
        return result
    monkeypatch.setattr(GuidanceAdvisor, 'advise', metered_guidance)
    result = asyncio.run(portal.turn(token, game, 'Hello', 'merged-usage'))
    assert result['billing']['input_tokens'] == 1011
    assert result['billing']['output_tokens'] == 507
