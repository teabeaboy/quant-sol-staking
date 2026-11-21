from __future__ import annotations

import os
from typing import Any

import httpx
from solders.pubkey import Pubkey

TOKEN_PROGRAM = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
ASSOC = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")

DEFAULT_RPC = os.environ.get("THANATOS_RPC_HTTP_URL") or os.environ.get(
    "RPC", "http://213.21.195.65:8898"
)


def rpc(method: str, params: list[Any], timeout: float = 30.0) -> Any:
    headers = {"Content-Type": "application/json"}
    tok = os.environ.get("THANATOS_RPC_X_TOKEN", "").strip()
    if tok:
        headers["x-token"] = tok
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    with httpx.Client(timeout=timeout) as c:
        r = c.post(DEFAULT_RPC, json=body, headers=headers)
        r.raise_for_status()
        j = r.json()
    if j.get("error"):
        raise RuntimeError(j["error"])
    return j["result"]


def lamports_sol(pk: str) -> int:
    return int(rpc("getBalance", [pk])["value"])


def ata(owner: str, mint: str) -> str:
    pk, _ = Pubkey.find_program_address(
        [
            bytes(Pubkey.from_string(owner)),
            bytes(TOKEN_PROGRAM),
            bytes(Pubkey.from_string(mint)),
        ],
        ASSOC,
    )
    return str(pk)


def token_amount(owner: str, mint: str) -> int:
    # Direct ATA getAccountInfo — no token secondary index on the local RPC.
    acc = rpc("getAccountInfo", [ata(owner, mint), {"encoding": "base64"}])
    if not acc or not acc.get("value"):
        return 0
    data_b64 = acc["value"]["data"][0]
    import base64

    raw = base64.b64decode(data_b64)
    if len(raw) < 72:
        return 0
    return int.from_bytes(raw[64:72], "little")


def send_b64_tx(b64: str) -> str:
    return rpc(
        "sendTransaction",
        [
            b64,
            {
                "encoding": "base64",
                "skipPreflight": False,
                "preflightCommitment": "confirmed",
                "maxRetries": 3,
            },
        ],
        timeout=60.0,
    )
