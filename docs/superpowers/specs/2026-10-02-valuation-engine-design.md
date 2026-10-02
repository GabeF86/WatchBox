# WatchBox v1, Part 1: Valuation Engine: Design

**Date:** 2026-10-02
**Status:** Approved in brainstorming, awaiting spec review
**Builds on:** `2026-09-27-watchbox-prototype-v0-design.md`, which is implemented in `server/`.

## Context

WatchBox v1 is three sub-projects, built in this order:

1. **Valuation engine** (this spec). It produces the most accurate estimate it can for each watch from several sources, adjusted for the watch's details.
2. **Web app, accounts and QR setup.** Each owner has a collection list with per-watch details. On first setup the box shows a QR code that opens the app's setup page and pairs the box to the account. This gets its own spec.
3. **3.5" display firmware.** The target board is an **ESP32-32E 3.5" LCD, 320×480, resistive touch**: panel HSD035577A3 (ST7796 driver), with a `BAT` LiPo connector, microSD and USB-C. It measures about 56 × 99 mm and 10.6 mm deep, and the long side still needs confirming. The screens show the slot map, plus per-watch detail: eBay 90-day sold median and range, Chrono24 asking price, and the estimate. This gets its own spec.

The v0 server already supports `PriceProvider` sources (eBay Browse, TheWatchAPI). TheWatchAPI's data ends in 2024-07, and eBay developer keys couldn't be obtained. Testing on 2026-10-02 showed that two Apify tools by `memo23` return good current data:
- **eBay sold listings, last 90 days:** for 116610LN, 30 sales with a median of about $11,500.
- **Chrono24 asking prices:** for 116610LN, 20 listings with a median of about $12,250.

The owner has decided to optimize for accuracy, not for data cost.

## Goals

1. Estimate each watch's resale value from comparable sales and listings, adjusted for its condition, box & papers, year, dial, bracelet and case metal.
2. Expose the underlying figures: eBay 90-day sold count, median and range, and Chrono24 asking count and median.
3. Report a confidence level backed by a measured accuracy check (the backtest).
4. Recalculate instantly when an owner edits a watch's details, without fetching new data.

## Non-goals (this part)

- Accounts, pairing and QR setup (part 2).
- 3.5" screens (part 3). The 16×2 LCD keeps showing one estimate per watch.
- The WatchCharts integration. The design leaves room for it as a third source, added once a key exists.
- Sold-price sources other than eBay.

## 1. Watch details (data model)

The `watches` table gains these columns. Older databases get them added on connect, like `price_date` and `price_reference` before them.

| Column | Type | Values | Default |
|---|---|---|---|
| `reference` | TEXT NOT NULL (existing) | may now be `""` when the owner doesn't know it | `""` |
| `year` | INTEGER NULL | 1900–current year | NULL |
| `condition` | TEXT | `new`, `excellent`, `very_good`, `good`, `fair` | `excellent` |
| `box_papers` | TEXT | `full_set`, `box_only`, `papers_only`, `watch_only` | `full_set` |
| `dial` | TEXT NULL | `black`, `blue`, `white`, `silver`, `green`, `grey`, `champagne`, `brown`, `red`, `other` | NULL |
| `bracelet` | TEXT NULL | `oyster`, `jubilee`, `president`, `leather`, `rubber`, `nato`, `other` | NULL |
| `metal` | TEXT NULL | `steel`, `yellow_gold`, `white_gold`, `rose_gold`, `two_tone`, `platinum`, `titanium`, `other` | NULL |

- **Validation:** brand and model are required. A reference, if given, must contain letters or digits.
- **Reference rule:** when `reference` is empty, the engine searches by brand and model plus whichever of dial and metal are set.
- **Web form:** the add and edit forms gain these fields, as dropdowns for the fixed lists.
- **Unchanged:** `price_reference`, the "price using reference" option, still overrides which reference is searched.

## 2. Sources and comparables

### Comparable (one normalized listing)

```
Comparable:
  source: "ebay" | "chrono24"
  kind: "sold" | "asking"
  price_usd: float
  date: date            # sold date for eBay, scraped date for Chrono24
  title: str
  url: str
  reference: str | None
  year: int | None
  condition: str | None   # same vocabulary as watches.condition
  box_papers: str | None
  dial: str | None
  bracelet: str | None
  metal: str | None
  best_offer: bool        # eBay "best offer accepted": the shown price may be above the real sale price
```

### Source interface

`ComparableSource.fetch(query: WatchQuery) -> list[Comparable]`, where `WatchQuery` holds brand, model, reference and the optional details. Network errors raise `SourceError`.

### `ApifyEbaySoldSource`
- **Actor:** `memo23/ebay-search-scraper-ppe`, called through `run-sync-get-dataset-items`.
- **Input:** `mode=sold`, `soldWithinDays=90`, `category=31387`, `marketplace=ebay.com`, `detailedItems=false`, `includeSummary=false`, `maxItems=60`, `searchQuery="<brand> <reference>"`. When there's no reference, the query is `"<brand> <model> <dial>"`.
- **Rows:** keep rows with a `priceValue` in USD.
  - `soldDate` (format `"Sold  Aug 31, 2026"`) is parsed to a date.
  - `bestOfferAccepted` is mapped to `best_offer`.

### `ApifyChrono24Source`
- **Actor:** `memo23/chrono24-scraper`.
- **Input:**
  - `startUrls=[https://www.chrono24.com/search/index.htm?query=<brand>+<reference>&dosearch=true]`
  - `fetchListingDetails=true`, so the listing's spec table is included: condition, scope of delivery, year, dial, bracelet, case material.
  - `maxIndexPages=1`, `maxItems=40`.
- **Rows:** keep rows priced in USD. The search URL sets `currencyId=USD`, and rows in other currencies are dropped.

### Shared settings
- **Auth:** `APIFY_TOKEN` in `server/.env`, sent as an `Authorization: Bearer` header. It never appears in logs or error messages.
- **Timeouts:** 300 s per run. Actors are run one at a time.

### Storage
New table `comparables`:

`id, watch_id, source, kind, price_usd, date, title, url, reference, year, condition, box_papers, dial, bracelet, metal, best_offer, fetched_at`

- Each refresh replaces that watch's comparables **per source**, so a source that fails keeps its previous rows.
- Rows are deleted along with their watch.

## 3. Reading listing details (`parse.py`)

These are pure functions with lots of tests. They take a title and an optional spec dictionary, and return the details.

- **Chrono24 spec table first.**
  - `Condition`: Unworn → `new`; Very good → `very_good`; Good → `good`; Fair or Poor → `fair`; Mint or Like new → `excellent`.
  - `Scope of delivery`: "Original box, original papers" → `full_set`. Box but no papers → `box_only`. Papers but no box → `papers_only`. Neither → `watch_only`.
  - `Year of production`, `Dial`, `Bracelet material`/`Bracelet`, `Case material`.
- **Title keywords** (used when the spec table is missing, or for eBay). All matching ignores case.

  | Detail | Keywords |
  |---|---|
  | `full_set` | `b&p`, `box and papers`, `box & papers`, `full set`, `complete set` |
  | `box_only` | `box only` alone means junk (see the junk filter); `with box` without papers means `box_only` |
  | `papers_only` | `papers`/`card` without box |
  | `watch_only` | `watch only`, `no box`, `no papers` |
  | `new` | `unworn`, `nos`, `brand new`, `new` (as a whole word) |
  | year | a standalone `19[5-9]\d` or `20[0-4]\d` |
  | dial, bracelet, metal | whole-word matches from the vocabularies in section 1, plus synonyms: `ss`/`stainless` → `steel`; `rolesor` → `two_tone`; `everose` → `rose_gold` |

- **Junk filter** (the listing is dropped):
  - Accessories: `box only`, `papers only`, `strap only`, `bracelet only`, `links only`, `dial only`, `bezel insert`, `crown only`, `case back`, `instruction manual`, `manual only`, `booklet`.
  - Not the real thing, or not as made: `for parts`, `parts only`, `for repair`, `needs repair`, `repair only`, `replica`, `homage`, `custom`, `aftermarket`, `diamonds added`, `aftermarket diamond`, `iced`. Factory gem-set models aren't filtered, because their own references keep them apart.
- **Reference match:** a listing matches when the normalized reference (letters and digits only, lowercase) appears in its normalized title or reference field. eBay sold rows must match the reference unless the owner left it empty.

## 4. Matching tiers (`match.py`)

Comparables are scored against the watch, using only the details the owner set:

| Tier | Rule |
|---|---|
| 1 | Reference matches (or, with no reference, brand and model appear in the title), **and** every set detail among dial, bracelet, metal matches. A listing that doesn't mention a detail counts as **neutral**, not a mismatch. |
| 2 | Reference matches. Dial, bracelet and metal are ignored. |
| 3 | Brand and model appear in the title. Only used when there's no reference, or when tiers 1–2 fail. |

- The engine picks the **tightest tier with at least 5 comparables**, counting both sources together. If none reaches 5, it uses the tier with the most comparables and caps confidence at low.
- Year: when the owner set a year, listings more than 3 years away are dropped, and listings with an unknown year are kept, provided at least 5 remain. Otherwise all are kept.
- **Outlier trimming, per source:** comparables outside `[Q1 − 1.5·IQR, Q3 + 1.5·IQR]` are dropped, computed after adjustment (section 5). With fewer than 4 comparables, nothing is trimmed.
- eBay comparables with `best_offer=true` are **excluded** before tier selection and factor learning, because the real sale price is unknown.
- **One consistent sample.** Trimming (`iqr_mask`) runs on adjusted prices and decides which comparables are kept. `n_ebay` / `n_c24` and the displayed raw stats (median, P10, P90, min, max) all come from those same kept comparables, with no second trim.

## 5. Adjustments (`adjust.py`)

Every comparable is converted to a **baseline watch** (full set, excellent condition), then to the owner's watch:

`adjusted = price / factor(comp) × factor(watch)`, where `factor = box_factor × condition_factor`.

**Starting factors (priors):**

| Box & papers | Factor | Condition | Factor |
|---|---|---|---|
| full_set | 1.00 | new | 1.10 |
| papers_only | 0.94 | excellent | 1.00 |
| box_only | 0.92 | very_good | 0.96 |
| watch_only | 0.85 | good | 0.90 |
| | | fair | 0.80 |

- **Unknown details:** a comparable with an unknown box & papers or condition uses factor 1.0 for that dimension, so it's treated as baseline.
- **Learned factors:** for each watch, and for each non-baseline value with `n ≥ 3` comparables, alongside `m ≥ 3` baseline comparables, from the same source:
  - `measured = median(group prices) / median(baseline prices)`
  - `factor = (n·measured + 10·prior) / (n + 10)` (shrinks toward the prior)
  - The result is clamped to `[prior − 0.10, prior + 0.10]`.

  Learned factors are stored with the valuation, so they can be inspected.

## 6. Blend and confidence (`blend.py`)

- **Per-source estimates.**
  - `ebay_est` = median of the adjusted, trimmed eBay sold comparables.
  - `c24_ask` = median of the adjusted, trimmed Chrono24 asking prices.
- **Asking-to-sold gap.** When both sources have at least 5 comparables at the chosen tier, `gap = 1 − median(eBay baseline prices) / median(Chrono24 baseline prices)`, clamped to `[0, 0.20]`. Otherwise `gap = 0.07`.
  - `c24_est = c24_ask × (1 − gap)`
- **Weights.** Start at `w_ebay = 0.7` and `w_c24 = 0.3`, then multiply each by `min(1, n_source / 10)` and renormalize. A source with zero comparables gets weight 0.
- **Final estimate.** `estimate = w_ebay·ebay_est + w_c24·c24_est`, rounded to the nearest $10.
- **Confidence.**

  | Level | Requirements |
  |---|---|
  | **high** | tier ≤ 2, and at least 10 comparables in total, and spread `(P90 − P10) / median ≤ 0.25`, and backtest median error ≤ 7% (when a backtest was possible) |
  | **medium** | at least 5 comparables, and spread ≤ 0.45 |
  | **low** | everything else |

  Using a `price_reference` (estimating from another reference) caps confidence at medium.
- **More caps.** With no eBay sold comparables (Chrono24 asking prices only), confidence is capped at medium. Tier 3 with an owner-set reference (a loose match) caps it at low.
- **Minimum sample.** If fewer than 3 comparables survive trimming, there is no valuation (the service keeps the previous one).
- The $10 rounding is half up.

## 7. Backtest (`backtest.py`)

A leave-one-out check on the watch's own eBay sold comparables at the chosen tier, run on every valuation:

- For each sold comparable `i`, compute the eBay estimate using all the other comparables (same tier rule, adjustments and trimming), converted to comparable `i`'s own details. Then record the error `|predicted − actual| / actual`.
- **Reported:** `n_tested`, the **median absolute percentage error** (MdAPE), and the share of predictions within ±10%.
- Runs on the kept (post-trim) eBay comparables.
- **Only run when** at least 6 sold comparables exist; otherwise it's reported as "not enough data".
- **Used for:** the confidence rule (section 6), and as evidence for tuning the priors. The check script prints it for every watch.

## 8. Output, storage and display

New table `valuations`, one row per valuation:

`id, watch_id, estimate_usd, confidence, tier, n_ebay, n_c24, ebay_median, ebay_p10, ebay_p90, ebay_min, ebay_max, c24_median, gap, w_ebay, w_c24, backtest_n, backtest_mdape, backtest_within10, factors_json, failed_sources, as_of`

- **The current price** becomes the latest valuation's `estimate_usd`. "Latest" means most recently written (highest id). A valuation's `as_of` is the fetch time of the comparables it was made from, so a recompute keeps the data date and doesn't count as a fetch. Existing code that reads `price_usd` gets it through the `_SELECT` join, which changes to join the latest valuation. The v0 `prices` table stays for providers that are still used (TheWatchAPI, eBay Browse).
- **Web page, per watch:**
  - The estimate with a confidence badge.
  - "eBay sold (90 days): N sales, median $X, typical $P10–$P90 (low $min, high $max)".
  - "Chrono24 asking: N listings, median $Y".
  - "Backtest: typically within ±Z%".
  - The tier, and the date.
- **LCD (16×2):** unchanged format, showing the estimate.
  - `~` still marks a `price_reference` estimate.
  - A low-confidence estimate adds `?` after the price when it fits, for example `$11,490?`.
- **`/api/display`:** unchanged for now. Part 3 adds a richer endpoint for the 3.5" screens.

## 9. Refresh and failure handling

- **Price source selection.** `PRICE_SOURCE=comps` selects the engine. With `PRICE_SOURCE=auto`, the engine is chosen when `APIFY_TOKEN` is set; otherwise the existing v0 providers are used.
- **Daily refresh** (`REFRESH_HOURS=24`), one watch at a time, both sources per watch. A watch is also refreshed when it's added, or when what its market data depends on changes (`Watch.priced_as`): its brand, reference or `price_reference`, and, only when it has no reference at all, its model, dial and metal too, since searches then use those. Editing the model of a watch that has a reference does not refetch.
- **Detail-only edits** (condition, box & papers, year, dial, bracelet, metal) **recompute from the stored comparables** with no new fetch, synchronously, before the edit page redirects.
- **"Refresh prices now"** refetches everything.
- **When a source fails:** keep the other source's comparables, mark the failed source in the valuation, and lower confidence one level. If both fail, keep the previous valuation and its date. Never store an empty valuation.
- **Edits during a refresh:** the existing protection applies. If the watch is edited or deleted while being fetched, the result is discarded.

## 10. Code layout

```
server/watchbox/valuation/
  __init__.py
  models.py        # Comparable, WatchQuery, Valuation dataclasses
  parse.py         # title and spec parsing, junk filter, reference matching
  match.py         # tiers, year preference, IQR trimming
  adjust.py        # priors, learned factors, to-baseline and from-baseline
  blend.py         # per-source estimates, gap, weights, confidence
  backtest.py      # leave-one-out MdAPE
  engine.py        # value(watch, comparables) -> Valuation (pure)
  sources/
    apify.py       # shared Apify client (run-sync, auth, errors, timeouts)
    ebay_sold.py   # ApifyEbaySoldSource
    chrono24.py    # ApifyChrono24Source
  service.py       # ValuationService: fetch, store comparables, value, recompute
server/scripts/check_valuation.py   # full breakdown for one watch
```

`engine.value()` is pure (no I/O), so all the maths is unit-testable.

## 11. Testing

- **Fixtures:** the real Apify output from 2026-10-02.
  - `ebay_sold_116610ln.json`: 31 rows, including the summary row.
  - `chrono24_116610ln.json`: 12 rows. It's re-captured with `fetchListingDetails=true` during implementation, so spec-table parsing has real data.
- **Unit tests:**
  - Parsing: each rule, the synonyms and the junk filter, with real titles from the fixtures.
  - Tiers: fallback, the 5-comparable minimum, year preference.
  - IQR trimming.
  - Adjustments: priors, learned-factor shrinkage and clamping.
  - Gap and weights, including the single-source case.
  - Confidence rules.
  - Backtest on a hand-built dataset with a known error.
  - Detail-only edits recompute without calling any source.
  - The failure behaviour in section 9.
  - Migration from a v0 database.
- **Source tests:** use `httpx.MockTransport` with the fixtures. No live calls in tests.
- **Manual check:** `scripts/check_valuation.py <watch id>` prints the comparables kept and dropped (with reasons), the tier, the factors, the per-source estimates, the blend, the confidence and the backtest. It's run live for all four of the owner's watches as acceptance.

## Acceptance

- All four of the owner's watches get a valuation.
- The 116610LN estimate falls between the eBay sold median and the Chrono24 asking median seen on 2026-10-02 (about $11.5k–$12.3k), unless the owner's details justify otherwise.
- Every valuation shows its breakdown and backtest on the web page.
- Editing a watch's condition or box & papers changes its estimate immediately, with no Apify call.

## Known limitations

- Condition factors rarely learn from data: sources seldom label a listing "excellent", so there is usually no baseline group and the priors stay in force.
- An unknown box & papers status is treated as a full set. Real data suggests unknown listings behave closer to 0.95.
- Per-source pooling of learned factors weights each source by its group size only, not by how reliable the source is.
- Engine refinements made during implementation:
  - IQR trimming uses a spread floor of 6% of the median, so tight clusters don't drop normal prices.
  - The asking-to-sold gap is shrunk toward the 7% default when there are few samples, and capped at 0–20%.
  - Learned factors are capped: no box & papers status beats a full set, "new" never ranks below excellent, and lower grades never rank above it.
  - Extra junk terms, including `pvd`, `dlc` and aftermarket gem phrases (diamond, sapphires, gem set). Gem phrases are ignored when the watch being valued is itself a gem-set reference.
  - "New" in an eBay title only counts at the start of the title.
  - The backtest reuses the factors learned on all comparables, so it has a slight optimistic bias.
  - Tier 3 may include listings without the reference, so when the owner set a reference, a tier-3 valuation is capped at low confidence.
- If a source keeps failing, its older comparables are kept and still used; the valuation lists that source as unavailable.
- If you switch from the engine back to a v0 source, an older engine valuation can hide the newer v0 price, because the latest valuation wins over prices.
- Per-watch refreshes on add or edit don't take the refresh-all lock, so they can overlap a scheduled refresh of the same watch (the result is still checked against the watch before it's stored).
