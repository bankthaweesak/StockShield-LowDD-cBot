"""
Deterministic, strictly causal (zero-lookahead) technical indicators in pure NumPy.
All formulas are engineered for exact 1:1 parity with cTrader Automate (C#).
"""

from __future__ import annotations

import math
import numpy as np


def sma(series: np.ndarray, period: int) -> np.ndarray:
    """Simple Moving Average. Returns NaN for indices < period - 1."""
    n = len(series)
    out = np.full(n, np.nan, dtype=np.float64)
    if period <= 0 or n < period:
        return out
    csum = np.cumsum(series, dtype=np.float64)
    out[period - 1] = csum[period - 1] / period
    if n > period:
        out[period:] = (csum[period:] - csum[:-period]) / period
    return out


def ema(series: np.ndarray, period: int) -> np.ndarray:
    """
    Exponential Moving Average seeded with SMA of first `period` valid bars,
    matching standard institutional & cTrader EMA behavior.
    """
    n = len(series)
    out = np.full(n, np.nan, dtype=np.float64)
    if period <= 0 or n < period:
        return out
    alpha = 2.0 / (period + 1.0)
    seed = float(np.mean(series[:period]))
    out[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = alpha * float(series[i]) + (1.0 - alpha) * prev
        out[i] = prev
    return out


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    n = len(close)
    tr = np.full(n, np.nan, dtype=np.float64)
    if n == 0:
        return tr
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)
    return tr


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder's Average True Range."""
    n = len(close)
    out = np.full(n, np.nan, dtype=np.float64)
    if period <= 0 or n < period:
        return out
    tr = true_range(high, low, close)
    seed = float(np.mean(tr[:period]))
    out[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = (prev * (period - 1) + tr[i]) / period
        out[i] = prev
    return out


def rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder's Relative Strength Index."""
    n = len(close)
    out = np.full(n, np.nan, dtype=np.float64)
    if period <= 0 or n <= period:
        return out
    gains = np.zeros(n, dtype=np.float64)
    losses = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        diff = close[i] - close[i - 1]
        if diff > 0.0:
            gains[i] = diff
        else:
            losses[i] = -diff

    avg_gain = float(np.mean(gains[1 : period + 1]))
    avg_loss = float(np.mean(losses[1 : period + 1]))

    def _calc(ag: float, al: float) -> float:
        if al <= 1e-12:
            return 100.0 if ag > 1e-12 else 50.0
        rs = ag / al
        return 100.0 - (100.0 / (1.0 + rs))

    out[period] = _calc(avg_gain, avg_loss)
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i] = _calc(avg_gain, avg_loss)
    return out


def ibs(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """Internal Bar Strength: (Close - Low) / (High - Low), bounded [0, 1]."""
    rng = high - low
    out = np.full(len(close), 0.5, dtype=np.float64)
    valid = rng > 1e-12
    out[valid] = np.clip((close[valid] - low[valid]) / rng[valid], 0.0, 1.0)
    return out


def alma(series: np.ndarray, window: int = 20, offset: float = 0.85, sigma: float = 6.0) -> np.ndarray:
    """Arnaud Legoux Moving Average (Gaussian-weighted)."""
    n = len(series)
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0 or n < window:
        return out
    m = offset * (window - 1)
    s = window / sigma
    weights = np.array(
        [math.exp(-((j - m) ** 2) / (2.0 * s * s)) for j in range(window)],
        dtype=np.float64,
    )
    weights /= np.sum(weights)
    for i in range(window - 1, n):
        out[i] = float(np.dot(series[i - window + 1 : i + 1], weights))
    return out


def cmf(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    period: int = 20,
) -> np.ndarray:
    """Chaikin Money Flow."""
    n = len(close)
    out = np.full(n, np.nan, dtype=np.float64)
    if period <= 0 or n < period:
        return out
    rng = high - low
    mfm = np.zeros(n, dtype=np.float64)
    valid = rng > 1e-12
    mfm[valid] = ((close[valid] - low[valid]) - (high[valid] - close[valid])) / rng[valid]
    mfv = mfm * volume

    for i in range(period - 1, n):
        vol_sum = float(np.sum(volume[i - period + 1 : i + 1]))
        if vol_sum > 1e-12:
            out[i] = float(np.sum(mfv[i - period + 1 : i + 1])) / vol_sum
        else:
            out[i] = 0.0
    return out


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder's Average Directional Index."""
    n = len(close)
    out = np.full(n, np.nan, dtype=np.float64)
    if period <= 0 or n < 2 * period:
        return out

    tr = true_range(high, low, close)
    plus_dm = np.zeros(n, dtype=np.float64)
    minus_dm = np.zeros(n, dtype=np.float64)

    for i in range(1, n):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]
        if up_move > down_move and up_move > 0.0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0.0:
            minus_dm[i] = down_move

    tr_s = float(np.sum(tr[1 : period + 1]))
    pdm_s = float(np.sum(plus_dm[1 : period + 1]))
    mdm_s = float(np.sum(minus_dm[1 : period + 1]))

    dx = np.full(n, np.nan, dtype=np.float64)

    def _dx(t_s: float, p_s: float, m_s: float) -> float:
        if t_s <= 1e-12:
            return 0.0
        pdi = 100.0 * p_s / t_s
        mdi = 100.0 * m_s / t_s
        denom = pdi + mdi
        if denom <= 1e-12:
            return 0.0
        return 100.0 * abs(pdi - mdi) / denom

    dx[period] = _dx(tr_s, pdm_s, mdm_s)
    for i in range(period + 1, n):
        tr_s = tr_s - (tr_s / period) + tr[i]
        pdm_s = pdm_s - (pdm_s / period) + plus_dm[i]
        mdm_s = mdm_s - (mdm_s / period) + minus_dm[i]
        dx[i] = _dx(tr_s, pdm_s, mdm_s)

    adx_val = float(np.mean(dx[period : 2 * period]))
    out[2 * period - 1] = adx_val
    for i in range(2 * period, n):
        adx_val = (adx_val * (period - 1) + dx[i]) / period
        out[i] = adx_val
    return out


def realized_vol_ann(close: np.ndarray, period: int = 20) -> np.ndarray:
    """
    Annualized close-to-close log-return volatility (in %, e.g. 20.0 = 20%).
    Strictly causal using returns ending at index i.
    """
    n = len(close)
    out = np.full(n, np.nan, dtype=np.float64)
    if period <= 1 or n <= period:
        return out
    log_ret = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        if close[i - 1] > 0.0 and close[i] > 0.0:
            log_ret[i] = math.log(close[i] / close[i - 1])
    sqrt252 = math.sqrt(252.0) * 100.0
    for i in range(period, n):
        window = log_ret[i - period + 1 : i + 1]
        out[i] = float(np.std(window, ddof=1)) * sqrt252
    return out
