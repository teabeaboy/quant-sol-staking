"""Walk-forward OU z-score on X = log(redeem / market). Same thresholds as the paper book."""

from __future__ import annotations

import numpy as np
import pandas as pd

Z_ENTER = 2.0
Z_EXIT = 0.5
Z_STOP = 3.5
HALF_LIFE_STOP_MULT = 3.0
ROLL_WINDOW = 60
MIN_FIT_OBS = 40


def spread_x(redeem, market) -> np.ndarray:
    r = np.asarray(redeem, dtype=float)
    m = np.asarray(market, dtype=float)
    return np.log(np.maximum(r, 1e-12) / np.maximum(m, 1e-12))


def fit_ou_ar1(x: np.ndarray) -> tuple[bool, float, float, float]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < MIN_FIT_OBS:
        return False, 0.0, 1.0, 999.0
    y = x[1:]
    xx = x[:-1]
    n = len(y)
    sx, sy = xx.sum(), y.sum()
    sxx, sxy = (xx * xx).sum(), (xx * y).sum()
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-18:
        return False, 0.0, 1.0, 999.0
    b = (n * sxy - sx * sy) / denom
    a = (sy - b * sx) / n
    if not (0.0 < b < 0.999):
        return False, 0.0, 1.0, 999.0
    resid = y - (a + b * xx)
    sig_e = float(np.std(resid, ddof=2)) if n > 2 else float(np.std(resid))
    kappa = float(-np.log(b))
    theta = float(a / (1.0 - b))
    sigma_eq = float(sig_e / np.sqrt(max(1.0 - b * b, 1e-12)))
    half_life = float(np.log(2.0) / kappa) if kappa > 1e-12 else 999.0
    return True, theta, max(sigma_eq, 1e-10), half_life


def last_signal(panel: pd.DataFrame) -> dict:
    df = panel.sort_values("date").reset_index(drop=True).copy()
    x = spread_x(df["redeem_sol"], df["market_sol"])
    i = len(df) - 1
    start = max(0, i - ROLL_WINDOW)
    hist = x[start:i]
    ok, theta, sigma_eq, hl = fit_ou_ar1(hist)
    z = float((x[i] - theta) / sigma_eq) if ok else float("nan")
    redeem = float(df["redeem_sol"].iloc[-1])
    market = float(df["market_sol"].iloc[-1])
    gross_bps = (redeem / market - 1.0) * 10_000.0 if market > 0 else -1e9
    return {
        "ok": ok and np.isfinite(z),
        "z": z,
        "theta": theta,
        "sigma_eq": sigma_eq,
        "half_life_days": hl,
        "redeem_sol": redeem,
        "market_sol": market,
        "gross_bps": gross_bps,
        "date": str(df["date"].iloc[-1]),
    }
