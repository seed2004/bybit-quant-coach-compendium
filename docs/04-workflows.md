# 04 — Workflows

The concrete, repeatable procedures the system is built around. Each is a sequence of
steps mapping a decision to the surfaces and signals that support it. The design goal is
that none of these requires holding state in your head — the tool surfaces the next input
at each step.

---

## 1. The daily desk review

The opening ritual every session.

1. **Land on the Portfolio.** See the whole book grouped per asset with margin, unrealized
   P&L, and theta subtotals; the heaviest-margin asset sits on top.
2. **Clear sync drift.** If the book has diverged from the exchange, resolve the banner
   first — import new fills, update partial closes, record early closes — so every later
   number is computed against reality.
3. **Read the regime line.** One named banner ("High-IV, range-bound, contango, premium-
   rich") plus signal cards with percentile and 5-day-movement context.
4. **Scan the action items.** The coach brief lists prioritized position actions (defend /
   near-expiry / roll-window) and net signed book greeks.
5. **Check margin headroom.** The live-margin panel (from the exchange wallet) shows IM
   utilization and the buffer above maintenance — the ceiling on any new risk.
6. **Note anything for later.** Legs approaching a take-profit Capture%, legs whose close
   quote has gone one-sided, expiries clustering.

## 2. Is vol rich? — the regime assessment

Before selling any premium, decide whether premium is worth selling *now*.

1. **VRP first.** Implied minus forecast realized vol. Positive and wide = premium is rich;
   thin or negative = the seller's edge isn't there.
2. **IV rank** for context — where current IV sits in its own recent history (a true
   percentile once history has accrued).
3. **Skew** — 25-delta put-minus-call. Rich puts (positive) reward put-side selling and
   skew-harvest structures.
4. **Term structure** — contango favors calendars; backwardation warns of near-term stress.
5. **Expected-move-vs-realized** — is the market pricing more movement than tends to happen?
6. **External reference** — the deepest-venue DVOL/ATM/skew as a labeled sanity check, never
   as the deciding signal.
7. **Backtest context** — remember the standing finding: ATM VRP is thin, so the edge lives
   in the OTM skew/tail, not ATM richness.

## 3. Entering a new position

1. **Consult the playbook.** It ranks every structure for the current regime with visible
   score components and reasons; the top pick fits the regime, or it says "Wait."
2. **Respect the personal-edge nudge.** If your own history in similar regimes tilts a family
   up or down, that shows as a reason line on the ranked card.
3. **Deep-link to the screener** with that strategy preselected; pick concrete, liquid
   strikes with acceptable credit / breakevens / probability-of-profit / annualized yield.
   **Read the credit as the executable one** — shorts fill on the bid, longs on the ask, and
   every leg pays a fee. Check **edge retention**: what fraction of the mid credit actually
   survives the order book. A candidate retaining 20% is mostly a gift to the market maker,
   and the two flags to respect are *credit vanishes* (mid says credit, the book says debit)
   and *quote estimated* (the side you need is unquoted, so the price shown is a model price
   — use a limit order and expect to negotiate).
4. **Check the payoff shape** (KPIs: max profit, max risk, reward:risk) — and the diagram
   family in [05 — Strategy payoffs](05-strategy-payoffs.md) — so the risk profile is what
   you intend (especially: is the tail bounded?).
5. **Size to limits.** The contracts-allowed figure comes from your capital, max-utilization
   setting, and vol-target scale. A `0` means your limits don't allow it here.
6. **Stress-test if adding meaningful risk** (workflow 8).
7. **Execute manually on the exchange.**
8. **Record the leg** (import or add) so the entry-context flywheel snapshots the full market
   state at entry — the fuel for future calibration.

## 4. Managing an open position

1. **Watch the action items.** A leg gets flagged when it needs defending, nears expiry, or
   enters the roll window.
2. **Read the executable close, not the mark.** The close-quote column shows the price you'd
   actually transact and its Capture% (premium kept if you close now).
3. **Decide:**
   - *Take profit* → workflow 6, when Capture% clears your threshold.
   - *Roll* → workflow 5, when the thesis holds but time/strike needs adjusting.
   - *Defend* → tighten or hedge a threatened side; re-check net book greeks after.
   - *Hold* → nothing to do; theta accrues.
4. **Re-check margin and net greeks** after any change.

## 5. Rolling a position

1. **Open the roll analyzer** for the flagged leg.
2. **Compare the two paths it tables**, soonest-expiry-first: **same-strike** (buy time only)
   and **strike-adjusted** (move further OTM toward a defensive delta target, buy time).
3. **Compare on credit *per day*, not on the headline credit.** The VRP term structure slopes
   down steeply, so rolling further out for a bigger absolute credit frequently buys *less*
   premium per unit of time-risk. The per-day and yield-per-day columns exist because the raw
   number is not comparable across expiries.
4. **Read the credit as executable.** A roll crosses the spread **twice** and pays a fee on
   both fills. The *mid flatters* flag marks the case where mid calls it a credit and the
   real book calls it a debit.
5. **Read the five-axis score — and read the axes, not just the number.** Carry, VRP on the
   contract you're *opening*, safety in expected moves, gamma relief, margin change. Two
   things to internalize:
   - a **same-strike roll scores worse on safety as tenor grows**, and that is correct — it
     buys time, not safety, because the move budget grows with √T;
   - the **VRP axis prices the new leg**. Rolling into cheap vol to repair an old position is
     the classic losing roll, and nothing else on the screen will show it to you.
6. **Treat gates as vetoes, not as inputs.** A debit roll or one selling below forecast RV
   caps the verdict at *questionable* however well it averages. A new strike inside one
   expected move is an open gate even on a high score.
7. **Check the chain before rolling again.** If this leg has already been rolled, look at the
   chain warnings: rolled ≥3×, size growing, cumulative P&L negative, every roll made while
   losing. That pattern is how an uncapped-tail book dies, and each individual roll looks like
   "collect more credit" right up until it doesn't.
8. **Prefer a roll that stays a credit** and moves delta toward neutral, unless you're
   deliberately taking a directional view.
9. **Execute manually**, then update the book (which re-runs the sync check). The roll context
   — *were you in profit or defending?* — is captured at that moment and cannot be
   reconstructed later; it is what makes the weekly review's "does rolling work for me"
   answerable at all.

## 6. Taking profit / closing

1. **Confirm Capture%**, not mark-profit. Capture% is the premium actually kept at the
   executable quote; the gap to mark-profit is the cost of reality.
2. **Check the close quote is two-sided.** A "one-sided" tag or a very wide half-spread means
   you can't exit cleanly at market — use a limit.
3. **For a short-premium book**, closing when the buy-back costs a small fraction of the
   credit locks in most of the max profit; a deep-OTM leg near worthless may be left to
   expire (OTM expiry pays no delivery fee).
4. **Model it first if unsure** in the calculator (workflow below), which nets both trading
   fees and, on exercise, the delivery fee.
5. **Record the close** so realized P&L (net of fees) feeds the scorecard and calibration.

## 7. Reconciling the book (sync)

1. **The diff runs automatically** on every portfolio reload and on the short auto-refresh.
2. **Resolve each drift type:** *new* (import the leg), *size-changed* (update via import —
   a partial close or add), *closed-early* (record the close to book realized P&L).
3. **Because the diff runs inside the reload path**, acting on a drift clears the banner
   immediately rather than waiting for the next timer tick.

## 8. Scenario stress test (before events / before adding risk)

1. **Dial three inputs:** spot shock, IV shift, days forward (or a preset: selloff, crash,
   rally, time-only).
2. **Run** — the whole book is repriced under the shock (Black-Scholes on matched legs).
3. **Read the outputs:** book P&L impact, projected margin and utilization with a warning
   banner if it breaches, and any newly-breached breakevens.
4. **Note skipped legs** (unrepriceable / no live IV) reported separately so the totals are
   never silently partial.
5. **Decide** whether the post-shock margin and tail are acceptable *before* adding the
   position.

## 9. The P&L / breakeven what-if (calculator)

1. **Load the open book** into the multi-leg calculator (expiry-grouped picker; prefilled at
   current mark and live spot).
2. **Set taker/maker** per leg and, for a breakeven, the strike + type.
3. **Read per-leg and whole-position net after fees**, and the **fee-adjusted breakeven**
   (solved against the exact fee model; a "daily option" flag drops the delivery term).
4. Use `close = 0` to model expire-worthless. The numbers agree with a real close to the
   cent because it's the same fee model.

## 10. Weekly edge review

1. **Open the scorecard.** Realized win-rate, expectancy, and profit factor, segmented by
   strategy, underlying, DTE-at-entry, and IV-rank-at-entry.
2. **Read the discipline metrics:** premium-capture efficiency and loss/win size asymmetry.
3. **Read the roll-chain evidence.** Completed chains you never rolled, rolled while in
   profit, and rolled while tested, compared on average P&L. This is the only honest answer
   to *"does rolling work for me"* — and note that a chain containing both kinds of roll
   counts as **defensive**, because the defensive roll is the risk-relevant event.
4. **Read the theta-efficiency roll-up.** How many open legs are *underpaid* — realized
   movement running above what their theta pays for — plus the median edge ratio and any legs
   flagged for stale greeks. A book can print positive theta every day and still be losing in
   expectation; this is the number that says so.
5. **Trust only what the sample supports** — insights are gated on size and say "only N so
   far" below it.
6. **Let it feed forward.** These same outcomes drive the calibration nudges that tilt next
   week's playbook toward what has actually worked for you (capped so market signals still
   dominate).

## 11. Asking the desk advisor

A book-aware assistant workflow for judgment questions ("should I roll this?", "is this vol
cheap?", "size this", "where's my edge?"):

1. It reads the live book and market data first (API, with local files as a fallback).
2. It answers **grounded only in that data** — never inventing numbers — and stays advisory:
   it enforces the VRP gate, the defined-risk bias, your risk-limit caps, and behavioral
   discipline drawn from your own closed trades.
3. It **never places an order.** Every suggestion is yours to execute or ignore.
