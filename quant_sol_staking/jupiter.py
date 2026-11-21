from __future__ import annotations

import base64
import os

import httpx
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

from quant_sol_staking.rpc import send_b64_tx
from quant_sol_staking.universe import WSOL

QUOTE = os.environ.get("JUPITER_QUOTE", "https://lite-api.jup.ag/swap/v1/quote")
SWAP = os.environ.get("JUPITER_SWAP", "https://lite-api.jup.ag/swap/v1/swap")
SLIPPAGE_BPS = int(os.environ.get("SLIPPAGE_BPS", "80"))


def quote(input_mint: str, output_mint: str, amount: int) -> dict:
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": str(SLIPPAGE_BPS),
        "swapMode": "ExactIn",
    }
    with httpx.Client(timeout=25.0) as c:
        r = c.get(QUOTE, params=params)
        r.raise_for_status()
        return r.json()


def market_sol_per_lst(mint: str, sol_lamports: int = 1_000_000_000) -> tuple[float, dict]:
    q = quote(WSOL, mint, sol_lamports)
    out = int(q["outAmount"])
    if out <= 0:
        raise RuntimeError("jupiter outAmount=0")
    return sol_lamports / out, q


def impact_bps(q: dict) -> float:
    impact = float(q.get("priceImpactPct") or 0.0)
    return abs(impact) * 10_000.0


def swap_and_send(kp: Keypair, q: dict) -> str:
    body = {
        "quoteResponse": q,
        "userPublicKey": str(kp.pubkey()),
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": "auto",
    }
    with httpx.Client(timeout=40.0) as c:
        r = c.post(SWAP, json=body)
        r.raise_for_status()
        d = r.json()
    raw = base64.b64decode(d["swapTransaction"])
    tx = VersionedTransaction.from_bytes(raw)
    signed = VersionedTransaction(tx.message, [kp])
    b64 = base64.b64encode(bytes(signed)).decode()
    return send_b64_tx(b64)


def buy_lst(kp: Keypair, mint: str, sol_lamports: int) -> tuple[str, dict]:
    q = quote(WSOL, mint, sol_lamports)
    sig = swap_and_send(kp, q)
    return sig, q


def sell_lst(kp: Keypair, mint: str, lst_lamports: int) -> tuple[str, dict]:
    q = quote(mint, WSOL, lst_lamports)
    sig = swap_and_send(kp, q)
    return sig, q
