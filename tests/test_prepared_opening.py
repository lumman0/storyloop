"""Prepared identity templates are genre data, never executable code."""

from dataclasses import replace
import unittest

from storyloop_harness.world.prepared_opening import render_prepared_opening, validate_prepared_opening
from storyloop_harness.world.story_blueprint import StoryBlueprint
from test_scene_responder_context import source_package


def prepared_package(**changes):
    package = source_package()
    raw = package.story_blueprint.model_dump()
    raw.update({
        "player_profiles": [{"name": "访客"}],
        "opening_options": [{"label": label, "input": text} for label, text in (
            ("打招呼", "我向工作人员打招呼。"), ("看环境", "我观察周围环境。"), ("问路", "我询问去向。"))],
    })
    raw.update(changes)
    return replace(package, story_blueprint=StoryBlueprint.model_validate(raw),
                   authored_prologue="{{player_intro}}\n\n{{player_name}}走到门口，等待下一步行动。",
                   actor_public_profiles={actor_id: "身穿外套，正在码头忙碌。" for actor_id in package.actor_names})


class PreparedOpeningTests(unittest.TestCase):
    def test_identity_templates_support_romance_fantasy_mystery_science_and_workplace(self):
        cases = [
            ("你是{{name}}，是应邀参加节目的大学生。", {"name": "艾然"}, "大学生"),
            ("你是{{name}}，来自{{realm}}的{{role}}。", {"name": "艾然", "realm": "星谷", "role": "法师"}, "法师"),
            ("你是{{name}}，调查{{case}}的{{role}}。", {"name": "艾然", "case": "失窃案", "role": "侦探"}, "侦探"),
            ("你是{{name}}，担任{{role}}，登上{{ship}}。", {"name": "艾然", "role": "工程师", "ship": "曙光号"}, "曙光号"),
            ("你是{{name}}，作为{{role}}进入{{company}}。", {"name": "艾然", "role": "设计师", "company": "青石公司"}, "青石公司"),
        ]
        for template, profile, expected in cases:
            with self.subTest(expected=expected):
                package = prepared_package(player_intro_template=template,
                    player_intro_variables=list(profile), player_profiles=[profile])
                result = render_prepared_opening(package, {"player": "random", "tone": "slow"})
                self.assertIn(expected, result.prose)
                self.assertEqual(result.state["player_profile"], profile)
                self.assertEqual(len(result.options), 3)
                if expected != "大学生":
                    self.assertNotIn("大学生", result.prose)
                    self.assertNotIn("节目", result.prose)

    def test_selected_option_uses_its_own_profile_pool(self):
        package = prepared_package(
            setup={"player_options": [
                {"id": option, "label": option, "guidance": option, "source_ref": "Source"}
                for option in ("engineer", "manager")],
                "tone_options": [{"id": "slow", "label": "Slow", "guidance": "Patient", "source_ref": "Source"}]},
            player_intro_template="你是{{name}}，担任{{role}}。", player_intro_variables=["name", "role"],
            player_profile_pools={"engineer": [{"name": "艾然", "role": "工程师"}],
                                  "manager": [{"name": "周然", "role": "经理"}]})
        for option, name, role in (("engineer", "艾然", "工程师"), ("manager", "周然", "经理")):
            result = render_prepared_opening(package, package.story_blueprint.setup.resolve({"player": option}))
            self.assertEqual(result.state["player_profile"], {"name": name, "role": role})
            self.assertIn(role, result.prose)

    def test_custom_and_random_identity_share_the_declared_fields(self):
        setup = {
            "player_options": [{"id": option, "label": option, "guidance": option, "source_ref": "Source"}
                               for option in ("random", "custom")],
            "tone_options": [{"id": "slow", "label": "Slow", "guidance": "Patient", "source_ref": "Source"}],
            "custom_fields": [{"id": key, "label": key, "required": True, "max_length": 80}
                              for key in ("name", "role", "ship")],
        }
        package = prepared_package(setup=setup, player_intro_template="你是{{name}}，作为{{role}}登上{{ship}}。",
            player_intro_variables=["name", "role", "ship"],
            player_profiles=[{"name": "艾然", "role": "工程师", "ship": "曙光号"}])
        custom = render_prepared_opening(package, package.story_blueprint.setup.resolve(
            {"player": "custom", "name": "岑予", "role": "领航员", "ship": "长风号"}))
        random = render_prepared_opening(package, package.story_blueprint.setup.resolve({"player": "random"}))
        self.assertEqual(set(custom.state["player_profile"]), set(random.state["player_profile"]))
        self.assertIn("领航员", custom.prose)
        self.assertIn("长风号", custom.prose)

    def test_expression_attribute_unknown_and_malformed_placeholders_are_rejected(self):
        for template in ("{{name.__class__}}", "{{name[0]}}", "{{__import__('os')}}",
                         "{{unknown}}", "{{name", "name}}"):
            with self.subTest(template=template):
                package = prepared_package(player_intro_template=template, player_intro_variables=["name"])
                with self.assertRaisesRegex(ValueError, "template|variable"):
                    validate_prepared_opening(package)

    def test_required_template_value_is_checked_before_publication(self):
        package = prepared_package(player_intro_template="你是{{name}}，担任{{role}}。",
                                   player_intro_variables=["name", "role"])
        with self.assertRaisesRegex(ValueError, "role"):
            validate_prepared_opening(package)

    def test_custom_template_fields_must_be_required_before_publication(self):
        raw = prepared_package().story_blueprint.setup.model_dump()
        raw["player_options"].append({"id": "custom", "label": "Custom", "guidance": "Custom",
                                      "source_ref": "Source"})
        raw["custom_fields"] = [{"id": "name", "label": "Name", "required": True, "max_length": 80},
                                {"id": "role", "label": "Role", "required": False, "max_length": 80}]
        package = prepared_package(setup=raw, player_intro_template="你是{{name}}，担任{{role}}。",
            player_intro_variables=["name", "role"], player_profiles=[{"name": "艾然", "role": "工程师"}])
        with self.assertRaisesRegex(ValueError, "custom.*role"):
            validate_prepared_opening(package)

    def test_custom_only_start_does_not_require_an_unused_random_profile(self):
        raw = prepared_package().story_blueprint.setup.model_dump()
        raw["player_options"] = [{"id": "custom", "label": "Custom", "guidance": "Custom",
                                  "source_ref": "Source"}]
        raw["custom_fields"] = [{"id": key, "label": key, "required": True, "max_length": 80}
                                for key in ("name", "role")]
        package = prepared_package(setup=raw, player_intro_template="你是{{name}}，担任{{role}}。",
                                   player_intro_variables=["name", "role"])
        result = render_prepared_opening(package, {"player": "custom", "tone": "slow",
                                                   "name": "艾然", "role": "工程师"})
        self.assertIn("工程师", result.prose)

    def test_profile_pool_names_cannot_conflict_with_cast(self):
        package = prepared_package(player_profile_pools={"random": [{"name": "Guide"}]})
        with self.assertRaisesRegex(ValueError, "conflicts"):
            validate_prepared_opening(package)

    def test_ambiguous_legacy_multi_option_pool_is_readable_but_cannot_start(self):
        package = prepared_package()
        raw = package.story_blueprint.model_dump()
        raw["setup"]["player_options"].append({"id": "engineer", "label": "Engineer",
                                                "guidance": "Engineer", "source_ref": "Source"})
        old = replace(package, story_blueprint=StoryBlueprint.model_validate(raw))
        with self.assertRaisesRegex(ValueError, "option ID"):
            validate_prepared_opening(old)

    def test_explicit_pools_require_every_noncustom_option(self):
        package = prepared_package(player_profile_pools={"other": [{"name": "艾然"}]})
        with self.assertRaisesRegex(ValueError, "pool|option"):
            validate_prepared_opening(package)

    def test_template_values_are_substituted_once_as_literal_text(self):
        package = prepared_package(player_intro_template="你是{{name}}，担任{{role}}。",
            player_intro_variables=["name", "role"],
            player_profiles=[{"name": "艾然", "role": "{{player_name}} __import__('os')"}])
        result = render_prepared_opening(package, {"player": "random", "tone": "slow"})
        self.assertIn("{{player_name}} __import__('os')", result.prose)

    def test_legacy_missing_new_fields_loads_and_uses_neutral_identity(self):
        package = prepared_package()
        raw = package.story_blueprint.model_dump(exclude={
            "player_intro_template", "player_intro_variables", "player_profile_pools"})
        old = replace(package, story_blueprint=StoryBlueprint.model_validate(raw))
        result = render_prepared_opening(old, {"player": "random", "tone": "slow"})
        self.assertIn("你是访客", result.prose)
        self.assertNotIn("大学生", result.prose)
        self.assertNotIn("节目", result.prose)

    def test_legacy_preprepared_blueprint_still_loads_without_new_start_fields(self):
        raw = source_package().story_blueprint.model_dump(exclude={
            "player_intro_template", "player_intro_variables", "player_profile_pools",
            "player_profiles", "opening_options"})
        old = StoryBlueprint.model_validate(raw)
        self.assertEqual(old.opening_options, [])
        self.assertEqual(old.player_profiles, [])
