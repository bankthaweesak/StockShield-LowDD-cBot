"""
Deterministic 10-year Daily (D1) OHLCV data loader for US Tech/Growth Mega-Cap
Leaders and macro benchmarks (QQQ, SPY) via Yahoo Finance public chart API.

All series are aligned onto a shared US trading calendar without forward-fill
lookahead. Local JSON caching avoids redundant network requests.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple
import numpy as np


CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_cache")

DEFAULT_STOCKS: List[str] = [
    "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META",
    "AVGO", "AMD", "TSLA", "ORCL", "NFLX", "COST",
]

BENCHMARK_SYMBOLS: List[str] = ["QQQ", "SPY"]

# Sub-sector / correlation clusters for Tech/Growth mega-caps
STOCK_CLUSTERS: Dict[str, str] = {
    "NVDA": "SEMIS",
    "AMD": "SEMIS",
    "AVGO": "SEMIS",
    "MSFT": "CLOUD",
    "AMZN": "CLOUD",
    "GOOGL": "CLOUD",
    "META": "CLOUD",
    "ORCL": "CLOUD",
    "AAPL": "CONSUMER_TECH",
    "TSLA": "CONSUMER_TECH",
    "NFLX": "CONSUMER_TECH",
    "COST": "DEFENSIVE_GROWTH",
}


@dataclass
class OHLCVData:
    symbol: str
    timeframe: str
    timestamps: np.ndarray  # int64 UTC epoch seconds
    dates: np.ndarray       # YYYY-MM-DD strings
    weekdays: np.ndarray    # 0=Mon .. 4=Fri
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray

    def __len__(self) -> int:
        return len(self.close)


def load_yahoo_ohlcv(
    symbol: str,
    interval: str = "1d",
    range_str: str = "10y",
    use_cache: bool = True,
) -> OHLCVData:
    """
    Fetch historical split/dividend-adjusted OHLCV bars via yfinance and cache
    locally as JSON so subsequent runs are deterministic and instantaneous.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    safe_sym = symbol.replace("=", "_").replace("-", "_").replace("^", "_")
    cache_path = os.path.join(CACHE_DIR, f"{safe_sym}_{interval}_{range_str}.json")

    rows: Optional[List[dict]] = None
    if use_cache and os.path.exists(cache_path):
        age_sec = time.time() - os.path.getmtime(cache_path)
        if age_sec < 86400 * 7:
            with open(cache_path, "r", encoding="utf-8") as f:
                rows = json.load(f)

    if rows is None:
        import yfinance as yf

        df = None
        last_err = None
        for attempt in range(4):
            try:
                df = yf.download(
                    symbol,
                    period=range_str,
                    interval=interval,
                    auto_adjust=True,
                    progress=False,
                    threads=False,
                    timeout=25,
                )
                if df is not None and not df.empty:
                    break
            except Exception as exc:
                last_err = exc
            time.sleep(1.5 * (attempt + 1))

        if df is None or df.empty:
            raise RuntimeError(f"Failed to download OHLCV data for {symbol}: {last_err}")
        # Flatten MultiIndex columns if present (yfinance >= 0.2.50)
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)

        rows = []
        seen_dates = set()
        for idx, row in df.iterrows():
            o = float(row["Open"])
            h = float(row["High"])
            l = float(row["Low"])
            c = float(row["Close"])
            v = float(row["Volume"]) if "Volume" in row and not np.isnan(row["Volume"]) else 0.0
            if any(np.isnan(x) or x <= 0.0 for x in (o, h, l, c)):
                continue
            dt = idx.to_pydatetime()
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            date_str = dt.strftime("%Y-%m-%d")
            if date_str in seen_dates:
                continue
            seen_dates.add(date_str)
            rows.append(
                {
                    "ts": int(dt.timestamp()),
                    "date": date_str,
                    "wd": int(dt.weekday()),
                    "o": o,
                    "h": h,
                    "l": l,
                    "c": c,
                    "v": v,
                }
            )
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(rows, f)

    return OHLCVData(
        symbol=symbol,
        timeframe=interval,
        timestamps=np.asarray([r["ts"] for r in rows], dtype=np.int64),
        dates=np.asarray([r["date"] for r in rows], dtype=object),
        weekdays=np.asarray([r["wd"] for r in rows], dtype=np.int32),
        open=np.asarray([r["o"] for r in rows], dtype=np.float64),
        high=np.asarray([r["h"] for r in rows], dtype=np.float64),
        low=np.asarray([r["l"] for r in rows], dtype=np.float64),
        close=np.asarray([r["c"] for r in rows], dtype=np.float64),
        volume=np.asarray([r["v"] for r in rows], dtype=np.float64),
    )


def load_aligned_universe(
    stocks: Sequence[str] = DEFAULT_STOCKS,
    benchmarks: Sequence[str] = BENCHMARK_SYMBOLS,
    range_str: str = "10y",
    use_cache: bool = True,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, OHLCVData], Dict[str, OHLCVData]]:
    """
    Loads all stocks and benchmarks and aligns them onto the common intersection
    of trading dates so every index `t` refers to the exact same US trading day.
    """
    raw_stocks: Dict[str, OHLCVData] = {}
    raw_bench: Dict[str, OHLCVData] = {}

    for sym in benchmarks:
        raw_bench[sym] = load_yahoo_ohlcv(sym, "1d", range_str, use_cache=use_cache)
    for sym in stocks:
        raw_stocks[sym] = load_yahoo_ohlcv(sym, "1d", range_str, use_cache=use_cache)

    # Common date intersection across all symbols
    common_dates = None
    for data in list(raw_bench.values()) + list(raw_stocks.values()):
        dset = set(data.dates.tolist())
        common_dates = dset if common_dates is None else (common_dates & dset)

    sorted_dates = sorted(common_dates)
    dates_arr = np.asarray(sorted_dates, dtype=object)

    def _align(d: OHLCVData) -> OHLCVData:
        idx_map = {dt: idx for idx, dt in enumerate(d.dates.tolist())}
        idxs = np.asarray([idx_map[dt] for dt in sorted_dates], dtype=np.int64)
        return OHLCVData(
            symbol=d.symbol,
            timeframe=d.timeframe,
            timestamps=d.timestamps[idxs],
            dates=d.dates[idxs],
            weekdays=d.weekdays[idxs],
            open=d.open[idxs],
            high=d.high[idxs],
            low=d.low[idxs],
            close=d.close[idxs],
            volume=d.volume[idxs],
        )

    aligned_bench = {k: _align(v) for k, v in raw_bench.items()}
    aligned_stocks = {k: _align(v) for k, v in raw_stocks.items()}
    ref_wd = next(iter(aligned_bench.values())).weekdays
    return dates_arr, ref_wd, aligned_stocks, aligned_bench
