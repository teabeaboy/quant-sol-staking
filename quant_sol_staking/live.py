"""
Live loop: at most one LST at a time, 1 SOL clip, 0.1 SOL fee buffer.

Enter: highest z among z≥2 and edge_bps>0.
Exit: sell on Jupiter when z≤0.5 or z≥3.5 or hold > 3·half-life.
Does not open a second name while any LST balance is outstanding.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from solders.keypair import Keypair

from quant_sol_staking.jupiter import buy_lst, sell_lst
from quant_sol_staking.model import HALF_LIFE_STOP_MULT, Z_ENTER, Z_EXIT, Z_STOP
from quant_sol_staking.quotes import snapshot_book
from quant_sol_staking.rpc import lamports_sol, token_amount
from quant_sol_staking.universe import UNIVERSE

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = Path(os.environ.get("QSS_STATE", ROOT / "data" / "live" / "state.json"))
LOG_PATH = Path(os.environ.get("QSS_LOG", ROOT / "logs" / "live.log"))
KEY_PATH = Path(
    os.environ.get("QSS_KEY", os.path.expanduser("~/.config/quant-sol-staking/id.json"))
)

POSITION_LAMPORTS = int(float(os.environ.get("QSS_POSITION_SOL", "1")) * 1e9)
RESERVE_LAMPORTS = int(float(os.environ.get("QSS_RESERVE_SOL", "0.09")) * 1e9)
NEED_LAMPORTS = POSITION_LAMPORTS + RESERVE_LAMPORTS
POLL_SEC = int(os.environ.get("QSS_POLL_SEC", "60"))
MAX_POSITIONS = 1


def log(msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")


def load_kp() -> Keypair:
    raw = json.loads(KEY_PATH.read_text())
    return Keypair.from_bytes(bytes(raw))


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"position": None}


def save_state(st: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(st, indent=2))


def detect_held(owner: str) -> tuple | None:
    for spec in UNIVERSE:
        amt = token_amount(owner, spec.mint)
        if amt > 10_000:  # dust
            return spec, amt
    return None


def pick_entry(rows: list[dict]) -> dict | None:
    cands = [
        r
        for r in rows
        if r.get("ok")
        and r.get("z", 0) >= Z_ENTER
        and r.get("edge_bps", -1) > 0
    ]
    if not cands:
        return None
    return max(cands, key=lambda r: r["z"])


def should_exit(row: dict | None, pos: dict) -> str | None:
    if not row or not row.get("ok"):
        return None
    z = row["z"]
    if z <= Z_EXIT:
        return f"mean-revert z={z:.2f}≤{Z_EXIT}"
    if z >= Z_STOP:
        return f"stop z={z:.2f}≥{Z_STOP}"
    entered = datetime.fromisoformat(pos["entered_at"].replace("Z", "+00:00"))
    age_days = (datetime.now(timezone.utc) - entered).total_seconds() / 86400.0
    hl = float(pos.get("half_life_days") or 999)
    if age_days > max(hl * HALF_LIFE_STOP_MULT, 2.0):
        return f"time-stop age={age_days:.1f}d > {HALF_LIFE_STOP_MULT}·t½"
    return None


def loop() -> None:
    kp = load_kp()
    pk = str(kp.pubkey())
    log(f"live start wallet={pk} position={POSITION_LAMPORTS/1e9:.4f} SOL reserve={RESERVE_LAMPORTS/1e9:.4f} SOL max_pos={MAX_POSITIONS}")
    log(f"deposit {NEED_LAMPORTS/1e9:.2f} SOL to {pk} then the book will arm")

    while True:
        try:
            st = load_state()
            sol = lamports_sol(pk)
            held = detect_held(pk)
            rows = snapshot_book(POSITION_LAMPORTS)
            brief = " | ".join(
                f"{r['symbol']} z={r['z']:.2f} edge={r['edge_bps']:.1f}bps"
                if r.get("ok")
                else f"{r['symbol']} n/a"
                for r in rows
            )
            log(f"sol={sol/1e9:.4f} {brief}")

            if held:
                spec, amt = held
                row = next((r for r in rows if r["mint"] == spec.mint), None)
                pos = st.get("position") or {
                    "symbol": spec.symbol,
                    "mint": spec.mint,
                    "entered_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "half_life_days": (row or {}).get("half_life_days", 999),
                }
                st["position"] = pos
                save_state(st)
                why = should_exit(row, pos)
                if why:
                    log(f"EXIT {spec.symbol} amt={amt} {why}")
                    sig, _ = sell_lst(kp, spec.mint, amt)
                    log(f"sold {spec.symbol} sig={sig}")
                    st["position"] = None
                    st["last_exit"] = {
                        "symbol": spec.symbol,
                        "sig": sig,
                        "why": why,
                        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
                    save_state(st)
                else:
                    log(f"HOLD {spec.symbol} amt={amt} (max 1 position — skip other names)")
            else:
                st["position"] = None
                save_state(st)
                if sol < NEED_LAMPORTS:
                    log(
                        f"waiting for deposit: have {sol/1e9:.4f} SOL, need {NEED_LAMPORTS/1e9:.2f} SOL at {pk}"
                    )
                else:
                    pick = pick_entry(rows)
                    if pick is None:
                        log("flat — no z≥2 name with after-cost edge")
                    else:
                        clip = min(POSITION_LAMPORTS, sol - RESERVE_LAMPORTS)
                        log(
                            f"ENTER {pick['symbol']} z={pick['z']:.2f} edge={pick['edge_bps']:.1f}bps clip={clip/1e9:.4f} SOL"
                        )
                        sig, q = buy_lst(kp, pick["mint"], clip)
                        log(f"bought {pick['symbol']} sig={sig} out={q.get('outAmount')}")
                        st["position"] = {
                            "symbol": pick["symbol"],
                            "mint": pick["mint"],
                            "sig": sig,
                            "sol_in": clip,
                            "z": pick["z"],
                            "half_life_days": pick["half_life_days"],
                            "entered_at": datetime.now(timezone.utc).strftime(
                                "%Y-%m-%dT%H:%M:%SZ"
                            ),
                        }
                        save_state(st)
        except Exception as e:  # noqa: BLE001
            log(f"ERR {type(e).__name__}: {e}")
        time.sleep(POLL_SEC)


def main() -> None:
    loop()


if __name__ == "__main__":
    main()
