"""
After the 1.1 SOL deposit: quote a 0.1 SOL clip on every LST (sim only).
If those quotes work, buy 0.00001 SOL of each name, wait 10s, sell back.
Does not open the 1 SOL book position.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from solders.keypair import Keypair

from quant_sol_staking.jupiter import buy_lst, quote, sell_lst
from quant_sol_staking.live import KEY_PATH
from quant_sol_staking.rpc import lamports_sol, rpc, token_amount
from quant_sol_staking.universe import UNIVERSE, WSOL

SIM_LAMPORTS = 100_000_000  # 0.1 SOL quote
PROBE_LAMPORTS = 10_000  # 0.00001 SOL
WAIT_SEC = 10
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "live" / "sim_probe.json"


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}", flush=True)


def wait_sig(sig: str, timeout: int = 90) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = rpc("getSignatureStatuses", [[sig], {"searchTransactionHistory": True}])
        v = (st.get("value") or [None])[0]
        if v:
            if v.get("err"):
                raise RuntimeError(f"{sig} err={v['err']}")
            if v.get("confirmationStatus") in ("confirmed", "finalized"):
                return
        time.sleep(1)
    raise TimeoutError(sig)


def sim_quotes() -> list[dict]:
    rows = []
    ok = True
    for spec in UNIVERSE:
        try:
            q = quote(WSOL, spec.mint, SIM_LAMPORTS)
            out = int(q["outAmount"])
            impact = float(q.get("priceImpactPct") or 0.0)
            row = {
                "symbol": spec.symbol,
                "mint": spec.mint,
                "ok": out > 0,
                "out_lst": out,
                "impact_pct": impact,
                "err": None,
            }
            log(
                f"SIM 0.1 SOL → {spec.symbol}  out={out}  impact={impact:.6f}  "
                f"{'ok' if out > 0 else 'FAIL'}"
            )
        except Exception as e:  # noqa: BLE001
            ok = False
            row = {
                "symbol": spec.symbol,
                "mint": spec.mint,
                "ok": False,
                "out_lst": 0,
                "impact_pct": None,
                "err": f"{type(e).__name__}: {e}",
            }
            log(f"SIM 0.1 SOL → {spec.symbol}  FAIL {row['err']}")
        if not row["ok"]:
            ok = False
        rows.append(row)
    return rows, ok


def roundtrip(kp: Keypair) -> list[dict]:
    owner = str(kp.pubkey())
    results = []
    for spec in UNIVERSE:
        rec = {"symbol": spec.symbol, "mint": spec.mint}
        try:
            log(f"PROBE BUY {spec.symbol}  {PROBE_LAMPORTS} lamports")
            sig_in, q_in = buy_lst(kp, spec.mint, PROBE_LAMPORTS)
            wait_sig(sig_in)
            rec["buy_sig"] = sig_in
            rec["buy_out"] = int(q_in.get("outAmount") or 0)
            log(f"  bought sig={sig_in}")
            time.sleep(WAIT_SEC)
            amt = token_amount(owner, spec.mint)
            rec["held"] = amt
            if amt <= 0:
                rec["ok"] = False
                rec["err"] = "no LST after buy"
                log(f"  no ATA/amount after buy")
                results.append(rec)
                continue
            log(f"PROBE SELL {spec.symbol}  amt={amt}")
            sig_out, q_out = sell_lst(kp, spec.mint, amt)
            wait_sig(sig_out)
            rec["sell_sig"] = sig_out
            rec["sell_out"] = int(q_out.get("outAmount") or 0)
            rec["ok"] = True
            rec["err"] = None
            log(f"  sold sig={sig_out}")
        except Exception as e:  # noqa: BLE001
            rec["ok"] = False
            rec["err"] = f"{type(e).__name__}: {e}"
            log(f"  FAIL {rec['err']}")
        results.append(rec)
    return results


def main() -> None:
    kp = Keypair.from_bytes(bytes(json.loads(KEY_PATH.read_text())))
    pk = str(kp.pubkey())
    sol = lamports_sol(pk)
    log(f"wallet {pk}  sol={sol/1e9:.9f}")
    if sol < 1_100_000_000:
        raise SystemExit("need 1.1 SOL on the wallet before the probe")

    sim, sim_ok = sim_quotes()
    payload = {
        "wallet": pk,
        "sol_before": sol,
        "sim_0_1_sol": sim,
        "sim_ok": sim_ok,
        "probe": None,
        "sol_after": None,
    }
    if not sim_ok:
        log("sim quotes failed — skip live 0.00001 probe")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2))
        sys.exit(1)

    log("sim quotes ok — tiny round-trips on all 5 names")
    payload["probe"] = roundtrip(kp)
    payload["sol_after"] = lamports_sol(pk)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    fails = [p for p in payload["probe"] if not p.get("ok")]
    log(f"done sol_after={payload['sol_after']/1e9:.9f}  fails={len(fails)}")
    if fails:
        sys.exit(2)


if __name__ == "__main__":
    main()
