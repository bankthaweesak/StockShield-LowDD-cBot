"""
StockShield-LowDD-cBot Final Walk-Forward Verification & Preset Selection Suite (V3).

Verifies all 4 production presets across:
  - 10Y Full (2017-2026), In-Sample (2017-2021), Out-of-Sample (2022-2026 incl. 2022 bear)
  - Realistic cTrader US Stock CFD costs (10 bps RT + 7.0%/yr swap w/ 3x Wed)
  - 2x Cost Stress (20 bps RT + 10.0%/yr swap)
  - 1.0x Cash / Low-Swap Equities (0% swap)
  - Single-Stock Fallback across all 12 Tech/Growth leaders
Exports exact verified JSON metrics to results/research_summary.json.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from dataclasses import asdict
from typing import Dict
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import DEFAULT_STOCKS, BENCHMARK_SYMBOLS, load_aligned_universe
from engines import RegimeConfig, build_stock_cache, compute_macro_regime
from portfolio_backtester import BacktestResult, PortfolioConfig, run_portfolio_backtest


def fmt_res(label: str, r: BacktestResult) -> str:
    return (
        f"{label:<32} | Eq ${r.final_equity:>8,.0f} | Ret {r.total_return_pct:>5.1f}% "
        f"| CAGR {r.cagr_pct:>5.2f}% | MaxDD {r.max_equity_dd_pct:>4.2f}% "
        f"| WDay {r.worst_day_dd_pct:>4.2f}% | Cal {r.calmar:>4.2f} "
        f"| Shp {r.sharpe:>4.2f} | PF {r.profit_factor:>4.2f} "
        f"| WR {r.win_rate_pct:>4.1f}% | Hold {r.avg_hold_days:>4.1f}d "
        f"| Tr {len(r.trades):>4d} | Swp ${r.total_swap_paid:>5,.0f} | Kill {r.dd_kill_switches}/{r.daily_halts}"
    )


def summarize_dict(r: BacktestResult) -> dict:
    return {
        "start_date": r.start_date,
        "end_date": r.end_date,
        "final_equity": round(r.final_equity, 2),
        "total_return_pct": round(r.total_return_pct, 2),
        "cagr_pct": round(r.cagr_pct, 2),
        "max_equity_dd_pct": round(r.max_equity_dd_pct, 2),
        "max_close_dd_pct": round(r.max_close_dd_pct, 2),
        "worst_day_dd_pct": round(r.worst_day_dd_pct, 2),
        "calmar": round(r.calmar, 2),
        "sharpe": round(r.sharpe, 2),
        "sortino": round(r.sortino, 2),
        "profit_factor": round(r.profit_factor, 2),
        "win_rate_pct": round(r.win_rate_pct, 2),
        "avg_hold_days": round(r.avg_hold_days, 2),
        "trades": len(r.trades),
        "total_swap_paid": round(r.total_swap_paid, 2),
        "total_costs_paid": round(r.total_costs_paid, 2),
        "avg_leverage": round(r.avg_leverage, 3),
        "max_leverage_seen": round(r.max_leverage_seen, 3),
        "dd_kill_switches": r.dd_kill_switches,
        "daily_halts": r.daily_halts,
        "yearly_stats": {
            yr: {k: round(v, 2) for k, v in d.items()} for yr, d in r.yearly_stats.items()
        },
        "engine_stats": {
            eng: {k: round(v, 2) for k, v in d.items()} for eng, d in r.engine_stats.items()
        },
        "stock_stats": {
            sym: {k: round(v, 2) for k, v in d.items()} for sym, d in r.stock_stats.items()
        },
    }


def build_production_presets() -> Dict[str, PortfolioConfig]:
    """The 4 verified production presets matching cbot/presets/*.cbotset 1:1."""
    reg_cfg = RegimeConfig(
        use_macro_gate=True,
        vol_caution_pct=26.0,
        vol_crash_pct=36.0,
        yellow_trend_mult=0.40,
        yellow_mr_mult=0.50,
    )

    # P1: Ultra-Safe CFD (<5.0% Max Equity DD, <1.8% Worst Day, PF 1.85)
    p1 = PortfolioConfig(
        regime=copy.deepcopy(reg_cfg),
        enable_trend=True,
        trend_top_k=7,
        trend_risk_pct=0.50,
        trend_min_rs_score=0.20,
        trend_sl_atr=2.0,
        trend_trail_atr=3.2,
        trend_be_r=1.0,
        trend_fast_exit_ema50=True,
        enable_ibs=False,
        enable_connors=False,
        max_concurrent_positions=6,
        max_positions_per_stock=1,
        max_cluster_positions=2,
        max_single_stock_notional_pct=9.5,
        stock_vol_ref_pct=20.0,
        max_portfolio_leverage=0.45,
        use_vol_targeting=True,
        target_benchmark_vol_pct=16.0,
        min_vol_scale=0.35,
        half_risk_dd_pct=2.2,
        quarter_risk_dd_pct=4.0,
        max_daily_loss_pct=0.0,
        max_total_dd_pct=6.0,
        flatten_on_dd_breach=True,
        annual_swap_pct=7.0,
        triple_wednesday_swap=True,
    )

    # P2: Balanced CFD (<6.5% Max Equity DD, <2.0% Worst Day, Trend + IBS Sniper)
    p2 = PortfolioConfig(
        regime=copy.deepcopy(reg_cfg),
        enable_trend=True,
        trend_top_k=7,
        trend_risk_pct=0.65,
        trend_min_rs_score=0.20,
        trend_sl_atr=2.0,
        trend_trail_atr=3.2,
        trend_be_r=1.0,
        trend_fast_exit_ema50=True,
        enable_ibs=True,
        ibs_top_k=8,
        ibs_risk_pct=0.45,
        ibs_thresh=0.12,
        ibs_require_above_ema50=True,
        ibs_sl_atr=2.5,
        ibs_max_hold_days=5,
        enable_connors=False,
        max_concurrent_positions=6,
        max_positions_per_stock=1,
        max_cluster_positions=2,
        max_single_stock_notional_pct=10.5,
        stock_vol_ref_pct=20.0,
        max_portfolio_leverage=0.52,
        use_vol_targeting=True,
        target_benchmark_vol_pct=16.5,
        min_vol_scale=0.35,
        half_risk_dd_pct=2.2,
        quarter_risk_dd_pct=4.0,
        max_daily_loss_pct=0.0,
        max_total_dd_pct=7.5,
        flatten_on_dd_breach=True,
        annual_swap_pct=7.0,
        triple_wednesday_swap=True,
    )

    # P3: Cash 1x / Low-Swap Equities (<7.0% Max Equity DD, PF > 2.0, Calmar ~1.4+)
    p3 = copy.deepcopy(p2)
    p3.trend_risk_pct = 0.80
    p3.ibs_risk_pct = 0.55
    p3.max_single_stock_notional_pct = 12.5
    p3.stock_vol_ref_pct = 22.0
    p3.max_portfolio_leverage = 0.65
    p3.target_benchmark_vol_pct = 18.0
    p3.annual_swap_pct = 0.0
    p3.triple_wednesday_swap = False

    # P4: Single-Stock Chart Fallback (optimized for 1 attached stock chart)
    p4 = copy.deepcopy(p2)
    p4.trend_top_k = 1
    p4.ibs_top_k = 1
    p4.trend_risk_pct = 0.65
    p4.ibs_risk_pct = 0.50
    p4.max_concurrent_positions = 1
    p4.max_positions_per_stock = 1
    p4.max_cluster_positions = 1
    p4.max_single_stock_notional_pct = 25.0
    p4.stock_vol_ref_pct = 24.0
    p4.max_portfolio_leverage = 0.25

    return {
        "SS_P1_CFD_ULTRA_SAFE_Under6DD": p1,
        "SS_P2_CFD_BALANCED_Under8DD": p2,
        "SS_P3_CASH_1X_Under8DD": p3,
        "SS_P4_SINGLE_STOCK_Fallback": p4,
    }


def main() -> None:
    dates, weekdays, stocks, benchmarks = load_aligned_universe(DEFAULT_STOCKS, BENCHMARK_SYMBOLS)
    n_total = len(dates)
    caches = {sym: build_stock_cache(d) for sym, d in stocks.items()}
    is_start_idx = 205
    oos_start_idx = next(i for i, d in enumerate(dates) if str(d) >= "2022-01-01")

    presets = build_production_presets()
    reg = compute_macro_regime(benchmarks, presets["SS_P2_CFD_BALANCED_Under8DD"].regime)

    print(f"StockShield-LowDD-cBot Verification | {dates[is_start_idx]} -> {dates[-1]} ({n_total - is_start_idx} bars)")
    print(f"IS: {dates[is_start_idx]} -> {dates[oos_start_idx - 1]} | OOS: {dates[oos_start_idx]} -> {dates[-1]}")
    print("=" * 155)

    summary_presets: Dict[str, dict] = {}
    for name in ("SS_P1_CFD_ULTRA_SAFE_Under6DD", "SS_P2_CFD_BALANCED_Under8DD", "SS_P3_CASH_1X_Under8DD"):
        cfg = presets[name]
        r_full = run_portfolio_backtest(dates, weekdays, stocks, benchmarks, cfg, is_start_idx, n_total, caches, reg)
        r_is = run_portfolio_backtest(dates, weekdays, stocks, benchmarks, cfg, is_start_idx, oos_start_idx, caches, reg)
        r_oos = run_portfolio_backtest(dates, weekdays, stocks, benchmarks, cfg, oos_start_idx, n_total, caches, reg)

        # 2x cost stress test
        stress_cfg = copy.deepcopy(cfg)
        stress_cfg.entry_cost_bps = 10.0
        stress_cfg.exit_cost_bps = 10.0
        stress_cfg.annual_swap_pct = 10.0 if cfg.annual_swap_pct > 0 else 0.0
        r_stress = run_portfolio_backtest(dates, weekdays, stocks, benchmarks, stress_cfg, is_start_idx, n_total, caches, reg)

        print(fmt_res(f"{name} [FULL]", r_full))
        print(fmt_res(f"{name} [IS]", r_is))
        print(fmt_res(f"{name} [OOS]", r_oos))
        print(fmt_res(f"{name} [2X STRESS]", r_stress))
        print("-" * 155)

        summary_presets[name] = {
            "config": asdict(cfg),
            "full": summarize_dict(r_full),
            "is": summarize_dict(r_is),
            "oos": summarize_dict(r_oos),
            "stress_2x": summarize_dict(r_stress),
        }

    # Yearly breakdown for P2 Balanced CFD
    print("\nYEARLY BREAKDOWN (SS_P2_CFD_BALANCED_Under8DD):")
    for yr, st in summary_presets["SS_P2_CFD_BALANCED_Under8DD"]["full"]["yearly_stats"].items():
        print(f"  {yr}: Ret {st['return_pct']:>6.2f}% | MaxDD {st['max_dd_pct']:>5.2f}% | WorstDay {st['worst_day_pct']:>4.2f}% | Trades {int(st['trades']):>3d}")

    # Single-stock fallback audit
    print("\nSINGLE-STOCK FALLBACK AUDIT (SS_P4_SINGLE_STOCK_Fallback, CFD Costs):")
    p4_cfg = presets["SS_P4_SINGLE_STOCK_Fallback"]
    ss_map: Dict[str, dict] = {}
    for sym in DEFAULT_STOCKS:
        r_ss = run_portfolio_backtest(dates, weekdays, {sym: stocks[sym]}, benchmarks, p4_cfg, is_start_idx, n_total, {sym: caches[sym]}, reg)
        print(fmt_res(f"SingleStock [{sym}]", r_ss))
        ss_map[sym] = summarize_dict(r_ss)
    summary_presets["SS_P4_SINGLE_STOCK_Fallback"] = {
        "config": asdict(p4_cfg),
        "per_stock": ss_map,
    }

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "research_summary.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "universe": DEFAULT_STOCKS,
                "benchmarks": BENCHMARK_SYMBOLS,
                "date_range": [str(dates[is_start_idx]), str(dates[-1])],
                "is_range": [str(dates[is_start_idx]), str(dates[oos_start_idx - 1])],
                "oos_range": [str(dates[oos_start_idx]), str(dates[-1])],
                "presets": summary_presets,
            },
            f,
            indent=2,
        )
    print(f"\nSaved verified research summary to {out_path}")


if __name__ == "__main__":
    main()
