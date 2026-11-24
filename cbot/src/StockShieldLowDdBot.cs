#pragma warning disable 0618
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using cAlgo.API;
using cAlgo.API.Internals;

namespace cAlgo.Robots
{
    /// <summary>
    /// StockShieldLowDdBot v1.0 (cTrader Automate .NET 6.0).
    ///
    /// Dedicated minimal-drawdown quantitative cBot for individual US Tech/Growth
    /// Mega-Cap Leaders (multi-symbol portfolio mode with automatic single-stock
    /// fallback). Engineered for 1:1 mathematical parity with the StockShield
    /// zero-lookahead Python walk-forward research suite:
    ///   1. Macro Regime Gate (QQQ + SPY EMA50/200 & 20d Realized Volatility).
    ///   2. Dynamic Benchmark Volatility Targeting & Inverse-Vol Per-Stock Notional Caps.
    ///   3. Top-K Cross-Sectional 60-day Risk-Adjusted Momentum (RS_Score) Ranking.
    ///   4. Orthogonal Engines: Leader ALMA20 Trend (with fast EMA50 exit, 1.0R BE &
    ///      Chandelier trail), IBS Sniper (1-5d MR), and optional Connors RSI(2).
    ///   5. Sub-Sector Cluster Caps (Semis / Cloud / Consumer Tech / Defensive).
    ///   6. Persistent LocalStorage DD state, cooldown-protected emergency kill-switch,
    ///      atomic SL attachment with sub-pip refinement, and Live On-Chart HUD.
    /// </summary>
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.FullAccess)]
    public class StockShieldLowDdBot : Robot
    {
        private const string BotVersion = "v1.0";
        private const string BaseLabel = "StockShield";

        // =====================================================================
        // 0. UNIVERSE, MODE & BROKER ALIASING
        // =====================================================================
        [Parameter("Portfolio Tag", DefaultValue = "SS_P2_CFD", Group = "0. Universe & Mode")]
        public string PortfolioTag { get; set; }

        [Parameter("Single-Stock Chart Mode?", DefaultValue = false, Group = "0. Universe & Mode")]
        public bool SingleSymbolMode { get; set; }

        [Parameter("Stock Universe (CSV)", DefaultValue = "NVDA,AAPL,MSFT,AMZN,GOOGL,META,AVGO,AMD,TSLA,ORCL,NFLX,COST", Group = "0. Universe & Mode")]
        public string SymbolsCsv { get; set; }

        [Parameter("Primary Benchmark (QQQ/NAS100)", DefaultValue = "QQQ", Group = "0. Universe & Mode")]
        public string PrimaryBenchmark { get; set; }

        [Parameter("Secondary Benchmark (SPY/SP500)", DefaultValue = "SPY", Group = "0. Universe & Mode")]
        public string SecondaryBenchmark { get; set; }

        [Parameter("Auto-Alias Broker Tickers?", DefaultValue = true, Group = "0. Universe & Mode")]
        public bool AutoAliasTickers { get; set; }

        // =====================================================================
        // 1. MACRO REGIME GATE & VOLATILITY TARGETING
        // =====================================================================
        [Parameter("Enable Macro Regime Gate?", DefaultValue = true, Group = "1. Macro Regime & Vol Targeting")]
        public bool UseMacroGate { get; set; }

        [Parameter("Benchmark Caution Vol (% Ann.)", DefaultValue = 26.0, MinValue = 10.0, MaxValue = 80.0, Step = 1.0, Group = "1. Macro Regime & Vol Targeting")]
        public double VolCautionPct { get; set; }

        [Parameter("Benchmark Crash Vol (% Ann.)", DefaultValue = 36.0, MinValue = 15.0, MaxValue = 100.0, Step = 1.0, Group = "1. Macro Regime & Vol Targeting")]
        public double VolCrashPct { get; set; }

        [Parameter("Yellow Regime Trend Mult", DefaultValue = 0.40, MinValue = 0.0, MaxValue = 1.0, Step = 0.05, Group = "1. Macro Regime & Vol Targeting")]
        public double YellowTrendMult { get; set; }

        [Parameter("Yellow Regime MR Mult", DefaultValue = 0.50, MinValue = 0.0, MaxValue = 1.0, Step = 0.05, Group = "1. Macro Regime & Vol Targeting")]
        public double YellowMrMult { get; set; }

        [Parameter("Enable Dynamic Vol Targeting?", DefaultValue = true, Group = "1. Macro Regime & Vol Targeting")]
        public bool UseVolTargeting { get; set; }

        [Parameter("Target Benchmark Vol (% Ann.)", DefaultValue = 16.5, MinValue = 8.0, MaxValue = 40.0, Step = 0.5, Group = "1. Macro Regime & Vol Targeting")]
        public double TargetBenchmarkVolPct { get; set; }

        [Parameter("Min Vol Scale Floor", DefaultValue = 0.35, MinValue = 0.1, MaxValue = 1.0, Step = 0.05, Group = "1. Macro Regime & Vol Targeting")]
        public double MinVolScale { get; set; }

        // =====================================================================
        // 2. ENGINE 1: LEADER ALMA20 TREND (TOP-K RS + FAST EMA50 EXIT)
        // =====================================================================
        [Parameter("Enable Leader Trend Engine?", DefaultValue = true, Group = "2. Engine: Leader ALMA20 Trend")]
        public bool EnableTrend { get; set; }

        [Parameter("Trend Top-K RS Leaders", DefaultValue = 7, MinValue = 1, MaxValue = 30, Group = "2. Engine: Leader ALMA20 Trend")]
        public int TrendTopK { get; set; }

        [Parameter("Trend Risk Per Trade (%)", DefaultValue = 0.65, MinValue = 0.05, MaxValue = 3.0, Step = 0.05, Group = "2. Engine: Leader ALMA20 Trend")]
        public double TrendRiskPct { get; set; }

        [Parameter("Trend Min 60d RS Score", DefaultValue = 0.20, MinValue = -2.0, MaxValue = 5.0, Step = 0.05, Group = "2. Engine: Leader ALMA20 Trend")]
        public double TrendMinRsScore { get; set; }

        [Parameter("Trend Initial SL (x ATR14)", DefaultValue = 2.0, MinValue = 0.5, MaxValue = 6.0, Step = 0.1, Group = "2. Engine: Leader ALMA20 Trend")]
        public double TrendSlAtrMult { get; set; }

        [Parameter("Trend Chandelier Trail (x ATR22)", DefaultValue = 3.2, MinValue = 1.0, MaxValue = 8.0, Step = 0.1, Group = "2. Engine: Leader ALMA20 Trend")]
        public double TrendTrailAtrMult { get; set; }

        [Parameter("Trend Break-Even Lock (R)", DefaultValue = 1.0, MinValue = 0.0, MaxValue = 5.0, Step = 0.1, Group = "2. Engine: Leader ALMA20 Trend")]
        public double TrendBeR { get; set; }

        [Parameter("Trend Fast Exit Below EMA(50)?", DefaultValue = true, Group = "2. Engine: Leader ALMA20 Trend")]
        public bool TrendFastExitEma50 { get; set; }

        // =====================================================================
        // 3. ENGINE 2: IBS SNIPER (ULTRA-SHORT 1-5D MEAN REVERSION)
        // =====================================================================
        [Parameter("Enable IBS Sniper Engine?", DefaultValue = true, Group = "3. Engine: IBS Sniper")]
        public bool EnableIbs { get; set; }

        [Parameter("IBS Top-K RS Candidates", DefaultValue = 8, MinValue = 1, MaxValue = 30, Group = "3. Engine: IBS Sniper")]
        public int IbsTopK { get; set; }

        [Parameter("IBS Risk Per Trade (%)", DefaultValue = 0.45, MinValue = 0.05, MaxValue = 3.0, Step = 0.05, Group = "3. Engine: IBS Sniper")]
        public double IbsRiskPct { get; set; }

        [Parameter("IBS Entry Threshold (<)", DefaultValue = 0.12, MinValue = 0.02, MaxValue = 0.35, Step = 0.01, Group = "3. Engine: IBS Sniper")]
        public double IbsThreshold { get; set; }

        [Parameter("IBS Require Close > EMA(50)?", DefaultValue = true, Group = "3. Engine: IBS Sniper")]
        public bool IbsRequireAboveEma50 { get; set; }

        [Parameter("IBS Initial SL (x ATR14)", DefaultValue = 2.5, MinValue = 0.5, MaxValue = 6.0, Step = 0.1, Group = "3. Engine: IBS Sniper")]
        public double IbsSlAtrMult { get; set; }

        [Parameter("IBS Max Hold Days", DefaultValue = 5, MinValue = 1, MaxValue = 20, Group = "3. Engine: IBS Sniper")]
        public int IbsMaxHoldDays { get; set; }

        // =====================================================================
        // 4. ENGINE 3: CONNORS RSI(2) SHIELD (OPTIONAL SHORT-HOLD MR)
        // =====================================================================
        [Parameter("Enable Connors RSI(2) Engine?", DefaultValue = false, Group = "4. Engine: Connors RSI(2)")]
        public bool EnableConnors { get; set; }

        [Parameter("Connors Risk Per Trade (%)", DefaultValue = 0.50, MinValue = 0.05, MaxValue = 3.0, Step = 0.05, Group = "4. Engine: Connors RSI(2)")]
        public double ConnorsRiskPct { get; set; }

        [Parameter("Connors RSI(2) Threshold (<)", DefaultValue = 12.0, MinValue = 2.0, MaxValue = 30.0, Step = 1.0, Group = "4. Engine: Connors RSI(2)")]
        public double ConnorsRsiThresh { get; set; }

        [Parameter("Connors Use SMA(8) Exit? (False=SMA5)", DefaultValue = true, Group = "4. Engine: Connors RSI(2)")]
        public bool ConnorsUseSma8 { get; set; }

        [Parameter("Connors Initial SL (x ATR14)", DefaultValue = 2.8, MinValue = 0.5, MaxValue = 6.0, Step = 0.1, Group = "4. Engine: Connors RSI(2)")]
        public double ConnorsSlAtrMult { get; set; }

        [Parameter("Connors Max Hold Days", DefaultValue = 8, MinValue = 2, MaxValue = 25, Group = "4. Engine: Connors RSI(2)")]
        public int ConnorsMaxHoldDays { get; set; }

        // =====================================================================
        // 5. PORTFOLIO CAPS, INVERSE-VOL SIZING & DD GUARDRAILS
        // =====================================================================
        [Parameter("Max Concurrent Positions", DefaultValue = 6, MinValue = 1, MaxValue = 30, Group = "5. Portfolio Shield & DD Guardrails")]
        public int MaxConcurrentPositions { get; set; }

        [Parameter("Max Positions Per Stock", DefaultValue = 1, MinValue = 1, MaxValue = 4, Group = "5. Portfolio Shield & DD Guardrails")]
        public int MaxPositionsPerStock { get; set; }

        [Parameter("Max Positions Per Cluster", DefaultValue = 2, MinValue = 1, MaxValue = 12, Group = "5. Portfolio Shield & DD Guardrails")]
        public int MaxClusterPositions { get; set; }

        [Parameter("Max Single-Stock Notional (%)", DefaultValue = 10.5, MinValue = 2.0, MaxValue = 50.0, Step = 0.5, Group = "5. Portfolio Shield & DD Guardrails")]
        public double MaxSingleStockNotionalPct { get; set; }

        [Parameter("Inverse-Vol Stock Ref (% Ann.)", DefaultValue = 20.0, MinValue = 10.0, MaxValue = 60.0, Step = 1.0, Group = "5. Portfolio Shield & DD Guardrails")]
        public double StockVolRefPct { get; set; }

        [Parameter("Max Portfolio Leverage (x Eq)", DefaultValue = 0.52, MinValue = 0.1, MaxValue = 3.0, Step = 0.02, Group = "5. Portfolio Shield & DD Guardrails")]
        public double MaxPortfolioLeverage { get; set; }

        [Parameter("Falling-Knife Max Drop (x ATR14)", DefaultValue = 3.5, MinValue = 1.5, MaxValue = 10.0, Step = 0.5, Group = "5. Portfolio Shield & DD Guardrails")]
        public double MaxDropAtr { get; set; }

        [Parameter("Tier-1 DD Throttle % (0.65x)", DefaultValue = 2.2, MinValue = 0.0, MaxValue = 20.0, Step = 0.2, Group = "5. Portfolio Shield & DD Guardrails")]
        public double HalfRiskDdPct { get; set; }

        [Parameter("Tier-2 DD Throttle % (0.35x)", DefaultValue = 4.0, MinValue = 0.0, MaxValue = 30.0, Step = 0.2, Group = "5. Portfolio Shield & DD Guardrails")]
        public double QuarterRiskDdPct { get; set; }

        [Parameter("Max Daily Loss % (0 = Off)", DefaultValue = 0.0, MinValue = 0.0, MaxValue = 15.0, Step = 0.2, Group = "5. Portfolio Shield & DD Guardrails")]
        public double MaxDailyLossPct { get; set; }

        [Parameter("Emergency Max Total DD % (0 = Off)", DefaultValue = 7.5, MinValue = 0.0, MaxValue = 40.0, Step = 0.5, Group = "5. Portfolio Shield & DD Guardrails")]
        public double MaxTotalDrawdownPct { get; set; }

        [Parameter("Flatten All on Emergency DD?", DefaultValue = true, Group = "5. Portfolio Shield & DD Guardrails")]
        public bool FlattenOnDdBreach { get; set; }

        [Parameter("Kill-Switch Cooldown (Days)", DefaultValue = 10, MinValue = 1, MaxValue = 60, Group = "5. Portfolio Shield & DD Guardrails")]
        public int KillCooldownDays { get; set; }

        [Parameter("Daily Reset UTC Offset (Hours)", DefaultValue = 0, MinValue = -12, MaxValue = 14, Group = "5. Portfolio Shield & DD Guardrails")]
        public int DailyResetUtcOffsetHours { get; set; }

        [Parameter("Persist DD State (LocalStorage)?", DefaultValue = true, Group = "5. Portfolio Shield & DD Guardrails")]
        public bool PersistDdState { get; set; }

        [Parameter("Show Live Shield HUD?", DefaultValue = true, Group = "5. Portfolio Shield & DD Guardrails")]
        public bool EnableHud { get; set; }

        [Parameter("Verbose Logs?", DefaultValue = true, Group = "5. Portfolio Shield & DD Guardrails")]
        public bool VerboseLogs { get; set; }

        // =====================================================================
        // 6. TIER 3: TREND-HOLD CORE MODE (WIDE EMA + BEAR SHIELD)
        // =====================================================================
        [Parameter("Enable Trend-Hold Core Mode?", DefaultValue = false, Group = "6. Tier 3: Trend-Hold Core Mode")]
        public bool EnableTrendHoldCore { get; set; }

        [Parameter("Trend-Hold Exit EMA Period", DefaultValue = 100, MinValue = 30, MaxValue = 250, Step = 10, Group = "6. Tier 3: Trend-Hold Core Mode")]
        public int TrendHoldExitEmaPeriod { get; set; }

        [Parameter("Trend-Hold Rebalance (Trading Days)", DefaultValue = 21, MinValue = 0, MaxValue = 126, Group = "6. Tier 3: Trend-Hold Core Mode")]
        public int TrendHoldRebalDays { get; set; }

        [Parameter("Trend-Hold Use Benchmark EMA(200) Gate?", DefaultValue = true, Group = "6. Tier 3: Trend-Hold Core Mode")]
        public bool TrendHoldUseQqq200Gate { get; set; }

        // =====================================================================
        // INTERNAL STATE & DATA STRUCTURES
        // =====================================================================
        private const int RegimeRed = 0;
        private const int RegimeYellow = 1;
        private const int RegimeGreen = 2;

        private sealed class StockContext
        {
            public string CanonicalTicker;
            public string Cluster;
            public Symbol Sym;
            public Bars DailyBars;
            public double LastRsScore;
            public double LastVol20;
            public DateTime LastEvaluatedBarTime;
        }

        private sealed class PosMeta
        {
            public string Engine;
            public string CanonicalTicker;
            public double InitialRiskDist;
            public double HighestHigh;
            public bool BeLocked;
            public DateTime EntryDayUtc;
        }

        private readonly List<StockContext> _universe = new List<StockContext>();
        private readonly Dictionary<long, PosMeta> _posMeta = new Dictionary<long, PosMeta>();

        private Bars _primaryBenchBars;
        private Bars _secondaryBenchBars;

        private double _peakEquity;
        private double _killAnchorPeak;
        private double _dayAnchorEquity;
        private DateTime _curResetDate;
        private DateTime _killCooldownUntilUtc = DateTime.MinValue;
        private bool _dailyHalted;
        private int _barsElapsed;

        private int _lastRegime = RegimeGreen;
        private double _lastBenchVol20 = 18.0;
        private double _lastVolScale = 1.0;

        private string StoragePrefix => $"{BaseLabel}_{PortfolioTag}_{Account.Number}";

        private static readonly Dictionary<string, string> ClusterMap = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            { "NVDA", "SEMIS" }, { "AMD", "SEMIS" }, { "AVGO", "SEMIS" },
            { "MSFT", "CLOUD" }, { "AMZN", "CLOUD" }, { "GOOGL", "CLOUD" }, { "META", "CLOUD" }, { "ORCL", "CLOUD" },
            { "AAPL", "CONSUMER_TECH" }, { "TSLA", "CONSUMER_TECH" }, { "NFLX", "CONSUMER_TECH" },
            { "COST", "DEFENSIVE_GROWTH" }
        };

        private static readonly Dictionary<string, string[]> BrokerAliases = new Dictionary<string, string[]>(StringComparer.OrdinalIgnoreCase)
        {
            { "QQQ", new[] { "QQQ", "QQQ.US", "US TECH 100", "USTEC", "NAS100", "NDX", "US100", "USTECH100" } },
            { "SPY", new[] { "SPY", "SPY.US", "US 500", "US500", "SPX500", "SP500" } },
            { "NVDA", new[] { "NVDA", "NVDA.US", "#NVDA", "NVDA_CFD", "NVDA.NAS" } },
            { "AAPL", new[] { "AAPL", "AAPL.US", "#AAPL", "AAPL_CFD", "AAPL.NAS" } },
            { "MSFT", new[] { "MSFT", "MSFT.US", "#MSFT", "MSFT_CFD", "MSFT.NAS" } },
            { "AMZN", new[] { "AMZN", "AMZN.US", "#AMZN", "AMZN_CFD", "AMZN.NAS" } },
            { "GOOGL", new[] { "GOOGL", "GOOGL.US", "#GOOGL", "GOOGL_CFD", "GOOG", "GOOG.US" } },
            { "META", new[] { "META", "META.US", "#META", "META_CFD", "META.NAS" } },
            { "AVGO", new[] { "AVGO", "AVGO.US", "#AVGO", "AVGO_CFD", "AVGO.NAS" } },
            { "AMD", new[] { "AMD", "AMD.US", "#AMD", "AMD_CFD", "AMD.NAS" } },
            { "TSLA", new[] { "TSLA", "TSLA.US", "#TSLA", "TSLA_CFD", "TSLA.NAS" } },
            { "ORCL", new[] { "ORCL", "ORCL.US", "#ORCL", "ORCL_CFD", "ORCL.NYS" } },
            { "NFLX", new[] { "NFLX", "NFLX.US", "#NFLX", "NFLX_CFD", "NFLX.NAS" } },
            { "COST", new[] { "COST", "COST.US", "#COST", "COST_CFD", "COST.NAS" } }
        };

        // =====================================================================
        // LIFECYCLE
        // =====================================================================
        protected override void OnStart()
        {
            _peakEquity = Account.Equity;
            _killAnchorPeak = Account.Equity;
            _dayAnchorEquity = Account.Equity;
            _curResetDate = GetResetDate(Server.Time);

            LoadPersistedState();
            InitBenchmarks();
            InitUniverse();
            RehydrateOpenPositions();

            Positions.Closed += OnPositionClosed;

            Print($"[{BaseLabel} {BotVersion}] Started | Tag={PortfolioTag} | Mode={(SingleSymbolMode || _universe.Count == 1 ? "SINGLE-STOCK" : "PORTFOLIO")} | Resolved={_universe.Count} stocks | PeakEq={_peakEquity:F2}");
            UpdateHud();
        }

        protected override void OnStop()
        {
            SavePersistedState();
        }

        protected override void OnTick()
        {
            CheckDailyReset();
            UpdatePeakEquity();
            CheckIntradayDdGuardrails();
        }

        protected override void OnBar()
        {
            CheckDailyReset();
            UpdatePeakEquity();

            if (CheckIntradayDdGuardrails())
            {
                UpdateHud();
                return;
            }

            // 1. Evaluate Macro Regime & Benchmark Vol Scale from prior closed bar
            EvaluateMacroRegime();
            _barsElapsed++;

            if (EnableTrendHoldCore)
            {
                EvaluateTrendHoldCore();
            }
            else
            {
                // 2. Process Open-of-Bar Exits & EOD Trails on all open bot positions
                ManageExistingPositions();

                // 3. Evaluate RS-Ranked Entries across universe
                if (Server.Time >= _killCooldownUntilUtc && !_dailyHalted && _lastRegime != RegimeRed)
                {
                    EvaluateEntries();
                }
            }

            SavePersistedState();
            UpdateHud();
        }

        private bool IsPrimaryBenchAboveEma200()
        {
            if (!TrendHoldUseQqq200Gate || _primaryBenchBars == null || _primaryBenchBars.Count < 210)
                return true;
            int idx = _primaryBenchBars.Count - 2;
            double[] closes = ExtractCloses(_primaryBenchBars, idx + 1);
            double ema200 = CalcEmaLast(closes, 200);
            return !double.IsNaN(ema200) && closes[closes.Length - 1] > ema200;
        }

        private void EvaluateTrendHoldCore()
        {
            bool qOk = IsPrimaryBenchAboveEma200();
            List<Position> botPositions = GetBotPositions();

            // 1. Exits: close below TrendHoldExitEmaPeriod or benchmark below EMA(200)
            foreach (Position pos in botPositions.ToList())
            {
                StockContext ctx = _universe.FirstOrDefault(u => u.Sym.Name.Equals(pos.SymbolName, StringComparison.OrdinalIgnoreCase));
                if (ctx == null || ctx.DailyBars == null || ctx.DailyBars.Count < 210)
                    continue;
                int s = ctx.DailyBars.Count - 2;
                double[] closes = ExtractCloses(ctx.DailyBars, s + 1);
                double exEma = CalcEmaLast(closes, TrendHoldExitEmaPeriod);
                if (!qOk || (!double.IsNaN(exEma) && closes[closes.Length - 1] < exEma))
                {
                    ClosePosition(pos);
                    if (VerboseLogs)
                        Print($"[{BaseLabel} TRENDHOLD EXIT] {ctx.CanonicalTicker} closed (BenchOK={qOk}).");
                }
            }

            if (!qOk || Server.Time < _killCooldownUntilUtc || _dailyHalted)
                return;

            // 2. Update RS scores for ranking
            foreach (StockContext ctx in _universe)
            {
                if (ctx.DailyBars == null || ctx.DailyBars.Count < 210)
                {
                    ctx.LastRsScore = -999.0;
                    continue;
                }
                int s = ctx.DailyBars.Count - 2;
                double[] closes = ExtractCloses(ctx.DailyBars, s + 1);
                double vol20 = CalcRealizedVolAnnLast(closes, 20);
                ctx.LastVol20 = (!double.IsNaN(vol20) && vol20 > 10.0) ? vol20 : 30.0;
                ctx.LastRsScore = CalcRsScoreLast(closes, ctx.LastVol20, 60);
            }

            int maxSlots = Math.Min(_universe.Count, MaxConcurrentPositions);
            double slotNotional = Math.Min(
                Account.Equity * (MaxSingleStockNotionalPct / 100.0),
                (Account.Equity * MaxPortfolioLeverage) / Math.Max(maxSlots, 1)
            );

            // 3. Fill open slots for stocks above EMA(50) & ExitEMA
            botPositions = GetBotPositions();
            foreach (StockContext ctx in _universe.OrderByDescending(u => u.LastRsScore))
            {
                if (botPositions.Count >= maxSlots)
                    break;
                if (botPositions.Any(p => p.SymbolName.Equals(ctx.Sym.Name, StringComparison.OrdinalIgnoreCase)))
                    continue;
                if (ctx.DailyBars == null || ctx.DailyBars.Count < 210)
                    continue;

                int s = ctx.DailyBars.Count - 2;
                double[] closes = ExtractCloses(ctx.DailyBars, s + 1);
                double c = closes[closes.Length - 1];
                double ema50 = CalcEmaLast(closes, 50);
                double exEma = CalcEmaLast(closes, TrendHoldExitEmaPeriod);
                double atr14 = CalcAtrLast(ctx.DailyBars, s + 1, 14);
                if (double.IsNaN(ema50) || double.IsNaN(exEma) || double.IsNaN(atr14) || atr14 <= 0.0)
                    continue;

                if (c > ema50 && c > exEma)
                {
                    double entryPx = ctx.Sym.Ask;
                    double valuePerUnitMove = ctx.Sym.PipValue / ctx.Sym.PipSize;
                    if (entryPx <= 0.0 || valuePerUnitMove <= 0.0)
                        continue;
                    double currPortNotional = ComputeTotalNotional(botPositions);
                    double remPortNotional = Math.Max(0.0, Account.Equity * MaxPortfolioLeverage - currPortNotional);
                    double notional = Math.Min(slotNotional, remPortNotional);
                    double units = ctx.Sym.NormalizeVolumeInUnits(notional / (entryPx * valuePerUnitMove), RoundingMode.Down);
                    if (units < ctx.Sym.VolumeInUnitsMin)
                        continue;

                    double slDist = 5.0 * atr14; // catastrophe SL only
                    double slPrice = RoundPrice(ctx.Sym, Math.Max(ctx.Sym.TickSize * 5, entryPx - slDist));
                    double slPips = Math.Max(1.0, (entryPx - slPrice) / ctx.Sym.PipSize);
                    string label = MakeLabel("TRENDHOLD", ctx.CanonicalTicker);

                    TradeResult res = ExecuteMarketOrder(TradeType.Buy, ctx.Sym.Name, units, label, slPips, null);
                    if (res.IsSuccessful && res.Position != null)
                    {
                        botPositions.Add(res.Position);
                        if (VerboseLogs)
                            Print($"[{BaseLabel} TRENDHOLD ENTRY] {ctx.CanonicalTicker} | Units={units} | Entry={res.Position.EntryPrice:F2} | CatSL={slPrice:F2}");
                    }
                }
            }
        }

        // =====================================================================
        // INITIALIZATION & BROKER ALIAS RESOLUTION
        // =====================================================================
        private Symbol TryResolveSymbol(string rawTicker, out string aliasUsed)
        {
            aliasUsed = null;
            string clean = rawTicker.Trim();
            if (string.IsNullOrEmpty(clean))
                return null;

            Symbol direct = null;
            try { direct = Symbols.GetSymbol(clean); } catch { direct = null; }
            if (direct != null)
                return direct;

            if (!AutoAliasTickers)
                return null;

            if (BrokerAliases.TryGetValue(clean, out string[] candidates))
            {
                foreach (string alt in candidates)
                {
                    Symbol s = null;
                    try { s = Symbols.GetSymbol(alt); } catch { s = null; }
                    if (s != null)
                    {
                        aliasUsed = alt;
                        return s;
                    }
                }
            }

            // Generic stock suffixes fallback
            string[] suffixes = { ".US", "_CFD", ".NAS", ".NYS" };
            foreach (string suf in suffixes)
            {
                Symbol s = null;
                try { s = Symbols.GetSymbol(clean + suf); } catch { s = null; }
                if (s != null)
                {
                    aliasUsed = clean + suf;
                    return s;
                }
            }
            return null;
        }

        private void InitBenchmarks()
        {
            if (!UseMacroGate && !UseVolTargeting)
                return;

            Symbol pSym = TryResolveSymbol(PrimaryBenchmark, out string pAlias);
            if (pSym != null)
            {
                _primaryBenchBars = (pSym.Name.Equals(SymbolName, StringComparison.OrdinalIgnoreCase) && TimeFrame == TimeFrame.Daily)
                    ? Bars
                    : MarketData.GetBars(TimeFrame.Daily, pSym.Name);
                if (VerboseLogs)
                    Print($"[{BaseLabel}] Primary Benchmark '{PrimaryBenchmark}' -> '{pSym.Name}'{(pAlias != null ? " (alias)" : "")}");
            }
            else
            {
                Print($"[{BaseLabel} WARN] Primary Benchmark '{PrimaryBenchmark}' not found on broker; falling back to attached chart '{SymbolName}'.");
                _primaryBenchBars = MarketData.GetBars(TimeFrame.Daily, SymbolName);
            }

            Symbol sSym = TryResolveSymbol(SecondaryBenchmark, out string sAlias);
            if (sSym != null)
            {
                _secondaryBenchBars = MarketData.GetBars(TimeFrame.Daily, sSym.Name);
                if (VerboseLogs)
                    Print($"[{BaseLabel}] Secondary Benchmark '{SecondaryBenchmark}' -> '{sSym.Name}'{(sAlias != null ? " (alias)" : "")}");
            }
            else
            {
                _secondaryBenchBars = _primaryBenchBars;
            }
        }

        private void InitUniverse()
        {
            _universe.Clear();
            List<string> rawTickers = new List<string>();

            if (SingleSymbolMode)
            {
                rawTickers.Add(SymbolName);
            }
            else
            {
                foreach (string part in (SymbolsCsv ?? string.Empty).Split(new[] { ',', ';', ' ' }, StringSplitOptions.RemoveEmptyEntries))
                {
                    string t = part.Trim();
                    if (!string.IsNullOrEmpty(t) && !rawTickers.Contains(t, StringComparer.OrdinalIgnoreCase))
                        rawTickers.Add(t);
                }
                if (rawTickers.Count == 0)
                    rawTickers.Add(SymbolName);
            }

            foreach (string raw in rawTickers)
            {
                Symbol sym = TryResolveSymbol(raw, out string aliasUsed);
                if (sym == null)
                {
                    Print($"[{BaseLabel} SKIP] Ticker '{raw}' not available on this broker.");
                    continue;
                }

                Bars dBars = (sym.Name.Equals(SymbolName, StringComparison.OrdinalIgnoreCase) && TimeFrame == TimeFrame.Daily)
                    ? Bars
                    : MarketData.GetBars(TimeFrame.Daily, sym.Name);

                if (dBars == null)
                {
                    Print($"[{BaseLabel} SKIP] Daily bars unavailable for '{sym.Name}'.");
                    continue;
                }

                string canonical = raw.ToUpperInvariant();
                string cluster = ClusterMap.TryGetValue(canonical, out string cl) ? cl : "OTHER";

                _universe.Add(new StockContext
                {
                    CanonicalTicker = canonical,
                    Cluster = cluster,
                    Sym = sym,
                    DailyBars = dBars,
                    LastRsScore = -999.0,
                    LastVol20 = 25.0,
                    LastEvaluatedBarTime = DateTime.MinValue
                });

                if (VerboseLogs && aliasUsed != null)
                    Print($"[{BaseLabel} ALIAS] '{raw}' -> '{sym.Name}' (Cluster={cluster})");
            }

            if (_universe.Count == 0)
            {
                // Guaranteed fallback to attached chart symbol
                Bars fallbackBars = TimeFrame == TimeFrame.Daily ? Bars : MarketData.GetBars(TimeFrame.Daily, SymbolName);
                _universe.Add(new StockContext
                {
                    CanonicalTicker = SymbolName.ToUpperInvariant(),
                    Cluster = "OTHER",
                    Sym = Symbol,
                    DailyBars = fallbackBars,
                    LastRsScore = 0.0,
                    LastVol20 = 25.0,
                    LastEvaluatedBarTime = DateTime.MinValue
                });
                Print($"[{BaseLabel} FALLBACK] Using attached chart symbol '{SymbolName}'.");
            }
        }

        private void RehydrateOpenPositions()
        {
            foreach (Position pos in GetBotPositions())
            {
                ParseLabel(pos.Label, out string engine, out string canonical);
                StockContext ctx = _universe.FirstOrDefault(u => u.Sym.Name.Equals(pos.SymbolName, StringComparison.OrdinalIgnoreCase));
                double hh = pos.EntryPrice;
                double riskDist = pos.StopLoss.HasValue ? Math.Abs(pos.EntryPrice - pos.StopLoss.Value) : pos.EntryPrice * 0.04;

                if (ctx != null && ctx.DailyBars != null && ctx.DailyBars.Count > 5)
                {
                    for (int i = ctx.DailyBars.Count - 1; i >= 0; i--)
                    {
                        if (ctx.DailyBars.OpenTimes[i] < pos.EntryTime.Date)
                            break;
                        if (ctx.DailyBars.HighPrices[i] > hh)
                            hh = ctx.DailyBars.HighPrices[i];
                    }
                }

                bool beLocked = pos.StopLoss.HasValue && pos.StopLoss.Value >= pos.EntryPrice - (ctx != null ? ctx.Sym.TickSize * 2 : 0.01);
                _posMeta[pos.Id] = new PosMeta
                {
                    Engine = engine,
                    CanonicalTicker = canonical,
                    InitialRiskDist = Math.Max(riskDist, 1e-6),
                    HighestHigh = hh,
                    BeLocked = beLocked,
                    EntryDayUtc = pos.EntryTime.Date
                };
            }
        }

        // =====================================================================
        // MACRO REGIME & DYNAMIC VOLATILITY TARGETING
        // =====================================================================
        private void EvaluateMacroRegime()
        {
            if (_primaryBenchBars == null || _primaryBenchBars.Count < 210)
            {
                _lastRegime = RegimeGreen;
                _lastBenchVol20 = TargetBenchmarkVolPct;
                _lastVolScale = 1.0;
                return;
            }

            int pIdx = _primaryBenchBars.Count - 2; // strictly prior closed D1 bar
            double[] qClose = ExtractCloses(_primaryBenchBars, pIdx + 1);
            double qEma50 = CalcEmaLast(qClose, 50);
            double qEma200 = CalcEmaLast(qClose, 200);
            double qVol20 = CalcRealizedVolAnnLast(qClose, 20);
            double qLast = qClose[pIdx];

            _lastBenchVol20 = double.IsNaN(qVol20) ? 20.0 : qVol20;

            if (UseVolTargeting && _lastBenchVol20 > 1.0)
                _lastVolScale = Math.Min(1.0, Math.Max(MinVolScale, TargetBenchmarkVolPct / Math.Max(_lastBenchVol20, 10.0)));
            else
                _lastVolScale = 1.0;

            if (!UseMacroGate)
            {
                _lastRegime = RegimeGreen;
                return;
            }

            double sLast = qLast;
            double sEma200 = qEma200;
            if (_secondaryBenchBars != null && _secondaryBenchBars.Count >= 210)
            {
                int sIdx = _secondaryBenchBars.Count - 2;
                double[] sClose = ExtractCloses(_secondaryBenchBars, sIdx + 1);
                sLast = sClose[sIdx];
                sEma200 = CalcEmaLast(sClose, 200);
            }

            if (double.IsNaN(qEma200) || double.IsNaN(qEma50) || double.IsNaN(sEma200))
            {
                _lastRegime = RegimeRed;
                return;
            }

            bool qBelow200 = qLast < qEma200;
            bool qBelow50 = qLast < qEma50;
            bool sBelow200 = sLast < sEma200;

            if (_lastBenchVol20 >= VolCrashPct || (qBelow200 && sBelow200))
                _lastRegime = RegimeRed;
            else if (_lastBenchVol20 >= VolCautionPct || qBelow50 || qBelow200)
                _lastRegime = RegimeYellow;
            else
                _lastRegime = RegimeGreen;
        }

        // =====================================================================
        // POSITION MANAGEMENT (EXITS, TIME-STOPS, BE & CHANDELIER TRAIL)
        // =====================================================================
        private void ManageExistingPositions()
        {
            foreach (Position pos in GetBotPositions().ToList())
            {
                if (!_posMeta.TryGetValue(pos.Id, out PosMeta meta))
                {
                    ParseLabel(pos.Label, out string eng, out string can);
                    meta = new PosMeta
                    {
                        Engine = eng,
                        CanonicalTicker = can,
                        InitialRiskDist = pos.StopLoss.HasValue ? Math.Abs(pos.EntryPrice - pos.StopLoss.Value) : pos.EntryPrice * 0.04,
                        HighestHigh = pos.EntryPrice,
                        BeLocked = false,
                        EntryDayUtc = pos.EntryTime.Date
                    };
                    _posMeta[pos.Id] = meta;
                }

                StockContext ctx = _universe.FirstOrDefault(u => u.Sym.Name.Equals(pos.SymbolName, StringComparison.OrdinalIgnoreCase));
                if (ctx == null || ctx.DailyBars == null || ctx.DailyBars.Count < 210)
                    continue;

                int s = ctx.DailyBars.Count - 2; // prior closed D1 bar
                double prevClose = ctx.DailyBars.ClosePrices[s];
                double prevHigh = ctx.DailyBars.HighPrices[s];
                double prevPrevHigh = ctx.DailyBars.HighPrices[s - 1];

                if (prevHigh > meta.HighestHigh)
                    meta.HighestHigh = prevHigh;

                int holdDays = CountTradingDaysSince(ctx.DailyBars, meta.EntryDayUtc);

                // Signal & Time-Stop Exits
                if (meta.Engine == "TREND")
                {
                    if (TrendFastExitEma50)
                    {
                        double[] closes = ExtractCloses(ctx.DailyBars, s + 1);
                        double ema50 = CalcEmaLast(closes, 50);
                        if (!double.IsNaN(ema50) && prevClose < ema50)
                        {
                            ClosePosition(pos);
                            if (VerboseLogs)
                                Print($"[{BaseLabel} EXIT] {ctx.CanonicalTicker} TREND closed (EMA50 fast exit).");
                            continue;
                        }
                    }

                    // Break-Even Lock & Chandelier Trail
                    double desiredSl = pos.StopLoss ?? 0.0;
                    if (!meta.BeLocked && TrendBeR > 0.0 && meta.HighestHigh >= pos.EntryPrice + TrendBeR * meta.InitialRiskDist)
                    {
                        desiredSl = Math.Max(desiredSl, pos.EntryPrice);
                        meta.BeLocked = true;
                    }

                    double atr22 = CalcAtrLast(ctx.DailyBars, s + 1, 22);
                    if (!double.IsNaN(atr22) && atr22 > 0.0)
                    {
                        double trailSl = meta.HighestHigh - TrendTrailAtrMult * atr22;
                        if (trailSl > desiredSl)
                            desiredSl = trailSl;
                    }

                    double roundedSl = RoundPrice(ctx.Sym, desiredSl);
                    if (roundedSl > (pos.StopLoss ?? 0.0) + ctx.Sym.TickSize && roundedSl < ctx.Sym.Bid)
                    {
                        ModifyPosition(pos, roundedSl, pos.TakeProfit);
                    }
                }
                else if (meta.Engine == "IBS")
                {
                    if (prevClose > prevPrevHigh || holdDays >= IbsMaxHoldDays)
                    {
                        ClosePosition(pos);
                        if (VerboseLogs)
                            Print($"[{BaseLabel} EXIT] {ctx.CanonicalTicker} IBS closed (Hold={holdDays}d).");
                    }
                }
                else if (meta.Engine == "CONNORS")
                {
                    double[] closes = ExtractCloses(ctx.DailyBars, s + 1);
                    double exitSma = CalcSmaLast(closes, ConnorsUseSma8 ? 8 : 5);
                    if ((!double.IsNaN(exitSma) && prevClose > exitSma) || holdDays >= ConnorsMaxHoldDays)
                    {
                        ClosePosition(pos);
                        if (VerboseLogs)
                            Print($"[{BaseLabel} EXIT] {ctx.CanonicalTicker} CONNORS closed (Hold={holdDays}d).");
                    }
                }
            }
        }

        // =====================================================================
        // RS-RANKED ENTRIES & INVERSE-VOL POSITION SIZING
        // =====================================================================
        private void EvaluateEntries()
        {
            double ddPct = _peakEquity > 0 ? (_peakEquity - Account.Equity) / _peakEquity * 100.0 : 0.0;
            double ddRiskMult = 1.0;
            if (QuarterRiskDdPct > 0 && ddPct >= QuarterRiskDdPct)
                ddRiskMult = 0.35;
            else if (HalfRiskDdPct > 0 && ddPct >= HalfRiskDdPct)
                ddRiskMult = 0.65;

            double regTrendMult = _lastRegime == RegimeGreen ? 1.0 : YellowTrendMult;
            double regMrMult = _lastRegime == RegimeGreen ? 1.0 : YellowMrMult;

            // Update RS Score & Vol20 for all universe stocks using strictly closed bar s
            foreach (StockContext ctx in _universe)
            {
                if (ctx.DailyBars == null || ctx.DailyBars.Count < 210)
                {
                    ctx.LastRsScore = -999.0;
                    continue;
                }
                int s = ctx.DailyBars.Count - 2;
                double[] closes = ExtractCloses(ctx.DailyBars, s + 1);
                double vol20 = CalcRealizedVolAnnLast(closes, 20);
                ctx.LastVol20 = (!double.IsNaN(vol20) && vol20 > 10.0) ? vol20 : 30.0;
                ctx.LastRsScore = CalcRsScoreLast(closes, ctx.LastVol20, 60);
            }

            List<StockContext> ranked = _universe.OrderByDescending(u => u.LastRsScore).ToList();

            // Engine 1: Leader ALMA20 Trend (Top-K RS Leaders)
            if (EnableTrend && regTrendMult > 0.0)
            {
                int limit = Math.Min(TrendTopK, ranked.Count);
                for (int i = 0; i < limit; i++)
                {
                    StockContext ctx = ranked[i];
                    if (CheckLeaderTrendSignal(ctx))
                        TryEnterPosition(ctx, "TREND", TrendRiskPct, TrendSlAtrMult, regTrendMult * ddRiskMult * _lastVolScale);
                }
            }

            // Engine 2: IBS Sniper
            if (EnableIbs && regMrMult > 0.0)
            {
                int limit = Math.Min(IbsTopK, ranked.Count);
                for (int i = 0; i < limit; i++)
                {
                    StockContext ctx = ranked[i];
                    if (CheckIbsSignal(ctx))
                        TryEnterPosition(ctx, "IBS", IbsRiskPct, IbsSlAtrMult, regMrMult * ddRiskMult * _lastVolScale);
                }
            }

            // Engine 3: Connors RSI(2) (Optional)
            if (EnableConnors && regMrMult > 0.0)
            {
                foreach (StockContext ctx in ranked)
                {
                    if (CheckConnorsSignal(ctx))
                        TryEnterPosition(ctx, "CONNORS", ConnorsRiskPct, ConnorsSlAtrMult, regMrMult * ddRiskMult * _lastVolScale);
                }
            }
        }

        private bool IsFallingKnife(Bars bars, int s, double atr14)
        {
            if (s < 1 || double.IsNaN(atr14) || atr14 <= 0.0)
                return true;
            double dayDrop = bars.ClosePrices[s - 1] - bars.ClosePrices[s];
            if (dayDrop > MaxDropAtr * atr14)
                return true;
            double gapAbs = Math.Abs(bars.OpenPrices[s] - bars.ClosePrices[s - 1]);
            if (gapAbs > MaxDropAtr * atr14)
                return true;
            return false;
        }

        private bool CheckLeaderTrendSignal(StockContext ctx)
        {
            if (ctx.DailyBars == null || ctx.DailyBars.Count < 210)
                return false;
            int s = ctx.DailyBars.Count - 2;
            double atr14 = CalcAtrLast(ctx.DailyBars, s + 1, 14);
            if (IsFallingKnife(ctx.DailyBars, s, atr14))
                return false;

            double[] closes = ExtractCloses(ctx.DailyBars, s + 1);
            int last = closes.Length - 1;
            double ema50 = CalcEmaLast(closes, 50);
            double ema200 = CalcEmaLast(closes, 200);
            double almaCurr = CalcAlmaAt(closes, last, 20, 0.85, 6.0);
            double almaPrev = CalcAlmaAt(closes, last - 1, 20, 0.85, 6.0);
            double c = closes[last];

            if (double.IsNaN(ema50) || double.IsNaN(ema200) || double.IsNaN(almaCurr) || double.IsNaN(almaPrev))
                return false;

            return c > ema200
                && c > ema50
                && c > almaCurr
                && almaCurr > almaPrev
                && ctx.LastRsScore > TrendMinRsScore;
        }

        private bool CheckIbsSignal(StockContext ctx)
        {
            if (ctx.DailyBars == null || ctx.DailyBars.Count < 210)
                return false;
            int s = ctx.DailyBars.Count - 2;
            double atr14 = CalcAtrLast(ctx.DailyBars, s + 1, 14);
            if (IsFallingKnife(ctx.DailyBars, s, atr14))
                return false;

            double[] closes = ExtractCloses(ctx.DailyBars, s + 1);
            double ema50 = CalcEmaLast(closes, 50);
            double ema200 = CalcEmaLast(closes, 200);
            double c = closes[closes.Length - 1];
            double h = ctx.DailyBars.HighPrices[s];
            double l = ctx.DailyBars.LowPrices[s];
            double ibs = (h - l) > 1e-12 ? (c - l) / (h - l) : 0.5;

            if (double.IsNaN(ema200) || double.IsNaN(ema50))
                return false;
            if (IbsRequireAboveEma50 && c <= ema50)
                return false;

            return c > ema200
                && ibs < IbsThreshold
                && c < ctx.DailyBars.HighPrices[s - 1];
        }

        private bool CheckConnorsSignal(StockContext ctx)
        {
            if (ctx.DailyBars == null || ctx.DailyBars.Count < 210)
                return false;
            int s = ctx.DailyBars.Count - 2;
            double atr14 = CalcAtrLast(ctx.DailyBars, s + 1, 14);
            if (IsFallingKnife(ctx.DailyBars, s, atr14))
                return false;

            double[] closes = ExtractCloses(ctx.DailyBars, s + 1);
            double ema200 = CalcEmaLast(closes, 200);
            double exitSma = CalcSmaLast(closes, ConnorsUseSma8 ? 8 : 5);
            double rsi2 = CalcRsiLast(closes, 2);
            double c = closes[closes.Length - 1];

            if (double.IsNaN(ema200) || double.IsNaN(exitSma) || double.IsNaN(rsi2))
                return false;

            return c > ema200 && rsi2 < ConnorsRsiThresh && c < exitSma;
        }

        private void TryEnterPosition(StockContext ctx, string engine, double baseRiskPct, double slAtrMult, double effRiskMult)
        {
            if (effRiskMult <= 0.0)
                return;

            List<Position> botPositions = GetBotPositions();
            if (botPositions.Count >= MaxConcurrentPositions)
                return;

            string label = MakeLabel(engine, ctx.CanonicalTicker);
            if (botPositions.Any(p => p.Label.Equals(label, StringComparison.OrdinalIgnoreCase)))
                return;

            List<Position> symPositions = botPositions.Where(p => p.SymbolName.Equals(ctx.Sym.Name, StringComparison.OrdinalIgnoreCase)).ToList();
            if (symPositions.Count >= MaxPositionsPerStock)
                return;

            // Sub-sector cluster cap
            int clusterCount = 0;
            foreach (Position p in botPositions)
            {
                StockContext pCtx = _universe.FirstOrDefault(u => u.Sym.Name.Equals(p.SymbolName, StringComparison.OrdinalIgnoreCase));
                if (pCtx != null && pCtx.Cluster.Equals(ctx.Cluster, StringComparison.OrdinalIgnoreCase))
                    clusterCount++;
            }
            if (clusterCount >= MaxClusterPositions)
                return;

            int s = ctx.DailyBars.Count - 2;
            double atr14 = CalcAtrLast(ctx.DailyBars, s + 1, 14);
            double entryPx = ctx.Sym.Ask;
            if (entryPx <= 0.0 || double.IsNaN(atr14) || atr14 <= 0.0)
                return;

            // Open-gap sanity filter (> 2.5 ATR overnight gap)
            if (Math.Abs(entryPx - ctx.DailyBars.ClosePrices[s]) > 2.5 * atr14)
                return;

            double slDist = slAtrMult * atr14;
            double slPrice = RoundPrice(ctx.Sym, entryPx - slDist);
            if (slPrice <= 0.0 || slPrice >= entryPx)
                return;

            // 1. Inverse-ATR Risk Sizing
            double riskDollars = Account.Equity * (baseRiskPct / 100.0) * effRiskMult;
            double valuePerUnitMove = ctx.Sym.PipValue / ctx.Sym.PipSize; // account currency per 1.0 price move per 1.0 volume unit
            if (valuePerUnitMove <= 0.0)
                return;
            double volByRisk = riskDollars / (slDist * valuePerUnitMove);

            // 2. Inverse-Volatility Per-Stock Notional Cap + Dynamic Vol-Targeted Portfolio Leverage Cap
            double volAdjNotionalPct = Math.Min(
                MaxSingleStockNotionalPct,
                MaxSingleStockNotionalPct * (StockVolRefPct / Math.Max(ctx.LastVol20, 10.0))
            );
            double unitNotional = entryPx * valuePerUnitMove;
            double existingSymNotional = symPositions.Sum(p => p.VolumeInUnits * entryPx * valuePerUnitMove);
            double remSymNotional = Math.Max(0.0, Account.Equity * (volAdjNotionalPct / 100.0) - existingSymNotional);

            double currPortNotional = ComputeTotalNotional(botPositions);
            double effMaxLev = MaxPortfolioLeverage * _lastVolScale;
            double remPortNotional = Math.Max(0.0, Account.Equity * effMaxLev - currPortNotional);

            double allowedNotional = Math.Min(remSymNotional, remPortNotional);
            if (allowedNotional <= 0.0 || unitNotional <= 0.0)
                return;

            double volByNotional = allowedNotional / unitNotional;
            double rawUnits = Math.Min(volByRisk, volByNotional);
            double units = ctx.Sym.NormalizeVolumeInUnits(rawUnits, RoundingMode.Down);
            if (units < ctx.Sym.VolumeInUnitsMin)
                return;

            double slPips = Math.Max(1.0, (entryPx - slPrice) / ctx.Sym.PipSize);
            TradeResult res = ExecuteMarketOrder(TradeType.Buy, ctx.Sym.Name, units, label, slPips, null);
            if (res.IsSuccessful && res.Position != null)
            {
                // Refine exact sub-pip SL price
                if (Math.Abs((res.Position.StopLoss ?? 0.0) - slPrice) > ctx.Sym.TickSize && slPrice < ctx.Sym.Bid)
                    ModifyPosition(res.Position, slPrice, null);

                _posMeta[res.Position.Id] = new PosMeta
                {
                    Engine = engine,
                    CanonicalTicker = ctx.CanonicalTicker,
                    InitialRiskDist = slDist,
                    HighestHigh = res.Position.EntryPrice,
                    BeLocked = false,
                    EntryDayUtc = Server.Time.Date
                };

                if (VerboseLogs)
                    Print($"[{BaseLabel} ENTRY] {ctx.CanonicalTicker} ({engine}) | Units={units} | Entry={res.Position.EntryPrice:F2} | SL={slPrice:F2} | RS={ctx.LastRsScore:F2} | Vol20={ctx.LastVol20:F1}%");
            }
        }

        // =====================================================================
        // REAL-TIME DD GUARDRAILS & PERSISTENCE
        // =====================================================================
        private DateTime GetResetDate(DateTime utcTime)
        {
            return utcTime.AddHours(DailyResetUtcOffsetHours).Date;
        }

        private void CheckDailyReset()
        {
            DateTime d = GetResetDate(Server.Time);
            if (d > _curResetDate)
            {
                _curResetDate = d;
                _dayAnchorEquity = Account.Equity;
                _dailyHalted = false;
                SavePersistedState();
            }
        }

        private void UpdatePeakEquity()
        {
            if (Account.Equity > _peakEquity)
                _peakEquity = Account.Equity;
            if (Account.Equity > _killAnchorPeak)
                _killAnchorPeak = Account.Equity;
        }

        private bool CheckIntradayDdGuardrails()
        {
            double dailyDd = _dayAnchorEquity > 0 ? (_dayAnchorEquity - Account.Equity) / _dayAnchorEquity * 100.0 : 0.0;
            double totalDd = _killAnchorPeak > 0 ? (_killAnchorPeak - Account.Equity) / _killAnchorPeak * 100.0 : 0.0;

            if (MaxTotalDrawdownPct > 0 && totalDd >= MaxTotalDrawdownPct)
            {
                if (FlattenOnDdBreach)
                    FlattenAllBotPositions("DD_KILL");
                _killCooldownUntilUtc = Server.Time.AddDays(KillCooldownDays);
                _killAnchorPeak = Account.Equity;
                SavePersistedState();
                Print($"[{BaseLabel} KILL-SWITCH] Total DD {totalDd:F2}% >= {MaxTotalDrawdownPct:F2}%. Cooldown until {_killCooldownUntilUtc:yyyy-MM-dd}.");
                return true;
            }

            if (MaxDailyLossPct > 0 && dailyDd >= MaxDailyLossPct && !_dailyHalted)
            {
                _dailyHalted = true;
                if (FlattenOnDdBreach)
                    FlattenAllBotPositions("DAILY_GUARD");
                SavePersistedState();
                Print($"[{BaseLabel} DAILY GUARD] Daily DD {dailyDd:F2}% >= {MaxDailyLossPct:F2}%. Halted until next session.");
                return true;
            }

            return false;
        }

        private void FlattenAllBotPositions(string reason)
        {
            foreach (Position p in GetBotPositions().ToList())
                ClosePosition(p);
            if (VerboseLogs)
                Print($"[{BaseLabel} FLATTEN] Closed all bot positions ({reason}).");
        }

        private void OnPositionClosed(PositionClosedEventArgs args)
        {
            if (args.Position != null && _posMeta.ContainsKey(args.Position.Id))
                _posMeta.Remove(args.Position.Id);
        }

        private void LoadPersistedState()
        {
            if (!PersistDdState)
                return;
            if (double.TryParse(LocalStorage.GetString($"{StoragePrefix}_PeakEq"), NumberStyles.Float, CultureInfo.InvariantCulture, out double sp) && sp > _peakEquity)
                _peakEquity = sp;
            if (double.TryParse(LocalStorage.GetString($"{StoragePrefix}_KillAnchor"), NumberStyles.Float, CultureInfo.InvariantCulture, out double ka) && ka > 0)
                _killAnchorPeak = ka;
            string savedDate = LocalStorage.GetString($"{StoragePrefix}_DayDate");
            if (savedDate == _curResetDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture))
            {
                if (double.TryParse(LocalStorage.GetString($"{StoragePrefix}_DayEq"), NumberStyles.Float, CultureInfo.InvariantCulture, out double de) && de > 0)
                    _dayAnchorEquity = de;
                if (bool.TryParse(LocalStorage.GetString($"{StoragePrefix}_DailyHalted"), out bool dh))
                    _dailyHalted = dh;
            }
            string coolStr = LocalStorage.GetString($"{StoragePrefix}_CooldownUntil");
            if (DateTime.TryParse(coolStr, CultureInfo.InvariantCulture, DateTimeStyles.AdjustToUniversal, out DateTime cd))
                _killCooldownUntilUtc = cd;
        }

        private void SavePersistedState()
        {
            if (!PersistDdState)
                return;
            LocalStorage.SetString($"{StoragePrefix}_PeakEq", _peakEquity.ToString("R", CultureInfo.InvariantCulture));
            LocalStorage.SetString($"{StoragePrefix}_KillAnchor", _killAnchorPeak.ToString("R", CultureInfo.InvariantCulture));
            LocalStorage.SetString($"{StoragePrefix}_DayDate", _curResetDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture));
            LocalStorage.SetString($"{StoragePrefix}_DayEq", _dayAnchorEquity.ToString("R", CultureInfo.InvariantCulture));
            LocalStorage.SetString($"{StoragePrefix}_DailyHalted", _dailyHalted.ToString());
            LocalStorage.SetString($"{StoragePrefix}_CooldownUntil", _killCooldownUntilUtc.ToString("O", CultureInfo.InvariantCulture));
            LocalStorage.Flush(LocalStorageScope.Instance);
        }

        // =====================================================================
        // LIVE ON-CHART HUD
        // =====================================================================
        private void UpdateHud()
        {
            if (!EnableHud)
                return;

            List<Position> openPos = GetBotPositions();
            double ddPct = _peakEquity > 0 ? Math.Max(0.0, (_peakEquity - Account.Equity) / _peakEquity * 100.0) : 0.0;
            double dayDdPct = _dayAnchorEquity > 0 ? Math.Max(0.0, (_dayAnchorEquity - Account.Equity) / _dayAnchorEquity * 100.0) : 0.0;
            double lev = Account.Equity > 0 ? ComputeTotalNotional(openPos) / Account.Equity : 0.0;
            string regStr = _lastRegime == RegimeGreen ? "GREEN (RISK-ON)" : (_lastRegime == RegimeYellow ? "YELLOW (CAUTION)" : "RED (CASH SHIELD)");
            string throttleStr = (QuarterRiskDdPct > 0 && ddPct >= QuarterRiskDdPct) ? "0.35x" : ((HalfRiskDdPct > 0 && ddPct >= HalfRiskDdPct) ? "0.65x" : "1.00x");
            string top3 = string.Join(", ", _universe.OrderByDescending(u => u.LastRsScore).Take(3).Select(u => $"{u.CanonicalTicker}({u.LastRsScore:F1})"));

            string hud =
                $"StockShield Low-DD {BotVersion} [{PortfolioTag}]\n" +
                $"Regime: {regStr} | BenchVol20: {_lastBenchVol20:F1}% | VolScale: {_lastVolScale:F2}x\n" +
                $"Eq DD: {ddPct:F2}% (Throttle {throttleStr}) | Day DD: {dayDdPct:F2}%\n" +
                $"Open: {openPos.Count}/{MaxConcurrentPositions} | Lev: {lev:F2}x / {MaxPortfolioLeverage * _lastVolScale:F2}x\n" +
                $"Top RS: {top3}";

            Color col = _lastRegime == RegimeGreen ? Color.LimeGreen : (_lastRegime == RegimeYellow ? Color.Gold : Color.OrangeRed);
            Chart.DrawStaticText($"{BaseLabel}_{PortfolioTag}_Hud", hud, VerticalAlignment.Top, HorizontalAlignment.Left, col);
        }

        // =====================================================================
        // HELPERS & CAUSAL INDICATORS (1:1 PARITY WITH PYTHON)
        // =====================================================================
        private string MakeLabel(string engine, string canonical) => $"{BaseLabel}_{PortfolioTag}_{engine}_{canonical}";

        private List<Position> GetBotPositions()
        {
            string prefix = $"{BaseLabel}_{PortfolioTag}_";
            return Positions.Where(p => p.Label != null && p.Label.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)).ToList();
        }

        private void ParseLabel(string label, out string engine, out string canonical)
        {
            engine = "TREND";
            canonical = SymbolName;
            string prefix = $"{BaseLabel}_{PortfolioTag}_";
            if (string.IsNullOrEmpty(label) || !label.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                return;
            string rest = label.Substring(prefix.Length);
            int sep = rest.IndexOf('_');
            if (sep > 0 && sep < rest.Length - 1)
            {
                engine = rest.Substring(0, sep);
                canonical = rest.Substring(sep + 1);
            }
        }

        private double ComputeTotalNotional(List<Position> positions)
        {
            double total = 0.0;
            foreach (Position p in positions)
            {
                Symbol s = Symbols.GetSymbol(p.SymbolName);
                if (s != null && s.PipSize > 0)
                    total += p.VolumeInUnits * s.Bid * (s.PipValue / s.PipSize);
            }
            return total;
        }

        private static double RoundPrice(Symbol sym, double price)
        {
            return Math.Round(price / sym.TickSize) * sym.TickSize;
        }

        private static int CountTradingDaysSince(Bars bars, DateTime entryDayUtc)
        {
            int count = 0;
            for (int i = bars.Count - 2; i >= 0; i--)
            {
                if (bars.OpenTimes[i].Date <= entryDayUtc)
                    break;
                count++;
            }
            return count;
        }

        private static double[] ExtractCloses(Bars bars, int count)
        {
            int start = Math.Max(0, count - 320);
            int len = count - start;
            double[] arr = new double[len];
            for (int i = 0; i < len; i++)
                arr[i] = bars.ClosePrices[start + i];
            return arr;
        }

        private static double CalcSmaLast(double[] s, int period)
        {
            if (s.Length < period || period <= 0)
                return double.NaN;
            double sum = 0.0;
            for (int i = s.Length - period; i < s.Length; i++)
                sum += s[i];
            return sum / period;
        }

        private static double CalcEmaLast(double[] s, int period)
        {
            if (s.Length < period || period <= 0)
                return double.NaN;
            double alpha = 2.0 / (period + 1.0);
            double ema = 0.0;
            for (int i = 0; i < period; i++)
                ema += s[i];
            ema /= period;
            for (int i = period; i < s.Length; i++)
                ema = alpha * s[i] + (1.0 - alpha) * ema;
            return ema;
        }

        private static double CalcAtrLast(Bars bars, int count, int period)
        {
            int start = Math.Max(0, count - 200);
            int len = count - start;
            if (len < period + 1)
                return double.NaN;

            double[] tr = new double[len];
            tr[0] = bars.HighPrices[start] - bars.LowPrices[start];
            for (int i = 1; i < len; i++)
            {
                int idx = start + i;
                double hl = bars.HighPrices[idx] - bars.LowPrices[idx];
                double hc = Math.Abs(bars.HighPrices[idx] - bars.ClosePrices[idx - 1]);
                double lc = Math.Abs(bars.LowPrices[idx] - bars.ClosePrices[idx - 1]);
                tr[i] = Math.Max(hl, Math.Max(hc, lc));
            }

            double atr = 0.0;
            for (int i = 0; i < period; i++)
                atr += tr[i];
            atr /= period;
            for (int i = period; i < len; i++)
                atr = (atr * (period - 1) + tr[i]) / period;
            return atr;
        }

        private static double CalcRsiLast(double[] s, int period)
        {
            if (s.Length <= period || period <= 0)
                return double.NaN;
            double avgGain = 0.0;
            double avgLoss = 0.0;
            for (int i = 1; i <= period; i++)
            {
                double d = s[i] - s[i - 1];
                if (d > 0) avgGain += d;
                else avgLoss += -d;
            }
            avgGain /= period;
            avgLoss /= period;
            for (int i = period + 1; i < s.Length; i++)
            {
                double d = s[i] - s[i - 1];
                double g = d > 0 ? d : 0.0;
                double l = d < 0 ? -d : 0.0;
                avgGain = (avgGain * (period - 1) + g) / period;
                avgLoss = (avgLoss * (period - 1) + l) / period;
            }
            if (avgLoss <= 1e-12)
                return avgGain > 1e-12 ? 100.0 : 50.0;
            double rs = avgGain / avgLoss;
            return 100.0 - (100.0 / (1.0 + rs));
        }

        private static double CalcAlmaAt(double[] s, int idx, int window, double offset, double sigma)
        {
            if (idx < window - 1 || idx >= s.Length)
                return double.NaN;
            double m = offset * (window - 1);
            double sd = window / sigma;
            double wSum = 0.0;
            double val = 0.0;
            for (int j = 0; j < window; j++)
            {
                double w = Math.Exp(-((j - m) * (j - m)) / (2.0 * sd * sd));
                wSum += w;
                val += s[idx - window + 1 + j] * w;
            }
            return wSum > 0.0 ? val / wSum : double.NaN;
        }

        private static double CalcRealizedVolAnnLast(double[] s, int period)
        {
            if (s.Length <= period || period <= 1)
                return double.NaN;
            double[] r = new double[period];
            int start = s.Length - period;
            double mean = 0.0;
            for (int i = 0; i < period; i++)
            {
                double c0 = s[start + i - 1];
                double c1 = s[start + i];
                r[i] = (c0 > 0 && c1 > 0) ? Math.Log(c1 / c0) : 0.0;
                mean += r[i];
            }
            mean /= period;
            double sumSq = 0.0;
            for (int i = 0; i < period; i++)
            {
                double diff = r[i] - mean;
                sumSq += diff * diff;
            }
            double std = Math.Sqrt(sumSq / (period - 1));
            return std * Math.Sqrt(252.0) * 100.0;
        }

        private static double CalcRsScoreLast(double[] s, double vol20, int lookback)
        {
            if (s.Length <= lookback || vol20 <= 1.0)
                return -999.0;
            double c0 = s[s.Length - 1 - lookback];
            double c1 = s[s.Length - 1];
            if (c0 <= 0.0)
                return -999.0;
            return ((c1 / c0 - 1.0) * 100.0) / vol20;
        }
    }
}
