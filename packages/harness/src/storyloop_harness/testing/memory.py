"""Small nonpersistent store for examples and adapter contract tests."""
from copy import deepcopy
from threading import RLock
from storyloop_harness.core.contracts import AgentContextCheckpoint, AgentContextEntry, PlayerInput
from storyloop_harness.core.state import apply_event


class InMemoryGameStore:
    def __init__(self):
        self._games = {}
        self._lock = RLock()

    def create_game(self, snapshot, initial_work=()):
        with self._lock:
            if snapshot.game_id in self._games:
                raise ValueError('game already exists')
            if len({w.work_id for w in initial_work}) != len(initial_work):
                raise ValueError('duplicate work')
            self._games[snapshot.game_id] = deepcopy(dict(snapshot=snapshot, events={}, observations={},
                work={w.work_id: w for w in initial_work}, consumed=set(), checkpoints={}))

    def load(self, game_id):
        return deepcopy(self._games[game_id]['snapshot'])

    def event_exists(self, game_id, event_id):
        return event_id in self._games[game_id]['events']

    def event_details(self, game_id, event_id):
        row = self._games[game_id]['events'].get(event_id)
        return deepcopy(row[1].details) if row else None

    def completed_turn_count(self, game_id):
        return sum(event.kind == 'campaign_turn_completed' for _, event in self._games[game_id]['events'].values())

    def commit(self, game_id, expected_version, event, observations, new_work, consumed_work_id=None):
        with self._lock:
            game = deepcopy(self._games[game_id])
            before = game['snapshot']
            if before.version != expected_version:
                raise ValueError('game state version changed')
            if consumed_work_id is not None:
                if consumed_work_id not in game['work'] or consumed_work_id in game['consumed']:
                    raise ValueError('pending work was already consumed or does not exist')
                game['consumed'].add(consumed_work_id)
            after = apply_event(before, event) if event else before
            if event:
                if event.event_id in game['events']:
                    raise ValueError('duplicate event')
                game['events'][event.event_id] = (after.version, deepcopy(event))
            for observation in observations:
                if observation.event_id not in game['events']:
                    raise ValueError('observation refers to an unknown event')
                if observation.observation_id in game['observations']:
                    raise ValueError('duplicate observation')
                game['observations'][observation.observation_id] = deepcopy(observation)
            for work in new_work:
                if work.work_id in game['work']:
                    raise ValueError('duplicate work')
                game['work'][work.work_id] = deepcopy(work)
            game['snapshot'] = after
            self._games[game_id] = game
            return deepcopy(after)

    @staticmethod
    def _limit(items, limit):
        if limit is not None and (type(limit) is not int or limit < 1):
            raise ValueError('history limit must be a positive integer')
        return deepcopy(items[-limit:] if limit is not None else items)

    def observations_for(self, game_id, recipient_id, *, limit=None):
        game = self._games[game_id]
        items = [o for o in game['observations'].values() if o.recipient_id == recipient_id]
        items.sort(key=lambda o: game['events'][o.event_id][0])
        return self._limit(items, limit)

    def dialogue_history_for_actor(self, game_id, actor_id):
        return [(e.details['player_message'], e.details['speech'])
                for _, e in self._games[game_id]['events'].values()
                if e.kind == 'npc_spoke' and e.actor_id == actor_id]

    def player_inputs_for(self, game_id, *, limit=None):
        channels = {'player_input': 'speech', 'player_query': 'query', 'player_action': 'action', 'action_rejected': 'action'}
        items = [PlayerInput(e.event_id, e.tick, e.details['text'], e.details.get('channel', channels[e.kind]),
                            tuple(e.details.get('target_ids', [])))
                 for _, e in self._games[game_id]['events'].values() if e.actor_id == 'player' and e.kind in channels]
        return self._limit(items, limit)

    def agent_context_entries(self, game_id, actor_id, after_version=-1):
        game = self._games[game_id]
        observations = self.observations_for(game_id, actor_id)
        seen = {(o.event_id, o.content) for o in observations}
        items = []
        for version, event in game['events'].values():
            if version <= after_version or event.actor_id != actor_id:
                continue
            if actor_id == 'player' and event.kind in ('player_input','player_query','player_action','action_rejected'):
                content = str(event.details.get('text', ''))
            elif actor_id != 'player' and event.kind == 'npc_spoke':
                message = str(event.details.get('player_message', ''))
                prefix = '' if (event.cause_id, message) in seen else f'玩家曾说：{message}\n'
                content = f"{prefix}你当时回答：{event.details.get('speech', '')}"
            else:
                continue
            items.append((version, 0, AgentContextEntry(version, event.event_id, event.kind, content, event.tick)))
        for observation in observations:
            version = game['events'][observation.event_id][0]
            if version > after_version:
                items.append((version, 1, AgentContextEntry(version, observation.observation_id,
                    observation.channel, observation.content, observation.tick)))
        items.sort(key=lambda item: item[:2])
        return deepcopy([item[2] for item in items])

    def agent_context_checkpoint(self, game_id, actor_id):
        return self._games[game_id]['checkpoints'].get(actor_id, AgentContextCheckpoint())

    def save_agent_context_checkpoint(self, game_id, actor_id, expected_version, checkpoint):
        with self._lock:
            if checkpoint.through_version <= expected_version or not checkpoint.summary.strip():
                raise ValueError('context checkpoint must advance with a nonempty summary')
            if self.agent_context_checkpoint(game_id, actor_id).through_version != expected_version:
                raise ValueError('agent context checkpoint changed')
            self._games[game_id]['checkpoints'][actor_id] = checkpoint

    def pending_work(self, game_id):
        game = self._games[game_id]
        return deepcopy(sorted((w for k, w in game['work'].items() if k not in game['consumed']),
            key=lambda w: (w.due_tick, -w.mandatory, -w.priority, w.work_id)))

    def ready_work(self, game_id, tick):
        return [w for w in self.pending_work(game_id) if w.due_tick <= tick]
