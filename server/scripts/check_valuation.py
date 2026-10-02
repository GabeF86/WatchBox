"""Explain one watch's valuation: python scripts/check_valuation.py <watch id> [--fetch]   (run from server/)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from watchbox import db  # noqa: E402
from watchbox.config import load_settings  # noqa: E402
from watchbox.providers import make_provider  # noqa: E402
from watchbox.valuation.engine import value  # noqa: E402
from watchbox.valuation.match import in_tier  # noqa: E402
from watchbox.valuation.parse import is_junk  # noqa: E402
from watchbox.valuation.service import ValuationService  # noqa: E402


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if len(args) != 1 or not args[0].isdigit() or any(f != "--fetch" for f in flags):
        sys.exit("usage: python scripts/check_valuation.py <watch id> [--fetch]")
    settings = load_settings()
    conn = db.connect(settings.db_path)
    watch = db.get_watch(conn, int(args[0]))
    if watch is None:
        sys.exit(f"no watch with id {args[0]}")
    if "--fetch" in sys.argv:
        provider = make_provider(settings)
        if not isinstance(provider, ValuationService):
            sys.exit("--fetch needs APIFY_TOKEN set (and PRICE_SOURCE auto or comps)")
        print("fetching comparables (takes a minute or two)...")
        if not provider.refresh_watch(conn, watch):
            print("fetch failed or no usable data; showing stored comparables")
    q = watch.query
    comps = db.load_comparables(conn, watch.id)
    print(f"\n{watch.brand} {watch.model} {q.reference or '(no reference)'} | {q.condition}, {q.box_papers}, "
          f"year {q.year or '?'}, dial {q.dial or '?'}, bracelet {q.bracelet or '?'}, metal {q.metal or '?'}")
    print(f"{len(comps)} stored comparables\n")
    for c in sorted(comps, key=lambda c: (c.source, c.price_usd)):
        reason = ("junk" if is_junk(c.title, q.reference) else "best offer" if c.best_offer
                  else "tier 1" if in_tier(c, q, 1) else "tier 2" if in_tier(c, q, 2)
                  else "tier 3" if in_tier(c, q, 3) else "no match")
        print(f"  {c.source:<8} ${c.price_usd:>9,.0f}  {reason:<10} {c.box_papers or '-':<11} "
              f"{c.condition or '-':<9} {str(c.year or '-'):<5} {c.dial or '-':<6} {c.title[:55]}")
    last = db.latest_valuation(conn, watch.id)
    v = value(q, comps, estimated_reference=bool(watch.price_reference),
              failed_sources=last["failed_sources"] if last else ())
    if v is None:
        sys.exit("\nno usable comparables")
    print(f"\nESTIMATE ${v.estimate_usd:,.0f}  ({v.confidence} confidence, tier {v.tier})")
    if v.n_ebay:
        print(f"  eBay sold: {v.n_ebay} used, median ${v.ebay_median:,.0f}, typical ${v.ebay_p10:,.0f}-"
              f"${v.ebay_p90:,.0f}, range ${v.ebay_min:,.0f}-${v.ebay_max:,.0f}")
    if v.n_c24:
        print(f"  Chrono24 asking: {v.n_c24} used, median ${v.c24_median:,.0f}, asking-to-sold gap {v.gap:.1%}")
    print(f"  weights: eBay {v.w_ebay:.0%}, Chrono24 {v.w_c24:.0%}")
    print(f"  factors: box {v.factors['box']}, condition {v.factors['condition']}, "
          f"learned {v.factors['learned']}")
    if v.factors.get("widened"):
        print(f"  widened to all dials/bracelets of the reference: {', '.join(v.factors['widened'])} "
              f"(too few exact matches); detail adjustments {v.factors['detail']}")
    if v.backtest_mdape is not None:
        print(f"  backtest: {v.backtest_n} sales, median error {v.backtest_mdape:.1%}, "
              f"{v.backtest_within10:.0%} within ±10%")
    else:
        print("  backtest: not enough sales")


if __name__ == "__main__":
    main()
