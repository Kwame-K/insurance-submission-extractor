"""Token pricing. Prices are configuration, never hardcoded: providers change them."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelPrice:
    input_per_million_usd: float
    output_per_million_usd: float


@dataclass(frozen=True)
class PriceBook:
    """Per-provider prices in USD per million tokens."""

    prices: dict[str, ModelPrice] = field(default_factory=dict)

    def cost_usd(self, usages: Iterable[object]) -> float | None:
        """Estimated cost of all calls, or None when any call has no configured price."""
        total = 0.0
        counted = 0

        for usage in usages:
            price = self.prices.get(usage.provider)
            if price is None:
                return None
            total += (
                usage.input_tokens * price.input_per_million_usd
                + usage.output_tokens * price.output_per_million_usd
            ) / 1_000_000
            counted += 1

        return round(total, 8) if counted else None
