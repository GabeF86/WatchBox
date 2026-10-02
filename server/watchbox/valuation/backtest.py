"""Leave-one-out accuracy check: predict each recent sale from the others and measure the error."""
from statistics import median
from typing import Callable

from .adjust import Factors
from .match import trim_iqr
from .models import Comparable

MIN_BACKTEST = 6


def backtest(sold: list[Comparable], factors: Factors,
             multiplier: Callable[[Comparable], float] = lambda c: 1.0) -> tuple[int, float | None, float | None]:
    """Returns (sales tested, median absolute % error, share within ±10%). `multiplier` is the engine's
    per-listing detail adjustment, so predictions use the same adjustments as the estimate."""
    if len(sold) < MIN_BACKTEST:
        return 0, None, None
    errors = []
    for i, target in enumerate(sold):
        others = sold[:i] + sold[i + 1:]
        target_factor = factors.factor(target.box_papers, target.condition) / multiplier(target)
        predicted = median(trim_iqr([factors.to_baseline(o) * multiplier(o) * target_factor for o in others]))
        errors.append(abs(predicted - target.price_usd) / target.price_usd)
    return len(errors), median(errors), sum(e <= 0.10 for e in errors) / len(errors)
