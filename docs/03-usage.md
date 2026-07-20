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
   come from — by strategy, underlying, DTE-at-entry, and IV-rank-at-entry.

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

A **trade-volume strip** (premium transacted, contracts, notional) and a **collapsible live-
margin panel** (grouped per underlying, sourced from the exchange's wallet balance) sit
above/around the table.

### 2.2 Screener

Runs the strategy library across the chain and lists liquid candidates with net credit,
breakevens, probability-of-profit, annualized yield, and the exact payoff KPIs (max profit,
max risk, reward:risk). The playbook can deep-link here with the right strategy preselected.

### 2.3 Intelligence

The market read. IV rank, ATM IV (with surface-average demoted to a sub-value so they're
never confused), 25-delta skew, term structure, VRP, expected-move-vs-realized table,
trend, funding, gamma flip and max pain. A **carry monitor** compares dated-futures basis,
funding, and VRP. An **external-reference card** shows the deepest-venue DVOL/ATM/skew with
explicit "Bybit − reference" richness gaps — labeled as reference, not signal. **IV-history**
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
  with net credit and resulting delta (a table, not one opaque "best" pick).
- **Ask the coach** — a grounded natural-language Q&A that answers only from the on-screen
  brief/scorecard data, with a strict "never invent numbers, advisory-only" prompt and a
  user-set daily question cap.

### 2.5 Calculator

A multi-leg P&L what-if. "Load my open book" opens an expiry-grouped picker that prefills
legs from the live book (buy-back = current mark, index = live spot). Per leg you set
taker/maker and optionally strike + type to get a **fee-adjusted breakeven**; per-leg and
whole-position net-after-fees update live. A "daily option" flag drops the delivery-fee term.
`close = 0` models expire-worthless. It uses the *same* fee model as real closes, so the
what-if agrees with reality to the cent.

### 2.6 Settings

Sub-account switch, API credential status (with a locked-state badge when encryption is on
but the passphrase is missing), risk configuration (capital, max utilization, vol-target),
and the bring-your-own-key config for the natural-language Q&A with its daily budget.

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
support; or hide a growing tail behind an optimistic mark. Execution, and the judgment of
whether to execute, stay with you.
