"""
StockShield Low-DD Strategy Engines & Macro Regime Gate (Production Parity V3).

All signal evaluations strictly inspect prior closed bar `s = t - 1` (and
earlier) to execute at bar `t` open — guaranteeing zero lookahead bias and
1:1 mathematical parity with `StockShieldLowDdBot.cs`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict
import numpy as np

from data_loader import OHLCVData
import indicators as ind


REGIME_RED = 0     # Confirmed Bear / Crash: block all new entries
REGIME_YELLOW = 1  # Caution / Pullback / Elevated Vol: scaled risk
REGIME_GREEN = 2   # Risk-On Bull: full risk


@dataclass
class RegimeConfig:
    use_macro_gate: bool = True
    vol_caution_pct: float = 26.0   # QQQ 20d ann. realized vol for YELLOW
    vol_crash_pct: float = 36.0     # QQQ 20d ann. realized vol for RED
    yellow_trend_mult: float = 0.40
    yellow_mr_mult: float = 0.50


@dataclass
class StockIndicatorCache:
    ema20: np.ndarray
    ema50: np.ndarray
    ema200: np.ndarray
    sma5: np.ndarray
    sma8: np.ndarray
    atr14: np.ndarray
    atr22: np.ndarray
    rsi2: np.ndarray
    rsi14: np.ndarray
    ibs: np.ndarray
    alma20: np.ndarray
    vol20: np.ndarray
    rs_score: np.ndarray  # 60-day risk-adjusted momentum (Return_60d% / Vol_20d%)


def _compute_rs_score(close: np.ndarray, vol20: np.ndarray, lookback: int = 60) -> np.ndarray:
    n = len(close)
    out = np.full(n, np.nan, dtype=np.float64)
    for i in range(lookback, n):
        if close[i - lookback] > 0.0 and not np.isnan(vol20[i]) and vol20[i] > 1.0:
            ret_pct = (close[i] / close[i - lookback] - 1.0) * 100.0
            out[i] = ret_pct / vol20[i]
    return out


def build_stock_cache(data: OHLCVData) -> StockIndicatorCache:
    v20 = ind.realized_vol_ann(data.close, 20)
    return StockIndicatorCache(
        ema20=ind.ema(data.close, 20),
        ema50=ind.ema(data.close, 50),
        ema200=ind.ema(data.close, 200),
        sma5=ind.sma(data.close, 5),
        sma8=ind.sma(data.close, 8),
        atr14=ind.atr(data.high, data.low, data.close, 14),
        atr22=ind.atr(data.high, data.low, data.close, 22),
        rsi2=ind.rsi(data.close, 2),
        rsi14=ind.rsi(data.close, 14),
        ibs=ind.ibs(data.high, data.low, data.close),
        alma20=ind.alma(data.close, 20, 0.85, 6.0),
        vol20=v20,
        rs_score=_compute_rs_score(data.close, v20, 60),
    )


def compute_macro_regime(
    benchmarks: Dict[str, OHLCVData],
    cfg: RegimeConfig,
) -> np.ndarray:
    """
    Computes daily macro regime for each closed bar `s` (read `regime[t - 1]` at bar `t`).
      - RED:    QQQ_vol20 >= vol_crash_pct
                OR (QQQ_close < QQQ_ema200 AND SPY_close < SPY_ema200)
      - YELLOW: QQQ_vol20 >= vol_caution_pct
                OR QQQ_close < QQQ_ema50
                OR QQQ_close < QQQ_ema200
      - GREEN:  otherwise
    """
    ref = benchmarks["QQQ"]
    n = len(ref)
    regime = np.full(n, REGIME_GREEN, dtype=np.int32)
    if not cfg.use_macro_gate:
        return regime

    q_c = ref.close
    q_ema50 = ind.ema(q_c, 50)
    q_ema200 = ind.ema(q_c, 200)
    q_vol20 = ind.realized_vol_ann(q_c, 20)

    if "SPY" in benchmarks:
        s_c = benchmarks["SPY"].close
        s_ema200 = ind.ema(s_c, 200)
    else:
        s_c = q_c
        s_ema200 = q_ema200

    for i in range(n):
        if np.isnan(q_ema200[i]) or np.isnan(q_ema50[i]) or np.isnan(q_vol20[i]) or np.isnan(s_ema200[i]):
            regime[i] = REGIME_RED
            continue

        q_below_200 = q_c[i] < q_ema200[i]
        q_below_50 = q_c[i] < q_ema50[i]
        s_below_200 = s_c[i] < s_ema200[i]

        if q_vol20[i] >= cfg.vol_crash_pct or (q_below_200 and s_below_200):
            regime[i] = REGIME_RED
        elif q_vol20[i] >= cfg.vol_caution_pct or q_below_50 or q_below_200:
            regime[i] = REGIME_YELLOW
        else:
            regime[i] = REGIME_GREEN

    return regime


def is_falling_knife(data: OHLCVData, cache: StockIndicatorCache, s: int, max_drop_atr: float = 3.5) -> bool:
    if s < 1 or np.isnan(cache.atr14[s]) or cache.atr14[s] <= 0.0:
        return True
    if (data.close[s - 1] - data.close[s]) > max_drop_atr * cache.atr14[s]:
        return True
    if abs(data.open[s] - data.close[s - 1]) > max_drop_atr * cache.atr14[s]:
        return True
    return False


# =============================================================================
# ENGINE 1: Leader ALMA20 Trend (Top-K RS Leaders + Fast EMA50 Exit + Trail)
# =============================================================================
def signal_leader_trend_entry(
    data: OHLCVData,
    cache: StockIndicatorCache,
    s: int,
    min_rs_score: float = 0.20,
    max_drop_atr: float = 3.5,
) -> bool:
    if s < 201:
        return False
    if (
        np.isnan(cache.ema50[s])
        or np.isnan(cache.ema200[s])
        or np.isnan(cache.alma20[s])
        or np.isnan(cache.alma20[s - 1])
        or np.isnan(cache.rs_score[s])
        or np.isnan(cache.atr14[s])
    ):
        return False
    if is_falling_knife(data, cache, s, max_drop_atr):
        return False
    return (
        data.close[s] > cache.ema200[s]
        and data.close[s] > cache.ema50[s]
        and data.close[s] > cache.alma20[s]
        and cache.alma20[s] > cache.alma20[s - 1]
        and cache.rs_score[s] > min_rs_score
    )


def signal_leader_trend_exit(data: OHLCVData, cache: StockIndicatorCache, s: int) -> bool:
    """Fast trend-break protection: exit if stock closes below EMA(50)."""
    if np.isnan(cache.ema50[s]):
        return False
    return data.close[s] < cache.ema50[s]


# =============================================================================
# ENGINE 2: IBS Sniper (Ultra-Short 1-5d Orthogonal Mean Reversion)
# =============================================================================
def signal_ibs_entry(
    data: OHLCVData,
    cache: StockIndicatorCache,
    s: int,
    ibs_thresh: float = 0.12,
    require_above_ema50: bool = True,
    max_drop_atr: float = 3.5,
) -> bool:
    if s < 201:
        return False
    if np.isnan(cache.ema200[s]) or np.isnan(cache.ema50[s]) or np.isnan(cache.atr14[s]):
        return False
    if is_falling_knife(data, cache, s, max_drop_atr):
        return False
    if require_above_ema50 and data.close[s] <= cache.ema50[s]:
        return False
    return (
        data.close[s] > cache.ema200[s]
        and cache.ibs[s] < ibs_thresh
        and data.close[s] < data.high[s - 1]
    )


def signal_ibs_exit(data: OHLCVData, cache: StockIndicatorCache, s: int) -> bool:
    if s < 1:
        return False
    return data.close[s] > data.high[s - 1]


# =============================================================================
# ENGINE 3: Connors RSI(2) Shield (Optional Short-Hold Mean Reversion)
# =============================================================================
def signal_connors_entry(
    data: OHLCVData,
    cache: StockIndicatorCache,
    s: int,
    rsi_thresh: float = 12.0,
    use_sma8: bool = True,
    max_drop_atr: float = 3.5,
) -> bool:
    if s < 201:
        return False
    if np.isnan(cache.ema200[s]) or np.isnan(cache.rsi2[s]) or np.isnan(cache.atr14[s]):
        return False
    if is_falling_knife(data, cache, s, max_drop_atr):
        return False
    exit_ma = cache.sma8[s] if use_sma8 else cache.sma5[s]
    if np.isnan(exit_ma):
        return False
    return (
        data.close[s] > cache.ema200[s]
        and cache.rsi2[s] < rsi_thresh
        and data.close[s] < exit_ma
    )


def signal_connors_exit(
    data: OHLCVData,
    cache: StockIndicatorCache,
    s: int,
    use_sma8: bool = True,
) -> bool:
    exit_ma = cache.sma8[s] if use_sma8 else cache.sma5[s]
    if np.isnan(exit_ma):
        return False
    return data.close[s] > exit_ma
