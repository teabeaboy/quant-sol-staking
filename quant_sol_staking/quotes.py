from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

from quant_sol_staking.jupiter import impact_bps, market_sol_per_lst
from quant_sol_staking.universe import Lst, UNIVERSE

SANCTUM = "https://extra-api.sanctum.so/v1/sol-value/current"
ROOT = Path(__file__).resolve().parents[1]
PANELS = ROOT / "data" / "processed"


def sanctum_redeem() -> dict[str, float]:
    params = [("lst", s.symbol) for s in UNIVERSE]
    with httpx.Client(timeout=20.0) as c:
        r = c.get(SANCTUM, params=params)
        r.raise_for_status()
        d = r.json()
    out = {}
    for s in UNIVERSE:
        lam = int((d.get("solValues") or {}).get(s.symbol) or 0)
        if lam:
            out[s.key] = lam / 1e9
    return out


def load_panel(key: str) -> pd.DataFrame:
    path = PANELS / f"panel_{key}.csv"
    df = pd.read_csv(path, parse_dates=["date"])
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df.sort_values("date")


def append_live_row(spec: Lst, redeem: float, market: float) -> pd.DataFrame:
    df = load_panel(spec.key)
    today = pd.Timestamp(datetime.now(timezone.utc).date(), tz="UTC")
    row = {
        "lst": spec.key,
        "date": today,
        "redeem_sol": redeem,
        "market_sol": market,
        "lst_symbol": spec.symbol,
    }
    df = df[df["date"].dt.normalize() != today]
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    return df


def snapshot_book(sol_lamports: int) -> list[dict]:
    redeem = sanctum_redeem()
    rows = []
    for spec in UNIVERSE:
        if spec.key not in redeem:
            continue
        market, q = market_sol_per_lst(spec.mint, sol_lamports)
        panel = append_live_row(spec, redeem[spec.key], market)
        from quant_sol_staking.model import last_signal

        sig = last_signal(panel)
        cost_bps = max(impact_bps(q), 5.0) * 2.0  # round-trip Jupiter
        unstake_bps = max(impact_bps(q), 5.0) + spec.withdrawal_fee_bps
        path_bps = min(cost_bps, unstake_bps)
        sig.update(
            {
                "key": spec.key,
                "symbol": spec.symbol,
                "mint": spec.mint,
                "path_bps": path_bps,
                "edge_bps": sig["gross_bps"] - path_bps,
                "impact_bps": impact_bps(q),
            }
        )
        rows.append(sig)
    return rows
