# 07 — Mathematical foundations & references

Every formula the system computes, stated precisely, with its provenance.

This document exists because a decision-support tool is only as trustworthy as the
weakest formula inside it. Where a model comes from the literature, it is cited. Where it
is an exchange's published mechanic, the exchange is the authority. Where it is a
practitioner construct with no canonical definition, that is **said out loud** rather than
dressed up as theory. Where it is this system's own choice, the choice and its cost are
stated.

**Provenance tags** appear on every model:

| Tag | Meaning |
|---|---|
| **[L]** | Peer-reviewed literature — the formula is standard and the citation is canonical |
| **[X]** | Exchange-documented mechanic — the venue's own published rule, verified against it |
| **[P]** | Practitioner construct — widely used, no canonical academic definition |
| **[S]** | This system's own choice — a deliberate modelling decision, not a citation |
| **[M]** | This system's own measurement — an empirical finding from its own data |

Numbered references are collected in [§12](#12-references).

---

## 1. Notation and conventions

| Symbol | Meaning |
|---|---|
| $S$ | spot / index price of the underlying |
| $F$ | forward price for a given expiry |
| $K$ | strike |
| $T$ | time to expiry, in years |
| $\sigma$ | volatility, annualized, as a decimal (0.55, not 55) |
| $r$ | risk-free rate — **taken as 0 throughout** (see §3.3) |
| $\Delta,\Gamma,\nu,\Theta$ | the greeks; $\nu$ per **vol point**, $\Theta$ per **day** |
| $O,H,L,C$ | daily open, high, low, close |
| $n$ | sample size (bars, trades, months — always stated per formula) |

**Conventions fixed once, applied everywhere:**

- **Annualization uses $\sqrt{365}$, not $\sqrt{252}$.** **[S]** Crypto trades every calendar
  day. Using the equity convention would inflate every volatility figure by
  $\sqrt{365/252} \approx 1.20$ — a 20% error that would look entirely plausible.
- **Quantity is stored in underlying units** (e.g. BTC), never in contract count. Contract
  count is derived as $q / \text{contract size}$, and contract size is a **venue** fact,
  not a global one (§8.4).
- **Implied volatility is stored as a decimal.** Venues differ — one publishes `0.5521`,
  another publishes `55.21` vol points. Normalizing at the adapter boundary is mandatory;
  a factor of 100 in $\sigma$ is not subtle in a payoff but is nearly invisible in a rank.
- **Skew sign:** positive = puts richer (§6). Defined once, restated at every consumption
  site, because a sign flip here is silent and directional.

---

## 2. Realized-volatility estimators

All four estimators below produce a **daily variance** $\hat\sigma^2_d$ which is annualized
as $\sigma = \sqrt{365\,\hat\sigma^2_d}$. All operate on completed bars only — the
in-progress candle is always dropped, since a partial bar's high/low understates the day's
true range and biases every range-based estimator downward.

### 2.1 Close-to-close **[L]**

The textbook baseline, with $r_i = \ln(C_i / C_{i-1})$:

$$\hat\sigma^2_{cc} = \frac{1}{n-1}\sum_{i=1}^{n}\left(r_i - \bar r\right)^2$$

Kept only as a reference point. It discards the intraday range entirely and is the
noisiest of the four.

### 2.2 Parkinson (1980) **[L]** — ref. [1]

$$\hat\sigma^2_{P} = \frac{1}{4n\ln 2}\sum_{i=1}^{n}\left[\ln\!\left(\frac{H_i}{L_i}\right)\right]^2$$

Uses the high–low range. Under driftless geometric Brownian motion its variance is roughly
**one fifth** that of the close-to-close estimator — the efficiency gain that motivates the
whole range-estimator family. It has a known downward bias in discretely-sampled data,
because the observed high and low understate the continuous extremes.

### 2.3 Garman–Klass (1980) **[L]** — ref. [2]

$$\hat\sigma^2_{GK} = \frac{1}{n}\sum_{i=1}^{n}\left[\tfrac12\ln^2\!\left(\frac{H_i}{L_i}\right) - (2\ln 2 - 1)\ln^2\!\left(\frac{C_i}{O_i}\right)\right]$$

Adds open/close information to Parkinson and is more efficient again. Both Parkinson and
Garman–Klass **assume zero drift**, which is why neither is the primary estimator here.

### 2.4 Rogers–Satchell (1991) **[L]** — ref. [3]

$$\hat\sigma^2_{RS} = \frac{1}{n}\sum_{i=1}^{n}\left[\ln\!\frac{H_i}{O_i}\ln\!\frac{H_i}{C_i} + \ln\!\frac{L_i}{O_i}\ln\!\frac{L_i}{C_i}\right]$$

**Drift-independent** — this is the property that matters for an asset that can trend 40%
in a month. It appears here as a component of Yang–Zhang rather than on its own.

### 2.5 Yang–Zhang (2000) **[L]** — ref. [4] — *the primary estimator*

Decomposes total variance into overnight, open-to-close, and intraday-drift-free parts:

$$\hat\sigma^2_{YZ} = \hat\sigma^2_{o} + k\,\hat\sigma^2_{c} + (1-k)\,\hat\sigma^2_{RS}$$

with

$$\hat\sigma^2_{o} = \mathrm{Var}\!\left[\ln\frac{O_t}{C_{t-1}}\right], \qquad
\hat\sigma^2_{c} = \mathrm{Var}\!\left[\ln\frac{C_t}{O_t}\right], \qquad
k = \frac{0.34}{1.34 + \dfrac{n+1}{n-1}}$$

Both variances are sample variances with the $n-1$ denominator. The weight $k$ is Yang and
Zhang's own minimum-variance choice and is **not tuned here**.

**The crypto caveat, stated because it changes what the estimator is.** Yang–Zhang's
advantage over Rogers–Satchell comes from separating the *overnight gap* — the risk that
accrues while the market is closed. Crypto perpetuals never close, so consecutive candles
are contiguous and $\hat\sigma^2_{o} \approx 0$. On this data YZ therefore degrades
gracefully into a $k$-weighted blend of open-to-close and Rogers–Satchell. It remains the
best of the four, but the specific efficiency figures quoted in the original paper are
derived under an *equity* open/close structure and should not be claimed verbatim here.
**[M]**

---

## 3. Option pricing and the greeks

### 3.1 Black–Scholes–Merton **[L]** — refs. [5], [6]

Used for delta reconstruction where a venue publishes a coarse strike grid, for scenario
repricing of the book under spot/IV/time shocks, and for probability-of-profit estimates.
With $r = 0$:

$$d_1 = \frac{\ln(S/K) + \tfrac12\sigma^2 T}{\sigma\sqrt T},\qquad d_2 = d_1 - \sigma\sqrt T$$

$$C = S\,N(d_1) - K\,N(d_2), \qquad P = K\,N(-d_2) - S\,N(-d_1)$$

### 3.2 Black-76 on the forward **[L]** — ref. [7] — *the cross-venue greeks*

Options on **forwards** (which is what a dated crypto option effectively is, since each
expiry has its own forward) are priced by Black's 1976 model. With $r = 0$:

$$d_1 = \frac{\ln(F/K) + \tfrac12\sigma^2 T}{\sigma\sqrt T}$$

$$\Delta_{\text{call}} = N(d_1), \qquad \Delta_{\text{put}} = N(d_1) - 1$$

$$\Gamma = \frac{\varphi(d_1)}{F\,\sigma\sqrt T}, \qquad
\nu = \frac{F\,\varphi(d_1)\sqrt T}{100}, \qquad
\Theta = -\frac{F\,\varphi(d_1)\,\sigma}{2\sqrt T \cdot 365}$$

where $\varphi$ is the standard normal density. The $/100$ on vega expresses it **per vol
point**, and the $/365$ on theta expresses it **per day** — both are display conventions,
chosen to match what the venues themselves publish so the two are interchangeable.

**Why this specific model matters here.** The system must produce greeks for a venue that
publishes some but not all of them, and those greeks must be *comparable* to the other
venue's. Black-76 on the per-expiry forward reproduces the venue's own published greeks
to **worst error 0.00002 in delta and 0.03% in vega** across the live chain. **[M]** That
agreement is the evidence that the model, the forward, and the IV units were all read
correctly — three things that would each be silently wrong on their own.

### 3.3 Why $r = 0$ **[S]**

There is no risk-free rate in a crypto options book in the sense Black–Scholes means.
Setting $r=0$ and pricing on the **forward** puts all the carry — funding, basis, and the
cost of the coin — into $F$, where the venue has already measured it and publishes it per
expiry. Introducing a separate $r$ would double-count it.

**A related trap, verified live:** both venues publish a per-expiry **forward**
(`underlyingPrice` / `underlying_price`) *and* an **index**. They are not the same number —
on one observation the forward sat **3.93% above** the index. **[M]** Greeks are computed
on the forward; money conversions use the index. Using one where the other belongs is a
~4% error in the moneyness of every strike.

### 3.4 Inverse (coin-margined) options — the self-quanto payoff **[L]/[X]** — ref. [8]

A coin-margined option quotes its premium *in the underlying* and settles *in the
underlying*. Its payoff per contract is therefore

$$\text{Payoff}_{\text{put}}(S_T) = \frac{\max(K - S_T,\,0)}{S_T},\qquad
\text{Payoff}_{\text{call}}(S_T) = \frac{\max(S_T - K,\,0)}{S_T}$$

denominated in the coin. This is a **self-quanto** structure — the payoff is divided by the
very price it is written on — and it is *not* a linear payoff even though the underlying
option is. The short-put P&L in coin is

$$\text{P\&L} = q\left(\text{premium}_{\text{coin}} - \frac{\max(K-S_T,0)}{S_T}\right)$$

Three consequences the system depends on:

1. **The curve bends.** The coin loss on a short put grows more slowly than the USD loss,
   because the denominator grows as price falls — no, it *shrinks*, which makes the coin
   loss grow **faster** than linearly in the region that matters. The distinction is not
   academic: it changes the shape of the drawdown.
2. **The breakeven moves.** Solving $q\,\text{prem} = q\max(K-S,0)/S$ gives
   $S^* = K/(1 + \text{prem})$, not $K - \text{prem}$. On a real book these differed by
   **$261**. **[M]**
3. **A USD-denominated payoff engine cannot be reused.** Subtracting a USD intrinsic from a
   coin premium is dimensionally meaningless, and — because the premium is numerically tiny
   in coin terms — it produces a curve that looks *almost right*. See
   [06 — Lessons](06-lessons-and-gotchas.md).

---

## 4. The variance / volatility risk premium

### 4.1 Definition as used here **[S]**, grounded in **[L]** — refs. [9], [10], [11]

$$\text{VRP}_{\text{pts}} = \sigma_{\text{IV}} - \hat\sigma_{\text{RV}}^{\,\text{fcast}},
\qquad \text{VRP}_{\text{ratio}} = \frac{\sigma_{\text{IV}}}{\hat\sigma_{\text{RV}}^{\,\text{fcast}}}$$

The academic construct (Carr–Wu [9], Bollerslev–Tauchen–Zhou [11]) is defined in
**variance** terms and against *realized-forward* variance — i.e. what volatility actually
turned out to be over the option's life. This system reports it in **volatility points**
against a **forecast**, because it is used as a live decision gate before the outcome
exists. The two are related but not identical, and the difference is stated wherever the
number is displayed.

Bakshi–Kapadia [10] is the cleanest evidence that the premium is real and negative for the
buyer: delta-hedged option positions lose money on average, which is the seller's edge
stated from the other side.

### 4.2 The RV forecast: HAR-inspired, deliberately unfitted **[S]**, after **[L]** ref. [12]

$$\hat\sigma^{\text{fcast}} = 0.30\,\sigma_{YZ}^{(5)} + 0.40\,\sigma_{YZ}^{(20)} + 0.30\,\sigma_{YZ}^{(60)}$$

Corsi's HAR-RV [12] regresses realized variance on daily / weekly / monthly components with
**OLS-fitted** coefficients, exploiting the long-memory structure of volatility. This
system keeps the multi-horizon *structure* and throws away the *fitting*:

- **Windows are 5 / 20 / 60 days**, not Corsi's 1 / 5 / 22.
- **Weights are fixed at 0.30 / 0.40 / 0.30** and are never estimated from data.
- When a window has insufficient history it is **dropped and the remaining weights
  renormalized**, so a young dataset yields a coarser but honest forecast rather than none.

This is a real accuracy sacrifice, taken on purpose: a fitted forecast on a single
underlying's short history would overfit, and — more importantly — could not be audited by
the person trusting it. Every weight here is visible in one line.

### 4.3 The headline empirical finding **[M]**

Measured on this book's own BTC history: the **ATM** vol-risk premium is razor-thin —
implied ≈ realized-forward over ~30 days. The edge in this book is therefore **not** ATM
richness; it is the **OTM skew and tail being sold**, plus theta/gamma management. This is
a finding that argues against the strategy's own marketing, which is why it is recorded.

---

## 5. Expected move, and the $\sqrt{2/\pi}$ correction

### 5.1 The straddle-implied move **[L]** — ref. [13]

$$\text{EM}\% = \frac{P_{\text{ATM}} + C_{\text{ATM}}}{S}$$

using the nearest-to-spot strike with **both sides quoted**.

**The precision point most tools get wrong.** Brenner and Subrahmanyam [13] show that at
the money, with $r=0$,

$$P_{\text{ATM}} + C_{\text{ATM}} \;\approx\; \sqrt{\tfrac{2}{\pi}}\;S\,\sigma\sqrt{T} \;\approx\; 0.7979\,S\,\sigma\sqrt T$$

So the straddle price is **not** a one-sigma move. It is $\approx 0.80\sigma$ — which is
exactly $E[|X|]$ for $X \sim N(0,\sigma^2)$, the **mean absolute deviation**. Calling the
straddle "the expected move" is therefore correct in the literal sense (it *is* the expected
absolute move) and wrong if read as a one-standard-deviation band, which contains ~68% of
outcomes rather than the ~58% this does.

The system compares EM% against the **realized** distribution of $|{\rm move}|$ over the
same horizon, which sidesteps the confusion entirely: mean-absolute is compared with
mean-absolute.

### 5.2 The overlapping-window caveat **[L]** — ref. [14]

The realized-move distribution is computed over **rolling, overlapping** $h$-day windows.
This is the standard trade-off for sample size on a short history, and it is standard that
overlapping windows induce serial correlation and **inflate the effective $n$** — the
Hansen–Hodrick problem [14]. The system reports the raw $n$ and does not compute confidence
intervals from it, because an interval built on an inflated $n$ would be worse than no
interval.

---

## 6. Skew

### 6.1 The 25-delta convention **[P]/[L]** — ref. [15]

$$\text{Skew}_{25} = \sigma_{\text{IV}}(\Delta_{\text{put}} = -0.25) - \sigma_{\text{IV}}(\Delta_{\text{call}} = +0.25)$$

**Positive = puts richer**, the normal fearful state. This is the FX **risk-reversal**
convention (Clark [15]) applied to crypto, where the same 25Δ market convention has been
adopted by the major venues.

Two disciplines around it:

- **The sign is defined once and restated at every consumption site** (labelling, digest,
  scoring). A sign error here inverts the reading of every fearful market and is completely
  invisible in the output — this exact bug shipped and ran live before an audit caught it.
- **Delta is reconstructed via Black-Scholes, not trusted from the strike grid**, and the
  value is **withheld** when the nearest available strike is not genuinely near 25Δ. A
  coarse grid must not be permitted to produce a precise-looking number.

### 6.2 What is *not* claimed

The system does **not** compute model-free risk-neutral skewness (Bakshi–Kapadia–Madan
[16]), which would require a full strike continuum and a different integral. The 25Δ
measure is a two-point proxy, and is labelled as such.

---

## 7. Gamma positioning

This section carries the heaviest **[P]** weighting in the document, and that is exactly why
the system *measures* its predictions rather than assuming them (§7.4).

### 7.1 Max pain **[P]**, with academic cousin **[L]** — refs. [17], [18], [19]

$$K^\ast = \arg\min_{K}\ \sum_{i}\text{OI}_i \cdot \text{intrinsic}_i(K)$$

i.e. the strike minimizing total option-holder payout across the expiry.

**"Max pain" itself is a practitioner heuristic with no academic derivation.** What the
literature establishes is narrower and better evidenced: prices *cluster at strikes* on
expiration dates (Ni, Pearson & Poteshman [17]), and there is a mechanism — delta-hedging
rebalancing by writers — that produces it (Avellaneda & Lipkin [18]); Golez & Jackwerth [19]
find pinning in S&P 500 futures. Related but not the same claim. The honest statement is:
*strike pinning is documented; "price drifts to the single max-pain strike" is folklore
until measured.*

### 7.2 Gamma exposure (GEX) **[P]**

$$\text{GEX}(K) = \Gamma_{\text{call}}(K)\,\text{OI}_{\text{call}}(K)\,S^2 - \Gamma_{\text{put}}(K)\,\text{OI}_{\text{put}}(K)\,S^2$$

(scaled by a constant for display). The sign convention assumes dealers are **long calls,
short puts** relative to the retail flow — the standard practitioner assumption, and one
that is *an assumption*, not a measurement. Positive net GEX is read as a dealer long-gamma
zone (hedging is mean-reverting: buy dips, sell rallies), negative as short-gamma
(hedging amplifies: sell dips, buy rallies).

The underlying mechanism — that option hedging feeds back into the underlying's dynamics —
*is* documented (Ni, Pearson, Poteshman & White [20]; Barbon & Buraschi [21]). The specific
GEX construction is not.

### 7.3 Zero-gamma flip **[P]**

The spot level where the cumulative net-GEX profile crosses zero: the boundary between the
stabilizing and accelerating regimes. Used as a summary field, a digest signal, and a
scoring input.

### 7.4 Why the system stores pin history **[S]/[M]**

Because §7.1–7.3 are practitioner constructs, the system does not take them on faith. It
snapshots, per (underlying, expiry) per day, the max-pain level, the gap to spot, the net
GEX, and the gamma zone at spot. Once an expiry passes, the row sequence becomes a
**completed sample**: did $|S - K^\ast|$ actually narrow between the first and last
pre-expiry capture, and did the gamma zone at capture time predict it?

Three honesty rules make that sample meaningful:

- An expiry needs **≥2 captures** to measure convergence at all; a single row is excluded.
- The report needs **≥5 completed expiries** before quoting any rate, and always carries $n$.
- **Daily expiries are segmented out.** The pinning literature concerns *serial* expirations
  carrying real open interest. Crypto dailies carry very little, so pooling them with the
  monthlies would drown the signal in noise that looks like data. Segmenting raises the
  minimum-$n$ bar rather than keeping it fixed while the cells get thinner.

---

## 8. Fees, margin, and breakeven

### 8.1 Trading fee **[X]**

$$\text{fee}_{\text{fill}} = \min\!\left(\text{rate} \times S_{\text{index}},\ \ c_{\text{prem}} \times \text{premium}\right) \times q$$

with taker rate ≈ 0.03%, maker ≈ 0.02%, and the **premium cap** $c_{\text{prem}}$ being a
**venue** parameter: **7%** on one venue, **12.5%** on the other. The cap is the subtle
term — on far-OTM cheap legs the percentage-of-premium term is smaller than the
percentage-of-index term, so the cap binds precisely on the legs a strangle seller trades
most. Ignoring it overstates the fee where it matters.

A round trip pays this on **both** the open and the close fill. Modelling one side halves
the cost.

### 8.2 Delivery (settlement) fee **[X]**

$$\text{fee}_{\text{delivery}} = \min\!\left(\text{deliveryRate} \times S_{\text{index}},\ 12.5\% \times \text{intrinsic}\right) \times q$$

charged **only on exercise**. An out-of-the-money expiry is free. `deliveryRate` ≈ 0.015%
for BTC/ETH, ≈ 0.02% for alts. **Daily options incur no delivery fee at all** — an exception
re-verified against the exchange's own help page, and one that materially changes breakeven
math (§8.5).

### 8.3 Initial margin, short option **[X]**

$$\text{IM} = \Big[\max\big(f_{\max}S - \text{OTM},\ f_{\min}S\big) + \max(\text{avg\_price},\ \text{mark})\Big] \times q$$

$$\text{OTM}_{\text{call}} = \max(0,\ K - S), \qquad \text{OTM}_{\text{put}} = \max(0,\ S - K)$$

with $(f_{\max}, f_{\min}) \approx (0.10,\ 0.05)$ for BTC/ETH, verified against the
exchange's own worked example. A long option's margin is its premium.

**This formula describes exactly one venue.** It is reconstructed by hand because the
unified account reports empty per-position IM for options — only an account-level total —
and per-leg attribution is what tells the trader *which* leg to trim. On a venue that
publishes no IM factors of its own, the system now **refuses to present this number as
modelled** rather than computing a confident figure with another exchange's parameters.

### 8.4 Contract size is a venue fact **[X]**

$$\text{contracts} = \frac{q}{\text{contract size}(\text{venue}, \text{underlying})}$$

0.01 BTC on one venue, **1 BTC** on another; **1.0** for SOL where BTC/ETH are 0.01. Because
$q$ is stored in underlying units, the margin and payoff formulas are size-agnostic — only
contract *counts* need it. This single convention prevents a family of 100× errors, and
every place it was violated produced exactly that: a 0.9-contract book reported as 90.

### 8.5 Fee-adjusted breakeven requires a root-finder **[S]**

The terminal price at which a leg nets exactly zero **after** the open trading fee **and**
the delivery fee has no closed form, because the delivery fee is a $\min(\cdot,\cdot)$ whose
binding term depends on the premium size. So the breakeven is obtained by **bisection
against the exact fee model** [22] rather than a formula:

- the net-at-expiry P&L is monotone on each side of the strike, so the root is bracketed;
- bisecting against the *same* fee function used on real closes guarantees the displayed
  breakeven and the realized P&L agree to the cent — same code path, different caller;
- for daily options the delivery term drops and the breakeven collapses to the clean
  $K - (\text{entry} - \text{fee}_{\text{open}})$ for a short put.

A short put's fee-adjusted breakeven shifts **up** toward the strike (less room); a short
call's shifts **down**; longs need a bigger move to overcome the drag.

---

## 9. Theta efficiency — the one comparison that carries information

This is the most mathematically load-bearing section in the system, because the obvious
version of it is **circular** and produces a number that looks informative and is not.

### 9.1 The daily P&L decomposition **[L]** — ref. [23]

For a delta-hedged short option over one day,

$$\Delta \text{P\&L} \;\approx\; |\Theta|\,\Delta t \;-\; \tfrac12\,\Gamma\,(\Delta S)^2$$

so the move that exactly consumes one day of theta is

$$\boxed{\ \Delta S^{\ast} = \sqrt{\frac{2\,|\Theta|}{\Gamma}}\ }$$

### 9.2 Why comparing $\Delta S^\ast$ to the *implied* move is circular **[L]/[M]**

The Black–Scholes PDE with $r = q = 0$ gives

$$\Theta = -\tfrac12\,\sigma^2 S^2\,\Gamma$$

Substituting into $\Delta S^\ast$ collapses it exactly:

$$\Delta S^{\ast} = \sqrt{\frac{2 \cdot \tfrac12 \sigma^2 S^2 \Gamma / 365}{\Gamma}} = \frac{S\sigma}{\sqrt{365}}$$

— which *is* the implied daily move. The comparison is an identity, not a signal. Verified
against the live BTC chain: $\Delta S^\ast / \text{implied}$ sits at a flat **≈0.96** across
every strike and every tenor. **[M]** The residual 4% is the venue's theta carrying a
rates/carry term that the $\tfrac12\Gamma(\Delta S)^2$ approximation drops.

### 9.3 The comparison that does carry information **[L]** — refs. [24], [25]

$$\text{edge ratio} = \frac{\Delta S^{\ast}}{\text{realized daily move}}$$

Comparing the breakeven move against **realized** movement is the variance risk premium
measured *on this specific leg with its own greeks*, rather than as a surface average. This
is the discrete, per-leg form of the classical delta-hedged P&L result (Carr–Madan [24];
El Karoui, Jeanblanc-Picqué & Shreve [25]):

$$\text{P\&L}_{\text{hedged}} = \tfrac12\int_0^T \Gamma_t\,S_t^2\left(\sigma^2_{\text{implied}} - \sigma^2_{\text{realized},t}\right)dt$$

Realized above breakeven ⇒ the position **loses in expectation** even while theta prints
positive every single day. That is the failure mode the whole module exists to surface.

Verdict bands: ≥1.15 *paid well*, ≥1.00 *marginal*, below *underpaid*. **[S]**

### 9.4 The stale-greeks detector **[S]**

Because §9.2 establishes that $\Delta S^\ast/\text{implied}$ *must* be ≈0.96, any leg whose
ratio wanders more than ±0.20 from it has greeks that are stale or internally inconsistent,
and its efficiency reading is flagged untrustworthy. A degenerate identity turned into a
data-quality check.

### 9.5 The units trap **[S]**

On an enriched leg, $\Theta$ is **position** theta (already $\times q$, signed so a seller
earns positive) while $\Gamma$ and $\nu$ are **per-unit and unsigned**. Mixing the two
scales leaves a stray $q$ inside the square root and yields a plausible, wrong breakeven.
Everything converts to per-unit first, and the function signature exists to force it.

---

## 10. Statistical machinery

### 10.1 Percentile rank with a sample gate **[S]**

Today's reading is ranked against the book's own trailing history (typically 90 days) as a
true empirical percentile, with a 5-day movement arrow attached. **Below a minimum sample
the percentile is withheld or explicitly hedged** — "only $N$ days tracked so far" is a
first-class output, not an error state.

### 10.2 Bootstrap for withdrawal sustainability **[L]** — refs. [26], [27]

Monthly returns are resampled **with replacement** from the months actually observed
(Efron [26]), compounding equity proportionally and taking the withdrawal in cash after
each month's return:

$$E_{t+1} = E_t\,(1 + r_{i_t}) - W, \qquad i_t \sim \text{Uniform}\{1,\dots,n\}$$

Ruin is declared below 30% of starting capital. The simulation is **seeded**, so the number
does not move between page reloads.

**Why bootstrap rather than fit.** Fitting a parametric distribution to a dozen observations
of a negatively-skewed, fat-tailed return stream produces a clean number worth nothing.
Resampling is honest about the evidence — at one specific, stated price:

> **A bootstrap cannot produce a month worse than the worst month observed.**

If the sample has not lived through a crash, every path is optimistic and the ruin rate is
a **floor, not an estimate**. This is the classical limitation of resampling in the tail
(Embrechts, Klüppelberg & Mikosch [27] is the standard treatment of what would be required
instead). It is why the tail budget is computed *separately*, by repricing the **current
book** under a shock — a number that does not depend on the sample having contained one.

Modelling choices, all explicit **[S]**: monthly returns are taken as P&L / capital (so a
materially different capital base today makes the estimate wrong, and the report says so);
equity compounds proportionally, so a shrinking account earns proportionally smaller premium
— holding size constant as equity falls would flatter every path.

### 10.3 Sequence-of-returns risk **[L]** — ref. [28]

The reason a "monthly income" framing needs simulation at all rather than an average: with
withdrawals, the **order** of returns changes the outcome, and a negatively-skewed return
stream concentrates the damage. Bengen [28] is the canonical treatment for withdrawal rates;
the mechanism is identical here even though the asset is not.

### 10.4 Trade statistics **[S]**

$$\text{expectancy} = \frac{\sum \text{P\&L}}{n_{\text{trades}}}, \qquad
\text{profit factor} = \frac{\sum \text{wins}}{\left|\sum \text{losses}\right|}$$

Segmented by strategy family, underlying, and DTE band. **The current month is excluded
from every monthly statistic** — a partial month flatters or damns the record at random.

### 10.5 A stated gap **[S]**

The system gates statistics on a **minimum $n$** rather than reporting a **confidence
interval**. A binomial proportion interval (Wilson [29] is the standard choice for small
$n$, and is materially better-behaved than the normal approximation) would be strictly more
informative than a hard gate: "62% ± 18pp on n=21" says more than either "62%" or nothing.
This is a known, deliberate simplification and a documented candidate for future work — it
is recorded here rather than quietly omitted.

---

## 11. Risk sizing and backtest method

### 11.1 Volatility targeting **[L]** — ref. [30]

$$w = \min\!\left(1,\ \frac{\sigma_{\text{target}}}{\sigma_{\text{realized}}}\right), \quad w \ge w_{\min}$$

Exposure shrinks when the market gets loud. Moreira & Muir [30] is the reference result that
volatility-managed exposure improves risk-adjusted returns; the floor $w_{\min}$ is this
system's own addition, to stop the rule from sizing to zero in a spike. **[S]**

### 11.2 Walk-forward backtesting, no lookahead **[S]**

The invariant, enforced by a strict slicing convention: the "known world" at day $t$ is the
slice **up to and including** $t$; forward outcomes are measured on **strictly later** bars.
IV-rank percentiles are computed only over the trailing window of *past* data. Any
accidental use of a future bar inflates results, so the slice boundaries are what the tests
guard — verified against **seeded ground truth** so the absence of lookahead is provable
rather than asserted.

### 11.3 Empirical findings from this book's own data **[M]**

- The **ATM** vol-risk premium is razor-thin (implied ≈ realized-forward over ~30 days).
  The edge is in the OTM skew/tail, not ATM richness.
- **IV-rank timing does add** roughly a couple of vol points — "sell when IV rank is high"
  is validated. The middle tier is noisy from overlapping windows (§5.2) and is reported as
  such rather than smoothed.
- Crypto **tails run ≈2.7× Gaussian** at monthly horizons: a 2σ/30-day put finishes
  in-the-money ~6% of the time against ~2% under normal theory. Consistent with the
  long-standing stylized facts on heavy-tailed returns (Mandelbrot [31]; Cont [32]), and a
  direct argument against long-dated naked puts at wide-but-not-wide-enough strikes.

---

## 12. References

### Peer-reviewed literature **[L]**

1. Parkinson, M. (1980). "The Extreme Value Method for Estimating the Variance of the Rate of Return." *Journal of Business*, 53(1), 61–65.
2. Garman, M. B., & Klass, M. J. (1980). "On the Estimation of Security Price Volatilities from Historical Data." *Journal of Business*, 53(1), 67–78.
3. Rogers, L. C. G., & Satchell, S. E. (1991). "Estimating Variance from High, Low and Closing Prices." *Annals of Applied Probability*, 1(4), 504–512.
4. Yang, D., & Zhang, Q. (2000). "Drift-Independent Volatility Estimation Based on High, Low, Open, and Close Prices." *Journal of Business*, 73(3), 477–491.
5. Black, F., & Scholes, M. (1973). "The Pricing of Options and Corporate Liabilities." *Journal of Political Economy*, 81(3), 637–654.
6. Merton, R. C. (1973). "Theory of Rational Option Pricing." *Bell Journal of Economics and Management Science*, 4(1), 141–183.
7. Black, F. (1976). "The Pricing of Commodity Contracts." *Journal of Financial Economics*, 3(1–2), 167–179.
8. Wystup, U. (2006). *FX Options and Structured Products*. Wiley. — quanto and self-quanto payoffs.
9. Carr, P., & Wu, L. (2009). "Variance Risk Premiums." *Review of Financial Studies*, 22(3), 1311–1341.
10. Bakshi, G., & Kapadia, N. (2003). "Delta-Hedged Gains and the Negative Market Volatility Risk Premium." *Review of Financial Studies*, 16(2), 527–566.
11. Bollerslev, T., Tauchen, G., & Zhou, H. (2009). "Expected Stock Returns and Variance Risk Premia." *Review of Financial Studies*, 22(11), 4463–4492.
12. Corsi, F. (2009). "A Simple Approximate Long-Memory Model of Realized Volatility." *Journal of Financial Econometrics*, 7(2), 174–196.
13. Brenner, M., & Subrahmanyam, M. G. (1988). "A Simple Formula to Compute the Implied Standard Deviation." *Financial Analysts Journal*, 44(5), 80–83.
14. Hansen, L. P., & Hodrick, R. J. (1980). "Forward Exchange Rates as Optimal Predictors of Future Spot Rates." *Journal of Political Economy*, 88(5), 829–853. — overlapping-observation inference.
15. Clark, I. J. (2011). *Foreign Exchange Option Pricing: A Practitioner's Guide*. Wiley. — 25Δ risk-reversal / butterfly market conventions.
16. Bakshi, G., Kapadia, N., & Madan, D. (2003). "Stock Return Characteristics, Skew Laws, and the Differential Pricing of Individual Equity Options." *Review of Financial Studies*, 16(1), 101–143.
17. Ni, S. X., Pearson, N. D., & Poteshman, A. M. (2005). "Stock Price Clustering on Option Expiration Dates." *Journal of Financial Economics*, 78(1), 49–87.
18. Avellaneda, M., & Lipkin, M. D. (2003). "A Market-Induced Mechanism for Stock Pinning." *Quantitative Finance*, 3(6), 417–425.
19. Golez, B., & Jackwerth, J. C. (2012). "Pinning in the S&P 500 Futures." *Journal of Financial Economics*, 106(3), 566–585.
20. Ni, S. X., Pearson, N. D., Poteshman, A. M., & White, J. (2021). "Does Option Trading Have a Pervasive Impact on Underlying Stock Prices?" *Review of Financial Studies*, 34(4), 1952–1986.
21. Barbon, A., & Buraschi, A. (2020). "Gamma Fragility." Working paper (SSRN).
22. Press, W. H., Teukolsky, S. A., Vetterling, W. T., & Flannery, B. P. (2007). *Numerical Recipes* (3rd ed.), Ch. 9. Cambridge University Press. — bracketing and bisection.
23. Hull, J. C. (2017). *Options, Futures, and Other Derivatives* (10th ed.). Pearson. — the greeks and the Black–Scholes PDE relation $\Theta + \tfrac12\sigma^2S^2\Gamma + rS\Delta = rV$.
24. Carr, P., & Madan, D. (1998). "Towards a Theory of Volatility Trading." In *Volatility: New Estimation Techniques for Pricing Derivatives*. Risk Books.
25. El Karoui, N., Jeanblanc-Picqué, M., & Shreve, S. E. (1998). "Robustness of the Black and Scholes Formula." *Mathematical Finance*, 8(2), 93–126.
26. Efron, B. (1979). "Bootstrap Methods: Another Look at the Jackknife." *Annals of Statistics*, 7(1), 1–26.
27. Embrechts, P., Klüppelberg, C., & Mikosch, T. (1997). *Modelling Extremal Events for Insurance and Finance*. Springer.
28. Bengen, W. P. (1994). "Determining Withdrawal Rates Using Historical Data." *Journal of Financial Planning*, 7(4), 171–180.
29. Wilson, E. B. (1927). "Probable Inference, the Law of Succession, and Statistical Inference." *Journal of the American Statistical Association*, 22(158), 209–212.
30. Moreira, A., & Muir, T. (2017). "Volatility-Managed Portfolios." *Journal of Finance*, 72(4), 1611–1644.
31. Mandelbrot, B. (1963). "The Variation of Certain Speculative Prices." *Journal of Business*, 36(4), 394–419.
32. Cont, R. (2001). "Empirical Properties of Asset Returns: Stylized Facts and Statistical Issues." *Quantitative Finance*, 1(2), 223–236.

### Exchange documentation **[X]**

The fee, margin, delivery, contract-size, and settlement mechanics in §8 are taken from the
venues' own published help pages and instrument metadata, and are **re-verified against the
live instrument list** by an automated check rather than trusted from a constant in the
code. Where a parameter could not be confirmed from a primary source, it is carried as an
explicitly flagged placeholder and the affected output emits a warning.

### On the practitioner constructs **[P]**

§7 (max pain, GEX, zero-gamma flip) has no canonical academic definition. The system uses
these constructs because the flow mechanism behind them is real and documented ([17]–[21]),
but treats their *predictions* as hypotheses under test rather than inputs — which is the
entire purpose of the pin-history store (§7.4).

---

## Disclaimer

Nothing in this document is financial advice. Formulas are reproduced for transparency about
what the system computes; their presence does not imply that any strategy derived from them
is profitable. Short-premium options trading carries the risk of large and, in some
structures, unbounded losses.
