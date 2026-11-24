"""
Deterministic .cbotset preset generator & C# parameter schema validator.

Generates all 4 verified cTrader presets from `build_production_presets()` and
asserts that every JSON parameter key maps 1:1 to a `[Parameter(...)]` property
in `cbot/src/StockShieldLowDdBot.cs`.
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import DEFAULT_STOCKS
from research_optimize import build_production_presets
from portfolio_backtester import PortfolioConfig


def _b(v: bool) -> str:
    return "True" if v else "False"


def config_to_cbotset(tag: str, cfg: PortfolioConfig, single_symbol: bool, chart_symbol: str) -> dict:
    return {
        "Chart": {
            "Symbol": chart_symbol,
            "Period": "d1",
        },
        "Parameters": {
            "PortfolioTag": tag,
            "SingleSymbolMode": _b(single_symbol),
            "SymbolsCsv": ",".join(DEFAULT_STOCKS),
            "PrimaryBenchmark": "QQQ",
            "SecondaryBenchmark": "SPY",
            "AutoAliasTickers": "True",
            "UseMacroGate": _b(cfg.regime.use_macro_gate),
            "VolCautionPct": f"{cfg.regime.vol_caution_pct:.1f}",
            "VolCrashPct": f"{cfg.regime.vol_crash_pct:.1f}",
            "YellowTrendMult": f"{cfg.regime.yellow_trend_mult:.2f}",
            "YellowMrMult": f"{cfg.regime.yellow_mr_mult:.2f}",
            "UseVolTargeting": _b(cfg.use_vol_targeting),
            "TargetBenchmarkVolPct": f"{cfg.target_benchmark_vol_pct:.1f}",
            "MinVolScale": f"{cfg.min_vol_scale:.2f}",
            "EnableTrend": _b(cfg.enable_trend),
            "TrendTopK": str(cfg.trend_top_k),
            "TrendRiskPct": f"{cfg.trend_risk_pct:.2f}",
            "TrendMinRsScore": f"{cfg.trend_min_rs_score:.2f}",
            "TrendSlAtrMult": f"{cfg.trend_sl_atr:.1f}",
            "TrendTrailAtrMult": f"{cfg.trend_trail_atr:.1f}",
            "TrendBeR": f"{cfg.trend_be_r:.1f}",
            "TrendFastExitEma50": _b(cfg.trend_fast_exit_ema50),
            "EnableIbs": _b(cfg.enable_ibs),
            "IbsTopK": str(cfg.ibs_top_k),
            "IbsRiskPct": f"{cfg.ibs_risk_pct:.2f}",
            "IbsThreshold": f"{cfg.ibs_thresh:.2f}",
            "IbsRequireAboveEma50": _b(cfg.ibs_require_above_ema50),
            "IbsSlAtrMult": f"{cfg.ibs_sl_atr:.1f}",
            "IbsMaxHoldDays": str(cfg.ibs_max_hold_days),
            "EnableConnors": _b(cfg.enable_connors),
            "ConnorsRiskPct": f"{cfg.connors_risk_pct:.2f}",
            "ConnorsRsiThresh": f"{cfg.connors_rsi_thresh:.1f}",
            "ConnorsUseSma8": _b(cfg.connors_use_sma8),
            "ConnorsSlAtrMult": f"{cfg.connors_sl_atr:.1f}",
            "ConnorsMaxHoldDays": str(cfg.connors_max_hold_days),
            "MaxConcurrentPositions": str(cfg.max_concurrent_positions),
            "MaxPositionsPerStock": str(cfg.max_positions_per_stock),
            "MaxClusterPositions": str(cfg.max_cluster_positions),
            "MaxSingleStockNotionalPct": f"{cfg.max_single_stock_notional_pct:.1f}",
            "StockVolRefPct": f"{cfg.stock_vol_ref_pct:.1f}",
            "MaxPortfolioLeverage": f"{cfg.max_portfolio_leverage:.2f}",
            "MaxDropAtr": f"{cfg.max_drop_atr:.1f}",
            "HalfRiskDdPct": f"{cfg.half_risk_dd_pct:.1f}",
            "QuarterRiskDdPct": f"{cfg.quarter_risk_dd_pct:.1f}",
            "MaxDailyLossPct": f"{cfg.max_daily_loss_pct:.1f}",
            "MaxTotalDrawdownPct": f"{cfg.max_total_dd_pct:.1f}",
            "FlattenOnDdBreach": _b(cfg.flatten_on_dd_breach),
            "KillCooldownDays": str(cfg.kill_cooldown_days),
            "DailyResetUtcOffsetHours": "0",
            "PersistDdState": "True",
            "EnableHud": "True",
            "VerboseLogs": "True",
            "EnableTrendHoldCore": _b(cfg.enable_trend_hold_core),
            "TrendHoldExitEmaPeriod": str(cfg.trend_hold_exit_ema_period),
            "TrendHoldRebalDays": str(cfg.trend_hold_rebal_days),
            "TrendHoldUseQqq200Gate": _b(cfg.trend_hold_use_qqq200_gate),
        },
    }


def extract_cs_parameter_names(cs_path: str) -> set[str]:
    with open(cs_path, "r", encoding="utf-8") as f:
        src = f.read()
    pattern = re.compile(
        r"\[Parameter\([^\]]*\)\]\s*public\s+[A-Za-z0-9_<>]+\s+([A-Za-z0-9_]+)\s*\{\s*get;\s*set;\s*\}",
        re.MULTILINE,
    )
    return set(pattern.findall(src))


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cs_path = os.path.join(root, "cbot", "src", "StockShieldLowDdBot.cs")
    presets_dir = os.path.join(root, "cbot", "presets")
    os.makedirs(presets_dir, exist_ok=True)

    cs_params = extract_cs_parameter_names(cs_path)
    if not cs_params:
        raise RuntimeError(f"No [Parameter] properties found in {cs_path}")

    presets = build_production_presets()
    chart_map = {
        "SS_P1_CFD_ULTRA_SAFE_Under6DD": ("SS_P1_ULTRA", False, "US TECH 100"),
        "SS_P2_CFD_BALANCED_Under8DD": ("SS_P2_CFD", False, "US TECH 100"),
        "SS_P3_CASH_1X_Under8DD": ("SS_P3_CASH", False, "US TECH 100"),
        "SS_P4_SINGLE_STOCK_Fallback": ("SS_P4_SINGLE", True, "AAPL"),
        "SS_P5_GROWTH_15DD_CFD": ("SS_P5_GRW_CFD", False, "US TECH 100"),
        "SS_P6_GROWTH_15DD_Cash": ("SS_P6_GRW_CSH", False, "US TECH 100"),
        "SS_P7_TRENDHOLD_CORE_CFD": ("SS_P7_TH_CFD", False, "US TECH 100"),
        "SS_P8_TRENDHOLD_CORE_Cash": ("SS_P8_TH_CSH", False, "US TECH 100"),
    }

    for name, cfg in presets.items():
        tag, single_mode, chart_sym = chart_map[name]
        payload = config_to_cbotset(tag, cfg, single_mode, chart_sym)
        preset_keys = set(payload["Parameters"].keys())

        missing_in_cs = preset_keys - cs_params
        missing_in_preset = cs_params - preset_keys
        if missing_in_cs or missing_in_preset:
            raise AssertionError(
                f"Schema mismatch for {name}: unknown={missing_in_cs}, missing={missing_in_preset}"
            )

        out_path = os.path.join(presets_dir, f"{name}.cbotset")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
        print(f"Generated & verified {out_path} ({len(preset_keys)} parameters matched 1:1)")


if __name__ == "__main__":
    main()
