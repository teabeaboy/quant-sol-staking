# quant-sol-staking

Live book of liquid Solana LSTs (jitoSOL, mSOL, bSOL, hSOL, jupSOL).

When an LST trades cheap vs its Sanctum redeem rate (OU z-score ≥ 2 and after-cost edge > 0), buy **1 SOL** of that name on Jupiter. Hold **at most one** position. Exit on Jupiter when z ≤ 0.5, z ≥ 3.5, or the hold exceeds 3× half-life.

Paper dashboard for the same rules lives under Thanatos `statsarb`. This repo is the live clip.

## Deposit

Send **1.1 SOL** to the bot wallet (1.0 clip + 0.1 fee buffer). The loop stays idle until that balance is there. It will never open a second name while an LST is held.

The wallet JSON is **not** in git. It lives at `~/.config/quant-sol-staking/id.json`.

```bash
python -m quant_sol_staking wallet   # print pubkey
python -m quant_sol_staking scan     # live z / edge
python -m quant_sol_staking status
python -m quant_sol_staking live
```

## Ops

User systemd: `quant-sol-staking.service` → `python -m quant_sol_staking live`.
