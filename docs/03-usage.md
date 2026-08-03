# 03 — Usage

How a trader actually drives the system. Organized as the workflow first, then each surface,
then the decisions each one supports.

---

## 1. The daily workflow

1. **Open on the Portfolio.** The landing surface is the live book, not a screener — because
   the first question every session is "what do I already have, and does anything need
   attention?" Legs are grouped per asset with margin, unrealized P&L, and theta subtotals,
   ordered so the heaviest-margin asset is on top (the trim shortlist).
2. **Clear any sync drift.** If the local book has drifted from the exchange (a fill, a
   partial close, an early close), a banner surfaces it with one-click import/update or
   record-close. It refreshes on every reload so it reflects reality immediately.
3. **Read the regime.** The Intelligence/Coach surfaces answer "is vol rich, which way is the
   tape leaning, where's the gamma?" in one named regime line plus supporting signal cards
   with percentile and 5-day-movement context.
4. **Check the coach brief.** The fused view lists prioritized position actions (defend /
   near-expiry / roll-window legs) and new-setup ideas already annotated by how they fit the
   current book.
5. **Act, then record.** Execute manually on the exchange, then import or add the leg so the
   entry-context flywheel captures the market state at entry.
6. **Review the edge periodically.** The scorecard shows where your realized results actually
   come from — by strategy, underlying, DTE-at-entry, and IV-rank-at-entry — alongside the
   roll-chain evidence and the theta-efficiency roll-up.
7. **Review the income monthly, after the month closes.** Whether the book supports a
   withdrawal is a question about months and capital, not about trades, and it has its own
   surface.

---

## 2. The surfaces

### 2.1 Portfolio

The operational center. Per-leg it shows: side, strike, expiry with a DTE pill, quantity,
entry, mark, the **executable close quote** (ask for shorts, bid for longs) with a spread /
one-sided tag, **Capture%** (premium actually kept if closed now at that quote), profit% (on
mark), theta/day, unrealized P&L, **per-leg margin** with its share of book margin, and
probability-of-profit / breakeven distance.

Decisions it supports:
- *Which legs to trim* — sort by margin share; the biggest consumers are the shortlist.
- *Which shorts to buy back cheaply* — Capture% ≥ a take-profit threshold, close-quote color
  green, means locking in most of the credit is available now.
- *Which legs are stuck* — a one-sided or very wide close quote means you can't exit at
  market; use a limit.
- *Whether a "green on mark" leg is actually a loser to close* — Capture% negative says yes.

Each short leg also carries a **theta-efficiency** sub-line: the breakeven daily move implied
by its own theta and gamma, versus recent *realized* movement. `1.51× paid` means the carry is
comfortably ahead of how much the market has actually been moving; below 1.0 the leg loses in
expectation **even while theta prints positive every day**. A leg whose greeks look stale is
flagged rather than scored.

Everything the trader reads as money is shown **in the currency the leg was booked in**, at
that currency's precision — cents for a stablecoin, satoshis for a coin. On a coin-settled
venue there is no single book currency, so totals appear per currency rather than summed.

A **trade-volume strip** (premium transacted per settlement currency, contracts at the
*venue's* contract size, notional in USD) and a **collapsible live-margin panel** sit
above/around the table. On a venue whose margin this build does not model, the per-leg margin
column is greyed with a `?` and the panel shows the exchange's own ledgers instead of a
modelled estimate.

### 2.2 Screener

Runs the strategy library across the chain and lists liquid candidates with net credit,
breakevens, probability-of-profit, annualized yield, and the exact payoff KPIs (max profit,
max risk, reward:risk). The playbook can deep-link here with the right strategy preselected.

**The credit shown is executable, not mid** — shorts fill on the bid, longs on the ask, and
every leg pays a fee. A sortable **edge-retention** column gives the fraction of the mid credit
that survives contact with the order book, with the mid figure and the spread/fee split
available underneath, so the gap is visible rather than merely absorbed. Two flags matter:
*credit vanishes* (mid says credit, the real book says debit) and *quote estimated* (the side
this fill needs is unquoted, so the price is a model price — use a limit).

### 2.3 Intelligence

The market read. IV rank, ATM IV (with surface-average demoted to a sub-value so they're
never confused), 25-delta skew, term structure, VRP, expected-move-vs-realized table,
trend, funding, gamma flip and max pain. A **carry monitor** compares dated-futures basis,
funding, and VRP. An **external-reference card** shows the deepest-venue DVOL/ATM/skew with
explicit "this venue − reference" richness gaps — labeled as reference, not signal, and
**hidden entirely on an account that trades at the reference venue**, where it would be a
comparison with itself rendered as a row of zeros that reads like agreement. **IV-history**
and **backtest** panels show accrued own-venue history and the walk-forward studies.

### 2.4 Coach

The synthesis surface:
- **Trade brief** — regime cards, net signed book greeks, prioritized position actions, and
  new-setup ideas annotated by book-fit (with concrete, sized strikes).
- **Scorecard** — realized win-rate/expectancy/profit-factor segmented four ways, plus
  discipline metrics (premium-capture efficiency, loss/win size asymmetry), all with
  sample-size-guarded insights.
- **Scenario stress test** — three sliders (spot shock / IV shift / days forward); dial all
  three, then run, and see book P&L impact, projected margin/utilization with a warning
  banner, and newly-breached legs.
- **Expiry-week focus** — per-held-expiry max-pain/GEX with each of your strikes tagged
  long- or short-gamma.
- **Roll analyzer** — for flagged legs, a comparison of same-strike vs strike-adjusted rolls
  (a table, not one opaque "best" pick). Credit is **executable and after both fees**, since a
  roll crosses the spread twice, and rows are compared on **credit per day** because the VRP
  term structure makes a bigger absolute credit further out frequently *worse* per unit of
  time-risk. Each row carries a **five-axis score** — carry, VRP on the contract being
  *opened*, safety in expected moves, gamma relief, margin change — with every component's raw
  value and reason shown, so you can disagree with one axis instead of trusting a rank. Gates
  (a debit roll, selling below forecast RV, a strike inside one expected move) sit **beside**
  the score and cap the verdict rather than being averaged into it.
- **Roll chains** — the history view: legs linked by roll, with structural warnings (rolled
  ≥3×, size growing across the chain, cumulative P&L negative) and the evidence buckets that
  answer *"does rolling work for me"* — never-rolled vs rolled-in-profit vs rolled-while-
  tested, sample-gated.
- **Ask the coach** — a grounded natural-language Q&A that answers only from the on-screen
  brief/scorecard data, with a strict "never invent numbers, advisory-only" prompt and a
  user-set daily question cap.

### 2.5 Income

The surface that answers *"is this an income stream, or just a profitable strategy?"* — a
different question from anything the scorecard measures.

- **Monthly ledger** — realized P&L per calendar month net of fees, return on the margin
  actually deployed (with the coverage percentage stated, since trades predating entry-context
  capture cannot have theirs reconstructed), and the realized equity curve with drawdown. The
  in-progress month is shown but excluded from every statistic, and below a minimum of complete
  months no averages are quoted at all.
- **Consistency** — headlined by *months erased by the worst month*, not by the average. On a
  negatively-skewed short-vol book that ratio is what decides whether the income is spendable.
- **Sustainability** — a seeded bootstrap over the observed months giving two withdrawal
  limits. Read the **preserving** one: the largest withdrawal that still leaves the median path
  with its starting capital. The "sustainable" figure only promises you will not hit the ruin
  floor, and will happily approve a withdrawal that consumes most of the account on the way.
  The ruin rate is stated as a **floor**, because a bootstrap cannot produce a month worse than
  the worst one you have lived through.
- **Tail budget** — one repriced shock on the *current* book, expressed in months of average
  income. This is the number that makes an uncapped tail legible, and unlike the bootstrap it
  does not need your sample to have contained a crash.
- **Cadence** — mid-month progress against a target, with booked P&L and still-open premium
  kept strictly apart, the target checked against measured capacity before anything else, and
  pace expressed as a multiple of your normal daily rate rather than as a shortfall.

### 2.6 Calculator

A multi-leg P&L what-if. "Load my open book" opens an expiry-grouped picker that prefills
legs from the live book (buy-back = current mark, index = live spot). Per leg you set
taker/maker and optionally strike + type to get a **fee-adjusted breakeven**; per-leg and
whole-position net-after-fees update live. A "daily option" flag drops the delivery-fee term.
`close = 0` models expire-worthless. It uses the *same* fee model as real closes, so the
what-if agrees with reality to the cent.

### 2.7 Settings

Sub-account switch, credential status (with a locked-state badge when encryption is on but the
passphrase is missing), risk configuration (capital, max utilization, vol-target), and the
bring-your-own-key config for the natural-language Q&A with its daily budget.

**Venue is chosen when an account is created and is fixed thereafter.** Switching accounts
therefore re-points the whole UI: the asset chips are rebuilt from the venue's own listed
underlyings (so an account can never offer an asset its venue does not list), the credential
fields are relabelled to that venue's own vocabulary — *client ID / client secret* versus *API
key / API secret* — and every user-visible exchange name is driven by the venue rather than by
a literal. Mislabelled credential fields are how someone pastes the wrong secret and then
debugs an auth error that was never ambiguous.

---

## 3. Auto-refresh and reconciliation

The portfolio auto-refreshes on a short default interval (adjustable, or off). Every refresh
re-diffs the book against the exchange and updates the sync banner. Because the diff runs
inside the same reload path as every mutation (import, add, close, expire, delete, account
switch), any action clears or updates the banner immediately rather than leaving a stale
alert until the next timer tick.

---

## 4. What the system will and won't do for you

**Will:** assemble the full market read, score structures transparently, size to your limits,
show you the real (executable, fee-inclusive) cost of getting in and out, flag the legs that
need attention, remember your entry context, and tell you where your realized edge actually
is — hedging every claim by how much data backs it.

**Won't:** place, modify, or cancel any order; move funds; give you a number it can't
support; sum two settlement currencies into one total; present one exchange's margin model as
a fact about another; or hide a growing tail behind an optimistic mark. Execution, and the
judgment of whether to execute, stay with you.
