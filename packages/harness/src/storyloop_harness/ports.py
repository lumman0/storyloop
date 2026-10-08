"""Ports for storage and structured model generation."""
from typing import Protocol
from storyloop_harness.core.contracts import Snapshot
from storyloop_harness.core.store_port import GameStore


class ModelResponse(Protocol):
    metadata: object
    usage: object


class ModelPort(Protocol):
    async def __call__(self, messages: list, *, structured_model: type, **kwargs: object) -> ModelResponse: ...


class CampaignContext(Protocol):
    """Optional narrative context supplied by a product campaign program."""
    def current_action_context(self, snapshot: "Snapshot") -> dict: ...
