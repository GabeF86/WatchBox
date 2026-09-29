"""Manual sanity check: python scripts/check_price.py Rolex 126610LN  (run from server/)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from watchbox.config import load_settings  # noqa: E402
from watchbox.ebay import EbayBrowseProvider  # noqa: E402
from watchbox.pricing import listing_matches, summarize_prices  # noqa: E402
from watchbox.providers import make_provider  # noqa: E402
from watchbox.watchapi import TheWatchApiProvider  # noqa: E402


def check_ebay(provider: EbayBrowseProvider, brand: str, reference: str) -> None:
    listings = provider.search(brand, reference)
    kept = sum(listing_matches(title, reference) for title, _ in listings)
    print(f"{len(listings)} USD listings, {kept} match {reference} and aren't accessories (✓)\n")
    for title, price in sorted(listings, key=lambda item: item[1]):
        flag = "✓" if listing_matches(title, reference) else " "
        print(f" {flag} ${price:>10,.0f}  {title[:80]}")
    result = summarize_prices(listings, reference, "ebay")
    print("\nPrice:", f"${result.price_usd:,.0f} (median of {result.sample_size} after outliers)" if result else "not enough data")


def check_watchapi(provider: TheWatchApiProvider, brand: str, reference: str) -> None:
    body = provider.price_history(reference)
    meta = body.get("meta") or {}
    points = sorted(body.get("data") or [], key=lambda p: p["date"])
    print(f"TheWatchAPI: {meta.get('brand')} {meta.get('reference_number')}, {len(points)} points, newest 5:\n")
    for point in points[-5:]:
        print(f"  {point['date'][:10]}  ${point['price']:>10,.0f}")
    result = provider.get_price(brand, reference)
    print("\nPrice:", f"${result.price_usd:,.0f} (data from {result.as_of})" if result else "no price (no data, or brand doesn't match)")


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: python scripts/check_price.py <brand> <reference>")
    brand, reference = sys.argv[1], sys.argv[2]
    provider = make_provider(load_settings())
    if isinstance(provider, TheWatchApiProvider):
        check_watchapi(provider, brand, reference)
    elif isinstance(provider, EbayBrowseProvider):
        check_ebay(provider, brand, reference)
    else:
        sys.exit("Set THEWATCHAPI_TOKEN (or EBAY_CLIENT_ID and EBAY_CLIENT_SECRET) in server/.env first")


if __name__ == "__main__":
    main()
