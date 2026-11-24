"""
Multi-Universe Out-of-Sample & Out-of-Universe Validation across ALL 3 Tiers:
  - Tier 1 (Ultra-Low DD <6-8%):    SS_P1, SS_P2, SS_P3
  - Tier 2 (Balanced Growth ~15%):  SS_P5 (CFD), SS_P6 (Cash)
  - Tier 3 (Trend-Hold Core ~25%):  SS_P7 (CFD), SS_P8 (Cash)

Tests across 3 distinct stock universes + Buy & Hold Equal-Weight benchmarks:
  A. 12 Tech/Growth Leaders (Default Universe)
  B. 10 Unseen Multi-Sector Blue-Chips (LLY, JPM, V, MA, WMT, HD, CAT, XOM, UNH, PG)
  C. 8 Unseen Software & Semi Equipment (CRM, ADBE, INTU, PANW, LRCX, KLAC, AMAT, QCOM)
"""

from __future__ import annotations

import copy
import math
import os
import sys
from typing import List
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import BENCHMARK_SYMBOLS, DEFAULT_STOCKS, load_aligned_universe
from engines import build_stock_cache, compute_macro_regime
from portfolio_backtester import run_portfolio_backtest
from research_optimize import build_production_presets


UNIVERSES = {
    "A_Tech_Leaders_12": DEFAULT_STOCKS,
    "B_MultiSector_Unseen_10": ["LLY", "JPM", "V", "MA", "WMT", "HD", "CAT", "XOM", "UNH", "PG"],
    "C_Software_Semis_Unseen_8": ["CRM", "ADBE", "INTU", "PANW", "LRCX", "KLAC", "AMAT", "QCOM"],
}


def buy_and_hold_ew(dates, wd, stocks, start_i: int, swap_pct: float = 0.0):
    syms = list(stocks.keys())
    sh = {s: (25000.0 / len(syms)) / stocks[s].open[start_i] for s in syms}
    cash = 0.0
    eqs, lows, rets = [], [], []
    prev_eq = 25000.0
    dswap = (swap_pct / 100.0) / 365.0
    for t in range(start_i, len(dates)):
        sm = 3.0 if wd[t] == 2 else 1.0
        v_low = sum(sh[s] * stocks[s].low[t] for s in syms) + cash
        v_c = sum(sh[s] * stocks[s].close[t] for s in syms)
        if dswap > 0:
            cash -= v_c * dswap * sm
        eq = v_c + cash
        eqs.append(eq)
        lows.append(min(eq, v_low))
        rets.append((eq - prev_eq) / prev_eq)
        prev_eq = eq
    ea, la, ra = np.array(eqs), np.array(lows), np.array(rets)
    rp = np.maximum.accumulate(np.maximum(ea, 25000.0))
    mdd = float(np.max((rp - la) / rp * 100.0))
    wday = float(-np.min(ra) * 100.0)
    cagr = ((ea[-1] / 25000.0) ** (252.0 / len(ea)) - 1.0) * 100.0
    cal = cagr / mdd if mdd > 0 else 0.0
    shp = (np.mean(ra) / np.std(ra, ddof=1)) * math.sqrt(252.0)
    return ea[-1], (ea[-1] / 25000.0 - 1.0) * 100.0, cagr, mdd, wday, cal, shp


def run_universe(u_name: str, tickers: List[str]) -> None:
    print("\n" + "=" * 145)
    print(f"UNIVERSE: {u_name} ({len(tickers)} stocks: {', '.join(tickers)})")
    print("=" * 145)
    dates, wd, stocks, bench = load_aligned_universe(tickers, BENCHMARK_SYMBOLS)
    caches = {s: build_stock_cache(d) for s, d in stocks.items()}
    n = len(dates)
    is_i = 205
    oos_i = next(i for i, d in enumerate(dates) if str(d) >= "2022-01-01")
    print(f"Aligned window: {dates[is_i]} -> {dates[-1]} ({n - is_i} bars | OOS from {dates[oos_i]})")

    bh_cash = buy_and_hold_ew(dates, wd, stocks, is_i, 0.0)
    bh_cfd = buy_and_hold_ew(dates, wd, stocks, is_i, 7.0)
    print(f"{'Buy & Hold EW (Cash)':<30} | Eq ${bh_cash[0]:>9,.0f} | Ret {bh_cash[1]:>6.1f}% | CAGR {bh_cash[2]:>5.2f}% | MaxDD {bh_cash[3]:>5.2f}% | WDay {bh_cash[4]:>5.2f}% | Cal {bh_cash[5]:>4.2f} | Shp {bh_cash[6]:>4.2f}")
    print(f"{'Buy & Hold EW (CFD 7%)':<30} | Eq ${bh_cfd[0]:>9,.0f} | Ret {bh_cfd[1]:>6.1f}% | CAGR {bh_cfd[2]:>5.2f}% | MaxDD {bh_cfd[3]:>5.2f}% | WDay {bh_cfd[4]:>5.2f}% | Cal {bh_cfd[5]:>4.2f} | Shp {bh_cfd[6]:>4.2f}")
    print("-" * 145)

    presets = build_production_presets()
    reg = compute_macro_regime(bench, presets["SS_P2_CFD_BALANCED_Under8DD"].regime)

    for pname in (
        "SS_P1_CFD_ULTRA_SAFE_Under6DD",
        "SS_P2_CFD_BALANCED_Under8DD",
        "SS_P3_CASH_1X_Under8DD",
        "SS_P5_GROWTH_15DD_CFD",
        "SS_P6_GROWTH_15DD_Cash",
        "SS_P7_TRENDHOLD_CORE_CFD",
        "SS_P8_TRENDHOLD_CORE_Cash",
    ):
        cfg = copy.deepcopy(presets[pname])
        rf = run_portfolio_backtest(dates, wd, stocks, bench, cfg, is_i, n, caches, reg)
        ro = run_portfolio_backtest(dates, wd, stocks, bench, cfg, oos_i, n, caches, reg)
        print(
            f"{pname:<30} | Eq ${rf.final_equity:>9,.0f} | Ret {rf.total_return_pct:>6.1f}% "
            f"| CAGR {rf.cagr_pct:>5.2f}% | MaxDD {rf.max_equity_dd_pct:>5.2f}% "
            f"| WDay {rf.worst_day_dd_pct:>4.2f}% | Cal {rf.calmar:>4.2f} | Shp {rf.sharpe:>4.2f} "
            f"| PF {rf.profit_factor:>4.2f} | OOS {ro.cagr_pct:>5.2f}% (DD {ro.max_equity_dd_pct:>5.2f}%)"
        )


def main() -> None:
    for u_name, tickers in UNIVERSES.items():
        run_universe(u_name, tickers)


if __name__ == "__main__":
    main()
