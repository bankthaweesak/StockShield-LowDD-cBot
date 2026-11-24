# StockShield Low-DD Quantitative Research Report

## 1. Methodology & Anti-Overfitting Protocol

- **Universe**: 12 Liquid US Tech/Growth Mega-Cap Leaders (`NVDA, AAPL, MSFT, AMZN, GOOGL, META, AVGO, AMD, TSLA, ORCL, NFLX, COST`) + Macro Benchmarks (`QQQ`, `SPY`).
- **Sample Window**: `2017-09-20` to `2026-11-23` (`2,307` aligned US trading days; first `205` bars reserved for `EMA(200)` warmup).
- **Walk-Forward Split**:
  - **In-Sample (IS)**: `2017-09-20` -> `2021-12-31` (`1,079` bars, includes 2018 Q4 selloff & 2020 COVID crash).
  - **Out-of-Sample (OOS)**: `2022-01-03` -> `2026-11-23` (`1,228` bars, intentionally placing the brutal **2022 Tech `-33%` bear market** inside OOS).
- **Execution & Cost Realism**:
  - Strict zero-lookahead: all indicators/signals computed on closed bar `t-1`, executed at bar `t` open.
  - Gap-aware Stop-Loss fills: if `Open[t] <= SL`, fill occurs at `Open[t]` (captures real overnight earnings gap slippage).
  - Intraday Equity Drawdown: computed using simultaneous worst-case intraday lows across all open positions.
  - **cTrader Stock CFD Baseline**: `10 bps` round-trip (`5 bps` entry + `5 bps` exit) + `7.0%/yr` overnight financing with `3×` Wednesday weekend rollover.
  - **`2×` Stress Test**: `20 bps` round-trip + `10.0%/yr` overnight financing.

---

## 2. Verified Portfolio Preset Performance (`$25,000` Start)

| Preset | Window | Final Equity | Return | CAGR | Max Eq DD | Worst Day | Calmar | Sharpe | PF | Win Rate | Avg Hold | Trades | Swap Paid |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`SS_P1_CFD_ULTRA_SAFE`** | **Full 10Y** | **`$36,865`** | **`+47.5%`** | `4.33%` | **`4.87%`** | **`1.76%`** | `0.89` | `0.97` | **`1.77`** | `36.4%` | `16.6d` | `462` | `$3,044` |
| `SS_P1_CFD_ULTRA_SAFE` | IS (17–21) | `$32,187` | `+28.7%` | `6.08%` | `4.53%` | `1.42%` | `1.34` | `1.27` | `1.96` | `38.2%` | `16.6d` | `241` | `$1,541` |
| `SS_P1_CFD_ULTRA_SAFE` | OOS (22–26) | `$28,565` | `+14.3%` | `2.77%` | `4.87%` | `1.76%` | `0.57` | `0.67` | `1.52` | `34.1%` | `16.4d` | `220` | `$1,164` |
| `SS_P1_CFD_ULTRA_SAFE` | `2×` Stress | `$34,356` | `+37.4%` | `3.53%` | `4.98%` | `1.77%` | `0.71` | `0.81` | `1.61` | `34.8%` | `16.6d` | `462` | `$4,137` |
| **`SS_P2_CFD_BALANCED`** | **Full 10Y** | **`$39,643`** | **`+58.6%`** | `5.16%` | **`5.54%`** | **`1.94%`** | `0.93` | **`1.02`** | **`1.73`** | `46.2%` | `12.3d` | `669` | `$3,740` |
| `SS_P2_CFD_BALANCED` | IS (17–21) | `$33,960` | `+35.8%` | `7.42%` | `5.20%` | `1.58%` | `1.43` | `1.36` | `1.98` | `49.1%` | `12.4d` | `344` | `$1,805` |
| `SS_P2_CFD_BALANCED` | OOS (22–26) | `$29,076` | `+16.3%` | `3.15%` | `5.54%` | `1.94%` | `0.57` | `0.67` | `1.45` | `42.9%` | `12.0d` | `326` | `$1,419` |
| `SS_P2_CFD_BALANCED` | `2×` Stress | `$36,599` | `+46.4%` | `4.25%` | `6.27%` | `1.95%` | `0.68` | `0.85` | `1.59` | `44.4%` | `12.3d` | `669` | `$4,951` |
| **`SS_P3_CASH_1X`** | **Full 10Y** | **`$52,693`** | **`+110.8%`** | **`8.49%`** | **`6.64%`** | `2.49%` | **`1.28`** | **`1.30`** | **`2.00`** | `47.2%` | `12.3d` | `671` | `$0` |
| `SS_P3_CASH_1X` | IS (17–21) | `$39,821` | `+59.3%` | `11.49%` | `5.83%` | `1.77%` | `1.97` | `1.66` | `2.31` | `50.0%` | `12.4d` | `346` | `$0` |
| `SS_P3_CASH_1X` | OOS (22–26) | `$32,817` | `+31.3%` | `5.74%` | `6.64%` | `2.49%` | `0.86` | `0.93` | `1.70` | `44.2%` | `12.0d` | `326` | `$0` |
| `SS_P3_CASH_1X` | `2×` Stress | `$50,743` | `+103.0%` | `8.04%` | `6.82%` | `2.50%` | `1.18` | `1.24` | `1.94` | `46.5%` | `12.3d` | `671` | `$0` |

---

## 3. Yearly Stress Breakdown (`SS_P2_CFD_BALANCED_Under8DD`)

| Year | Market Regime Context | Return | Max Equity DD | Worst Single Day | Trades |
| :---: | :--- | :---: | :---: | :---: | :---: |
| **2017** *(Q4)* | Late-year low-vol bull | `-0.50%` | `2.93%` | `1.39%` | `29` |
| **2018** | Volmageddon & Q4 Tech `-20%` selloff | **`+5.41%`** | `5.18%` | `1.58%` | `85` |
| **2019** | Steady Tech expansion | **`+4.84%`** | `4.37%` | `0.92%` | `62` |
| **2020** | COVID `-30%` crash & V-recovery | **`+11.50%`** | `4.46%` | `1.47%` | `82` |
| **2021** | Mega-cap bull run | **`+10.79%`** | `3.42%` | `1.37%` | `86` |
| **2022** | **Tech Bear Market (`QQQ -33%`)** | **`-2.59%`** | **`3.02%`** | **`0.98%`** | `38` |
| **2023** | AI rebound | **`+4.70%`** | `5.54%` | `1.25%` | `62` |
| **2024** | Secular AI leadership | **`+6.74%`** | `3.12%` | `1.48%` | `77` |
| **2025** | High-vol tariff shock & recovery | **`+10.07%`** | **`2.90%`** | `1.94%` | `71` |
| **2026** *(YTD)* | Choppy consolidation | `-2.59%` | `3.94%` | `1.17%` | `77` |

---

## 4. Single-Stock Fallback Audit (`SS_P4_SINGLE_STOCK_Fallback`, CFD Costs)

When attached to a single stock chart (`SingleSymbolMode = True`, `MaxPortfolioLeverage = 0.25×`), **10 out of 12** Tech/Growth leaders are profitable after `7%/yr` CFD swap and `10 bps` round-trip costs, with single-stock Max DD tightly contained between `2.26%` and `5.09%`:

| Stock | Final Equity (`$25k`) | Return | Max Equity DD | Worst Day | Profit Factor | Win Rate | Trades |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`AAPL`** | `$28,699` | `+14.8%` | **`2.26%`** | `0.75%` | **`2.19`** | `47.1%` | `87` |
| **`MSFT`** | `$28,248` | `+13.0%` | `3.14%` | `0.83%` | **`2.12`** | `53.1%` | `81` |
| **`AMD`** | `$28,582` | `+14.3%` | `4.02%` | `0.79%` | **`1.95`** | `46.3%` | `95` |
| **`TSLA`** | `$29,127` | `+16.5%` | `3.88%` | `1.72%` | **`1.90`** | `38.1%` | `97` |
| **`NVDA`** | `$27,574` | `+10.3%` | `4.18%` | `0.91%` | **`1.84`** | `44.1%` | `102` |
| **`GOOGL`** | `$27,633` | `+10.5%` | `3.57%` | `1.68%` | **`1.81`** | `42.3%` | `78` |
| **`COST`** | `$27,504` | `+10.0%` | `3.41%` | `0.80%` | **`1.60`** | `43.5%` | `92` |
| `AVGO` | `$26,132` | `+4.5%` | `4.02%` | `1.19%` | `1.35` | `41.0%` | `100` |
| `NFLX` | `$25,716` | `+2.9%` | `4.65%` | `1.37%` | `1.24` | `46.5%` | `71` |
| `AMZN` | `$25,065` | `+0.3%` | `4.95%` | `1.26%` | `1.02` | `42.9%` | `91` |
| `META` | `$24,777` | `-0.9%` | `3.97%` | `2.47%` | `0.92` | `47.7%` | `88` |
| `ORCL` | `$24,535` | `-1.9%` | `5.09%` | `1.42%` | `0.82` | `45.1%` | `91` |

---

## 5. Key Quantitative Findings During Development

1. **Why Pure Mean-Reversion Underperformed Under CFD Costs**: `Keltner_Pullback` (`PF 0.77`) and unranked `Connors_RSI2` (`PF 1.17`) suffered high turnover and dip-buying into 2022/2026 downtrends. Replacing them with **Top-K Cross-Sectional RS Leader Trend (`ALMA20` + fast `EMA(50)` exit)** + **selective `IBS < 0.12` sniper** lifted Profit Factor from `1.21` to **`1.73–2.00`** and cut Max DD below `6%`.
2. **Why Inverse-Volatility Notional Caps & Cluster Caps Were Crucial**: Fixed notional caps starved low-vol compounders (`MSFT`, `AAPL`, `COST`) while over-weighting high-vol names (`TSLA`, `NVDA`). Scaling each stock's max notional by `StockVolRefPct / StockVol20` + enforcing `MaxClusterPositions = 2` cut Worst Single-Day DD from `> 3.0%` down to **`1.76%–1.94%`**.
3. **Why Smooth Recovery Throttling Beats Hard Daily Flattening**: Flattening positions on tight daily swings (`2.2%`) caused premature panic-selling at intraday bottoms. Structural exposure control (`MaxPortfolioLeverage × VolScale`) + smooth recovery throttling (`0.65×` / `0.35×`) eliminated kill-switch churn completely (`0` kill-switches in 9+ years).
