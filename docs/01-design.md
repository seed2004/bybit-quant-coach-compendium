# 01 — Design

This document is the conceptual core: the architecture and the full library of quant
models the system is built on. Formulas are given because they *are* the ideas; no source
code is included.

> Every formula referenced here is stated in full — with its provenance tag and a numbered
> citation — in [07 — Math & references](07-math-and-references.md). Where this document
> says "Yang-Zhang" or "HAR-inspired" or "the delivery-fee cap", that document says exactly
> what the expression is and where it comes from.

---

## 1. Architecture

### 1.1 Two layers, one machine

- **A pure-function core.** Every piece of math — fees, margin, volatility estimators,
  payoff geometry, scoring, calibration, backtests — lives in modules that take plain
  numbers and return plain numbers. No network, no disk, no global state. This is what
  makes the whole system unit-testable against synthetic fixtures with zero I/O.
- **A thin I/O shell.** A small async web layer fetches exchange data, reads/writes the
  JSON stores, and calls into the pure core. Endpoints are deliberately dumb: fetch,
  compute, serialize.
- **A venue layer between the two.** Each exchange is described by a **spec** (pure data:
  contract sizes, fee rates and caps, which underlyings it lists, how it settles) and an
  **adapter** (the only code that knows that exchange's wire format). Everything above them
  talks to one canonical contract object and never to an exchange. See §6.

The discipline of "math is pure, I/O is a shell" is the single most important structural
decision. It is why every model below could be verified in isolation.

### 1.2 Frontend

- A **single self-contained HTML file** with vanilla JavaScript and no build step. Chosen
  for zero-friction deployment and total transparency — the entire UI is one file you can
  read top to bottom.
- **Tabbed surfaces**, each mapping to one decision context (screener, intelligence,
  portfolio, coach, calculator, etc.).
- **Event delegation** on stable container elements rather than per-row handlers, so live
  re-renders never steal input focus mid-typing. Network writes are **debounced**.

### 1.3 Per-account isolation

- Multiple sub-accounts, each with its own data directory and its own API credentials.
- **The race-safety rule:** every request handler captures the active account's directory
  path into a local variable *before its first `await`*. Because an account switch can land
  between awaits, reading the "current account" lazily would let one request read account A's
  positions and write them under account B. Snapshotting up front closes that race. This one
  rule is applied to every account-scoped endpoint without exception.

### 1.4 Storage

- **Flat JSON files.** Per-account: the open portfolio and the closed-trade ledger. Global
  (market data, not account-scoped): the daily regime history and the intraday IV history.
- No database — the data volumes are small, the access patterns are simple, and flat files
  are trivially inspectable and backup-able.
- **Global vs per-account is a deliberate split.** Market history is shared across all
  accounts because the market is the same for everyone; only positions and outcomes are
  private.

### 1.5 The background snapshot loop (the only "automation")

- A single background task wakes periodically and, for each underlying, captures a snapshot
  of the market context if one is due. It feeds **two stores at two cadences off one
  computation**: the daily regime store (once per UTC calendar day) and the intraday IV
  store (once per session window).
- **Idempotent capture:** writing "today's" snapshot replaces the existing row for that key
  rather than appending, so restarts and multiple fires never corrupt history.
- **Gaps are tolerated, never backfilled.** If the server was offline, that day is simply
  missing; the system never fabricates history.
- This is read-only capture. It is the *only* automated behavior in the entire system, and
  it touches nothing but its own history files.

---

## 2. Data sources

### 2.1 Bybit public (V5)

Option instruments and tickers (mark, mark-IV, bid/ask, greeks), daily candles, and
linear/perpetual index price and funding history. The option chain is assembled by merging
the instruments list with the tickers list into a unified contract object, filtered by
days-to-expiry, and briefly cached.

### 2.2 Bybit private (V5), read-only

Only two endpoints: current option positions and unified wallet balance. HMAC-signed
requests. **No trade, transfer, or withdrawal endpoint is ever called** — this is enforced
by simply never implementing them in the client.

### 2.3 Deribit — two distinct roles

Deribit appears twice in the system, and conflating the two would be a category error:

- **As an external reference (public, unauthenticated).** The DVOL volatility index and the
  option book summary, used to answer "are we rich or cheap versus the deepest-liquidity
  venue?" — always labeled as an external reference, never fed silently into any signal. This
  overlay is **hidden on a Deribit account**, where it would be a comparison with itself
  rendered as a row of zeros that reads like agreement.
- **As a first-class venue an account can trade on** (public chain + private read-only
  positions and balances). This is what §6 is about.

### 2.4 The index-price gotcha, and its bigger sibling

Bybit option tickers carry an `underlyingPrice` field that is **unreliable** as spot. Spot is
taken instead from the **linear perpetual's `indexPrice`**. Getting this wrong poisons every
downstream calculation (OTM amount, margin, moneyness, greeks), so it is centralized.

Both venues, it turns out, publish **two different underlying prices per expiry**: a
per-expiry **forward** *and* an **index**. They are not the same number — on one live
observation the forward sat **3.93% above** the index. The rule the system settles on:

- **greeks are computed on the forward** (that is what the option is written on), and
- **money conversions use the index** (that is what settles).

Using one where the other belongs is a ~4% error in the moneyness of every strike, and it
looks entirely ordinary.

---

## 3. The quant concept library

### 3.1 Options fee model

Realized P&L is computed **net of exchange fees**, because on a premium-selling book fees
are not a rounding error — on the reference book they ran roughly **13% of gross P&L**.

- **Trading fee per fill** = `min(rate × index, cap × option_price) × size`
  - taker rate ≈ 0.03%, maker ≈ 0.02%.
  - The **percentage-of-premium cap is the subtle part**, and it is a **venue** parameter —
    7% on one exchange, 12.5% on the other. For far-OTM cheap legs the percentage-of-premium
    term is smaller than the percentage-of-index term, so the cap binds. Ignoring it
    overstates the fee on exactly the legs a strangle-seller trades most; hardcoding one
    venue's value understates it on the other by nearly a factor of two.
- **Delivery (settlement) fee** = `min(deliveryRate × index, 12.5% × intrinsic) × size`,
  charged **only on exercise** (in-the-money at expiry); an out-of-the-money expiry is free.
  - `deliveryRate` ≈ 0.015% for BTC/ETH, ≈ 0.02% for alt underlyings.
  - **Exception:** *Daily* options incur **no** delivery fee. This single exception matters
    for breakeven math (below) and was re-verified against the exchange's own help page.
- A round-trip close pays trading fees on **both** the open and the close fill. Modeling
  only one side understates cost by half.

### 3.2 Initial-margin model (short options)

Per unit, for a short option:

```
IM = max( MaxIMFactor × index − OTM_amount , MinIMFactor × index ) + max( avg_price , mark )
```

then multiplied by size. Where:

- `OTM_amount(call) = max(0, strike − index)`, `OTM_amount(put) = max(0, index − strike)`.
- `MaxIMFactor`, `MinIMFactor` ≈ (0.10, 0.05) for BTC/ETH (verified against the exchange's
  worked example). Alt-coin factors are higher and live on a dynamically-rendered exchange
  page; where they can't be scraped, the BTC/ETH values are used as a **clearly-flagged
  placeholder** and the risk summary emits an "estimated" warning.
- A long option's margin is simply its premium.

**Why hand-roll this:** the unified account reports empty per-position IM/MM for options;
the real figures only come from the account-level wallet balance. To attribute margin *per
leg* (so the trader can see which legs to trim), the formula must be reconstructed. An early
version used a wrong delta-proxy and was ~2x off on deep-OTM legs — the corrected OTM-scan
formula above matches the exchange to the cent.

### 3.3 Contract-size convention

- Quantity is always stored in **underlying units** (e.g. BTC), not contract count.
- `1 contract = contract_size` underlying units: 0.01 for BTC/ETH, **1.0 for SOL** (a real
  gotcha — SOL's minimum order quantity is 1, not 0.01).
- Because qty is in underlying units, the margin formula is **size-agnostic** — it needs no
  knowledge of contract size. Only *contract count* and per-contract sizing need it. Keeping
  this straight prevents a whole class of 100x errors.

### 3.4 Volatility models

- **Realized-vol estimators** from OHLC candles: Parkinson (high-low range), Garman-Klass
  (adds open/close), and **Yang-Zhang** (adds overnight gaps; the primary estimator, most
  efficient for gappy 24/7 crypto).
- **RV forecast, HAR-inspired:** a fixed-weight blend of short/medium/long realized vol
  (weights 0.3 / 0.4 / 0.3 over 5 / 20 / 60 days of Yang-Zhang). The weights are **fixed and
  visible, not fitted** — deliberately un-optimizable so they cannot overfit.
- **Variance/volatility risk premium (VRP)** = `IV − forecast_RV`, reported both in vol
  points and as a ratio. This is the core "is selling premium worth it right now" gate.
- **Expected move** per expiry from the ATM straddle price, compared against the realized
  distribution of absolute moves over the same horizon — answers "is the market pricing more
  movement than tends to happen?"
- **Trend filter:** fast/slow moving-average relationship with a **dead-band** (~0.5%) plus a
  short lookback return. The dead-band is essential: a zero-tolerance MA comparison flips
  label on noise. (A test caught exactly this.)
- **Funding summary:** perpetual funding annualized from recent 8-hour rates — a positioning
  and carry signal.

### 3.5 ATM IV versus surface-average IV (a load-bearing distinction)

Averaging implied vol over *every* contract (all expiries, the whole smile) produces a
number dominated by the expensive wings — it can read ~41% when the true at-the-money vol is
~33%. That surface-average is **not comparable** to any single-point reference like DVOL or
another venue's ATM.

- The correct "IV" for cross-venue comparison and for headline display is **ATM IV**: the
  near-the-money implied vol at a reference expiry (the soonest with a few days to go, to
  skip the noisy 0-DTE smile).
- Mislabeling the surface-average as "ATM IV" and comparing it to an external ATM reference
  manufactures a phantom "we're 9 points rich" signal. **Always compare ATM-to-ATM.**

### 3.6 Skew (25-delta) and its sign convention

- **25-delta skew = put IV − call IV** at equal delta magnitude. **Positive = puts richer**
  (the normal fearful state).
- The sign convention must be applied *identically* everywhere it is consumed (labeling,
  digest signals, scoring). A sign bug that treated negative as put-rich labeled every
  fearful, put-rich market as "call skew" and scored it backwards — live and invisible until
  audited. The lesson: define the sign once, document it at every consumption site.
- When computing skew from a reference venue, the delta is reconstructed via Black-Scholes
  (all inputs are present) rather than trusted from a coarse strike grid, and the value is
  **withheld** when the nearest available strike isn't genuinely near 25-delta — a coarse
  grid must not be allowed to lie.

### 3.7 IV rank and term structure

- **IV rank** = where current IV sits within its own recent history, as a true percentile.
  Early versions used realized vol as a proxy denominator; the system now accrues real IV
  history (below) so the rank becomes a genuine self-referential percentile over time.
- **Term structure** = the shape of ATM IV across expiries (backwardation vs contango),
  which flips the attractiveness of calendar structures.

### 3.8 Executable pricing — the mark is not a price

The most practically important insight in the whole system. It applies at **both ends** of a
trade, and the system got the exit right long before it got the entry right.

#### 3.8a Entry: what a structure actually fills at

As a taker you never get mid. You get the side of the book that is worse for you:

- **SELL a leg → you receive the BID.**
- **BUY a leg → you pay the ASK.**

So a short strangle collects `bid_put + bid_call`, not `mid_put + mid_call`; a bull put
spread collects `bid_short − ask_long`. On the wide, deep-OTM books this account trades the
difference is not a rounding detail — **for a put quoted 5 / 25 the mid is 15 and the bid is
5, so two thirds of the "credit" a mid-based screener reports is spread handed to the market
maker on entry.** Every fill also pays a trading fee, charged on *every* leg — a four-leg
iron condor pays it four times on the way in.

The screener therefore reports **three numbers side by side**, so the gap cannot be missed:

| | meaning |
|---|---|
| `net_credit_mid` | the optimistic number a mid-based screener shows |
| `net_credit_exec` | after crossing the spread: bid on shorts, ask on longs |
| **`net_credit`** | after crossing **and** after entry fees — **what you keep** |

`net_credit` is the headline **deliberately**: it is the only one of the three that describes
money, and every downstream figure (breakeven, max loss, annualized yield, probability of
profit) is derived from it, so a candidate's numbers reconcile with each other. The identity

$$\texttt{net\_credit\_mid} - \texttt{net\_credit} = \texttt{spread\_cost} + \texttt{entry\_fees}$$

always holds, which is what makes the decomposition auditable rather than merely
pessimistic. **Edge retention** = `net_credit / net_credit_mid` is the fraction of the paper
credit that survives contact with the order book: a structure retaining 90% is a real trade,
one retaining 20% is mostly a gift to the market maker. (Formal statement:
[07 §8.6](07-math-and-references.md).)

Two failure modes are named rather than smoothed over:

- **`credit_vanishes`** — mid calls it a credit trade and the real book calls it a debit.
- **`quote_estimated`** — the venue publishes no quote on the side this fill needs (normal on
  short-DTE deep-OTM contracts), so the price fell back to mid/mark. The number is then a
  *model* price, not a fillable one, and the caller is told so rather than shown a plausible
  fiction.

**Exit costs are deliberately excluded from entry pricing.** What it costs to get out depends
on when and why you leave — expiring worthless is free, closing early crosses the spread
again and pays another fee — and that belongs to the roll analyzer (§3.20) and the P&L
calculator, not to a screener ranking entries.

**One source of truth.** The screener and the roll analyzer originally carried separate
copies of the same three helpers, which is exactly how a fix to one silently misses the
other. They now share a single pricing module; the identity above is what a test asserts.

#### 3.8b Exit: the executable close quote and Capture%

- Bybit's option **mark is theoretical (a model mid)**. It is *not* a price you can trade.
- To **close** a position you cross the spread: a short buys back at the **ask**, a long
  sells at the **bid**. That executable quote is what determines whether you can actually
  exit and at what cost.
- On deep-OTM legs the mark can be near zero (e.g. 0.02) while the only ask is a wide,
  one-sided quote (e.g. 5). "Slippage versus mark" therefore explodes to thousands of
  percent and is meaningless. Two corrected readings replace it:
  - **Crossing cost** measured as the **half-spread versus the bid-ask mid**, which never
    explodes; and a **one-sided flag** when only the side you must hit is quoted (no
    opposite quote → fill price is uncertain, use a limit).
  - **Capture%** = the fraction of the premium you actually keep if you close *now at the
    executable quote*: `(entry − buyback_ask) / entry` for a short (mirrored for a long).
    This is the honest cousin of the mark-based "profit%"; the gap between the two columns
    is the *cost of reality* (stale marks plus the spread). A leg can show a healthy
    mark-profit yet a negative capture — meaning closing it actually realizes a loss.
- **Color follows economics, not liquidity.** The close-price color tracks Capture% (green
  only when you keep a majority of the credit), while spread width lives as a subordinate
  tag. An earlier version colored by spread width and painted losing-but-tight legs green —
  a genuine confusion that the redesign fixed.

### 3.9 Fee-adjusted breakeven (why it needs a root-finder)

The at-expiry underlying price where a leg nets exactly zero **after** the open trading fee
**and** the delivery fee is not a closed-form expression. Because the delivery fee is
`min(rate × index, 12.5% × intrinsic)`, *which term binds depends on the premium size* —
cheap OTM legs hit the intrinsic cap, large legs hit the index term. So the breakeven is
solved by **bisection against the exact fee model**, not a formula.

- A short put's fee-adjusted breakeven shifts **up** toward the strike (less room); a short
  call's shifts **down**; longs need a bigger move to overcome the fee drag.
- For *daily* options the delivery term is dropped entirely, so the breakeven collapses to a
  clean `strike − (entry − open_fee)`.

### 3.10 Payoff engine (piecewise-linear)

A generic engine computes **exact breakevens, max profit, max loss, and reward:risk for any
combination of legs** by evaluating the piecewise-linear expiry payoff — the kinks are at
the strikes, so the whole curve is determined by its value at and between strikes. Verified
against the closed-form payoffs of standard structures. Cross-expiry structures (calendars)
are excluded because their payoff isn't piecewise-linear at a single expiry.

### 3.11 Gamma positioning: GEX, max pain, zero-gamma flip

- **Max pain** = the strike minimizing total option-holder value (where the most open
  interest expires worthless) — a soft magnet into expiry.
- **Gamma exposure (GEX) profile** across strikes classifies each of your strikes as sitting
  in a dealer **long-gamma** zone (mean-reverting, pin-safe) or **short-gamma** zone
  (trend-accelerating). Heavy put open interest flags short-gamma; heavy call OI flags
  long-gamma.
- **Zero-gamma flip** = the spot level where the cumulative net-GEX profile crosses zero —
  the boundary between the stabilizing and accelerating regimes. Used as a summary field, a
  digest signal, and a scoring input.

### 3.12 Regime detection and memory

- Each underlying's regime is summarized from IV rank, VRP, trend, skew, put/call ratio,
  funding, and term structure, and condensed into a one-line **named regime banner** (e.g.
  "High-IV, range-bound, contango, premium-rich"), tinted by VRP.
- **Historical context via percentile rank:** today's reading is ranked against the book's
  own recent history (e.g. last 90 days), and a 5-day movement arrow is attached. Both are
  **withheld or hedged below a minimum sample** — "only N days tracked so far" instead of a
  percentile the data can't support.

### 3.13 Strategy playbook — transparent additive scoring

- Every candidate strategy starts at a **base score of 50**. Each signal component (VRP, IV
  rank, trend, skew, put/call ratio, funding, term structure, expected-move richness, gamma
  regime) adds or subtracts **visible points**, and each point contribution is carried
  inline in a human-readable **reason string**. Scores are clamped to a sane band.
- **Defined risk is structurally favored:** naked/undefined-risk structures carry a small
  fixed penalty plus a tie-break, so at equal signal edge a defined-risk structure outranks
  a naked one.
- The top pick is emitted, or **"Wait"** when nothing clears an action threshold — but the
  full ranked list is always attached so the UI can show *what was considered and why*.
- Because scoring is pure addition of labeled components, it is completely auditable. There
  is no fitted model and no hidden weight.

### 3.14 Strategy library (the structures scored)

A library of ~11 generators, each a pure function over a chain: cash-secured put, covered
call, bull-put and bear-call credit spreads, iron condor, short strangle, **jade lizard**
(short put + short call spread, emitted only when the credit ≥ the call-spread width so
upside risk is structurally zero), **broken-wing butterfly** (credit put fly harvesting put
skew), **put ratio spread**, **calendar** (the only long-vega/debit structure — it *inverts*
the VRP/IV-rank/term-structure scoring because it wants cheap vol and contango, so low-IV
regimes surface a calendar instead of "Wait"), and defensive structures: **put ladder**
(short put + two lower longs, credit-only, so a crash turns *profitable*), **iron butterfly**
(ATM pin play), and **seagull** (zero-cost-or-credit directional participation). Each is
liquidity-filtered and payoff-annotated.

### 3.15 Personal-edge calibration (the learning loop)

The system leans its advice toward what has actually worked for the trader — bounded,
transparent, and sample-gated:

- Closed trades are **attributed by the short leg**: a short put credits the put-selling
  families (CSP, bull-put, jade, broken-wing, put-ratio); a short call credits the
  call-selling families. Range structures (condor, strangle, calendar) are honestly
  **un-attributable** from leg data and get no nudge.
- The nudge is computed from **win-rate and expectancy**, and is **regime-aware**: it narrows
  to trades entered within a ±20 IV-rank band of the current regime when enough exist, else
  uses all history.
- It is **expectancy-gated** (a high win-rate can't rescue negative expectancy) and
  **hard-capped** (roughly ±6 points) so market signals still dominate. A minimum trade count
  gates it on entirely.
- When applied, each nudge adds its own reason line carrying the actual record
  (e.g. "your put-selling in similar IV: 8-2, +142 avg → personalized +6").
- **The flywheel that feeds it:** every entered leg snapshots the full market context at
  entry (IV rank, IV/RV, skew, term structure, put/call ratio, VRP, funding, trend, regime
  label, spot). This snapshot **cannot be backfilled**, so it is captured from day one and
  becomes more valuable the longer the system runs. Stored *market* history stays pure — the
  calibration feedback is applied only at the advice layer, never written back into the
  recorded regime data.

### 3.16 Carry monitor

Compares three sources of yield to decide where the income is: **dated-futures basis**
(annualized, cash-and-carry), **perpetual funding**, and the **VRP** (option selling). A
rule-based verdict picks carry / vol / both / neither against explicit bars (e.g. basis
≥ 5%/yr, VRP ratio ≥ 1.05). A venue gotcha shaped this: the exchange **ignores the base-coin
filter on linear tickers**, returning every contract, so results must be filtered by symbol
prefix.

### 3.17 Backtesting methodology

- **Walk-forward with no lookahead**, enforced by a strict slicing convention: "the world as
  of day *t*" is only the data available up to *t*. Forward outcomes are measured on strictly
  later bars. This rule is the difference between an honest backtest and an accidental oracle.
- **Realized-vol studies:** HAR-blend forecast vs a naive trailing estimator (error/bias/beat-
  rate); trend-label to forward outcomes (the "falling-knife" guard's report card); and
  sigma-based strike touch/finish probabilities versus one-sided normal theory.
- **IV studies**, unblocked by a reference venue's multi-year DVOL history: the structural VRP
  edge (implied vs tenor-matched realized-forward) and the predictiveness of IV rank (does
  "sell when IV rank is high" pay?).
- **Headline empirical findings** (the reference book, BTC):
  - The **ATM vol-risk premium is razor-thin** (implied ≈ realized-forward over ~30 days) —
    so this book's edge is **not** ATM richness but the **OTM skew/tail it sells** (naked
    strangles) plus theta/gamma management.
  - **IV-rank timing does add** a couple of vol points (sell-high-IV-rank validated); the mid
    tier is noisy from overlapping windows and is reported as such.
  - Crypto **tails are ~2.7x Gaussian** at monthly horizons (a 2-sigma/30-day put finishes
    in-the-money ~6% of the time vs ~2% under normal theory) — an argument for shorter DTE or
    wider strikes on long-dated naked puts.

### 3.18 Risk sizing

- **Vol-targeted sizing:** scale position size by `min(1, target_vol / realized_vol)` with a
  floor, so exposure shrinks when the market gets loud. The realized-vol feed is the latest
  regime snapshot (disk read, no network).
- **Capital and margin limits** convert a capital figure and a max-utilization setting into a
  contracts-allowed cap; a result of `0` is a real "your limits don't allow this at current
  capital" signal, distinct from `null` (capital not configured).

### 3.19 Book-sync / reconciliation

On a cadence, the local book is diffed against the exchange's live positions to detect three
kinds of drift: **new** legs present on the exchange but not tracked, **size-changed** legs
(a partial close or add), and **closed-early** legs gone from the exchange before expiry. The
trader is prompted to import/update or to record the close. The diff runs on every book
reload so any action clears or refreshes it immediately, rather than lingering until the
next timer tick.

### 3.20 Roll economics — price it, score it, then check your own record

Rolling is the single most consequential recurring decision on a short-premium book, and the
one most easily rationalized. The system attacks it in three layers, each answering a
question the previous one cannot.

#### Layer 1 — what does this roll actually pay?

For a short leg that is tested or near expiry, the analyzer tables the concrete choices from
the live chain: **roll out** (same strike, later expiry) and **roll out & adjust** (strike
moved further OTM toward a defensive delta target, later expiry).

A roll **crosses the spread twice** — buy the old leg back at the ask, sell the new one at
the bid — and pays a trading fee on **both** fills. Mid-based roll numbers therefore
overstate the payment systematically; on a wide deep-OTM book the entire apparent "credit"
can be slippage. The same three-number decomposition as §3.8a applies, with `mid_flatters`
flagging the case where mid says credit and reality says debit.

**Per-day figures, not the raw credit, are the comparison.** The variance risk premium's term
structure slopes steeply downward, so rolling further out for a bigger *absolute* credit
often buys **less premium per unit of time-risk**. Candidates at different expiries are
compared on credit-per-day and yield-per-day (credit per day as a percentage of collateral),
never on the headline number.

#### Layer 2 — is it a *good* roll, not merely a paying one?

A roll can pay a fat credit and still be a bad idea: it may be selling cheap vol, moving the
strike inside one expected move, or doubling the margin to buy a few days. Five independent
axes are scored 0–100 and weight-averaged, and **the full breakdown is always returned**, so
the trader can disagree with any single axis instead of trusting an opaque rank:

| Axis | Weight | What it asks |
|---|---|---|
| **carry** | 0.25 | credit per day on collateral, annualized — are you paid enough per day? |
| **vrp** | 0.25 | the **new** contract's IV vs forecast RV — is what you're selling actually rich? |
| **safety** | 0.25 | distance from spot to the new strike **in expected moves** |
| **gamma** | 0.15 | improvement in \|θ\|/\|Γ\| — the mechanical reason to roll out of expiry week |
| **capital** | 0.10 | margin change — a credit that doubles initial margin is not free |

Three design points carry the section:

- **Safety is measured in expected moves ($\sigma\sqrt{T}$), not in %OTM.** Raw distance is
  not comparable across tenors. A consequence worth stating because it surprises people: a
  **same-strike roll scores *worse* on safety as the tenor grows** — correct, because it buys
  *time*, not *safety*, while the move budget grows with $\sqrt{T}$.
- **The VRP axis prices the contract you are opening, not the one you are closing.** "Rolling
  into cheap vol to fix an old problem" is the classic losing roll, and it is only visible if
  the new leg's IV is checked against forecast RV.
- **Gates are reported separately and never folded silently into the score.** A debit roll,
  or one selling below forecast RV, caps the verdict at *questionable* no matter how the
  weighted average lands — so a high score with an open gate still reads as a warning rather
  than as approval.

Weights renormalize over whichever axes are computable, so a missing gamma feed degrades the
score's resolution instead of silently zeroing an axis.

#### Layer 3 — across your history, do rolls create value or postpone losses?

Layers 1 and 2 are about one decision in front of you. Layer 3 is the only one that can
answer *"does rolling work for me"*. Legs are linked by a **roll chain**: the original
position, then each replacement created by rolling it.

- **Martingale detection.** Rolling a tested position repeatedly — especially while
  increasing size — is the classic way an income book with an uncapped tail dies. Each roll
  individually looks like "collect more credit"; **the chain is what reveals that fresh risk
  has been financing a losing position.** Warnings fire on structure, not prediction: rolled
  ≥3×; size grew across the chain ("adding size to defend a position is doubling down, not
  managing risk"); the chain's realized total is negative; every roll in the chain was made
  while losing.
- **Personal evidence.** Completed chains are split by **the state at roll time** — rolled
  while in profit (redeploying a winner) versus rolled while tested (defending a loser) — and
  both are compared against positions never rolled. Two rules keep that comparison honest:
  only **completed** chains are scored (an open chain's P&L is not decided yet, and counting
  it flatters whichever way the position happens to be sitting), and a chain containing
  **both** kinds of roll counts as *defensive* — the defensive roll is the risk-relevant
  event, and treating a mixed chain as clean would bias the comparison in rolling's favour.
- The roll context is **captured on the new leg at roll time**, never reconstructed
  afterwards, because "was I in profit when I rolled?" cannot be recovered from a closed
  ledger.
- Below the sample gates the report shows **counts and withholds the verdict**.

### 3.21 Theta efficiency — is the carry actually being paid for?

The portfolio table shows theta per day, but that number alone says nothing. **Theta is not
income: it is the rent collected for carrying gamma.** Over a day a short option earns
roughly $|\Theta| - \tfrac12\Gamma(\Delta S)^2$, so the move that exactly consumes a day's
theta is $\Delta S^\ast = \sqrt{2|\Theta|/\Gamma}$.

**The trap this module exists to avoid.** It is tempting to compare $\Delta S^\ast$ against
the IV-implied daily move. That comparison is **circular**: Black–Scholes fixes
$\Theta = -\tfrac12\sigma^2S^2\Gamma$, so substituting collapses $\Delta S^\ast$ into the
implied move itself. Verified on the live chain, the ratio sits at a flat **≈0.96 across
every strike and every tenor** — it carries no information at all. (Derivation:
[07 §9.2](07-math-and-references.md).)

**The comparison that does carry information is against *realized* movement.** That is the
variance risk premium measured on *this specific leg with its own greeks*, rather than as a
surface average — and it is the honest answer to "is this theta worth it". Realized above
breakeven means the position **loses in expectation even while theta prints positive every
day**, which is precisely the failure mode a theta-focused dashboard would otherwise hide.

Two by-products fall out of the same numbers:

- **A stale-greeks detector.** Because the ratio in the trap above *must* be ≈0.96, any leg
  wandering far from it has stale or inconsistent greeks, and its efficiency read is flagged
  untrustworthy. A degenerate identity turned into a data-quality check.
- **Fragility to a vol spike**, as the number of days of theta one vol point costs
  ($|\nu| q / \Theta$). A leg needing many days to earn back a one-point IV rise is fragile
  regardless of how good its carry looks.

Alongside these: theta per unit of margin (comparable across legs of different sizes) and
days-to-collect the remaining premium. When no realized-movement baseline is available the
verdict is **`unknown`** — the system does not substitute implied, because that is exactly
the circular comparison above.

**The units trap, stated because it is invisible.** On an enriched leg theta is *position*
theta (already multiplied by quantity) while gamma and vega are *per-unit*. Mixing the two
scales leaves a stray quantity inside the square root and produces a plausible, wrong
breakeven. Everything converts to per-unit first.

### 3.22 The monthly-income layer — earn, support, and don't chase

Everything else in the system measures a **trade**: expectancy, win rate, profit factor, hold
time. *"Can I live off this?"* is a different question — it is about **time and capital, not
about trades** — and none of the per-trade statistics answer it. A book can have an excellent
expectancy per trade and still be unusable as an income stream if the month-to-month path is
violent enough.

Three layers, each answering the question the previous one exposes.

#### A — What did the months actually do?

Realized P&L bucketed by the calendar month a trade **closed** in, net of fees, plus:

- **Return on the margin that was tied up to earn it.** 500 on 5,000 of margin and 500 on
  50,000 are not the same business. Margin at entry is reconstructed with the same formula the
  risk tab uses, which needs the index at entry — so trades opened before entry-context
  capture existed are **reported as uncovered rather than guessed at**, with the coverage
  percentage stated.
- **Consistency, expressed as the number that actually decides it.** Not the average:
  **how many average winning months the worst month erased.** For a negatively-skewed
  short-vol book that ratio is what determines whether the income is spendable.
- **Drawdown on the cumulative curve**, with whether and how quickly it recovered.

Two honesty rules are load-bearing:

- **The current month is incomplete and is excluded from every statistic** — including it
  flatters or damns the record at random. It is still *shown*, flagged as partial.
- **This is a realized-P&L curve, not account equity.** Open positions are not marked. A
  short-vol book can show a beautifully smooth realized curve while carrying a large
  unrealized loss it has not taken yet — which is precisely the failure mode a "monthly
  income" framing encourages. Every report says so.

And the gate: monthly statistics need **months, not trades**. A hundred trades inside three
months is still three data points, so below a minimum of complete months every derived
statistic is withheld and the reason is printed.

#### B — How much can come out before the program stops surviving?

Fitting a distribution to a dozen observations of a negatively-skewed, fat-tailed return
stream produces a clean number worth nothing. So the system **bootstraps from the months
actually observed** — resampling with replacement, compounding equity proportionally, taking
the withdrawal in cash afterwards, seeded so the answer does not move between reloads.

That buys honesty at a price which is restated every time it is shown:

> **A bootstrap cannot produce a month worse than the worst one observed.** If the sample has
> not lived through a crash, every path is optimistic and the ruin rate is a **floor, not an
> estimate**.

**The distinction that makes this layer worth having.** There are two different "how much can
I take out" questions, and the obvious one is not the one people mean:

- **Max sustainable** = the largest withdrawal whose ruin rate stays inside a tolerance. Its
  test only cares about not falling below a ruin threshold — so it will happily approve a path
  that consumes most of the account. On the reference book, a +555/month average produced a
  "sustainable" **2,966/month while the median account fell from 100k to 38k**. That is
  capital depletion on a schedule, not income.
- **Max preserving** = the largest withdrawal that still leaves the **median path with at
  least its starting capital** at the horizon. This is living off the income rather than
  eating the principal, and it is the number the cadence layer checks targets against.

Both are found by bisection and **rounded down, never to nearest** — a safety limit was
chosen because it clears a threshold, and rounding it up can push the reported figure past the
very threshold that selected it. A returned `0` is a real answer: *even withdrawing nothing
breaches the tolerance*, i.e. the sample does not support drawing an income at all.

**The tail budget sits deliberately alongside, not inside, the bootstrap.** Because the
resampling cannot invent a crash, the stress number is computed by **repricing the current
book under a shock** — which does not depend on the sample having contained one — and is
expressed in the only unit that makes an uncapped-tail book legible:

> *"A 20% move erases N months of average income."* Premium selling accumulates income
> linearly and gives it back in jumps. This is the size of one jump.

#### C — The guardrail: what a target does to behaviour when the month runs short

Phases A and B measure what the book earns and what it can support. Phase C watches the thing
that destroys both: **the behaviour a monthly target induces when the month is behind.**

The failure mode is specific and predictable. Two thirds through the month, income is behind
target, and the fastest way to close the gap is to sell more premium — bigger size, or strikes
closer to spot. Both raise risk precisely when the motivation is a number rather than a setup.
On a naked short book, that is how a good year ends.

So this layer refuses to make progress look easier than it is:

- **Premium sold is not income.** Credit collected on legs still open is an **obligation** —
  it can be handed back in full and then some. It is reported separately and **never added to
  booked P&L**. A trader "hitting target" on open premium has hit nothing.
- **The target is checked against measured capacity, not accepted as given.** If it exceeds
  the preserving withdrawal from layer B, the target is not ambitious, it is *unsupported* —
  and no amount of pace fixes that. This is raised as a critical warning regardless of how the
  month is going.
- **Risk headroom is checked before pace.** If the margin budget is already spent, the gap
  cannot be closed within the plan at any pace, and the only honest answer is that the month
  ends where it ends.
- **Pace is expressed as a multiple of normal.** *"Needs 3.4× your usual daily rate with 9
  days left"* is a statement about pressure; *"behind by 400"* is not. Past a stretch multiple
  the advice is to decide **now** that you will accept missing the target; past a chase
  multiple the warning names the mechanism — *"a number that far out of reach is how size
  creeps up and strikes drift toward spot: the trade gets taken for the target, not the
  setup."*

The verdict orders **pressure first, progress second** — a book that is nominally on pace but
has already spent its margin budget reads as *chasing risk*, not as *on pace*.

### 3.23 Wheel cycles

A small store that links related legs — a cash-secured put and the covered call that follows
assignment — into one **cycle**, so premium collected, net cost basis (`strike − total
premium`, the break-even if assigned) and full P&L are tracked across the whole structure
rather than per leg. Cycle statistics are **derived at query time** from the portfolio and
closed ledgers rather than stored, so they cannot drift out of sync with the legs they
describe.

### 3.24 Pin evidence — measuring the practitioner constructs

§3.11's gamma machinery (max pain, GEX, zero-gamma flip) is **practitioner folklore with a
real mechanism underneath it** and no canonical academic definition. Rather than trusting it
or discarding it, the system **measures it on this venue's own data**.

Every day, each live expiry gets one row: max pain, spot, the gap between them, net GEX, the
gamma zone at spot. Once the expiry passes, the row sequence becomes a completed sample. Two
tests, in a deliberate order of trustworthiness:

1. **Settlement evidence — the real test.** Where the expiry actually printed: did it land
   closer to max pain than it started, and did it settle within a tolerance of the pin?
2. **Convergence evidence — a proxy.** Did the spot-to-max-pain gap narrow between the first
   and the last pre-expiry capture?

Everything is scored on the **context at first capture** — the gamma zone, the approach
direction — because that is what a forecast would actually have had available. Scoring on
context known later would be a lookahead in miniature.

The honesty rules mirror the rest of the system, with one addition that matters:

- An expiry needs **≥2 captures** to measure convergence at all; a single row is dropped.
- **Daily expiries are segmented out and never silently pooled.** The pinning literature is
  about *serial* expirations carrying real open interest; crypto dailies carry very little, so
  pooling them with the monthlies drowns the signal in noise that looks like data.
- **The sample gate rises with the cut.** Segmenting splits the same evidence into thinner
  cells, so a segment must clear its own higher bar rather than inheriting the pooled minimum.

The advice layer consumes this through a **preference hierarchy** — settlement evidence over
convergence, and within each, the most specific segment that clears its own bar, falling back
to pooled. When nothing clears, the answer is **`sufficient: false` with no rate at all**, and
callers are required to say the pin is **unmeasured** rather than quietly reverting to
asserting that pins hold. That last rule is the whole point of the store: it converts a belief
into either a number or an admission.

---

## 4. Security design

- **Encryption at rest.** Credentials and any bring-your-own API key are encrypted with a
  passphrase-derived key (scrypt over a per-value random salt → an authenticated symmetric
  cipher). The salt is embedded per value in a self-describing envelope, so there is no
  separate salt file to lose. A missing/wrong passphrase yields a clearly-reported **locked**
  state (configured but unusable) rather than a crash. Legacy plaintext is passed through and
  auto-migrated to ciphertext on the next save.
- **Optional login gate** for remote access: an HMAC-signed, HttpOnly session cookie with the
  signing key derived from the password; the whole app sits behind a device-level VPN, and
  the app password is defense-in-depth on top.
- **Secret hygiene is the real leak guard.** Credentials, the account directory, the
  bring-your-own-key file, and the market-history files are all excluded from version control.
  Encryption is defense-in-depth; the ignore rules are the primary control. (See
  [06 — Lessons](06-lessons-and-gotchas.md) for the incident that taught this the hard way.)

---

## 5. Risk constitution (the naked-strangle lens)

The reference book runs **fully naked short strangles on BTC** — an uncapped-tail posture.
That shapes the risk view:

- Every "looks fine" reading is stress-tested against the tail, never just the mark. The
  executable-close and Capture% work exists precisely so a growing tail can't hide behind an
  optimistic mark.
- The backtest finding that crypto tails run far fatter than Gaussian is treated as a
  standing warning, not a curiosity — it argues directly against long-dated naked puts at
  wide-but-not-wide-enough strikes.
- Defined-risk structures are structurally favored in scoring, and the calibration loop can
  only *tilt*, never *override*, the market-signal and risk-limit gates.

---

## 6. Multi-venue accounts, and inverse settlement

An account belongs to **one venue**, fixed at creation. Everything the account sees — the
asset list, the credential labels, the chain, the positions, the margin panel, the currency
its P&L is denominated in — follows from that. This section is the design that makes a second
exchange possible without forking the engine.

### 6.1 Which book to integrate — a decision made by measurement

Deribit lists BTC options in **two separate books**, and they are not interchangeable:

| | coin-margined `BTC-*` | `BTC_USDC-*` |
|---|---|---|
| instruments listed | 866 | 468 |
| with a two-sided quote | 808 | 392 |
| open interest | **323,905 BTC** | 7,367 BTC (**2.3%**) |

The USDC book would have been far easier — it is linear, so it behaves like the existing
venue and needs none of §6.3–6.5. It is also, on the evidence, **not where the market is**.
Integrating the easy book would have produced a working feature that nobody could trade at
size. The coin-margined book was chosen because the numbers said so, and the entire
inverse-settlement problem below is the price of that choice.

### 6.2 Normalise at the edge

The strategy engine, the playbook, the payoff math and the scoring exist once. Making them
venue-aware would mean threading a venue through every function and adding a branch at every
site — the shape of change that produces subtle divergence between two code paths that are
*supposed* to agree.

Instead, **each adapter converts its venue's wire format into one canonical contract object**,
with implied vol as a decimal, prices in USD, and greeks on the forward. Above the adapter,
nothing knows which exchange it is looking at. A coin-quoted premium is multiplied by the
index at the adapter boundary; vol points are divided by 100 there; the venue's own greeks are
reproduced there (with Black-76 where they are not published, verified against the venue's own
figures to a worst error of 0.00002 in delta).

### 6.3 The one thing that must **not** be normalised: booked money

This is the single most important rule in the multi-venue design, and it contradicts §6.2 on
purpose.

Sell 1 BTC put for **0.01 BTC** with BTC at $60,000; buy it back for **0.005 BTC** with BTC at
$90,000:

| | premium | index | in USD |
|---|---|---|---|
| open | 0.01 BTC | $60,000 | $600 |
| close | 0.005 BTC | $90,000 | $450 |

The account **keeps +0.005 BTC**, worth **$450** today. A naive USD difference says
**+$150**. Both look reasonable. They differ by **3×**.

The error is not arithmetic — it is that a round trip has **two ends at two different
indices**, so there is no single exchange rate at which the difference is meaningful. Booked
money is therefore stored, summed, and displayed **in the currency it was actually booked
in**, and never converted after the fact.

### 6.4 The principle that resolves §6.2 against §6.3

> **Converting is valid for a snapshot and invalid for booked money.**

Every screener figure is a *ratio or a comparison at one instant* — yield, breakeven distance,
probability of profit, the ranking of two candidates. One index at one moment leaves all of
them invariant, so normalising the chain changes nothing about the answer. Realized P&L is
not a comparison at an instant; it is a difference between two instants. That is the whole
distinction, and every case falls cleanly on one side of it.

Two consequences the system enforces mechanically:

- **A coin P&L and a stablecoin P&L are never summed.** `0.05 BTC + 300 USDT = 300.05` is not
  wrong by a detectable margin — it is wrong by a *category*, and it looks exactly like a
  number. Any attempt to total across currencies raises rather than averaging.
- **On an inverse venue there is no single book currency.** A BTC leg books BTC and an ETH leg
  books ETH, so the book-level currency field is deliberately **empty** and the per-leg
  currency is the truth. Emitting one label there would be a label waiting to be applied to
  the wrong number.
- **Currencies are stamped at write time**, so a leg keeps the denomination it was actually
  booked in even if the account's venue spec later changes. Records written before any of this
  existed are read as the stablecoin, which is what every one of them actually is.

### 6.5 Precision is a property of the currency

Two decimal places is right for a stablecoin and **destroys a coin ledger**: at $63,000/BTC
the second decimal is $630. A 0.0049 BTC round-trip fee (~$490) rounds to `0.00`; a 0.004 BTC
P&L (~$400) rounds to zero. Money is therefore rounded to the precision its currency can
actually carry — cents for stablecoins, satoshis for coins — and an **unknown** currency gets
*coin* precision, because over-rounding destroys money while under-rounding only looks untidy.

The display layer mirrors the storage layer exactly, for the same reason.

### 6.6 Degrade honestly: no number where the model does not apply

Adding a venue means discovering which parts of the system were quietly venue-specific. The
initial-margin formula is one exchange's; the fee premium cap differs (7% versus 12.5%); the
contract size differs by 100×.

The rule adopted: **where a model does not describe the active venue, the system says so
rather than returning a confident number computed with another exchange's parameters.** That
is wrong in the one direction that matters — sizing — and it looks entirely ordinary. So the
margin figure on a venue with no initial-margin factors of its own is marked *not modelled*,
greyed, and accompanied by an instruction to size from the exchange's own panel. The same flag
travels with the per-leg column and the risk summary, so the two tabs cannot contradict each
other.

### 6.7 Venue facts are claims about the world, not constants

A wrong venue fact is **invisible**: every calculation uses the same wrong value on both
sides, so nothing ever disagrees. That is exactly how one venue's ETH contract size sat at
0.01 for months while the exchange reported 0.1 on all 548 listed ETH options.

Two defences:

- Anything that **can** be re-derived from the venue's own instrument metadata is re-derived
  by an automated check that compares the stored spec against the live listing.
- Anything that **cannot** is named in an explicit `unverified` list on the spec itself, and
  the output that depends on it carries a warning. Margin factors, fee caps and delivery
  parameters that live on dynamically-rendered help pages sit here — carried as flagged
  placeholders, never as quiet assumptions.

### 6.8 Read-only by construction

The second venue authenticates differently — an OAuth2 client-credentials exchange yielding a
short-lived bearer token, rather than a per-request signature — so the credential fields are
**relabelled per venue** (client ID / client secret versus API key / API secret). Labelling
them wrongly is how someone pastes the wrong credential and then debugs an auth error that
was never ambiguous.

The read-only guarantee is unchanged and enforced the same way: a read-only scope is requested
explicitly, and **no order, transfer, or withdrawal endpoint is implemented at all**. The
entire client was built and tested against a stubbed transport, offline, without credentials —
which is also the reason it could be written without ever asking the trader for keys.
