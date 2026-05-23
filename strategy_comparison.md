# Strategy Comparison for 563300 (CSI2000 ETF)

> Capital: 20,000 yuan | Max position: 50% (10,000 yuan) | Period: 2026-01-05 ~ 2026-05-22
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
| **v5.3** ⭐ | v3.0 + (turnover ≥ 25000 OR limit-down > limit-up) | Same as v3.0 | **Best: +7.63%, 10 trades, 0.15% DD** |

---

## Results Summary

| Strategy | Return | Max DD | Trades | Final Value |
|:--------:|:------:|:------:|:------:|:-----------:|
| **v3.0** | +5.90% | 3.69% | 18 | 21,179.43 |
| **v3.1** | +5.90% | 3.69% | 17 | 21,179.43 |
| **v5.0** 放量 | +2.89% | 3.69% | 8 | 20,578.24 |
| **v5.2** 跌停确认 | +6.88% | 0.15% | 7 | 21,376.09 |
| **v5.3** 综合版 ⭐ | **+7.63%** | **0.15%** | **10** | **21,525.53** |

---

## Key Insights

1. **v5.3 wins on all metrics**: +7.63% return, 0.15% max drawdown, only 10 trades
2. **Volume filter eliminates false signals**: v3.0 triggers 18 trades; v5.3 only buys confirmed panic days
3. **Market capital flow (大盘资金流向)** API discovered, correlation with sentiment: **0.725**
4. **Northbound flow data** — API requires IPv4 force (`socket.AF_INET`), intermittently unavailable

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
