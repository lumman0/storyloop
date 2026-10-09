"""Provider token usage and configurable, provider-independent story credits."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Iterator, Mapping


MILLI_POINTS = 1000
MILLION_TOKENS = Decimal(1_000_000)


def _positive_decimal(value: object, field_name: str, *, allow_zero: bool = False) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a decimal number") from error
    if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
        raise ValueError(f"{field_name} must be positive")
    return amount


@dataclass(frozen=True)
class ModelRate:
    input_rmb_per_million: Decimal
    output_rmb_per_million: Decimal
    cached_input_rmb_per_million: Decimal
    multiplier: Decimal = Decimal("1")

    @classmethod
    def from_dict(cls, value: object, model: str) -> ModelRate:
        if not isinstance(value, dict):
            raise ValueError(f"billing rate for {model} must be an object")
        input_rate = _positive_decimal(value.get("input_rmb_per_million"),
                                       f"{model}.input_rmb_per_million")
        return cls(
            input_rate,
            _positive_decimal(value.get("output_rmb_per_million"), f"{model}.output_rmb_per_million"),
            _positive_decimal(value.get("cached_input_rmb_per_million", input_rate),
                              f"{model}.cached_input_rmb_per_million", allow_zero=True),
            _positive_decimal(value.get("multiplier", 1), f"{model}.multiplier"),
        )


from storyloop_harness.usage import ModelUsage, UsageCollector, collect_usage, record_model_usage


@dataclass(frozen=True)
class BillingPolicy:
    welcome_points: int
    points_per_rmb: int
    pricing_version: str
    rates: Mapping[str, ModelRate] = field(repr=False)

    def to_dict(self) -> dict:
        """Freeze prices as decimal strings so retries never adopt a new tariff."""
        return {"welcome_points": self.welcome_points, "points_per_rmb": self.points_per_rmb,
                "pricing_version": self.pricing_version,
                "models": {name: {
                    "input_rmb_per_million": str(rate.input_rmb_per_million),
                    "output_rmb_per_million": str(rate.output_rmb_per_million),
                    "cached_input_rmb_per_million": str(rate.cached_input_rmb_per_million),
                    "multiplier": str(rate.multiplier),
                } for name, rate in self.rates.items()}}

    @classmethod
    def from_dict(cls, value: object, models: Mapping[str, str]) -> BillingPolicy | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("billing must be an object")
        welcome = value.get("welcome_points")
        conversion = value.get("points_per_rmb")
        version = value.get("pricing_version")
        if type(welcome) is not int or welcome < 0:
            raise ValueError("billing.welcome_points must be a nonnegative integer")
        if type(conversion) is not int or conversion < 1:
            raise ValueError("billing.points_per_rmb must be positive")
        if not isinstance(version, str) or not version.strip():
            raise ValueError("billing.pricing_version is required")
        raw_rates = value.get("models")
        if not isinstance(raw_rates, dict):
            raise ValueError("billing.models must be an object")
        rates = {str(name): ModelRate.from_dict(raw, str(name))
                 for name, raw in raw_rates.items()}
        missing = set(models.values()) - set(rates)
        if missing:
            raise ValueError(f"billing prices missing for configured models: {', '.join(sorted(missing))}")
        return cls(welcome, conversion, version.strip(), rates)

    def price_milli_points(self, records: list[ModelUsage]) -> int:
        cost_rmb = Decimal(0)
        for usage in records:
            try:
                rate = self.rates[usage.model]
            except KeyError as error:
                raise ValueError(f"billing price missing for model: {usage.model}") from error
            uncached = usage.input_tokens - usage.cached_input_tokens
            cost_rmb += ((uncached * rate.input_rmb_per_million
                          + usage.cached_input_tokens * rate.cached_input_rmb_per_million
                          + usage.output_tokens * rate.output_rmb_per_million)
                         * rate.multiplier / MILLION_TOKENS)
        return int((cost_rmb * self.points_per_rmb * MILLI_POINTS)
                   .to_integral_value(rounding=ROUND_CEILING))
