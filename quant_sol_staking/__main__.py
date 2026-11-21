from __future__ import annotations

import json
import sys

from solders.keypair import Keypair

from quant_sol_staking.live import KEY_PATH, NEED_LAMPORTS, loop
from quant_sol_staking.quotes import snapshot_book
from quant_sol_staking.rpc import lamports_sol


def cmd_wallet() -> None:
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if KEY_PATH.exists():
        kp = Keypair.from_bytes(bytes(json.loads(KEY_PATH.read_text())))
    else:
        kp = Keypair()
        KEY_PATH.write_text(json.dumps(list(bytes(kp))))
        KEY_PATH.chmod(0o600)
    print(str(kp.pubkey()))
    print(f"key {KEY_PATH} (chmod 600, not in git)")
    print(f"deposit {NEED_LAMPORTS/1e9:.2f} SOL then the live loop will arm 1 SOL clips")


def cmd_scan() -> None:
    rows = snapshot_book(1_000_000_000)
    for r in rows:
        print(
            f"{r['symbol']:8} z={r.get('z', float('nan')):7.3f}  "
            f"gross={r.get('gross_bps', 0):7.1f}bps  edge={r.get('edge_bps', 0):7.1f}bps  "
            f"redeem={r['redeem_sol']:.6f} mkt={r['market_sol']:.6f}"
        )


def cmd_live() -> None:
    loop()


def cmd_status() -> None:
    kp = Keypair.from_bytes(bytes(json.loads(KEY_PATH.read_text())))
    pk = str(kp.pubkey())
    sol = lamports_sol(pk)
    print(f"wallet {pk}")
    print(f"sol    {sol/1e9:.9f}")
    print(f"need   {NEED_LAMPORTS/1e9:.2f} to arm")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "live"
    if cmd == "wallet":
        cmd_wallet()
    elif cmd == "scan":
        cmd_scan()
    elif cmd == "status":
        cmd_status()
    elif cmd == "live":
        cmd_live()
    else:
        raise SystemExit("usage: python -m quant_sol_staking [wallet|scan|status|live]")


if __name__ == "__main__":
    main()
