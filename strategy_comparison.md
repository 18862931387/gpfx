# Strategy Comparison for 563300 (CSI2000 ETF)

> Capital: 20,000 yuan | Max position: 50% (10,000 yuan) | Period: 2026-01-05 ~ 2026-05-25
>
> Database: `data_analysis` — `fund_history`, `market_sentiment`, `market_daily_stats`, `market_capital_flow`

---

## Core Strategy (v3.x — Sentiment-based)

| ID | Buy Rule | Sell Rule | Notes |
|:--:|:---------|:----------|:------|
| **v3.0** | sent ≤ -0.8 AND drop ≥ 1% | sent ≥ 1.0 clear / +2% sell half / -3% stop-loss | Baseline, max 50% position |
| **v3.1** | sent ≤ -0.8 AND drop ≥ 1% (skip if same-day recovery after prior loss) | Same as v3.0 | Psychological variant |

## Volume-enhanced (v5.x)

| ID | Buy Rule | Sell Rule | Notes |
|:--:|:---------|:----------|:------|
| **v5.0** | v3.0 + turnover ≥ 25000亿 | Same as v3.0 | "放量" — high volume confirms panic |
| **v5.1** | v3.0 + turnover ≤ 22000亿 | Same as v3.0 | "缩量" — low volume (discarded) |
| **v5.2** | v3.0 + limit-down count > limit-up | Same as v3.0 | "跌停确认" — extreme bearish sentiment |
| **v5.3** | v3.0 + (turnover ≥ 25000 OR limit-down > limit-up) | Same as v3.0 | +7.63%, 10 trades, 0.15% DD |
| **v5.4** ⭐ | v3.0 + (turnover ≥ 25000 OR limit-down > limit-up) | **sent ≥ 1.5** clear / +2% sell half / -3% stop-loss | **Best: +10.92%, 10 trades, 0.32% DD** |

---

## Results Summary

| Strategy | Return | Max DD | Trades | Final Value |
|:--------:|:------:|:------:|:------:|:-----------:|
| **v3.0** | +5.90% | 3.69% | 18 | 21,179.43 |
| **v3.1** | +5.90% | 3.69% | 17 | 21,179.43 |
| **v5.0** 放量 | +2.89% | 3.69% | 8 | 20,578.24 |
| **v5.2** 跌停确认 | +6.88% | 0.15% | 7 | 21,376.09 |
| **v5.3** 综合版 | **+7.63%** | **0.15%** | **10** | **21,525.53** |
| **v5.4** 情绪1.5 ⭐ | **+10.92%** | **0.32%** | **10** | **22,183.47** |

---

## Key Insights

1. **v5.4 wins on all metrics**: +10.92% return, 0.32% max drawdown, 10 trades in 42 trading days (3 months)
2. **Sell threshold raised from 1.0 to 1.5**: avoids premature exits during 微热 zone, gains +2.74% over v5.3
3. **Volume filter (cond3) is essential**: removing it lets in losing trades (3/17, 3/19) → DD jumps to 7.45%
4. **融资融券 data doesn't improve this period**: any meaningful filter blocks profitable trades; loose enough to not filter = same as baseline
5. **Margin sell boost never triggers**: sentiment hits 1.5 threshold first, always
6. **Market capital flow / Northbound data** retained as reference output only, not as hard buy/sell conditions

## Data Sources

| Table | Source | API |
|:------|:-------|:----|
| `fund_history` | East Money Fund | `api.fund.eastmoney.com/f10/lsjz` |
| `market_sentiment` | Tencent | `web.ifzq.gtimg.cn/appstock/app/fqkline/get` |
| `market_daily_stats` | East Money | `push2.eastmoney.com/api/qt/stock/fflow/kline/get` (with ut param) |
| `market_capital_flow` | East Money | `push2his.eastmoney.com/api/qt/stock/fflow/daykline/get` |

## Next Directions

- Integrate **market capital flow** into strategy (main force vs retail divergence)
- Use **行业板块资金流向** (sector capital flow) for sector rotation signals
