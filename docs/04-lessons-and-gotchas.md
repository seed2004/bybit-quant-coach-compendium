# 04 — Lessons & gotchas

The bugs, surprises, and rules that came out of actually building and running the system.
These are the parts most worth carrying to any similar project.

---

## 1. Market-data traps

- **Mark is not a price.** An exchange's option *mark* is a theoretical mid. Position value,
  profit, and "can I get out?" must be computed from the executable **bid/ask**, not the mark.
  This is the single most impactful correction in the project.
- **Slippage-versus-mark explodes on cheap legs.** With a near-zero mark, any "% versus mark"
  ratio blows up to thousands of percent and paints trivially-cheap buybacks as disasters.
  Measure crossing cost as the **half-spread versus the bid-ask mid**, and flag one-sided
  books explicitly instead of emitting a nonsense number.
- **Average-over-the-smile is not ATM.** Averaging IV over all contracts is dominated by the
  wings and runs ~8 vol points hot. Comparing that to an external ATM reference manufactures a
  phantom edge. Always compare **ATM-to-ATM**.
- **Use the perp index for spot.** The option ticker's underlying-price field is unreliable;
  the linear perpetual's index price is the trustworthy spot.
- **The exchange ignores the base-coin filter on linear tickers.** A "give me BTC contracts"
  query returns *every* linear contract (other coins, even novelty futures). Filter by symbol
  prefix.
- **Unified account reports empty per-position option margin.** Real IM/MM come only from the
  account-level wallet balance; per-leg margin must be reconstructed from the formula.
- **`positionValue` is negative for shorts.** Take absolute value.

## 2. Money-math traps

- **Fees are ~13% of gross on a premium book.** Model them or your P&L is fiction. Both the
  open and the close fill are charged; a round trip is two trading fees.
- **The 7%-of-premium fee cap binds on cheap OTM legs** — exactly the legs a strangle-seller
  trades most. Omitting the cap overstates their cost.
- **Delivery fees exist, both sides, on exercise — except daily options.** OTM expiry is free.
  The "which term binds" `min(rate × index, 12.5% × intrinsic)` structure is why fee-adjusted
  breakeven needs a root-finder, not a formula.
- **Contract size is not universal.** BTC/ETH are 0.01 of the underlying per contract; SOL is
  1.0. Storing quantity in *underlying units* keeps margin math size-agnostic and prevents
  100x errors — but contract *counts* still need the per-underlying size.
- **Never let `inf`/`nan` reach JSON.** An infinite profit factor (no losses yet) must be
  `null`; infinity breaks the browser's JSON parse and silently blanks the screen.

## 3. Modeling discipline

- **Fixed, visible weights can't overfit.** The RV forecast blend uses hand-set weights on
  purpose. A fitted model would score better in-sample and lie out-of-sample.
- **Sign conventions must be defined once and honored everywhere.** A skew-sign bug
  (treating negative as put-rich when positive means put-rich) mislabeled and mis-scored every
  fearful market — live and invisible until audited. Document the sign at every consumption
  site.
- **Dead-bands beat exact comparisons on noisy signals.** A zero-tolerance moving-average
  crossover flips its label on microscopic noise; a small dead-band fixes it. A test caught
  this.
- **Walk-forward or it's an oracle.** The backtest's "world as of day *t*" must exclude every
  future bar, including in the percentile windows. The slice boundary is the invariant to
  test.
- **Withhold statistics you can't support.** Percentiles, seasonality marks, and personal
  edge are all gated on a minimum sample and say "only N so far" below it. Honesty about
  sample size is a feature, not a caveat.
- **Let calibration tilt, never override.** Personal-edge nudges are expectancy-gated and
  hard-capped so the market signal and risk limits always dominate. A learning loop that can
  overpower its guardrails is a liability.

## 4. Empirical findings worth remembering

- **The ATM vol-risk premium is razor-thin.** Over ~30-day horizons, implied ≈ realized-
  forward. A naked-strangle book's edge is therefore **not** ATM richness — it is the OTM
  **skew/tail** it sells, plus theta/gamma management. This reframed where the book thinks its
  edge comes from.
- **"Sell when IV rank is high" is validated** (a couple of vol points of edge), while the mid
  tier is noisy from overlapping-window clustering — and that noise is reported, not hidden.
- **Crypto tails run ~2.7x Gaussian at monthly horizons.** A 2-sigma/30-day put finishes ITM
  ~6% of the time versus ~2% under normal theory — a direct argument against wide-but-not-
  wide-enough long-dated naked puts.

## 5. Product & UX lessons

- **Color the decision, not the number.** When a value's meaning depends on interpretation,
  make the color track the *decision* (is this a good exit?) and demote the raw detail (spread
  width) to a tag. Coloring by the wrong dimension made losing-but-tight legs look green.
- **Land on the operational surface.** The first screen should be the live book, because the
  first question is always "what do I hold and what needs attention?"
- **Group and collapse once it scales.** Flat lists that were fine at five legs become noise at
  forty. Group per asset with subtotals; hide dense detail behind a toggle whose state
  survives refresh.
- **Reconcile on every mutation, not just on a timer.** Running the exchange-diff inside the
  same reload path as every action means an alert clears the instant you act on it, instead of
  nagging until the next tick.
- **Explicit apply beats debounced auto-run for expensive, deliberate actions.** The scenario
  stress test dials in three inputs and then runs on click — mid-drag auto-runs were annoying
  and wasteful.
- **Remove redundant alerting.** A separate notification badge was built and then deleted once
  the trade brief already surfaced the same priority items. Duplicated nudges erode trust.

## 6. Engineering & operational lessons

- **Pure core, I/O shell.** Keeping all math in pure functions is what made every model
  testable offline against synthetic fixtures. It is the structural decision everything else
  leaned on.
- **Snapshot the account directory before the first await.** Otherwise an account switch mid-
  request can read one account and write another. This race is silent and data-corrupting.
- **Soft-fail every network dependency.** A dead upstream returns a labeled "unavailable," not
  an exception, so one outage never blanks a whole screen.
- **Verify by observing the real flow.** Unit tests can't catch a correct formula wired to the
  wrong column. Drive the UI, read the DOM back, and compare against what the number *should*
  mean. The most important bugs were found this way.
- **`.gitignore` has no inline comments.** A `pattern  # comment` line treats the whole thing
  as the pattern and silently ignores nothing — which once let plaintext credentials get
  tracked. Comments go on their own line, and the ignore rules are the real secret-leak guard.
- **`git add -A` does not un-track already-tracked files** even after you ignore them; they
  must be explicitly removed from the index. Always scan the staged diff for secrets before a
  commit that could ever go public.
- **Encryption at rest is defense-in-depth, not the primary control.** The primary control is
  never committing the secret in the first place.

---

## 7. The one-line summary

Build the boring, honest plumbing first — executable prices, real fees, correct margin,
lookahead-free backtests, sample-gated statistics — and *then* the synthesis on top is
trustworthy. A pretty score on top of a fictional mark is worse than no score at all.
