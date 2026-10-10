"""Synthetic authored packages loaded through the public Harness scenario API."""
import json
import tempfile
from copy import deepcopy
from pathlib import Path

from storyloop_harness import ScenarioPackage

EXAMPLE = Path(__file__).resolve().parents[1] / 'examples/freeform'


def synthetic_package(*, manifest_changes=None, worldbook=None, blueprint=None):
    manifest = json.loads((EXAMPLE / 'manifest.json').read_text(encoding='utf-8'))
    manifest.update(deepcopy(manifest_changes or {}))
    book = worldbook if worldbook is not None else json.loads((EXAMPLE / 'worldbook.json').read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        manifest['worldbook'] = 'worldbook.json'
        if blueprint is not None:
            manifest['story_blueprint'] = 'story_blueprint.json'
            (root / 'story_blueprint.json').write_text(json.dumps(blueprint), encoding='utf-8')
        (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        (root / 'worldbook.json').write_text(json.dumps(book), encoding='utf-8')
        return ScenarioPackage.load(root)


def source_package():
    manifest = json.loads((EXAMPLE / 'manifest.json').read_text(encoding='utf-8'))
    names = {'dockhand': 'Dockhand', 'vendor': 'Vendor', 'guard': 'Guard', 'guide': 'Guide'}
    state = manifest['initial_state']
    state['actors'].update({actor: {'location': 'harbor_square'} for actor in names})
    actors = [{'id': actor, 'name': name, 'card': f'{actor}_card'} for actor, name in names.items()]
    book = {'package_id': manifest['id'], 'version': manifest['version'], 'entries': [
        {'id': actor['card'], 'text': f"{actor['name']} knows only their own harbor experiences. " * 8,
         'visibility': 'actor', 'allowed_actors': [actor['id']], 'kind': 'card'} for actor in actors]}
    blueprint = {
        'source_document': 'Synthetic harbor story',
        'opening_focus': 'Four workers share a public harbor scene.',
        'setup': {'player_options': [{'id': 'random', 'label': 'Visitor', 'guidance': 'Visitor', 'source_ref': 'Source'}],
                  'tone_options': [{'id': 'slow', 'label': 'Slow', 'guidance': 'Patient', 'source_ref': 'Source'}]},
        'actor_slots': [{'actor_id': actor, 'brief': f'{name} works at the harbor.',
                         'source_ref': 'Synthetic cast'} for actor, name in names.items()],
        'facts': [{'id': 'harbor', 'text': 'Visitors arrive by boat.', 'source_ref': 'Source', 'visibility': 'public'}],
    }
    return synthetic_package(manifest_changes={'actors': actors, 'initial_state': state,
                             'initial_work': [], 'presentation_mode': 'interactive'},
                             worldbook=book, blueprint=blueprint)


def loaded_status_fields(declarations, state):
    return synthetic_package(manifest_changes={'initial_state': state, 'status_fields': declarations,
                'initial_work': [], 'actions': []}).status_fields


def status_package(base):
    state = deepcopy(base.initial_state)
    state['player_stats'] = {'pressure': 3, 'secret': 5}
    declarations = [
        {'id': 'pressure', 'label': '压力', 'description': '压力越大越紧张',
         'path': ['player_stats', 'pressure'], 'bounds': {'min': 0, 'max': 10, 'max_delta': 2}},
        {'id': 'secret', 'label': '隐藏数值', 'visible': False,
         'path': ['player_stats', 'secret'], 'bounds': {'min': 0, 'max': 10, 'max_delta': 2}},
    ]
    return synthetic_package(manifest_changes={'initial_state': state, 'status_fields': declarations,
                                              'initial_work': []})
