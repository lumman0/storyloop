import unittest
from decimal import Decimal
from types import SimpleNamespace

from storyloop_platform.portal.billing import (BillingPolicy, ModelUsage, UsageCollector,
                                        collect_usage, record_model_usage)


class BillingPolicyTests(unittest.TestCase):
    def test_prices_actual_input_output_and_cached_tokens_once_per_turn(self):
        policy = BillingPolicy.from_dict({
            "welcome_points": 500, "points_per_rmb": 50, "pricing_version": "test-1",
            "models": {
                "flash": {"input_rmb_per_million": "0.8", "output_rmb_per_million": "2.7",
                          "cached_input_rmb_per_million": "0.1"},
                "max": {"input_rmb_per_million": "12", "output_rmb_per_million": "36",
                        "cached_input_rmb_per_million": "1.5"},
            },
        }, {"light": "flash", "deep": "max"})
        self.assertEqual(policy.price_milli_points([
            ModelUsage("flash", "selection", 1000, 500, 200),
            ModelUsage("max", "reply", 1000, 500),
        ]), 1601)

    def test_usage_collection_is_scoped_and_requires_provider_usage(self):
        usage = SimpleNamespace(input_tokens=100, output_tokens=20,
                                metadata=SimpleNamespace(prompt_tokens_details={"cached_tokens": 30}))
        record_model_usage("flash", "outside", usage)
        with collect_usage() as collector:
            record_model_usage("flash", "selection", usage)
            self.assertEqual(collector.records, [ModelUsage("flash", "selection", 100, 20, 30)])
            with self.assertRaisesRegex(RuntimeError, "did not report token usage"):
                record_model_usage("flash", "selection", None)
        self.assertEqual(len(collector.records), 1)

    def test_model_multiplier_is_configurable(self):
        policy = BillingPolicy.from_dict({
            "welcome_points": 500, "points_per_rmb": 50, "pricing_version": "test-2",
            "models": {"future-model": {"input_rmb_per_million": "1",
                                      "output_rmb_per_million": "3", "multiplier": "2.5"}},
        }, {"main_react": "future-model"})
        self.assertEqual(policy.price_milli_points([
            ModelUsage("future-model", "main_react", 1000, 1000),
        ]), 500)
