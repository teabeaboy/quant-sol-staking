from __future__ import annotations

from dataclasses import dataclass

WSOL = "So11111111111111111111111111111111111111112"


@dataclass(frozen=True)
class Lst:
    key: str
    symbol: str
    mint: str
    withdrawal_fee_bps: float = 10.0


# Same five names as the research dashboard.
UNIVERSE: tuple[Lst, ...] = (
    Lst("jitosol", "jitoSOL", "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn"),
    Lst("msol", "mSOL", "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So"),
    Lst("bsol", "bSOL", "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1"),
    Lst("hsol", "hSOL", "he1iusmfkpAdwvxLNGV8Y1iSbj4rUy6yMhEA3fotn9A"),
    Lst("jupsol", "jupSOL", "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v"),
)
