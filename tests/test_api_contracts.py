"""API projections preserve presence and reject malformed player wire data."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from storyloop_platform.api.contracts import History, TurnFailure, View, stream_event_adapter


def view_payload():
    return dict(game_id="game", catalog_id="story", mode="freeform", presentation_mode="interactive",
                opening="", body="", segments=[], suggestions=[], action_options=[], status_fields=[],
                interaction=None, tick=0, state_version=0, day=None, time_of_day=None,
                complete=False, turn_id=None)


@pytest.mark.parametrize("mode,presentation,interaction", [
    ("freeform", "interactive", None), ("campaign", "novel", None),
    ("campaign", "interactive", dict(id="gate", kind="choice", prompt="Choose",
                                      options=[dict(id="yes", label="Yes", enabled=True, requires_text=False)])),
    ("campaign", "novel", dict(id="next", kind="continue", prompt="Continue", label="Next", options=[])),
    ("campaign", "interactive", dict(id="message", kind="message", prompt="Say hello", options=[])),
])
def test_view_round_trips_all_modes_and_presence(mode, presentation, interaction):
    payload = {**view_payload(), "mode": mode, "presentation_mode": presentation, "interaction": interaction}
    payload["segments"] = [dict(kind=kind, text="", **({"speaker_id": "actor", "speaker_name": "Actor"}
                                                   if kind == "dialogue" else {}))
                           for kind in ("narration", "scene", "dialogue", "message", "prompt", "time")]
    payload["action_options"] = [dict(label="Look", input="Look around")]
    payload["status_fields"] = [dict(id=str(i), label="Status", value=value)
                                for i, value in enumerate((False, 0, "0"))]
    payload["status_fields"].append(dict(id="bounded", label="Count", value=0, min=0, max=10))
    assert View.model_validate(payload).model_dump(mode="json", exclude_unset=True) == payload
    assert "billing" not in View.model_validate(payload).model_dump(exclude_unset=True)
    payload["billing"] = dict(charged_milli_points=0, charged_points="0.000", usage_cost_milli_points=0,
                              balance_milli_points=10, balance_points="0.010", input_tokens=0,
                              output_tokens=0, model_calls=0)
    assert View.model_validate(payload).model_dump(mode="json", exclude_unset=True) == payload
    history = dict(game_id="game", intro=payload, turns=[dict(request_id="turn", input=None, response=payload)])
    assert History.model_validate(history).model_dump(mode="json", exclude_unset=True) == history


@pytest.mark.parametrize("key", list(view_payload()))
def test_every_production_view_core_key_is_required(key):
    payload = view_payload()
    del payload[key]
    with pytest.raises(ValidationError):
        View.model_validate(payload)


@pytest.mark.parametrize("change", [dict(tick=True), dict(tick=1.2), dict(state_version="1"),
    dict(day="1"), dict(complete=0), dict(billing=None), dict(mode="other"),
    dict(status_fields=[dict(id="a", label="A", value=1.2)]),
    dict(segments=[dict(kind="dialogue", text="hello", speaker_id=None)])])
def test_view_rejects_wrong_scalar_types(change):
    with pytest.raises(ValidationError):
        View.model_validate({**view_payload(), **change})


def failure_payload():
    return dict(code="TURN_FAILED", message="Try again", retryable=True, commit_state="unknown", request_id=None)


@pytest.mark.parametrize("detail", [False, True])
def test_failure_presence_and_all_stream_variants(detail):
    failure = failure_payload()
    if detail:
        failure["detail"] = failure["message"]
    assert TurnFailure.model_validate(failure).model_dump(exclude_unset=True) == failure
    events = [dict(type="stage", stage="thinking"), dict(type="segment", segment=dict(kind="scene", text="")),
              dict(type="preview", body="", segments=[]), dict(type="complete", view=view_payload()),
              dict(type="error", **failure)]
    for event in events:
        assert stream_event_adapter.dump_python(stream_event_adapter.validate_python(event), mode="json",
                                                exclude_unset=True) == event
        mutated = deepcopy(event)
        del mutated[next(key for key in event if key != "type")]
        with pytest.raises(ValidationError):
            stream_event_adapter.validate_python(mutated)
    with pytest.raises(ValidationError):
        stream_event_adapter.validate_python(dict(type="future", stage="thinking"))


@pytest.mark.parametrize("key", list(failure_payload()))
def test_failure_core_keys_required(key):
    failure = failure_payload()
    del failure[key]
    with pytest.raises(ValidationError):
        TurnFailure.model_validate(failure)
