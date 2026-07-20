#!/usr/bin/env python3
"""
Generate expiry-payoff diagrams (PNG) for every strategy in the library.

Pure Python: numpy + Pillow only. Each chart is the piecewise-linear P&L at
expiry versus the underlying price, per 1 unit of underlying, gross of fees —
illustrative shapes with representative BTC-scale strikes and premiums, not a
live quote. Max-profit / max-loss labels are hand-verified per structure (the
plotted range can't be trusted for naked tails). The calendar is special-cased
(cross-expiry, long-vega) and valued with a small Black-Scholes model at the
front expiry, clearly labelled.

Output: docs/images/*.png
Usage:  python generate_payoffs.py
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "docs", "images")
os.makedirs(OUTDIR, exist_ok=True)
FONTS = r"C:\Windows\Fonts"

SCALE = 2
W, H = 1000 * SCALE, 560 * SCALE
ML, MR, MT, MB = 100 * SCALE, 46 * SCALE, 66 * SCALE, 88 * SCALE

INK = (27, 31, 36)
ACCENT = (31, 111, 235)
GREEN = (32, 128, 56)
RED = (200, 44, 54)
GREY = (140, 148, 158)
GRID = (226, 231, 236)
PALE_G = (223, 242, 227)
PALE_R = (250, 226, 228)
WHITE = (255, 255, 255)


def font(sz, bold=False):
    return ImageFont.truetype(os.path.join(FONTS, "arialbd.ttf" if bold else "arial.ttf"), int(sz * SCALE))


F_TITLE, F_SUB = font(19, True), font(11)
F_AXIS, F_TICK = font(11, True), font(9.5)
F_ANNO, F_K, F_FOOT = font(11, True), font(9.5, True), font(8.5)


def _nd(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs(S, K, T, iv, call):
    if T <= 0:
        return max(0.0, (S - K) if call else (K - S))
    d1 = (math.log(S / K) + 0.5 * iv * iv * T) / (iv * math.sqrt(T))
    d2 = d1 - iv * math.sqrt(T)
    return (S * _nd(d1) - K * _nd(d2)) if call else (K * _nd(-d2) - S * _nd(-d1))


def leg_pnl(kind, side, strike, prem, S):
    if kind == "under":
        return S - strike
    intr = np.maximum(0.0, (S - strike) if kind == "call" else (strike - S))
    return (prem - intr) if side == "short" else (intr - prem)


def payoff(legs, S):
    tot = np.zeros_like(S, dtype=float)
    for lg in legs:
        tot += leg_pnl(*lg, S)
    return tot


def calendar_payoff(K, S, iv=0.62, t_far=30 / 365):
    debit = bs(K, K, 37 / 365, iv, True) - bs(K, K, 7 / 365, iv, True)
    val = np.array([bs(s, K, t_far, iv, True) - max(0.0, s - K) for s in S])
    return val - debit


SPOT = 65000
STRATS = [
    dict(file="cash_secured_put", title="Cash-Secured Put  (short put)",
         sub="Sell downside premium; keep the full credit while spot stays above the strike.",
         legs=[("put", "short", 60000, 1200)], maxl="large down (to $0, naked)"),
    dict(file="covered_call", title="Covered Call  (long underlying + short call)",
         sub="Own the underlying, sell an upside call; caps the upside for extra yield.",
         legs=[("under", "long", 65000, 0), ("call", "short", 70000, 1000)],
         maxl="large down (to $0)"),
    dict(file="bull_put_spread", title="Bull Put Credit Spread",
         sub="Short put financed by a lower long put — defined risk, bullish-to-neutral.",
         legs=[("put", "short", 62000, 1400), ("put", "long", 58000, 600)]),
    dict(file="bear_call_spread", title="Bear Call Credit Spread",
         sub="Short call capped by a higher long call — defined risk, bearish-to-neutral.",
         legs=[("call", "short", 68000, 1200), ("call", "long", 72000, 500)]),
    dict(file="iron_condor", title="Iron Condor",
         sub="Short strangle with both wings bought back — defined risk, range-bound.",
         legs=[("put", "short", 60000, 1300), ("put", "long", 56000, 500),
               ("call", "short", 70000, 1200), ("call", "long", 74000, 400)]),
    dict(file="short_strangle", title="Short Strangle  (naked)",
         sub="Sell an OTM put and an OTM call — max premium, UNCAPPED tail both sides.",
         legs=[("put", "short", 60000, 1300), ("call", "short", 70000, 1200)],
         maxl="unlimited up / large down"),
    dict(file="jade_lizard", title="Jade Lizard",
         sub="Short put + short call spread; credit >= call-spread width, so there is NO upside risk.",
         legs=[("put", "short", 60000, 1300), ("call", "short", 70000, 1200),
               ("call", "long", 71500, 300)], maxl="large down only (no upside risk)"),
    dict(file="broken_wing_butterfly", title="Broken-Wing Butterfly  (put fly for a credit)",
         sub="1-2-1 put fly, wider lower wing, entered for a credit — harvests put skew, no upside risk.",
         legs=[("put", "long", 64000, 1700), ("put", "short", 60000, 1300),
               ("put", "short", 60000, 1300), ("put", "long", 54000, 400)]),
    dict(file="put_ratio_spread", title="Put Ratio Spread  (1x2 front ratio)",
         sub="Long put over two short lower puts for a credit — undefined risk below the lower breakeven.",
         legs=[("put", "long", 62000, 1000), ("put", "short", 58000, 700),
               ("put", "short", 58000, 700)], maxl="large down (undefined)"),
    dict(file="calendar", title="Calendar  (long far / short near, same strike)",
         sub="The only long-vega / debit structure — wants cheap vol + contango. Value shown at the front expiry.",
         calendar=65000),
    dict(file="put_ladder", title="Put Ladder  (short put + two lower longs)",
         sub="Credit-only defensive structure — a defined pocket of loss, then a CRASH turns profitable.",
         legs=[("put", "short", 60000, 1400), ("put", "long", 56000, 800),
               ("put", "long", 52000, 400)], maxp="grows in a crash down"),
    dict(file="iron_butterfly", title="Iron Butterfly  (ATM body)",
         sub="Sell the ATM straddle, buy protective wings — max theta, tight pin play.",
         legs=[("put", "short", 65000, 1600), ("call", "short", 65000, 1400),
               ("put", "long", 61000, 500), ("call", "long", 69000, 400)]),
    dict(file="seagull", title="Seagull  (zero-cost / credit bullish)",
         sub="Short put funds a long call spread — cheap bullish participation, capped upside, downside tail.",
         legs=[("put", "short", 60000, 1300), ("call", "long", 68000, 1000),
               ("call", "short", 74000, 300)], maxl="large down (naked put)"),
    dict(file="risk_reversal", title="Risk Reversal  (short put + long call)",
         sub="Sell rich put skew to finance a call — synthetic-long shape, near zero cost.",
         legs=[("put", "short", 60000, 1300), ("call", "long", 70000, 1200)],
         maxp="unlimited up", maxl="large down (naked put)"),
]


def ref_prices(s):
    if s.get("calendar"):
        return [s["calendar"], SPOT]
    ks = [k for (kind, _, k, _) in s["legs"] if kind != "under"]
    return ks + [SPOT]


def draw(s):
    refs = ref_prices(s)
    lo, hi = min(refs), max(refs)
    span = max(hi - lo, 8000)
    x0, x1 = lo - span * 0.7, hi + span * 0.7
    S = np.linspace(x0, x1, 1600)
    P = calendar_payoff(s["calendar"], S) if s.get("calendar") else payoff(s["legs"], S)

    ymin, ymax = float(P.min()), float(P.max())
    pad = max((ymax - ymin) * 0.20, 300)
    ymin, ymax = ymin - pad, ymax + pad

    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    px0, px1, py0, py1 = ML, W - MR, MT, H - MB

    def sx(v):
        return px0 + (v - x0) / (x1 - x0) * (px1 - px0)

    def sy(v):
        return py1 - (v - ymin) / (ymax - ymin) * (py1 - py0)

    zy = sy(0)

    # profit/loss shading (solid pale fills, no alpha needed on white)
    xs = np.arange(px0, px1)
    Pi = np.interp(np.linspace(x0, x1, len(xs)), S, P)
    for xi, pv in zip(xs, Pi):
        d.line([(xi, zy), (xi, sy(pv))], fill=(PALE_G if pv >= 0 else PALE_R), width=1)

    # y grid + ticks
    for gy in np.linspace(ymin, ymax, 7):
        yy = sy(gy)
        d.line([(px0, yy), (px1, yy)], fill=GRID, width=1)
        d.text((px0 - 10 * SCALE, yy), f"{gy:+,.0f}", font=F_TICK, fill=GREY, anchor="rm")

    d.line([(px0, zy), (px1, zy)], fill=(90, 99, 108), width=2)   # zero line

    # strikes (dashed verticals + k-labels)
    for k in sorted({r for r in refs if r != SPOT}):
        xk, yy = sx(k), py0
        while yy < py1:
            d.line([(xk, yy), (xk, min(yy + 8 * SCALE, py1))], fill=(198, 205, 212), width=1)
            yy += 14 * SCALE
        d.text((xk, py1 + 6 * SCALE), f"{k/1000:.1f}k".replace(".0k", "k"), font=F_K, fill=INK, anchor="mt")

    # payoff line
    d.line([(sx(v), sy(p)) for v, p in zip(S, P)], fill=ACCENT, width=3 * SCALE, joint="curve")

    # breakevens
    sign = np.sign(P)
    for i in range(1, len(P)):
        if sign[i - 1] != sign[i] and sign[i] != 0 and P[i] != P[i - 1]:
            xv = np.interp(0, [P[i - 1], P[i]], [S[i - 1], S[i]])
            bx = sx(xv)
            r = 5 * SCALE
            d.ellipse([bx - r, zy - r, bx + r, zy + r], fill=WHITE, outline=INK, width=2 * SCALE)
            d.text((bx, zy - 9 * SCALE), f"BE {xv/1000:.1f}k", font=F_TICK, fill=INK, anchor="mb")

    # max profit / loss (hand-authored where the tail is naked)
    maxp = s.get("maxp", f"{float(P.max()):+,.0f}")
    maxl = s.get("maxl", f"{float(P.min()):+,.0f}")
    d.text((px1, py0 - 4 * SCALE), f"max profit  {maxp}", font=F_ANNO, fill=GREEN, anchor="rb")
    d.text((px1, py0 + 15 * SCALE), f"max loss  {maxl}", font=F_ANNO, fill=RED, anchor="rb")

    # titles, axis labels, footer
    d.text((px0, 15 * SCALE), s["title"], font=F_TITLE, fill=INK, anchor="lm")
    d.text((px0, 37 * SCALE), s["sub"], font=F_SUB, fill=GREY, anchor="lm")
    d.text((px0, py1 + 26 * SCALE), "underlying price at expiry (BTC, USDT)", font=F_AXIS, fill=INK, anchor="lt")
    d.text(((px0 + px1) / 2, H - 20 * SCALE),
           "Illustrative shape — per 1 unit underlying, gross of fees. Strikes / premiums are representative, not live quotes.",
           font=F_FOOT, fill=GREY, anchor="mt")

    # rotated y-axis label
    lbl = Image.new("RGBA", (300 * SCALE, 20 * SCALE), (0, 0, 0, 0))
    ImageDraw.Draw(lbl).text((0, 0), "profit / loss at expiry (USDT)", font=F_AXIS, fill=INK)
    lbl = lbl.rotate(90, expand=True)
    img.paste(lbl, (8 * SCALE, py0 + 30 * SCALE), lbl)

    out = img.resize((W // SCALE, H // SCALE), Image.LANCZOS)
    out.save(os.path.join(OUTDIR, s["file"] + ".png"), "PNG")
    return s["file"]


if __name__ == "__main__":
    for s in STRATS:
        print("wrote", draw(s) + ".png")
    print(f"\n{len(STRATS)} payoff charts -> {OUTDIR}")
