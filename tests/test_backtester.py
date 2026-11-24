"""Unit tests for portfolio backtester: swap accounting, gap SL, DD guards, single-stock mode."""

from __future__ import annotations

import os
import sys
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))

from data_loader import OHLCVData
from portfolio_backtester import PortfolioConfig, run_portfolio_backtest


def _make_synthetic_ohlcv(symbol: str, n: int = 320, seed: int = 1, drift: float = 0.0020) -> OHLCVData:
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, 0.008, size=n)
    # Inject clean 3-day pullbacks in an uptrend (RSI2 < 5, drop < 2 ATR)
    for idx in (220, 245, 270, 295):
        if idx + 3 < n:
            rets[idx] = -0.014
            rets[idx + 1] = -0.014
            rets[idx + 2] = -0.014
            rets[idx + 3] = 0.025
    close = 100.0 * np.exp(np.cumsum(rets))
    open_ = np.concatenate(([close[0]], close[:-1] * (1.0 + rng.normal(0.0, 0.001, size=n - 1))))
    high = np.maximum(open_, close) * (1.0 + rng.uniform(0.003, 0.01, size=n))
    low = np.minimum(open_, close) * (1.0 - rng.uniform(0.003, 0.01, size=n))
    vol = rng.uniform(1e6, 3e6, size=n)
    ts = np.arange(n, dtype=np.int64) * 86400 + 1_600_000_000
    dates = np.asarray([f"2022-{(i // 28) % 12 + 1:02d}-{i % 28 + 1:02d}" for i in range(n)], dtype=object)
    weekdays = np.asarray([i % 5 for i in range(n)], dtype=np.int32)
    return OHLCVData(symbol, "1d", ts, dates, weekdays, open_, high, low, close, vol)


def test_swap_cost_reduces_equity_vs_cash():
    n = 320
    qqq = _make_synthetic_ohlcv("QQQ", n=n, seed=10, drift=0.0020)
    spy = _make_synthetic_ohlcv("SPY", n=n, seed=11, drift=0.0018)
    nvda = _make_synthetic_ohlcv("NVDA", n=n, seed=21, drift=0.0022)
    aapl = _make_synthetic_ohlcv("AAPL", n=n, seed=22, drift=0.0020)

    stocks = {"NVDA": nvda, "AAPL": aapl}
    bench = {"QQQ": qqq, "SPY": spy}

    cfg_cash = PortfolioConfig(annual_swap_pct=0.0, triple_wednesday_swap=False)
    cfg_cfd = PortfolioConfig(annual_swap_pct=7.0, triple_wednesday_swap=True)

    r_cash = run_portfolio_backtest(qqq.dates, qqq.weekdays, stocks, bench, cfg_cash)
    r_cfd = run_portfolio_backtest(qqq.dates, qqq.weekdays, stocks, bench, cfg_cfd)

    assert len(r_cash.trades) > 0
    assert r_cash.total_swap_paid == pytest.approx(0.0)
    assert r_cfd.total_swap_paid > 0.0
    assert r_cfd.final_equity < r_cash.final_equity


def test_single_stock_mode_runs_cleanly():
    n = 320
    qqq = _make_synthetic_ohlcv("QQQ", n=n, seed=10, drift=0.0008)
    spy = _make_synthetic_ohlcv("SPY", n=n, seed=11, drift=0.0006)
    msft = _make_synthetic_ohlcv("MSFT", n=n, seed=33, drift=0.0010)

    cfg = PortfolioConfig(
        max_concurrent_positions=1,
        max_cluster_positions=1,
        max_single_stock_notional_pct=30.0,
        max_portfolio_leverage=0.30,
    )
    res = run_portfolio_backtest(qqq.dates, qqq.weekdays, {"MSFT": msft}, {"QQQ": qqq, "SPY": spy}, cfg)
    assert res.max_leverage_seen <= 0.35  # small mark-to-market drift allowed
    assert res.final_equity > 0.0


def test_dd_kill_switch_caps_drawdown():
    n = 320
    qqq = _make_synthetic_ohlcv("QQQ", n=n, seed=10, drift=0.0010)
    spy = _make_synthetic_ohlcv("SPY", n=n, seed=11, drift=0.0008)
    nvda = _make_synthetic_ohlcv("NVDA", n=n, seed=21, drift=0.0012)
    # Inject a sudden crash bar after a known entry window
    nvda.open[223] *= 0.78
    nvda.low[223] = nvda.open[223] * 0.98
    nvda.close[223] = nvda.open[223] * 0.99

    cfg = PortfolioConfig(
        max_single_stock_notional_pct=15.0,
        max_total_dd_pct=7.5,
        max_daily_loss_pct=1.8,
        flatten_on_dd_breach=True,
    )
    res = run_portfolio_backtest(qqq.dates, qqq.weekdays, {"NVDA": nvda}, {"QQQ": qqq, "SPY": spy}, cfg)
    assert res.max_equity_dd_pct < 8.0
