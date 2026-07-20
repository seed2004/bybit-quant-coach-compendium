# 00 — Overview

## The problem being solved

Selling options premium on crypto is attractive (high implied volatility, 24/7 markets,
weekly and daily expiries) but operationally punishing for a solo trader:

1. **The data is scattered.** Implied-vol surface, skew, term structure, funding, realized
   vol, open-interest/gamma positioning, and your own live greeks live in five different
   places. Deciding whether vol is *rich* right now means assembling all of it by hand.
2. **The exchange hides the true cost.** Bybit's option *mark* price is theoretical; the
   price you can actually transact is the bid/ask. Fees (trading + delivery) quietly eat a
   double-digit percentage of gross P&L. A position that looks green on mark can be a loss
   to close.
3. **Discipline decays.** Without a memory of what has actually worked *for you*, every
   decision restarts from intuition. The edge in premium selling is small and statistical;
   it only shows up if you measure your own record honestly.
4. **Naked short premium is unforgiving.** The book this was built for runs fully naked
   short strangles on BTC — an uncapped-tail posture. That demands a risk lens that never
   lets a "looks fine on mark" reading hide a tail that is quietly growing.

The system exists to collapse all of that into a handful of screens that answer concrete
questions: *Is vol cheap or rich? What structure fits this regime? Which of my legs needs
attention? Can I actually get out of this position, and at what cost? Where is my real
edge?*

## Product philosophy

- **Coach, not autopilot.** The software's job is synthesis, judgment support, and memory.
  The human keeps the executing hand. This is a deliberate safety and skill-building choice,
  not a technical limitation.
- **Transparency over black boxes.** Every score is a sum of visible components, each with
  a reason string that carries its own point contribution. The trader can always see *why*
  a strategy ranked where it did. No fitted ML weights that can overfit or can't be audited.
- **Honesty about sample size.** Any statistical claim (percentile ranks, personal
  win-rates, seasonality) is withheld or explicitly hedged until enough data exists to
  support it. "Only N days tracked so far" is a first-class output.
- **First-party data where it matters.** Rather than scraping third-party visualizers, the
  system computes its own IV surface from the exchange and accrues its own history. External
  venues (Deribit) are used only as a labeled *reference*, never as a hidden signal source.
- **The flywheel.** Every trade entered snapshots the full market context at entry. That
  record cannot be backfilled, so capture starts on day one — and the longer the system
  runs, the more its calibration is worth.

## The non-negotiable constraints (guardrails)

These held for the entire life of the project and shaped every feature:

1. **No order automation.** The read-only API surface is used deliberately: positions and
   wallet balance only. No trade, transfer, or withdrawal endpoints are ever touched.
2. **Not personalized financial advice.** Output is framed as data synthesis plus the
   trader's own rules. A disclaimer is always present.
3. **Per-account isolation.** The tool supports multiple sub-accounts with separate data and
   separate keys; no calculation ever leaks one account's data into another.
4. **Never emit invalid numbers.** `inf`/`nan` must never reach the JSON layer (they break
   the browser's parser). Undefined ratios are `null`, not infinity.
5. **Clearly flag estimated or missing data.** Anything unverified, placeholder, or
   soft-failed is labeled as such in the surface that shows it.

## Technology at a glance

- **Backend:** Python, an async web framework, an async HTTP client. Pure-function core
  modules (all the math) separated from the I/O layer so everything is unit-testable
  without a network.
- **Frontend:** a single self-contained HTML file, vanilla JavaScript, no build step. Tabs
  for each surface; a multi-account switcher.
- **Storage:** flat JSON files on disk (per-account portfolios and closed trades; global
  market-history stores). No database.
- **Data sources:** Bybit public V5 (instruments, tickers, candles, linear/perp index &
  funding), Bybit private V5 read-only (positions, wallet balance), Deribit public v2
  (DVOL index + option book summary) as an external reference.
