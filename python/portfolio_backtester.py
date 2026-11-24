"""
Zero-lookahead shared-equity portfolio backtester for StockShield-LowDD-cBot (V3).

Exact 1:1 mathematical parity with `cbot/src/StockShieldLowDdBot.cs`:
  - Top-K Cross-Sectional RS Leader Trend (`ALMA20` + `EMA50` fast exit + Chandelier trail + BE)
  - Orthogonal `IBS Sniper` & optional `Connors RSI(2)` short-hold mean reversion
  - Inverse-Volatility Per-Stock Notional Cap (`max_not * (sv_ref / stock_vol20)`)
  - Dynamic Benchmark Volatility Targeting (`target_benchmark_vol_pct / qqq_vol20`)
  - Sub-Sector Cluster Cap (`max_cluster_positions = 2`) & 1-Position-Per-Stock Cap
  - Smooth Recovery-Capable DD Throttling (`HalfRisk` / `QuarterRisk`)
  - Realistic cTrader US Stock CFD Cost Model (`10 bps` RT + `7.0%/yr` swap w/ 3x Wed)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np

from data_loader import OHLCVData, STOCK_CLUSTERS
import indicators as ind
from engines import (
    REGIME_GREEN,
    REGIME_RED,
    REGIME_YELLOW,
    RegimeConfig,
    StockIndicatorCache,
    build_stock_cache,
    compute_macro_regime,
    signal_connors_entry,
    signal_connors_exit,
    signal_ibs_entry,
    signal_ibs_exit,
    signal_leader_trend_entry,
    signal_leader_trend_exit,
)


@dataclass
class PortfolioConfig:
    initial_capital: float = 25_000.0

    # Macro Regime Gate
    regime: RegimeConfig = field(default_factory=RegimeConfig)

    # Engine 1: Leader ALMA20 Trend
    enable_trend: bool = True
    trend_top_k: int = 7
    trend_risk_pct: float = 0.70
    trend_min_rs_score: float = 0.20
    trend_sl_atr: float = 2.0
    trend_trail_atr: float = 3.2
    trend_be_r: float = 1.0
    trend_fast_exit_ema50: bool = True

    # Engine 2: IBS Sniper (Ultra-Short Orthogonal MR)
    enable_ibs: bool = True
    ibs_top_k: int = 8
    ibs_risk_pct: float = 0.50
    ibs_thresh: float = 0.12
    ibs_require_above_ema50: bool = True
    ibs_sl_atr: float = 2.5
    ibs_max_hold_days: int = 5

    # Engine 3: Connors RSI(2) (Optional MR)
    enable_connors: bool = False
    connors_risk_pct: float = 0.50
    connors_rsi_thresh: float = 12.0
    connors_use_sma8: bool = True
    connors_sl_atr: float = 2.8
    connors_max_hold_days: int = 8

    # Falling-knife / Gap filter
    max_drop_atr: float = 3.5

    # Portfolio Exposure, Clustering & Inverse-Vol Sizing
    max_concurrent_positions: int = 6
    max_positions_per_stock: int = 1
    max_cluster_positions: int = 2
    max_single_stock_notional_pct: float = 11.0  # base cap at stock_vol == stock_vol_ref_pct
    stock_vol_ref_pct: float = 21.0              # inverse-vol notional reference
    max_portfolio_leverage: float = 0.55         # max gross leverage at calm vol

    # Dynamic Benchmark Volatility Targeting
    use_vol_targeting: bool = True
    target_benchmark_vol_pct: float = 17.0
    min_vol_scale: float = 0.35

    # Smooth Recovery-Capable DD Throttling + Emergency Circuit Breaker
    half_risk_dd_pct: float = 2.2
    quarter_risk_dd_pct: float = 4.0
    max_daily_loss_pct: float = 0.0              # 0 = structural cap only (no panic bottom-selling)
    max_total_dd_pct: float = 7.8                # emergency circuit breaker
    flatten_on_dd_breach: bool = True
    kill_cooldown_days: int = 10

    # Tier 3: Trend-Hold Core Mode (replaces short-hold engines with wide EMA trend-hold)
    enable_trend_hold_core: bool = False
    trend_hold_exit_ema_period: int = 100
    trend_hold_rebal_days: int = 21
    trend_hold_use_qqq200_gate: bool = True

    # Realistic cTrader US Stock CFD Cost Model
    entry_cost_bps: float = 5.0
    exit_cost_bps: float = 5.0
    annual_swap_pct: float = 7.0
    triple_wednesday_swap: bool = True


@dataclass
class OpenPosition:
    symbol: str
    cluster: str
    engine: str
    entry_idx: int
    entry_date: str
    entry_price: float
    shares: float
    initial_sl: float
    current_sl: float
    initial_risk_per_share: float
    highest_high: float
    be_locked: bool = False
    swap_paid: float = 0.0
    entry_cost: float = 0.0


@dataclass
class ClosedTrade:
    symbol: str
    engine: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: float
    hold_days: int
    gross_pnl: float
    costs: float
    swap_paid: float
    net_pnl: float
    exit_reason: str


@dataclass
class BacktestResult:
    config: PortfolioConfig
    start_date: str
    end_date: str
    dates: np.ndarray
    equity_curve: np.ndarray
    intraday_low_equity: np.ndarray
    daily_returns: np.ndarray
    trades: List[ClosedTrade]
    final_equity: float
    total_return_pct: float
    cagr_pct: float
    max_equity_dd_pct: float
    max_close_dd_pct: float
    worst_day_dd_pct: float
    calmar: float
    sharpe: float
    sortino: float
    profit_factor: float
    win_rate_pct: float
    avg_hold_days: float
    total_swap_paid: float
    total_costs_paid: float
    avg_leverage: float
    max_leverage_seen: float
    dd_kill_switches: int
    daily_halts: int
    yearly_stats: Dict[str, Dict[str, float]]
    engine_stats: Dict[str, Dict[str, float]]
    stock_stats: Dict[str, Dict[str, float]]


def run_portfolio_backtest(
    dates: np.ndarray,
    weekdays: np.ndarray,
    stocks: Dict[str, OHLCVData],
    benchmarks: Dict[str, OHLCVData],
    cfg: PortfolioConfig,
    start_idx: int = 205,
    end_idx: Optional[int] = None,
    stock_caches: Optional[Dict[str, StockIndicatorCache]] = None,
    regime_arr: Optional[np.ndarray] = None,
) -> BacktestResult:
    n_total = len(dates)
    if end_idx is None or end_idx > n_total:
        end_idx = n_total
    start_idx = max(start_idx, 202)
    n_sim = end_idx - start_idx
    if n_sim <= 5:
        raise ValueError("Simulation window too short.")

    caches = stock_caches if stock_caches is not None else {sym: build_stock_cache(d) for sym, d in stocks.items()}
    regime = regime_arr if regime_arr is not None else compute_macro_regime(benchmarks, cfg.regime)
    qqq_vol20 = ind.realized_vol_ann(benchmarks["QQQ"].close, 20)
    qqq_ema200 = ind.ema(benchmarks["QQQ"].close, 200) if cfg.enable_trend_hold_core else None
    trend_hold_emas = (
        {sym: ind.ema(d.close, cfg.trend_hold_exit_ema_period) for sym, d in stocks.items()}
        if cfg.enable_trend_hold_core
        else {}
    )

    cash = cfg.initial_capital
    peak_equity = cfg.initial_capital
    kill_anchor_peak = cfg.initial_capital
    kill_cooldown_until = -1
    open_positions: List[OpenPosition] = []
    closed_trades: List[ClosedTrade] = []

    equity_curve = np.zeros(n_sim, dtype=np.float64)
    intraday_low_eq = np.zeros(n_sim, dtype=np.float64)
    daily_returns = np.zeros(n_sim, dtype=np.float64)
    lev_series = np.zeros(n_sim, dtype=np.float64)

    dd_kill_switches = 0
    daily_halts = 0
    prev_close_eq = cfg.initial_capital

    stock_order = list(stocks.keys())
    daily_swap_rate = (cfg.annual_swap_pct / 100.0) / 365.0

    def _mark_equity_at(idx: int, use_open: bool = False) -> float:
        eq = cash
        for p in open_positions:
            px = stocks[p.symbol].open[idx] if use_open else stocks[p.symbol].close[idx]
            eq += p.shares * px
        return eq

    def _close_pos(p: OpenPosition, exit_px: float, idx: int, reason: str) -> None:
        nonlocal cash
        notional_exit = p.shares * exit_px
        exit_cost = notional_exit * (cfg.exit_cost_bps / 10_000.0)
        cash += notional_exit - exit_cost
        gross_pnl = (exit_px - p.entry_price) * p.shares
        total_costs = p.entry_cost + exit_cost
        net_pnl = gross_pnl - total_costs - p.swap_paid
        closed_trades.append(
            ClosedTrade(
                symbol=p.symbol,
                engine=p.engine,
                entry_date=p.entry_date,
                exit_date=str(dates[idx]),
                entry_price=p.entry_price,
                exit_price=exit_px,
                shares=p.shares,
                hold_days=idx - p.entry_idx,
                gross_pnl=gross_pnl,
                costs=total_costs,
                swap_paid=p.swap_paid,
                net_pnl=net_pnl,
                exit_reason=reason,
            )
        )

    for step, t in enumerate(range(start_idx, end_idx)):
        s = t - 1
        day_anchor_eq = prev_close_eq
        reg_s = int(regime[s])

        # 1. Open-of-day exits (SL gap, EMA50 fast trend-break, MR signal/time-stop)
        survivors: List[OpenPosition] = []
        for p in open_positions:
            d = stocks[p.symbol]
            c = caches[p.symbol]
            open_px = float(d.open[t])
            hold_days = t - p.entry_idx

            if open_px <= p.current_sl:
                _close_pos(p, open_px, t, "SL_GAP")
                continue

            exit_reason: Optional[str] = None
            if p.engine == "TREND":
                if cfg.trend_fast_exit_ema50 and signal_leader_trend_exit(d, c, s):
                    exit_reason = "EMA50_EXIT"
            elif p.engine == "TRENDHOLD":
                q_ok = (not cfg.trend_hold_use_qqq200_gate) or (
                    qqq_ema200 is not None and not np.isnan(qqq_ema200[s]) and benchmarks["QQQ"].close[s] > qqq_ema200[s]
                )
                ex_ema = trend_hold_emas[p.symbol][s]
                if not q_ok or (not np.isnan(ex_ema) and d.close[s] < ex_ema):
                    exit_reason = "TRENDHOLD_EXIT"
            elif p.engine == "IBS":
                if signal_ibs_exit(d, c, s):
                    exit_reason = "SIGNAL"
                elif hold_days >= cfg.ibs_max_hold_days:
                    exit_reason = "TIMESTOP"
            elif p.engine == "CONNORS":
                if signal_connors_exit(d, c, s, cfg.connors_use_sma8):
                    exit_reason = "SIGNAL"
                elif hold_days >= cfg.connors_max_hold_days:
                    exit_reason = "TIMESTOP"

            if exit_reason is not None:
                _close_pos(p, open_px, t, exit_reason)
            else:
                survivors.append(p)
        open_positions = survivors

        # 2. Smooth DD Throttle, Dynamic Vol Targeting & RS-Ranked Entries
        open_eq = _mark_equity_at(t, use_open=True)
        if open_eq > peak_equity:
            peak_equity = open_eq
        if open_eq > kill_anchor_peak:
            kill_anchor_peak = open_eq
        curr_dd_pct = (peak_equity - open_eq) / peak_equity * 100.0 if peak_equity > 0 else 0.0

        # Tier 3: Trend-Hold Core Mode (wide EMA trend-hold + QQQ200 bear shield)
        if cfg.enable_trend_hold_core:
            q_ok = (not cfg.trend_hold_use_qqq200_gate) or (
                qqq_ema200 is not None and not np.isnan(qqq_ema200[s]) and benchmarks["QQQ"].close[s] > qqq_ema200[s]
            )
            if t >= kill_cooldown_until and q_ok:
                max_slots = min(len(stock_order), cfg.max_concurrent_positions)
                slot_notional = min(
                    open_eq * (cfg.max_single_stock_notional_pct / 100.0),
                    (open_eq * cfg.max_portfolio_leverage) / max(max_slots, 1),
                )
                need_rebal = (cfg.trend_hold_rebal_days > 0) and (step > 0) and (step % cfg.trend_hold_rebal_days == 0)

                # Rebalance existing positions periodically to prevent single-stock drift
                if need_rebal:
                    for p in list(open_positions):
                        op = float(stocks[p.symbol].open[t])
                        cur_not = p.shares * op
                        diff_not = slot_notional - cur_not
                        if abs(diff_not) > max(200.0, 0.15 * slot_notional):
                            diff_sh = diff_not / op
                            cost = abs(diff_not) * (cfg.entry_cost_bps / 10_000.0)
                            cash -= diff_not + cost
                            p.shares += diff_sh
                            p.entry_cost += cost

                # Rank by RS score and fill open slots
                ranked_th = (
                    sorted(
                        stock_order,
                        key=lambda sym: float(caches[sym].rs_score[s]) if not np.isnan(caches[sym].rs_score[s]) else -999.0,
                        reverse=True,
                    )
                    if len(stock_order) > 1
                    else stock_order
                )
                for sym in ranked_th:
                    if len(open_positions) >= max_slots:
                        break
                    if any(p.symbol == sym for p in open_positions):
                        continue
                    d = stocks[sym]
                    c = caches[sym]
                    ex_ema = trend_hold_emas[sym][s]
                    if np.isnan(c.ema50[s]) or np.isnan(ex_ema) or np.isnan(c.atr14[s]):
                        continue
                    if d.close[s] > c.ema50[s] and d.close[s] > ex_ema:
                        entry_px = float(d.open[t])
                        atr14 = float(c.atr14[s])
                        if entry_px <= 0.0 or atr14 <= 0.0:
                            continue
                        curr_port_not = sum(p.shares * float(stocks[p.symbol].open[t]) for p in open_positions)
                        rem_port_not = max(0.0, open_eq * cfg.max_portfolio_leverage - curr_port_not)
                        notional = min(slot_notional, rem_port_not)
                        if notional < 100.0:
                            continue
                        shares = notional / entry_px
                        sl_dist = 5.0 * atr14  # catastrophe SL only
                        sl_px = max(0.01, entry_px - sl_dist)
                        entry_cost = notional * (cfg.entry_cost_bps / 10_000.0)
                        cash -= notional + entry_cost
                        open_positions.append(
                            OpenPosition(
                                symbol=sym,
                                cluster=STOCK_CLUSTERS.get(sym, "OTHER"),
                                engine="TRENDHOLD",
                                entry_idx=t,
                                entry_date=str(dates[t]),
                                entry_price=entry_px,
                                shares=shares,
                                initial_sl=sl_px,
                                current_sl=sl_px,
                                initial_risk_per_share=sl_dist,
                                highest_high=entry_px,
                                be_locked=False,
                                swap_paid=0.0,
                                entry_cost=entry_cost,
                            )
                        )
        dd_risk_mult = 1.0
        if cfg.quarter_risk_dd_pct > 0 and curr_dd_pct >= cfg.quarter_risk_dd_pct:
            dd_risk_mult = 0.35
        elif cfg.half_risk_dd_pct > 0 and curr_dd_pct >= cfg.half_risk_dd_pct:
            dd_risk_mult = 0.65

        vol_scale = 1.0
        if cfg.use_vol_targeting and not np.isnan(qqq_vol20[s]) and qqq_vol20[s] > 1.0:
            vol_scale = min(1.0, max(cfg.min_vol_scale, cfg.target_benchmark_vol_pct / max(float(qqq_vol20[s]), 10.0)))

        eff_max_leverage = cfg.max_portfolio_leverage * vol_scale

        if len(stock_order) > 1:
            ranked_symbols = sorted(
                stock_order,
                key=lambda sym: float(caches[sym].rs_score[s]) if not np.isnan(caches[sym].rs_score[s]) else -999.0,
                reverse=True,
            )
        else:
            ranked_symbols = stock_order

        if not cfg.enable_trend_hold_core and t >= kill_cooldown_until and reg_s != REGIME_RED and len(open_positions) < cfg.max_concurrent_positions:
            reg_trend = 1.0 if reg_s == REGIME_GREEN else cfg.regime.yellow_trend_mult
            reg_mr = 1.0 if reg_s == REGIME_GREEN else cfg.regime.yellow_mr_mult

            def _try_enter(sym: str, eng_name: str, base_risk_pct: float, sl_atr_mult: float, reg_mult: float) -> None:
                nonlocal cash
                if len(open_positions) >= cfg.max_concurrent_positions:
                    return
                if any(p.symbol == sym and p.engine == eng_name for p in open_positions):
                    return
                sym_pos = [p for p in open_positions if p.symbol == sym]
                if len(sym_pos) >= cfg.max_positions_per_stock:
                    return
                cluster = STOCK_CLUSTERS.get(sym, "OTHER")
                if sum(1 for p in open_positions if p.cluster == cluster) >= cfg.max_cluster_positions:
                    return

                d = stocks[sym]
                c = caches[sym]
                entry_px = float(d.open[t])
                atr14 = float(c.atr14[s])
                if entry_px <= 0.0 or np.isnan(atr14) or atr14 <= 0.0:
                    return
                if abs(entry_px - float(d.close[s])) > 2.5 * atr14:
                    return

                sl_dist = sl_atr_mult * atr14
                sl_px = entry_px - sl_dist
                if sl_px <= 0.0:
                    return

                risk_dollars = open_eq * (base_risk_pct / 100.0) * reg_mult * dd_risk_mult * vol_scale
                shares_by_risk = risk_dollars / sl_dist

                # Inverse-Volatility Per-Stock Notional Cap
                svol = float(c.vol20[s]) if (not np.isnan(c.vol20[s]) and c.vol20[s] > 10.0) else 30.0
                vol_adj_not_pct = min(
                    cfg.max_single_stock_notional_pct,
                    cfg.max_single_stock_notional_pct * (cfg.stock_vol_ref_pct / svol),
                )
                existing_sym_not = sum(p.shares * entry_px for p in sym_pos)
                rem_sym_not = max(0.0, open_eq * (vol_adj_not_pct / 100.0) - existing_sym_not)
                curr_port_not = sum(p.shares * float(stocks[p.symbol].open[t]) for p in open_positions)
                rem_port_not = max(0.0, open_eq * eff_max_leverage - curr_port_not)

                allowed_not = min(rem_sym_not, rem_port_not)
                if allowed_not < 100.0:
                    return

                shares = min(shares_by_risk, allowed_not / entry_px)
                notional = shares * entry_px
                if notional < 100.0:
                    return

                entry_cost = notional * (cfg.entry_cost_bps / 10_000.0)
                cash -= notional + entry_cost
                open_positions.append(
                    OpenPosition(
                        symbol=sym,
                        cluster=cluster,
                        engine=eng_name,
                        entry_idx=t,
                        entry_date=str(dates[t]),
                        entry_price=entry_px,
                        shares=shares,
                        initial_sl=sl_px,
                        current_sl=sl_px,
                        initial_risk_per_share=sl_dist,
                        highest_high=entry_px,
                        be_locked=False,
                        swap_paid=0.0,
                        entry_cost=entry_cost,
                    )
                )

            if cfg.enable_trend and reg_trend > 0.0:
                for sym in ranked_symbols[: cfg.trend_top_k]:
                    if signal_leader_trend_entry(stocks[sym], caches[sym], s, cfg.trend_min_rs_score, cfg.max_drop_atr):
                        _try_enter(sym, "TREND", cfg.trend_risk_pct, cfg.trend_sl_atr, reg_trend)

            if cfg.enable_ibs and reg_mr > 0.0:
                for sym in ranked_symbols[: cfg.ibs_top_k]:
                    if signal_ibs_entry(stocks[sym], caches[sym], s, cfg.ibs_thresh, cfg.ibs_require_above_ema50, cfg.max_drop_atr):
                        _try_enter(sym, "IBS", cfg.ibs_risk_pct, cfg.ibs_sl_atr, reg_mr)

            if cfg.enable_connors and reg_mr > 0.0:
                for sym in ranked_symbols:
                    if signal_connors_entry(stocks[sym], caches[sym], s, cfg.connors_rsi_thresh, cfg.connors_use_sma8, cfg.max_drop_atr):
                        _try_enter(sym, "CONNORS", cfg.connors_risk_pct, cfg.connors_sl_atr, reg_mr)

        # 3. Intraday worst-case equity & SL hits
        worst_eq = cash
        for p in open_positions:
            d = stocks[p.symbol]
            bar_low = float(d.low[t])
            worst_px = max(bar_low, p.current_sl) if float(d.open[t]) > p.current_sl else float(d.open[t])
            worst_eq += p.shares * worst_px

        survivors_intra: List[OpenPosition] = []
        for p in open_positions:
            d = stocks[p.symbol]
            if float(d.low[t]) <= p.current_sl:
                fill_px = min(float(d.open[t]), p.current_sl)
                _close_pos(p, fill_px, t, "SL_HIT")
            else:
                survivors_intra.append(p)
        open_positions = survivors_intra

        # Emergency Kill-Switch / Daily Guard
        daily_dd_pct = (day_anchor_eq - worst_eq) / day_anchor_eq * 100.0 if day_anchor_eq > 0 else 0.0
        total_dd_intra_pct = (kill_anchor_peak - worst_eq) / kill_anchor_peak * 100.0 if kill_anchor_peak > 0 else 0.0

        killed_today = False
        if cfg.flatten_on_dd_breach:
            if cfg.max_total_dd_pct > 0 and total_dd_intra_pct >= cfg.max_total_dd_pct and open_positions:
                dd_kill_switches += 1
                killed_today = True
                for p in list(open_positions):
                    _close_pos(p, float(stocks[p.symbol].close[t]), t, "DD_KILL")
                open_positions = []
                kill_cooldown_until = t + cfg.kill_cooldown_days
                kill_anchor_peak = _mark_equity_at(t, use_open=False)
            elif cfg.max_daily_loss_pct > 0 and daily_dd_pct >= cfg.max_daily_loss_pct and open_positions:
                daily_halts += 1
                killed_today = True
                for p in list(open_positions):
                    _close_pos(p, float(stocks[p.symbol].close[t]), t, "DAILY_GUARD")
                open_positions = []

        # 4. EOD Chandelier Trail & Break-Even + Overnight CFD Swap
        swap_mult = 3.0 if (cfg.triple_wednesday_swap and int(weekdays[t]) == 2) else 1.0
        for p in open_positions:
            d = stocks[p.symbol]
            c = caches[p.symbol]
            bar_high = float(d.high[t])
            bar_close = float(d.close[t])
            if bar_high > p.highest_high:
                p.highest_high = bar_high

            if p.engine == "TREND":
                if not p.be_locked and bar_high >= p.entry_price + cfg.trend_be_r * p.initial_risk_per_share:
                    p.current_sl = max(p.current_sl, p.entry_price)
                    p.be_locked = True
                atr_t = float(c.atr22[t]) if not np.isnan(c.atr22[t]) else float(c.atr14[t])
                if not np.isnan(atr_t) and atr_t > 0:
                    trail_sl = p.highest_high - cfg.trend_trail_atr * atr_t
                    if trail_sl > p.current_sl:
                        p.current_sl = trail_sl

            if daily_swap_rate > 0.0:
                notional_close = p.shares * bar_close
                swap_fee = notional_close * daily_swap_rate * swap_mult
                cash -= swap_fee
                p.swap_paid += swap_fee

        # 5. Record daily equity, leverage & peak
        close_eq = _mark_equity_at(t, use_open=False)
        intraday_low_eq[step] = close_eq if killed_today else min(worst_eq, close_eq)
        equity_curve[step] = close_eq
        daily_returns[step] = (close_eq - prev_close_eq) / prev_close_eq if prev_close_eq > 0 else 0.0
        prev_close_eq = close_eq

        if close_eq > peak_equity:
            peak_equity = close_eq

        open_notional_close = sum(p.shares * float(stocks[p.symbol].close[t]) for p in open_positions)
        lev_series[step] = open_notional_close / close_eq if close_eq > 0 else 0.0

    final_eq = equity_curve[-1]
    total_ret_pct = (final_eq / cfg.initial_capital - 1.0) * 100.0
    years = max(n_sim / 252.0, 1e-6)
    cagr_pct = ((final_eq / cfg.initial_capital) ** (1.0 / years) - 1.0) * 100.0 if final_eq > 0 else -100.0

    running_peak = np.maximum.accumulate(np.maximum(equity_curve, cfg.initial_capital))
    intra_dd_series = (running_peak - intraday_low_eq) / running_peak * 100.0
    close_dd_series = (running_peak - equity_curve) / running_peak * 100.0
    max_equity_dd_pct = float(np.max(intra_dd_series))
    max_close_dd_pct = float(np.max(close_dd_series))
    worst_day_dd_pct = float(-np.min(daily_returns) * 100.0) if len(daily_returns) > 0 else 0.0

    calmar = cagr_pct / max_equity_dd_pct if max_equity_dd_pct > 1e-6 else 0.0
    mean_ret = float(np.mean(daily_returns))
    std_ret = float(np.std(daily_returns, ddof=1)) if len(daily_returns) > 1 else 0.0
    sharpe = (mean_ret / std_ret) * math.sqrt(252.0) if std_ret > 1e-12 else 0.0
    neg_rets = daily_returns[daily_returns < 0.0]
    down_std = float(np.std(neg_rets, ddof=1)) if len(neg_rets) > 1 else 0.0
    sortino = (mean_ret / down_std) * math.sqrt(252.0) if down_std > 1e-12 else 0.0

    wins = [tr.net_pnl for tr in closed_trades if tr.net_pnl > 0.0]
    losses = [-tr.net_pnl for tr in closed_trades if tr.net_pnl <= 0.0]
    gross_win = sum(wins)
    gross_loss = sum(losses)
    pf = gross_win / gross_loss if gross_loss > 1e-9 else (99.0 if gross_win > 0 else 0.0)
    win_rate = (len(wins) / len(closed_trades) * 100.0) if closed_trades else 0.0
    avg_hold = float(np.mean([tr.hold_days for tr in closed_trades])) if closed_trades else 0.0
    total_swap = sum(tr.swap_paid for tr in closed_trades) + sum(p.swap_paid for p in open_positions)
    total_costs = sum(tr.costs for tr in closed_trades) + sum(p.entry_cost for p in open_positions)

    sim_dates = dates[start_idx:end_idx]
    yearly_stats: Dict[str, Dict[str, float]] = {}
    years_seen = sorted({str(d)[:4] for d in sim_dates})
    prev_yr_end_eq = cfg.initial_capital
    for yr in years_seen:
        idxs = [i for i, d in enumerate(sim_dates) if str(d).startswith(yr)]
        if not idxs:
            continue
        yr_eq = equity_curve[idxs]
        yr_low = intraday_low_eq[idxs]
        yr_ret = (yr_eq[-1] / prev_yr_end_eq - 1.0) * 100.0
        yr_peak = np.maximum.accumulate(np.maximum(yr_eq, prev_yr_end_eq))
        yr_dd = float(np.max((yr_peak - yr_low) / yr_peak * 100.0))
        yr_worst_day = float(-np.min(daily_returns[idxs]) * 100.0)
        yr_trades = sum(1 for tr in closed_trades if tr.exit_date.startswith(yr))
        yearly_stats[yr] = {
            "return_pct": yr_ret,
            "max_dd_pct": yr_dd,
            "worst_day_pct": yr_worst_day,
            "trades": float(yr_trades),
        }
        prev_yr_end_eq = float(yr_eq[-1])

    def _group_stats(key_fn) -> Dict[str, Dict[str, float]]:
        groups: Dict[str, List[ClosedTrade]] = {}
        for tr in closed_trades:
            groups.setdefault(key_fn(tr), []).append(tr)
        out: Dict[str, Dict[str, float]] = {}
        for k, trs in sorted(groups.items()):
            w = sum(x.net_pnl for x in trs if x.net_pnl > 0)
            l = sum(-x.net_pnl for x in trs if x.net_pnl <= 0)
            out[k] = {
                "trades": float(len(trs)),
                "win_rate_pct": sum(1 for x in trs if x.net_pnl > 0) / len(trs) * 100.0,
                "net_pnl": sum(x.net_pnl for x in trs),
                "pf": w / l if l > 1e-9 else (99.0 if w > 0 else 0.0),
                "avg_hold": float(np.mean([x.hold_days for x in trs])),
                "swap_paid": sum(x.swap_paid for x in trs),
            }
        return out

    return BacktestResult(
        config=cfg,
        start_date=str(sim_dates[0]),
        end_date=str(sim_dates[-1]),
        dates=sim_dates,
        equity_curve=equity_curve,
        intraday_low_equity=intraday_low_eq,
        daily_returns=daily_returns,
        trades=closed_trades,
        final_equity=float(final_eq),
        total_return_pct=float(total_ret_pct),
        cagr_pct=float(cagr_pct),
        max_equity_dd_pct=max_equity_dd_pct,
        max_close_dd_pct=max_close_dd_pct,
        worst_day_dd_pct=worst_day_dd_pct,
        calmar=float(calmar),
        sharpe=float(sharpe),
        sortino=float(sortino),
        profit_factor=float(pf),
        win_rate_pct=float(win_rate),
        avg_hold_days=avg_hold,
        total_swap_paid=float(total_swap),
        total_costs_paid=float(total_costs),
        avg_leverage=float(np.mean(lev_series)),
        max_leverage_seen=float(np.max(lev_series)),
        dd_kill_switches=dd_kill_switches,
        daily_halts=daily_halts,
        yearly_stats=yearly_stats,
        engine_stats=_group_stats(lambda x: x.engine),
        stock_stats=_group_stats(lambda x: x.symbol),
    )
