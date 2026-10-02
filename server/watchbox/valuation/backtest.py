"""Leave-one-out accuracy check: predict each recent sale from the others and measure the error."""
from statistics import median

from .adjust import Factors
from .match import trim_iqr
from .models import Comparable

MIN_BACKTEST = 6


def backtest(sold: list[Comparable], factors: Factors) -> tuple[int, float | None, float | None]:
    """Returns (sales tested, median absolute % error, share within ±10%)."""
    if len(sold) < MIN_BACKTEST:
        return 0, None, None
    errors = []
    for i, target in enumerate(sold):
        others = sold[:i] + sold[i + 1:]
        target_factor = factors.factor(target.box_papers, target.condition)
        predicted = median(trim_iqr([factors.to_baseline(o) * target_factor for o in others]))
        errors.append(abs(predicted - target.price_usd) / target.price_usd)
    return len(errors), median(errors), sum(e <= 0.10 for e in errors) / len(errors)
