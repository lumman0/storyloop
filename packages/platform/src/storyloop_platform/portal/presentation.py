"""Player-safe API projection for campaign interaction gates."""

from __future__ import annotations

from storyloop_harness.core.contracts import Snapshot
from storyloop_platform.runtime.campaign import CampaignProgram


def campaign_interaction(program: CampaignProgram, snapshot: Snapshot,
                         gate_id: str | None) -> dict | None:
    if gate_id is None:
        return None
    cursor = snapshot.data["campaign"]["cursor"]
    if cursor >= len(program.steps):
        return None
    step = program.steps[cursor]
    if step["id"] != gate_id or step["kind"] not in {"continue", "choice", "message"}:
        return None
    if step["kind"] == "continue":
        return {"id": step["id"], "kind": "continue", "prompt": step["prompt"],
                "label": step["label"], "options": []}
    met = snapshot.data["campaign"].get("met", {})
    return {
        "id": step["id"], "kind": step["kind"], "prompt": step["prompt"],
        "options": [
            {"id": option["id"], "label": option["label"],
             "enabled": (step["kind"] != "message" or option["id"] == "skip"
                         or bool(met.get(option.get("recipient")))),
             "requires_text": step["kind"] == "message" and option["id"] != "skip"}
            for option in step["options"]
        ],
    }
