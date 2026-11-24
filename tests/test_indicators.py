"""Unit tests for deterministic zero-lookahead indicators."""

from __future__ import annotations

import os
import sys
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))

import indicators as ind


def test_sma_exact():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    out = ind.sma(x, 3)
    assert np.isnan(out[0]) and np.isnan(out[1])
    assert out[2] == pytest.approx(2.0)
    assert out[3] == pytest.approx(3.0)
    assert out[4] == pytest.approx(4.0)


def test_ema_exact_and_causal():
    x = np.array([10.0, 12.0, 14.0, 16.0, 18.0, 20.0])
    out = ind.ema(x, 3)
    assert np.isnan(out[0]) and np.isnan(out[1])
    assert out[2] == pytest.approx(12.0)  # SMA(10,12,14)
    # alpha = 2/(3+1) = 0.5 -> 0.5*16 + 0.5*12 = 14.0
    assert out[3] == pytest.approx(14.0)

    # Zero-lookahead invariance: perturbing future bars must not alter past values
    x_mod = x.copy()
    x_mod[4:] = 9999.0
    out_mod = ind.ema(x_mod, 3)
    assert np.allclose(out[:4], out_mod[:4], equal_nan=True)


def test_rsi_bounds_and_causality():
    rng = np.random.default_rng(42)
    prices = 100.0 + np.cumsum(rng.normal(0.05, 1.5, size=250))
    r2 = ind.rsi(prices, 2)
    r14 = ind.rsi(prices, 14)

    valid2 = r2[~np.isnan(r2)]
    valid14 = r14[~np.isnan(r14)]
    assert np.all((valid2 >= 0.0) & (valid2 <= 100.0))
    assert np.all((valid14 >= 0.0) & (valid14 <= 100.0))

    # Zero-lookahead check
    p_mod = prices.copy()
    p_mod[150:] *= 3.0
    r2_mod = ind.rsi(p_mod, 2)
    r14_mod = ind.rsi(p_mod, 14)
    assert np.allclose(r2[:150], r2_mod[:150], equal_nan=True)
    assert np.allclose(r14[:150], r14_mod[:150], equal_nan=True)


def test_ibs_and_atr_and_alma_and_cmf_and_adx_causality():
    rng = np.random.default_rng(7)
    n = 260
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, size=n)))
    high = close * (1.0 + rng.uniform(0.002, 0.02, size=n))
    low = close * (1.0 - rng.uniform(0.002, 0.02, size=n))
    vol = rng.uniform(1e6, 5e6, size=n)

    cut = 180
    high_m, low_m, close_m, vol_m = high.copy(), low.copy(), close.copy(), vol.copy()
    high_m[cut:] *= 2.5
    low_m[cut:] *= 0.4
    close_m[cut:] *= 1.8
    vol_m[cut:] *= 10.0

    for fn_a, fn_b in [
        (ind.atr(high, low, close, 14), ind.atr(high_m, low_m, close_m, 14)),
        (ind.ibs(high, low, close), ind.ibs(high_m, low_m, close_m)),
        (ind.alma(close, 20, 0.85, 6.0), ind.alma(close_m, 20, 0.85, 6.0)),
        (ind.cmf(high, low, close, vol, 20), ind.cmf(high_m, low_m, close_m, vol_m, 20)),
        (ind.adx(high, low, close, 14), ind.adx(high_m, low_m, close_m, 14)),
        (ind.realized_vol_ann(close, 20), ind.realized_vol_ann(close_m, 20)),
    ]:
        assert np.allclose(fn_a[:cut], fn_b[:cut], equal_nan=True)
