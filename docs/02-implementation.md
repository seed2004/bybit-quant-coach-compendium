# 02 — Implementation

How the system is built — described at the level of responsibilities, algorithms, and
patterns. No source code; this is the "how it's put together" companion to the design.

---

## 1. Module map (responsibilities, not code)

The backend is ~45 small modules. The split that matters is **pure core** (math, testable
offline) versus **I/O shell** (network, disk, endpoints).

### Pure core — market & instrument math

| Module | Responsibility |
|---|---|
| Chain builder | Merge instruments + tickers into unified contract objects; DTE filter; short cache |
| RV / IV stats | ATR, annualized realized vol, IV rank, IV/RV ratio |
| Volatility models | Parkinson / Garman-Klass / Yang-Zhang RV, HAR forecast, VRP, expected move, trend filter, funding summary |
| Fees | Trading-fee (with 7% premium cap) and delivery-fee model; round-trip fee helper |
| Risk / margin | Per-leg OTM-scan initial margin; position sizing; capital & utilization limits; vol-target scale |
| Payoff | Piecewise-linear breakeven / max-profit / max-loss / reward:risk for any leg set |
| P&L calculator | Side-aware gross minus round-trip fees; multi-leg totals; fee-adjusted breakeven via bisection |

### Pure core — synthesis & judgment

| Module | Responsibility |
|---|---|
| Strategy generators | ~11 structure builders, each producing candidate legs from a chain |
| Strategy engine | Runs all generators across the chain (calendars handled outside the per-expiry loop) |
| Playbook | Transparent additive scoring of every strategy; ranked output; "Wait" logic; gamma-flip |
| Idea engine | Re-runs the engine filtered to the coach's own strategy/DTE/delta band; sizes candidates |
| Roll engine | Same-strike vs strike-adjusted roll tables for flagged legs |
| Coach | Net signed book greeks; book assessment; prioritized position actions; setup annotation |
| Analytics | Closed-trade win-rate / expectancy / profit factor, segmented; discipline metrics |
| Calibration | Personal-edge nudges from closed trades, regime-aware, expectancy-gated, capped |
| Scenario | Reprice the book under spot/IV/time shocks (Black-Scholes); P&L, margin, breakeven breaches |
| Expiry focus | Per-held-expiry max-pain / GEX; gamma-zone tagging of your strikes |
| Carry | Dated-futures basis vs funding vs VRP; rule-based income verdict |
| Backtests | Walk-forward RV studies and IV-rule studies; no lookahead |

### I/O shell

| Module | Responsibility |
|---|---|
| Public exchange client | Instruments, tickers, candles, linear index & funding |
| Private exchange client | HMAC-signed read-only positions & wallet balance |
| Reference client | External venue's DVOL index + option book summary; delta reconstructed locally |
| Portfolio store | Leg CRUD; close (carries entry-context into the closed ledger); volume summary |
| Accounts store | Sub-account management; per-account directories; credential load/save |
| Regime history | Daily market snapshots; percentile / movement context |
| IV history | Intraday session-keyed IV snapshots; own-range percentile; seasonality |
| Crypto | Passphrase-based encryption at rest |
| Auth | Optional login gate |
| App / endpoints | ~40 routes wiring the above together |

---

## 2. Key algorithms in prose

### 2.1 Assembling the chain

Fetch instruments and tickers separately, key both by symbol, and merge into one contract
per symbol carrying strike, expiry, type, mark, mark-IV, bid/ask, and greeks. Compute
days-to-expiry from the expiry timestamp (options settle at 08:00 UTC). Filter by a DTE
window and cache briefly so a burst of endpoints doesn't refetch.

### 2.2 Computing the intelligence snapshot

For one underlying: pull the chain and spot (from the perp index, never the option ticker's
underlying field), compute ATM IV at the reference expiry, 25-delta skew, IV rank, term
structure, put/call ratio, the volatility-model block (RV, forecast, VRP, expected move,
trend, funding), and the gamma/max-pain/zero-flip block. Everything is assembled into one
summary object that the playbook, the coach, and the snapshot loop all consume. Optional
inputs (funding, the account's closed trades for calibration) are passed in so the same pure
function serves market-only and personalized callers.

### 2.3 Scoring the playbook

Start each strategy at 50. For each signal, look up that strategy's weight for that signal
and add `weight × signal_strength`, appending a reason string with the points inline. Apply
the defined-risk tie-break and the optional personal-edge nudges (after signal scoring,
before the clamp). Clamp, sort, and emit the top pick in the legacy recommendation shape (so
existing consumers don't break) plus the full ranked list. If the top score is below the
action threshold, the recommendation becomes "Wait" but the ranked list still ships.

### 2.4 Fee-adjusted breakeven by bisection

The net-at-expiry P&L as a function of the terminal underlying price is monotonic on each
side of the strike but kinked by the delivery-fee `min(...)`. Rather than solve the kink
analytically, bracket the breakeven and bisect against the *exact* fee model until the net
crosses zero. This automatically handles whichever fee term binds, and it agrees to the cent
with the fee model used on real closes (same code path, different caller).

### 2.5 Personal-edge nudge

Attribute each closed trade to a strategy family by its short leg. Within the family, filter
to a ±20 IV-rank band around the current regime if enough trades exist. Compute win-rate and
average expectancy. Convert to a point nudge that is gated on positive expectancy and capped
in magnitude, and attach the actual record as the reason. Below the minimum trade count,
emit nothing.

### 2.6 Walk-forward backtest slicing

Iterate day *t* over the history. The "known world" at *t* is the slice up to and including
*t*; the forward outcome is measured on strictly later bars over the study horizon. IV-rank
percentiles are computed only over the trailing window of *past* data. Any accidental use of
a future bar would inflate results, so the slice boundaries are the invariant the tests
guard.

### 2.7 Background snapshot loop

Wake on a coarse interval. For each underlying, check whether a daily regime snapshot and/or
an intraday IV snapshot is *due* (by UTC day and by session window). If either is due,
compute the intelligence snapshot once and write whichever stores are due. Window-based
due-ness (not a fixed instant) means an arbitrary wake phase never misses a session and
absorbs daylight-saving shifts in the reference session boundaries.

---

## 3. API surface (shape, not signatures)

Roughly 40 endpoints, grouped:

- **Market:** chain, strategy suggestions, the intelligence snapshot, matrix, arb scan,
  carry, the RV and IV backtests.
- **Portfolio:** enriched legs (with live mark, greeks, executable close quote, per-leg
  margin), volume summary, cycles, risk summary, analytics.
- **Coach:** the fused brief, scenario stress test, expiry focus, roll analyzer, regime
  history, grounded natural-language Q&A.
- **Account & settings:** sub-account CRUD and switch, credential status, risk config, the
  bring-your-own-key config.
- **Reconciliation:** the position preview/diff and the import.

Every account-scoped endpoint snapshots the active account directory before its first await.
Every endpoint that can hit the network soft-fails to a labeled "unavailable" rather than
throwing, so one dead upstream never breaks a whole screen.

---

## 4. Frontend patterns

- **One file, tab-switched surfaces.** Each tab lazy-loads its data on first open and on an
  explicit refresh.
- **Event delegation on stable containers.** Editable tables (the calculator, the legs
  table) attach one handler to the container, not one per row, so a full re-render never
  moves the caret while the user is typing. Writes are **debounced**.
- **Render from synthetic payloads.** Render functions are driven purely by a data object, so
  they can be exercised in a browser with a fabricated payload — which is exactly how the UI
  is verified (below) without needing live positions in a particular state.
- **Grouping and collapsing for scale.** Once the book grows, flat lists become noise, so
  legs and the live-margin breakdown are grouped per underlying with subtotals, and dense
  per-position detail hides behind a toggle whose open/closed state survives auto-refresh.
- **Color encodes the decision, not the raw number.** Where a value's usefulness depends on
  interpretation (close-quote economics, capture, margin share), color follows the *decision*
  meaning, with the raw/secondary detail demoted to a tag.

---

## 5. Testing and verification

### 5.1 Unit tests against synthetic fixtures

Because the math core is pure, every model is tested offline:

- Volatility estimators are checked against **seeded geometric-Brownian-motion candles** with
  a known vol.
- Fees are checked against the exchange's own **worked examples**.
- The payoff engine is checked against **closed-form** payoffs of standard structures.
- The margin formula is checked against the exchange's **worked margin example**.
- Backtests are checked against **seeded ground truth** so the walk-forward slicing is
  provably lookahead-free.
- Calibration, scoring, and the IV/skew sign conventions each have targeted tests — including
  a regression test that would catch the skew-sign bug.
- Invariants that protect the JSON layer (never emit `inf`/`nan`) are asserted directly.

### 5.2 Browser-driven verification of the UI

Beyond unit tests, UI changes are verified by driving a real browser against the running app:
render the affected surface (often from a **synthetic multi-asset payload** so edge cases
appear deterministically), read the resulting DOM back, and assert on the actual rendered
values and colors. Console and network are checked for errors. This catches the class of bug
that unit tests can't — a formula that's right but wired to the wrong column, or a color rule
that contradicts the number next to it.

### 5.3 The verification mindset

A change isn't "done" because the code looks right; it's done when the affected flow has been
exercised and observed. Several of the most important fixes in the project (the surface-avg-
vs-ATM IV bug, the close-quote color confusion) were found precisely because a rendered
result was read back and compared against what the number *should* mean.
