# 06 — Lessons & gotchas

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
- **The percentage-of-premium fee cap binds on cheap OTM legs** — exactly the legs a
  strangle-seller trades most. Omitting it overstates their cost; hardcoding one venue's
  value (7% on one exchange, 12.5% on the other) understates it on the other by nearly 2x.
- **Delivery fees exist, both sides, on exercise — except daily options.** OTM expiry is free.
  The "which term binds" `min(rate × index, 12.5% × intrinsic)` structure is why fee-adjusted
  breakeven needs a root-finder, not a formula.
- **Contract size varies by underlying AND by venue.** 0.01 for BTC/ETH on one exchange, 1.0
  for SOL, and 1.0 for BTC on the other exchange — a 100x gap for the same asset. Storing
  quantity in *underlying units* keeps margin math size-agnostic; contract *counts* still
  need the per-venue, per-underlying size, and getting it from the wrong venue reported a
  0.9-contract book as 90.
- **Never let `inf`/`nan` reach JSON.** An infinite profit factor (no losses yet) must be
  `null`; infinity breaks the browser's JSON parse and silently blanks the screen.
- **A mid-based credit is not a conservative estimate, it is a different number.** On a put
  quoted 5 / 25 the mid is 15 and the bid is 5 — **two thirds of the reported credit was
  spread**. The fix that mattered was not applying a haircut but reporting the decomposition
  as an **identity** (`mid − net = spread + fees`), because an identity can be tested and a
  haircut cannot.
- **Publish the headline number your other numbers derive from.** The first version of
  executable pricing reported the *pre*-fee credit as the headline while deriving max-loss
  from the *post*-fee one. Every figure was individually defensible and the candidate did not
  reconcile with itself. A test comparing max-loss against net credit caught it.
- **Two copies of a pricing rule is one copy plus a future bug.** The screener and the roll
  analyzer each carried their own bid/ask/fee helpers — which is exactly how a fix to one
  silently misses the other. They now share one module.

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
- **Check whether your "signal" is an identity in disguise.** Comparing a leg's theta/gamma
  breakeven move against the *implied* move looks like a genuine efficiency read. It is
  algebra: Black–Scholes fixes θ = −½σ²S²Γ, so the ratio is pinned at ≈0.96 across every
  strike and tenor. The tell was that it *never varied* — and the fix was to compare against
  **realized** movement instead. A constant is not a signal; but a constant you can *predict*
  makes an excellent data-quality check, which is what that ratio became.
- **Normalize before you compare, or the comparison encodes the tenor.** Roll safety measured
  as %OTM is not comparable across expiries; measured in expected moves (σ√T) it is. This has
  a consequence that reads like a bug and is not: a same-strike roll scores *worse* on safety
  the further out you go, because it buys time while the move budget grows with √T.
- **Score the thing you are about to own, not the thing you are leaving.** A roll's VRP axis
  prices the *new* contract. Rolling into cheap vol to repair an old position is the classic
  losing roll, and it is invisible on every other column.
- **Gates must sit beside the score, never inside it.** A weighted average will happily let a
  strong carry number bury a structural objection like "this is a debit" or "you are selling
  below forecast RV". Kept separate, a high score with an open gate still reads as a warning.
- **Some warnings should be structural, not predictive.** Roll-chain flags — rolled ≥3×, size
  growing, cumulative P&L negative — describe the *shape of what already happened*. They make
  no forecast, so they cannot be wrong, and on an uncapped-tail book that shape is the
  failure mode itself.
- **Capture the context at the moment, or lose it forever.** "Was I in profit when I rolled?"
  cannot be reconstructed from a closed ledger. Same principle as the entry-context flywheel:
  the cheapest data to record is the data that is impossible to backfill.
- **Classify ambiguous samples against your own hypothesis.** A roll chain containing both an
  opportunistic and a defensive roll counts as **defensive**. The other choice would have
  quietly biased the evidence in rolling's favour — which is the question being tested.
- **Check that your metric answers the question you think you asked.** A "max sustainable
  withdrawal" whose only test is *don't hit the ruin floor* approved **2,966/month on a book
  averaging +555**, while the median account fell from 100k to 38k. Every step was correct;
  the *question* was wrong. The fix was a second limit — the largest withdrawal leaving the
  median path with its capital intact — not a better search.
- **Round a safety limit DOWN, never to nearest.** The value was chosen precisely because it
  clears a threshold; rounding it up can push the number you display back across the very
  threshold that selected it.
- **Validate the bracket before you bisect.** Doubling the upper bound until it actually
  *fails* is what makes the search meaningful — bisecting inside a bracket whose top still
  passes converges to the bracket edge and reports a limit nothing ever tested.
- **State a method's blind spot every time you show its output, not once in a docstring.** A
  bootstrap cannot produce a month worse than the worst one observed, so on a sample with no
  crash in it the ruin rate is a *floor*, not an estimate. That sentence ships with the number.
- **When a method has a blind spot, put the compensating measure BESIDE it, not inside it.**
  The tail budget reprices the current book under a shock, so it does not need the sample to
  have contained one. Folding a synthetic tail into the resampling would have hidden which
  part of the answer came from evidence and which from assumption.
- **Money still owed is not money earned.** Premium collected on open legs is an obligation
  that can be handed back in full and then some. It is reported next to booked P&L and never
  added to it — a trader "hitting target" on open premium has hit nothing.
- **Check the target against capacity before checking the pace.** If a monthly target exceeds
  what the measured distribution supports, it is not a pace problem and no month can fix it.
  Ordering the checks wrongly would let a structural objection be reported as a schedule.
- **Express pressure as a multiple, not as a difference.** "Needs 3.4x your usual daily rate
  with 9 days left" changes behaviour; "behind by 400" does not. The risk on an income book is
  not the shortfall, it is the trade taken *for the target* rather than for the setup.
- **Score a forecast on the information it would have had.** Pin evidence is segmented by the
  gamma zone and approach direction at *first* capture, never at settlement. Segmenting on
  anything learned later is lookahead in miniature — the same sin as the backtest slice, at a
  smaller scale and much easier to miss.
- **Make "not enough evidence" a return value, not a fallback.** The pin-prior lookup returns
  *insufficient* rather than the pooled number when nothing clears its bar, so a caller cannot
  quote thin evidence as though it were measured. A belief should resolve to a number or to an
  admission — never to a default.
- **Raise the sample bar when you cut the sample.** Segmenting splits the same evidence into
  thinner cells; keeping the pooled minimum while the cells shrink is how a two-observation
  "rate" gets published.

## 4. Multi-venue and inverse settlement

The recurring theme of this whole project, stated once: **the dangerous bugs are the ones
where every individual number is internally consistent.** Adding a second exchange produced
three of them in a row.

- **A wrong venue constant is invisible.** Every calculation uses the same wrong value on both
  sides, so nothing ever disagrees. One venue's ETH contract size sat at 0.01 for months while
  the exchange reported 0.1 on all 548 listed ETH options. Anything re-derivable from the
  venue's own API is now re-derived by an automated check; anything that is not is named in an
  explicit "unverified" list, and the output that depends on it carries a warning.
- **Pick the book by measurement, not by ease of integration.** The linear USDC book would
  have needed none of the inverse work. It also carries **2.3%** of the coin-margined book's
  open interest. Integrating the easy one would have shipped a working feature nobody could
  trade at size.
- **Two correct decisions can be jointly wrong.** Normalising the chain to USD was right (one
  engine ranks both venues). Storing booked money unconverted was right (a round trip has two
  ends at two different indices). Nothing reconciled them where they met, so a 0.0003 BTC
  entry was compared against a 6.28 USD ask and Capture% printed **−2,091,700%**. Every input
  was individually correct.
- **The tell for a units bug is a number too absurd to be a modelling error.** −2,091,700% is
  not a bad model, it is a unit mismatch — and back-solving it (`(entry − ask)/entry = −20917`
  ⇒ entry = 0.00030022) identified the exact pair of quantities before a single line was
  changed. Reverse-engineer the absurd number rather than guessing at the cause.
- **The same mismatch hides completely when the scales are far apart.** The payoff chart
  subtracted a USD intrinsic from a coin premium, so the entire credit contributed 0.0004
  against a −6,168 loss and simply vanished. The curve looked plausible. What exposed it was a
  structural impossibility: the reported breakeven sat **above the highest strike in the
  book**, which no short-put book can do.
- **Derive the rule, don't patch the case.** "Converting is valid for a snapshot and invalid
  for booked money" resolves every instance — screener, portfolio, cash-flow, payoff — because
  a snapshot figure is invariant under one exchange rate at one instant and a round trip is
  not. Patching each screen separately would have produced four different conventions.
- **Category errors look exactly like numbers.** `0.05 BTC + 300 USDT = 300.05` is not wrong
  by a detectable margin. The guard has to *refuse*, not round.
- **Rounding is part of the unit.** Two decimal places is correct for a stablecoin and
  destroys a coin ledger — at \$63,000/BTC the second decimal is \$630, so a \$490 fee prints
  as `0.00`. An **unknown** currency gets coin precision, because over-rounding destroys money
  while under-rounding only looks untidy.
- **Emit no label rather than a plausible one.** On an inverse venue a BTC leg books BTC and an
  ETH leg books ETH, so a book-level currency field is a label waiting to be attached to the
  wrong number. Leave it empty.
- **When a model does not describe the venue, say so — don't compute.** Presenting one
  exchange's margin formula as a confident figure on another is wrong in the single direction
  that matters, sizing, and looks entirely ordinary. The flag travels with both the per-leg
  column and the risk summary so the two tabs cannot contradict each other.
- **A stale label is worse than no label.** "Import from \<other exchange\>" on the wrong
  venue, an "undefined positions" panel that reads as *no margin used* rather than *wrong data
  shape*, a note filter matching one venue's exact wording so the other venue's imports
  cluttered every row. Any user-visible exchange name must come from the venue, never a
  literal.
- **Verify a ported model against the source it claims to reproduce.** Black-76 on the
  per-expiry forward matches the venue's own published greeks to 0.00002 in delta and 0.03% in
  vega. That agreement is what proves the model, the forward, and the IV units were *all* read
  correctly — three things that would each be silently wrong on their own.
- **Compare rounded values with an absolute tolerance.** The venue publishes gamma to 5
  decimals, so a deep-ITM call's true 6.2e-07 reads as exactly 0.0. No relative tolerance can
  ever match a rounded zero.
- **A canonical field name is not a safe global rename.** Renaming a field across the venue
  layer also hit the *raw* exchange payloads one endpoint still read directly, silently
  removing its spot anchor while every other route kept working.
- **A read-only client can be built and tested without ever holding a credential.** The entire
  private integration was written against a stubbed transport, offline. Requesting a read-only
  scope and never implementing an order endpoint is what makes the guarantee structural rather
  than procedural.

## 5. Empirical findings worth remembering

- **The ATM vol-risk premium is razor-thin.** Over ~30-day horizons, implied ≈ realized-
  forward. A naked-strangle book's edge is therefore **not** ATM richness — it is the OTM
  **skew/tail** it sells, plus theta/gamma management. This reframed where the book thinks its
  edge comes from.
- **"Sell when IV rank is high" is validated** (a couple of vol points of edge), while the mid
  tier is noisy from overlapping-window clustering — and that noise is reported, not hidden.
- **Crypto tails run ~2.7x Gaussian at monthly horizons.** A 2-sigma/30-day put finishes ITM
  ~6% of the time versus ~2% under normal theory — a direct argument against wide-but-not-
  wide-enough long-dated naked puts.

## 6. Product & UX lessons

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

## 7. Engineering & operational lessons

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

### Verification (see [02 — Implementation §5](02-implementation.md))

- **A passing suite proves the tests pass, not that they would fail.** Break each guard
  deliberately and confirm the suite goes red. A **surviving mutation is a missing test** — one
  survived here (an account switcher re-merging two ledgers) and became a test named after
  exactly that. And when a mutation produces no failure, check the *mutation* first: one of
  mine was malformed (a method name without its call parentheses), so the "broken" line was
  never reached. That is a false negative in the mutation, not evidence about the test.
- **Before a big refactor, freeze the output and byte-compare it.** "This should be
  behaviour-preserving" is not a test. A golden snapshot over a frozen chain fails and *names
  the field*. The escape hatch that re-approves the snapshot is fine — provided the rule is
  that **the resulting diff is the review artefact**, never a way to make the test pass.
- **A golden fixture must be free of `now()` and of the network**, or it drifts sub-second
  between runs and can never be byte-compared.
- **Generate fixture prices, don't eyeball them.** Hand-written mids that disagreed with their
  own implied vols — a 3-DTE ATM option written as 600 where 50% vol implies ~1,800 — quietly
  **starved four strategy modules of any candidate at all**, so those modules were "tested"
  against an empty result. Prices from a model keep price, delta and IV agreeing.
- **Make fixtures adversarial on purpose.** Spreads that widen with distance from the money and
  one deliberately one-sided contract are what exercise the code paths that matter; a tidy
  fixture tests the happy path and nothing else.
- **Duplicated logic drifts silently — test both copies against each other.** Numbers computed
  in both Python and JavaScript are compared by **extracting the real frontend functions and
  running them in Node**. Never against a re-typed copy: a copy drifts too, and a parity test
  comparing two copies of the same drift is worse than none.
- **Assert absences, not just behaviour.** "No order method exists on this client" and "the
  token is minted read-only" survive refactors that a behavioural test would not — and they
  put the final guarantee on the **venue**, not on our own good intentions.
- **A stubbed transport means a private client can be built and verified without ever holding
  a credential.** Offline by construction is both safer and faster than fixtures recorded from
  a live account.
- **The most dangerous test is one that passes without exercising anything.** A refactor moved
  a module path that ~118 tests patched *by name*; the patches then pointed at nothing, the
  tests kept passing, and they had stopped testing the code. **Point fixtures at a seam, not at
  an implementation detail** — and when reviving a suite, confirm it can still fail.
- **Compare rounded values with an absolute tolerance.** A venue publishing gamma to 5dp turns
  a true 6.2e-07 into exactly 0.0, and no relative tolerance can ever match a rounded zero.
- **Verify generated artefacts by reading them back.** This compendium's PDF build is checked
  by extracting the text and asserting no unrendered markup survived — which found three
  rendering bugs that had each **silently dropped content** while looking entirely normal.
- **`.gitignore` has no inline comments.** A `pattern  # comment` line treats the whole thing
  as the pattern and silently ignores nothing — which once let plaintext credentials get
  tracked. Comments go on their own line, and the ignore rules are the real secret-leak guard.
- **`git add -A` does not un-track already-tracked files** even after you ignore them; they
  must be explicitly removed from the index. Always scan the staged diff for secrets before a
  commit that could ever go public.
- **Encryption at rest is defense-in-depth, not the primary control.** The primary control is
  never committing the secret in the first place.

---

## 8. The one-line summary

Build the boring, honest plumbing first — executable prices, real fees, correct margin,
lookahead-free backtests, sample-gated statistics — and *then* the synthesis on top is
trustworthy. A pretty score on top of a fictional mark is worse than no score at all.

**And the corollary, learned the hard way and repeatedly:** the bugs that survive are the ones
where **every individual number is internally consistent**. Nothing disagrees with anything, so
nothing raises an alarm. They are caught only by checking the system against something outside
it — an identity that must hold, a structural impossibility (a short-put breakeven above the
highest strike in the book), a value too absurd to be a modelling error (−2,091,700%), or a
constant that should vary and never does. Build those external checks in deliberately; you
will not stumble across them.
