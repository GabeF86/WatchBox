"""Combining sources into one estimate, and how sure we are about it."""
import math
from statistics import median

W_EBAY, W_C24 = 0.7, 0.3
FULL_WEIGHT_N = 10  # a source gets its full weight from 10 comparables
DEFAULT_GAP, MAX_GAP = 0.07, 0.20
MIN_GAP_SAMPLES = 5
LEVELS = ("low", "medium", "high")


def percentile(values: list[float], p: float) -> float:
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def asking_gap(ebay_baseline: list[float], c24_baseline: list[float]) -> float:
    """How far Chrono24 asking prices sit above eBay sold prices for this watch (0-20%)."""
    if len(ebay_baseline) < MIN_GAP_SAMPLES or len(c24_baseline) < MIN_GAP_SAMPLES:
        return DEFAULT_GAP
    gap = 1 - median(ebay_baseline) / median(c24_baseline)
    return min(max(gap, 0.0), MAX_GAP)


def weights(n_ebay: int, n_c24: int) -> tuple[float, float]:
    w_ebay = W_EBAY * min(1.0, n_ebay / FULL_WEIGHT_N)
    w_c24 = W_C24 * min(1.0, n_c24 / FULL_WEIGHT_N)
    total = w_ebay + w_c24
    return (w_ebay / total, w_c24 / total) if total else (0.0, 0.0)


def confidence(tier: int, n_total: int, spread: float, mdape: float | None,
               estimated_reference: bool, degraded: bool) -> str:
    if tier <= 2 and n_total >= 10 and spread <= 0.25 and (mdape is None or mdape <= 0.07):
        level = 2
    elif n_total >= 5 and spread <= 0.45:
        level = 1
    else:
        level = 0
    if estimated_reference:
        level = min(level, 1)
    if degraded:  # a source failed this time
        level = max(level - 1, 0)
    return LEVELS[level]
