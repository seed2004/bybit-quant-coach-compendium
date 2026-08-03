# 02 — Implementation

How the system is built — described at the level of responsibilities, algorithms, and
patterns. No source code; this is the "how it's put together" companion to the design.

---

## 1. Module map (responsibilities, not code)

The backend is ~50 small modules. The split that matters is **pure core** (math, testable
offline) versus **I/O shell** (network, disk, endpoints), with a thin **venue layer** between
them.

### Venue layer

| Module | Responsibility |
|---|---|
| Venue spec | Pure data per exchange: contract sizes, fee rates and caps, delivery parameters, margin factors, listed underlyings, perp symbols, whether settlement is inverse — plus an explicit list of fields that could **not** be verified from the venue's own API |
| Venue registry | Maps a venue id to its adapter, lazily; raises on an unknown venue rather than defaulting to one |
| Adapters (one per venue) | The only code that knows a wire format: chain, spot, perp context, funding, candles → one canonical contract object. Normalizes IV units, converts coin-quoted prices at the index, and fills in greeks the venue does not publish |
| Settlement | The currency guard on booked money: stamp, partition, currency-aware rounding, and a **refusal** to sum across currencies |
| Venue check | Re-derives the spec's verifiable facts from the live instrument listing and reports disagreements |

The spec module **imports nothing from the rest of the backend**. That is structural, not
tidiness: the shared config re-exports the default spec's fields, so any import back into
the application would close a cycle.

### Pure core — market & instrument math

| Module | Responsibility |
|---|---|
| Chain builder | Merge instruments + tickers into unified contract objects; DTE filter; short cache |
| RV / IV stats | ATR, annualized realized vol, IV rank, IV/RV ratio |
| Volatility models | Parkinson / Garman-Klass / Yang-Zhang RV, HAR forecast, VRP, expected move, trend filter, funding summary |
| Fees | Trading-fee (with the venue's premium cap) and delivery-fee model; round-trip fee helper |
| Executable pricing | The single source of truth for "which side of the book do I get?" — bid on shorts, ask on longs, fee per fill; returns the mid / exec / after-fee decomposition and flags estimated quotes. Shared by the screener and the roll analyzer |
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
| Roll engine | Same-strike vs strike-adjusted roll tables for flagged legs, priced executable with both fees; per-day and per-day-yield figures |
| Roll score | Five-axis roll assessment (carry / VRP / safety / gamma / capital) with renormalized weights, full component breakdown, and gates kept separate from the score |
| Roll chains | Links legs by roll chain; martingale warnings; never-rolled vs rolled-in-profit vs rolled-tested evidence buckets, sample-gated |
| Theta edge | Per-leg breakeven move from θ and Γ, compared against realized movement; stale-greeks detector; θ/margin, vol-spike fragility, days-to-collect |
| Coach | Net signed book greeks; book assessment; prioritized position actions; setup annotation |
| Analytics | Closed-trade win-rate / expectancy / profit factor, segmented; discipline metrics |
| Calibration | Personal-edge nudges from closed trades, regime-aware, expectancy-gated, capped |
| Scenario | Reprice the book under spot/IV/time shocks (Black-Scholes); P&L, margin, breakeven breaches |
| Expiry focus | Per-held-expiry max-pain / GEX; gamma-zone tagging of your strikes |
| Carry | Dated-futures basis vs funding vs VRP; rule-based income verdict |
| Cashflow | Monthly realized ledger net of fees; return on margin-at-entry; consistency (months-erased-by-worst); realized equity curve and drawdown |
| Sustain | Seeded bootstrap of monthly returns; max-sustainable vs max-preserving withdrawal by bisection; tail budget in months of income |
| Cadence | Month progress with open premium kept separate from booked P&L; target-vs-capacity and margin-headroom checks; pace as a multiple of normal |
| Backtests | Walk-forward RV studies and IV-rule studies; no lookahead |

### I/O shell

| Module | Responsibility |
|---|---|
| Public exchange clients | Instruments, tickers, candles, linear index & funding — one per venue, reached only through that venue's adapter |
| Private exchange clients | Read-only positions & wallet balance. One venue signs each request (HMAC); the other exchanges client credentials for a short-lived read-scoped bearer token |
| Reference client | External venue's DVOL index + option book summary; delta reconstructed locally |
| Portfolio store | Leg CRUD; close (carries entry-context into the closed ledger); volume summary |
| Accounts store | Sub-account management; per-account directories; credential load/save |
| Regime history | Daily market snapshots; percentile / movement context |
| IV history | Intraday session-keyed IV snapshots; own-range percentile; seasonality |
| Pin history | Daily max-pain / GEX / gap rows per (underlying, expiry); settlement and convergence reports, segmented; the pin-prior lookup with its evidence hierarchy |
| Cycles store | Wheel cycles linking a CSP to its follow-on CC; stats derived at query time, never stored |
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

### 2.7 Pricing a structure the way it fills

Take a list of `(contract, side, quantity)`. For each leg pick the side of the book the fill
actually takes — bid to sell, ask to buy — falling back to mid, then to mark, when the needed
side is unquoted, and **record that the fallback happened**. Compute the leg's fee from the
index price and the executable premium. Accumulate three running totals with the sign
convention *positive = credit received*: at mid, at executable prices, and executable minus
fees. Return all three plus their difference decomposed into spread cost and fees, the
retention ratio, per-leg detail including a **fee-folded net price**, and two boolean flags:
credit-vanishes and quote-estimated.

Two consequences of doing it this way rather than applying a haircut:

- The identity `mid − net = spread + fees` is **checkable**, and a test asserts it. A single
  "adjusted credit" would be unfalsifiable.
- Because each leg carries a fee-folded price, the payoff engine produces fee-inclusive
  breakevens **without importing the fee model** — fees are folded in at the one place that
  knows about them, and every other consumer stays ignorant of venue fee rules.

### 2.8 Building a roll table

For a short leg that is tested or near expiry: buy the old leg back at its **ask**, then for
each candidate expiry (soonest first, capped) sell the new leg at its **bid**. Two tables are
produced — same strike, and strike adjusted toward a defensive delta target. Each row pays a
trading fee on both fills.

Per row, derive `added_days` from the DTE difference and divide the after-fee credit by it;
divide again by collateral (strike for puts, spot for calls — the same convention the matrix
tab's annualized yield uses) to get yield-per-day. **These per-day figures, not the raw
credit, are what makes rows at different expiries comparable**, because the VRP term structure
slopes down steeply enough that a bigger absolute credit often buys less premium per unit of
time-risk.

Then score the row (§2.9) — which requires locating the leg *being closed* in the chain, for
the gamma-relief axis. When it cannot be located the row still prices correctly and simply
carries no score, rather than scoring on a guessed old leg.

### 2.9 Scoring a roll

Each axis produces `(raw value, subscore, weight, plain-English reason, display string)` and
appends to a component list; the score is the weight-average over **whichever axes computed**,
with the used-weight total reported so a partially-scored roll is visibly partial. Subscores
come from piecewise-linear interpolation over fixed breakpoints, clamped at both ends.

Gates accumulate into a separate list. Two of them are *hard* — a debit roll, or a new
contract whose IV is at or below forecast RV — and force the verdict to *questionable*
regardless of the average; the rest are advisory and surface next to the score. The
component list is always returned, so the UI can show a trader exactly which axis they are
disagreeing with.

### 2.10 The theta-efficiency read

Convert position theta down to per-unit so the quantity cancels against per-unit gamma, then
compute the breakeven move and express it as a percentage of spot. Compute the leg's own
implied daily move and take the ratio: if it is far from the expected ≈0.96 the greeks are
stale, so flag the leg and treat its read with suspicion. Divide the breakeven percentage by
the **realized** daily percentage supplied by the caller (from ATR or an RV forecast) for the
edge ratio and verdict. If the caller supplies no realized baseline, the verdict stays
`unknown` — the system does **not** fall back to implied, because that is the circular
comparison the module exists to avoid.

The book-level roll-up reports how many legs scored, how many are underpaid, how many have
suspect greeks, and the median edge ratio — deliberately the median, since one deep-OTM leg
with a near-zero gamma can produce an enormous ratio that a mean would not survive.

### 2.11 Searching for a withdrawal limit

Both withdrawal limits are found the same way, and the shape of the search is the interesting
part. Start with a bracket `[0, hi]`; **double `hi` until it actually fails the test**, because
a bracket whose upper end still passes would let bisection converge to the bracket edge and
report a limit that was never tested. Then bisect a fixed number of times, always keeping the
*passing* side as the lower bound. Finally **floor** the result to two decimals.

Before searching at all, test $W=0$. If withdrawing nothing already fails, return `0` with a
note — that is the real answer, and a bisection over an empty feasible set would otherwise
return a meaningless number.

The two tests differ only in the predicate: ruin rate within tolerance (sustainable) versus
median terminal equity at or above starting capital (preserving). Reusing one search with a
swappable predicate is what makes it obvious that they are the *same* procedure answering
*different* questions — which is the point the numbers themselves make loudly.

### 2.12 Assembling the cadence check

Compute what the month has booked and, **separately**, the premium sold on legs opened this
month that are still open. The second number is never added to the first anywhere in the
pipeline; it is passed through to the UI as its own field with its own label.

Then run the checks in a fixed order, because the order encodes which objection dominates:
first whether the target exceeds measured capacity (a structural problem no month can fix),
then whether margin headroom exists to add at all (if not, pace is moot), and only then pace
as a multiple of the normal daily rate. Any input may be absent — average month, preserving
withdrawal, margin figures all come from other layers — and a missing input **withholds its
check** rather than substituting a default. The verdict reads pressure before progress: a
critical warning outranks being nominally on pace.

### 2.13 Turning pin snapshots into evidence

Group rows by expiry; keep expiries strictly in the past that have at least two captures
carrying a usable gap. For each, take the first and last capture: the gap at each end, whether
it narrowed, and — critically — the **context at first capture** (gamma zone, net GEX,
approach direction) as the "prediction" being scored. Classify the expiry as
daily/weekly/monthly/quarterly from its calendar position rather than from a listing flag.

Rates are then computed per segment with an $n$ attached to every one, and the pin-prior
lookup walks the hierarchy from most to least trustworthy, returning the first cell that
clears its own minimum. The function's most important return value is the one where nothing
clears: it returns *insufficient* rather than the pooled number, so a caller cannot
accidentally quote thin evidence as if it were the measured rate.

### 2.14 Routing a request through the active account's venue

Every market-data call in the application layer goes through a small set of helpers —
chain, spot, perp context, funding, candles — that resolve the active account's venue and
dispatch to its adapter. Nothing above that layer names an exchange.

Two implementation details carry most of the risk:

- **The venue is resolved once, alongside the account directory snapshot** taken before the
  first `await` ([01 — Design §1.3](01-design.md)). An account switch landing mid-request must not be able to fetch one
  venue's chain and store it under another venue's account.
- **A canonical field name is not a safe global rename.** Renaming a field across the layer
  also hit the *raw* exchange payloads that one endpoint still reads directly, which silently
  removed that endpoint's spot anchor while every other route kept working. The reverted site
  carries a comment saying why.

### 2.15 Expressing the portfolio in the settlement currency

The chain is normalized to USD at the adapter (§6.2 of the design) and booked money is stored
unconverted (§6.3). Enrichment sits exactly where those two meet, and must reconcile them:
on an inverse venue every field the trader reads as **money** — mark, bid, ask, close quote,
unrealized P&L, theta, vega — is divided by the index so it lands in the same unit as the
stored entry price, and unrealized P&L is then **recomputed from the converted mark** so it
cannot drift from it.

What deliberately does *not* convert: **prices** (spot, strike) stay USD because they are
prices rather than money; **delta and gamma** stay as reported; and **theta efficiency** is
computed from the USD figures on purpose, because its answer is a *price move*.

With no index available, the money fields are **blanked** rather than left as USD numbers
sitting under a coin label.

### 2.16 Background snapshot loop

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
- **Income:** the monthly cash-flow ledger and equity curve, the sustainability report
  (bootstrap, both withdrawal limits, tail budget), and the cadence check against a target.
- **Coach:** the fused brief, scenario stress test, expiry focus, the roll analyzer (priced
  table + five-axis score) and the roll-chain evidence report, regime history, grounded
  natural-language Q&A.
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

~550 tests, all offline. The section below is less about coverage than about the **kinds** of
mistake each technique is designed to catch — because the failure modes this project actually
hit were rarely "the formula is wrong".

### 5.1 Unit tests against synthetic fixtures

Because the math core is pure, every model is tested with zero I/O:

- Volatility estimators against **seeded geometric-Brownian-motion candles** with a known vol.
- Fees and margin against the **exchange's own worked examples**.
- The payoff engine against the **closed-form** payoffs of standard structures.
- Backtests against **seeded ground truth**, so the walk-forward slicing is provably
  lookahead-free rather than asserted to be.
- Sign conventions, scoring, and calibration each have targeted tests — including a regression
  test that would catch the skew-sign bug.
- Invariants that protect the JSON layer (never emit `inf`/`nan`) are asserted directly.

**Compare rounded values with an absolute tolerance.** A venue publishes gamma to five
decimals, so a deep-ITM call's true `6.2e-07` reads as exactly `0.0`. No *relative* tolerance
can ever match a rounded zero — a detail that costs an afternoon if you meet it as a mystery
failure rather than as a rule.

### 5.2 Golden-output regression — the refactor safety net

Before a large refactor (threading a venue through everything, reshaping the fee module), the
question is not "do the tests pass" but **"is the behaviour byte-identical"** — and "it should
be" is not a test.

So: run the whole computation core over a **frozen chain**, serialise the result, and compare
it byte-for-byte against a committed snapshot. If a refactor changes one number anywhere in
the strategy engine, executable pricing, the payoff engine, or the intelligence signals, it
fails and **names the field**.

Four design points make it work:

- **The fixture must be free of `now()` and of the network.** The chain builder computes
  days-to-expiry from the current time, so anything routed through it drifts sub-second
  between runs and can never be byte-compared. The fixture builds contract objects directly
  with hardcoded expiries anchored to a fixed date. Bypassing the chain builder is also the
  right *scope*: REST parsing is already covered elsewhere; what a refactor threatens is
  everything **downstream** of a chain.
- **Floats are rounded to a fixed precision** before comparison, so the test measures
  behaviour rather than the last bit of IEEE-754.
- **The fixture is generated, not hand-written.** The first version used eyeballed mids that
  were not internally consistent with their own implied vols — a 3-DTE at-the-money option
  written as 600 where 50% vol implies about 1,800 — which quietly **starved four strategy
  modules of any candidate at all**. Prices generated by Black-Scholes off a skewed IV curve
  keep price, delta and IV agreeing, so the structures behave as they would on a real book.
- **The shape is deliberately adversarial**: two expiries so term structure and calendars have
  work to do, spreads that *widen* with distance from the money (which is what executable
  pricing is supposed to punish), and one deliberately one-sided contract to exercise the
  estimated-quote path.

**The escape hatch, and its rule.** An environment variable re-approves the snapshot. What
matters is the discipline around it: the resulting diff **is the review artefact** — read it
and confirm every changed number is one you meant to change. It is never run to "make the test
pass", and that sentence is written into the test file itself.

### 5.3 Mutation testing — proving the tests bite

A passing test suite proves the tests pass. It does not prove they would **fail**. So every
guard that matters is broken deliberately, one at a time, and the suite is re-run to confirm
it goes red:

- rounding a coin ledger back to 2dp,
- using one venue's contract size on the other's book,
- claiming margin is modelled where it is not,
- summing two settlement currencies into one scalar,
- comparing a coin-denominated entry against a USD mark.

Two outcomes, both informative:

- **A mutation that survives is a missing test**, not a passing one. One did — an account
  switcher that re-merged two ledgers — and the fix was a new test named after exactly that.
- **A mutation that produces no failure because the mutation itself was malformed** is a false
  negative *in the mutation*, not evidence about the test. This happened once: a method name
  written without its call parentheses, so the "broken" line was never reached. Verify that a
  mutation actually changes behaviour before concluding anything about the test.

### 5.4 Cross-language parity

Several numbers are computed **twice** — once in Python for the API, once in JavaScript so a
panel can render without a round-trip: the trading fee, the roll economics row, contract
sizes, and the verdict vocabularies.

Duplicated logic drifts silently: a threshold changes on one side, both sides still "work",
and the UI quietly disagrees with the API. Nothing catches that except a test that runs
**both** and compares.

The parity tests **extract the real functions out of the frontend file** and execute them in
Node against the same inputs as the Python originals. Crucially they do *not* use a re-typed
copy of the JavaScript — **a copy would drift too**, and a parity test comparing two copies of
the same drift is worse than none. When Node is unavailable the tests **skip rather than
fail**, so the suite still runs in a bare environment.

### 5.5 Private clients: tested offline, never holding a credential

The private integrations are driven through a **stubbed transport**, so they run offline and
cannot touch a live account. This is not only convenient — it is what allowed a venue's
private client to be written and verified without ever asking the trader for keys.

The properties pinned there are the **safety** ones, and they are asserted as *absences*:

- no order, transfer, or withdrawal method exists on the client at all;
- the token is minted with an explicitly read-only scope, so even a future mistake is rejected
  **by the venue** rather than by our own good intentions.

Asserting an absence is unusual and deliberate: a test that says "there is no way to do this"
survives refactors that a test of behaviour would not.

### 5.6 Verifying venue facts against the venue

A wrong venue constant is invisible (design section 6.7). A dedicated check re-derives every
verifiable spec field from the live instrument listing and reports disagreements, so a
contract size or fee rate cannot silently rot. Fields that **cannot** be derived from an API
are listed as unverified on the spec itself rather than being quietly trusted.

### 5.7 Browser-driven verification of the UI

Beyond unit tests, UI changes are verified by driving a real browser against the running app:
render the affected surface (often from a **synthetic multi-asset payload** so edge cases
appear deterministically), read the resulting DOM back, and assert on the actual rendered
values and colours. Console and network are checked for errors.

This catches the class of bug unit tests cannot — a formula that is right but wired to the
wrong column, a colour rule that contradicts the number beside it, a panel rendering
"undefined positions" because it branched on a field the payload does not have.

The same principle applies to generated documents: this compendium's own PDF build is verified
by extracting the text back out and asserting that no unrendered markup, unresolved LaTeX, or
escaped character survived. Three real rendering bugs were found that way, each of which had
**silently dropped content** while looking entirely normal.

### 5.8 Tests that test nothing

The most dangerous test is one that passes without exercising anything. A per-account refactor
moved a module-level path that ~118 tests patched by name; the patches then pointed at
something that no longer existed, the tests kept passing, and they had stopped testing the
code entirely.

Two habits came out of it:

- **Point fixtures at a seam, not at an implementation detail.** A patch aimed at a helper the
  code no longer calls is indistinguishable from a passing test. One such fixture pinned a
  function that a later phase stopped calling, and three API tests quietly went back to hitting
  the live network.
- **When a suite is revived, confirm it can fail.** The same mutation technique as 5.3, used as
  a smoke test on the whole file.

### 5.9 The verification mindset

A change isn't "done" because the code looks right; it's done when the affected flow has been
exercised and observed. The most important fixes in this project — the surface-average-versus-
ATM IV bug, the close-quote colour confusion, the coin-versus-USD units mismatch, the payoff
curve with no premium in it — were all found because a rendered result was read back and
compared against what the number *should* mean.

The recurring shape is worth stating one final time: **every one of those bugs produced numbers
that were internally consistent.** Nothing disagreed with anything. That is precisely why they
survived until something outside the system was checked against them — an identity that must
hold, a structural impossibility, or a value too absurd to be a modelling error.
