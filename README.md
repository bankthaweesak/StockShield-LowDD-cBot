# StockShield Low-DD cBot (`StockShieldLowDdBot`)

Standalone **cTrader Automate (`.NET 6.0`)** quantitative cBot and **zero-lookahead Python walk-forward research suite** engineered to compound profit on **individual US Tech/Growth Mega-Cap Leaders** while enforcing **minimal equity drawdown (`< 5–7%` Max Equity DD, `< 2.0%` Worst Day)** under realistic **cTrader US Stock CFD** overnight swap and spread costs.

---

## Master Preset Mapping (Start Here)

All presets are verified over **9+ years (`2017-09-20` -> `2026-11-23`, `2,307` trading days)** across 12 US Tech/Growth Mega-Cap Leaders (`NVDA, AAPL, MSFT, AMZN, GOOGL, META, AVGO, AMD, TSLA, ORCL, NFLX, COST`) with strict zero-lookahead (`t-1` closed bar -> `t` open fill), gap-aware Stop-Loss slippage, and realistic cTrader Stock CFD costs (`10 bps` round-trip + `7.0%/yr` overnight financing with `3×` Wednesday rollover).

| Tier / Profile | Preset (`.cbotset`) | Chart | 10Y Return (`$25k`) | Max Eq DD | Worst Day | PF | Sharpe / Calmar | OOS (`2022–2026`) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Tier 1 — Ultra-Safe CFD (`< 5%` DD)** | [`SS_P1_CFD_ULTRA_SAFE_Under6DD.cbotset`](cbot/presets/SS_P1_CFD_ULTRA_SAFE_Under6DD.cbotset) | `US TECH 100, D1` | **`$36,865` (`+47.5%`)** | **`4.87%`** | **`1.76%`** | **`1.77`** | `0.97` / `0.89` | `+2.77%/yr` (`4.87%` DD) |
| **Tier 1 — Balanced CFD (`< 6%` DD)** | [`SS_P2_CFD_BALANCED_Under8DD.cbotset`](cbot/presets/SS_P2_CFD_BALANCED_Under8DD.cbotset) | `US TECH 100, D1` | **`$39,643` (`+58.6%`)** | **`5.54%`** | **`1.94%`** | **`1.73`** | `1.02` / `0.93` | `+3.15%/yr` (`5.54%` DD) |
| **Tier 1 — Cash `1.0×` (`< 7%` DD)** | [`SS_P3_CASH_1X_Under8DD.cbotset`](cbot/presets/SS_P3_CASH_1X_Under8DD.cbotset) | `US TECH 100, D1` | **`$52,693` (`+110.8%`)** | **`6.64%`** | `2.49%` | **`2.00`** | `1.30` / `1.28` | `+5.74%/yr` (`6.64%` DD) |
| **Tier 1 — Single-Stock Fallback** | [`SS_P4_SINGLE_STOCK_Fallback.cbotset`](cbot/presets/SS_P4_SINGLE_STOCK_Fallback.cbotset) | Any Stock `D1` | `10/12` profitable | `2.26%–5.09%` | `0.75%–1.72%` | `1.60–2.19` | — | Positive across leaders |
| **Tier 2 — Balanced Growth CFD (`~15%` DD)** | [`SS_P5_GROWTH_15DD_CFD.cbotset`](cbot/presets/SS_P5_GROWTH_15DD_CFD.cbotset) | `US TECH 100, D1` | **`$100,333` (`+301.3%`)** | **`15.49%`** | `5.30%` | `1.57` | `1.06` / `1.06` | **`+9.26%/yr`** (`15.49%` DD) |
| **Tier 2 — Balanced Growth Cash (`~14%` DD)** | [`SS_P6_GROWTH_15DD_Cash.cbotset`](cbot/presets/SS_P6_GROWTH_15DD_Cash.cbotset) | `US TECH 100, D1` | **`$133,422` (`+433.7%`)** | **`14.24%`** | `4.65%` | **`1.78`** | **`1.33` / `1.41`** | **`+12.53%/yr`** (`14.24%` DD) |
| **Tier 3 — Trend-Hold Core CFD** | [`SS_P7_TRENDHOLD_CORE_CFD.cbotset`](cbot/presets/SS_P7_TRENDHOLD_CORE_CFD.cbotset) | `US TECH 100, D1` | **`$123,746` (`+395.0%`)** | `27.33%` | `7.77%` | `1.41` | `0.94` / `0.70` | **`+10.76%/yr`** (`27.91%` DD) |
| **Tier 3 — Trend-Hold Core Cash** | [`SS_P8_TRENDHOLD_CORE_Cash.cbotset`](cbot/presets/SS_P8_TRENDHOLD_CORE_Cash.cbotset) | `US TECH 100, D1` | **`$198,385` (`+693.5%`)** | `25.85%` | `7.76%` | **`1.71`** | `1.19` / `0.98` | **`+15.94%/yr`** (`26.33%` DD) |

> **Out-of-Universe Proof (`python/backtest_multi_universe.py`):** All 3 tiers are profitable across **18 unseen stocks** — 10 Multi-Sector Blue-Chips (`LLY, JPM, V, MA, WMT, HD, CAT, XOM, UNH, PG`) and 8 Software/Semi Equipment (`CRM, ADBE, INTU, PANW, LRCX, KLAC, AMAT, QCOM`) — with `SS_P8_TRENDHOLD_CORE_Cash` beating Buy & Hold's Calmar ratio on **3/3 universes** while cutting Max DD by **50%–60%**.

---

## Anti-Drawdown Architecture ("StockShield")

1. **Macro Regime Gate (`QQQ` + `SPY`)**:
   - `GREEN` (Risk-On): `QQQ > EMA(50) & EMA(200)` and `20d Realized Vol < 26%` -> `100%` risk.
   - `YELLOW` (Caution): `QQQ < EMA(50)` or `20d Vol >= 26%` -> scaled down (`0.40×` Trend, `0.50×` IBS).
   - `RED` (Bear / Crash): `QQQ < EMA(200) & SPY < EMA(200)` or `20d Vol >= 36%` -> **100% Cash** (blocks all new entries).
2. **Dynamic Benchmark Volatility Targeting**: Scales portfolio leverage inversely with `QQQ` 20-day realized volatility (`TargetBenchmarkVolPct / QqqVol20`, floor `0.35×`).
3. **Inverse-Volatility Per-Stock Notional Cap**: Caps each stock's notional inversely by its own 20-day volatility (`MaxSingleStockNotionalPct * (StockVolRefPct / StockVol20)`), preventing high-beta overnight earnings gaps (`NVDA`, `TSLA`) from dominating daily P&L.
4. **Cross-Sectional `RS_Score` Ranking + Sub-Sector Cluster Caps**: Ranks all stocks daily by 60-day Risk-Adjusted Momentum (`Return_60d% / Vol_20d%`), focuses on the Top-7 leaders, and enforces `MaxClusterPositions = 2` (`SEMIS`, `CLOUD`, `CONSUMER_TECH`, `DEFENSIVE_GROWTH`) and `MaxPositionsPerStock = 1`.
5. **Orthogonal Engines & Fast Exits**:
   - **Leader `ALMA20` Trend**: Enters Top-K RS leaders above `EMA(200)`, `EMA(50)`, and rising `ALMA(20)`; protected by `2.0 ATR` atomic SL, `1.0R` Break-Even lock, `3.2 ATR` Chandelier trail, and **fast `EMA(50)` trend-break exit**.
   - **`IBS` Sniper (`SS_P2`/`SS_P3`)**: Ultra-short 1–5 day mean-reversion overlay (`IBS < 0.12` above `EMA(50)` & `EMA(200)`, exit `Close > High[t-1]` or 5-day time-stop).
   - **Smooth Recovery DD Throttling + `LocalStorage` Persistence**: Throttles risk to `0.65×` at `2.2%` DD and `0.35×` at `4.0%` DD (never deadlocks), with cooldown-protected emergency kill-switch (`KillCooldownDays = 10`).

---

## Quick Start (cTrader Automate)

1. Copy [`cbot/src/StockShieldLowDdBot.cs`](cbot/src/StockShieldLowDdBot.cs) into cTrader Automate (or build locally with `dotnet build cbot/src/StockShieldLowDdBot.csproj -c Release`).
2. Attach to a **`US TECH 100` (`D1`)** chart (or any individual stock `D1` chart for Single-Stock mode).
3. Import one of the 4 verified presets from [`cbot/presets/`](cbot/presets/).
4. Enable `AutoAliasTickers = True` (default) to automatically map `NVDA`, `AAPL`, `QQQ`, `SPY`, etc. to your broker's exact CFD symbol names (`.US`, `_CFD`, `US TECH 100`, `US 500`).
5. Check the **Live On-Chart HUD** and **Log** tab to confirm resolved symbols and active regime state.

---

## Local Verification & Research Reproduction

```bash
# 1. Run Python unit & zero-lookahead invariance tests + .cbotset schema parity check
.venv/bin/pytest -v tests/

# 2. Reproduce full 10Y / IS / OOS / 2x-Stress / Single-Stock walk-forward audit
.venv/bin/python python/research_optimize.py

# 3. Regenerate and verify all 4 .cbotset presets against StockShieldLowDdBot.cs
.venv/bin/python python/generate_presets.py

# 4. Compile the .NET 6.0 cTrader cBot
dotnet build cbot/src/StockShieldLowDdBot.csproj -c Release
```

See [`RESEARCH_REPORT.md`](RESEARCH_REPORT.md) for the complete quantitative audit, yearly breakdown, and per-stock isolation tables.
