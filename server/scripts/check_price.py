"""Manual sanity check: python scripts/check_price.py Rolex 126610LN  (run from server/)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from watchbox.config import load_settings  # noqa: E402
from watchbox.ebay import EbayBrowseProvider  # noqa: E402
from watchbox.pricing import listing_matches, summarize_prices  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: python scripts/check_price.py <brand> <reference>")
    brand, reference = sys.argv[1], sys.argv[2]
    settings = load_settings()
    if not (settings.ebay_client_id and settings.ebay_client_secret):
        sys.exit("Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET in server/.env first")
    listings = EbayBrowseProvider(settings.ebay_client_id, settings.ebay_client_secret).search(brand, reference)
    kept = sum(listing_matches(title, reference) for title, _ in listings)
    print(f"{len(listings)} USD listings, {kept} match {reference} and aren't accessories (✓)\n")
    for title, price in sorted(listings, key=lambda item: item[1]):
        flag = "✓" if listing_matches(title, reference) else " "
        print(f" {flag} ${price:>10,.0f}  {title[:80]}")
    result = summarize_prices(listings, reference, "ebay")
    print("\nPrice:", f"${result.price_usd:,.0f} (median of {result.sample_size} after outliers)" if result else "not enough data")


if __name__ == "__main__":
    main()
