"""Render a prepared scenario opening without a model call."""

from __future__ import annotations

from dataclasses import dataclass
import re
from secrets import choice

from story_harness.runtime.player_knowledge import merge_knowledge
from story_harness.world.scenario import ScenarioPackage
from story_harness.world.story_blueprint import OpeningAction


@dataclass(frozen=True)
class PreparedOpening:
    prose: str
    options: tuple[OpeningAction, ...]
    state: dict[str, object]


_PLACEHOLDER = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")


def _template_variables(template: str, allowed: set[str]) -> set[str]:
    variables = set(_PLACEHOLDER.findall(template))
    remainder = _PLACEHOLDER.sub("", template)
    if "{{" in remainder or "}}" in remainder or variables - allowed:
        raise ValueError("template requires declared simple variables; expressions are not supported")
    return variables


def _render_template(template: str, values: dict[str, str]) -> str:
    required = _template_variables(template, set(values))
    if any(not values[key].strip() for key in required):
        raise ValueError("template requires nonempty variable values")
    # One substitution pass: values containing braces remain literal text.
    return _PLACEHOLDER.sub(lambda match: values[match.group(1)].strip(), template)


def validate_prepared_opening(package: ScenarioPackage, *,
                              require_prologue: bool = True) -> None:
    blueprint = package.story_blueprint
    if blueprint is None:
        raise ValueError("prepared opening requires a story blueprint")
    if (require_prologue and (not package.authored_prologue.strip()
            or "{{player_intro}}" not in package.authored_prologue)):
        raise ValueError("source story requires a prepared prologue with {{player_intro}}")
    if len(blueprint.opening_options) != 3:
        raise ValueError("source story requires three prepared opening options")
    noncustom = {option.id for option in blueprint.setup.player_options if option.id != "custom"}
    pools = blueprint.player_profile_pools
    if pools and set(pools) != noncustom:
        raise ValueError("player profile pools must match every non-custom setup option")
    if not pools and len(noncustom) > 1:
        raise ValueError("multiple non-custom options require player profile pools keyed by option ID")
    if noncustom and not pools and not blueprint.player_profiles:
        raise ValueError("non-custom start requires prepared player profiles")
    if package.authored_prologue:
        _template_variables(package.authored_prologue, {"player_intro", "player_name"})
    if blueprint.player_intro_template is not None:
        required = _template_variables(blueprint.player_intro_template,
                                       set(blueprint.player_intro_variables))
        profiles = ([profile for pool in (pools.values() if pools else [blueprint.player_profiles])
                     for profile in pool] if noncustom else [])
        for profile in profiles:
            missing = {key for key in required if not profile.get(key, "").strip()}
            if missing:
                raise ValueError("player profile missing template variables: " + ", ".join(sorted(missing)))
        if any(option.id == "custom" for option in blueprint.setup.player_options):
            custom_required = {field.id for field in blueprint.setup.custom_fields if field.required}
            missing = (required | {"name"}) - custom_required
            if missing:
                raise ValueError("custom identity requires template fields: " + ", ".join(sorted(missing)))
    names = list(package.actor_names.values())
    if (len(set(names)) != len(names)
            or any(name == actor_id for actor_id, name in package.actor_names.items())):
        raise ValueError("source story requires distinct named actors")
    public = package.actor_public_profiles or {}
    cards = package.role_cards
    if any(actor_id not in public or len(public[actor_id]) < 8
           or len(cards[actor_id]) < 80
           for actor_id in package.actor_names):
        raise ValueError("source story requires complete actor cards and public profiles")
    all_profiles = [*blueprint.player_profiles,
                    *(profile for pool in pools.values() for profile in pool)]
    if set(names) & {profile["name"].strip() for profile in all_profiles}:
        raise ValueError("player profile name conflicts with a cast member")


def _player_intro(profile: dict[str, str]) -> str:
    name = profile["name"].strip()
    age = profile.get("age", "").strip()
    school = profile.get("school", "").strip()
    major = profile.get("major", "").strip()
    lead = f"你是{name}"
    if age:
        lead += f"，{age}岁"
    lead += "。"
    if school and major:
        lead += f"你在{school}学习{major}。"
    elif school:
        lead += f"你就读于{school}。"
    elif major:
        lead += f"你学习{major}。"
    return lead


def render_prepared_opening(package: ScenarioPackage,
                            setup: dict[str, str]) -> PreparedOpening:
    validate_prepared_opening(package)
    blueprint = package.story_blueprint
    assert blueprint is not None
    setup = blueprint.setup.resolve(setup)
    if setup["player"] == "custom":
        profile = {key: value for key, value in setup.items()
                   if key not in {"player", "tone"}}
    else:
        pool = (blueprint.player_profile_pools[setup["player"]]
                if blueprint.player_profile_pools else blueprint.player_profiles)
        profile = dict(choice(pool))
    if not profile.get("name", "").strip():
        raise ValueError("player profile requires a name")
    if profile["name"].strip() in package.actor_names.values():
        raise ValueError("player name conflicts with a cast member")
    intro = (_render_template(blueprint.player_intro_template, profile)
             if blueprint.player_intro_template is not None else _player_intro(profile))
    prose = _render_template(package.authored_prologue,
                             {"player_intro": intro, "player_name": profile["name"]})
    profiles = {actor_id: {
        "name": package.actor_names[actor_id],
        "role_card": card,
        "public_profile": (package.actor_public_profiles or {})[actor_id],
    } for actor_id, card in package.role_cards.items()}
    return PreparedOpening(prose, tuple(blueprint.opening_options), {
        "player_profile": profile,
        "story_setup": dict(setup),
        "actor_profiles": profiles,
        "player_knowledge": merge_knowledge({}, []),
    })
