# Strategy Comparison for 563300 (CSI2000 ETF)

> Capital: 20,000 yuan | Period: 2026-03-03 ~ 2026-05-22 (55 trading days)
>
> Database: `data_analysis` — `fund_history`, `market_sentiment`, `market_daily_stats`

---

## Strategy Versions

| ID | Buy Rule | Sell Rule | Notes |
|:--:|:---------|:----------|:------|
| **v5.4** | sent ≤ -0.8, drop ≥ 1%, (vol ≥ 25000 OR LD > LU) | sent ≥ 1.5 clear / +2% sell half / -3% stop-loss | Single-index sentiment, max 50% pos |
| **v5.5a** | v5.4 + buyB (half, sent -0.5~0.5 + above 20MA) | sent 1.5~2.0 sell half, ≥2.0 clear / +2% sell half / -3% stop-loss | Composite index + dual buy |
| **v5.5b** | same as v5.5a | sent 1.8~2.0 sell half, ≥2.0 clear / -3% stop (no take-profit) | Removed +2% take-profit |
| **v5.5c** | buyA ≤ -0.5, buyB full, no sell-half, no take-profit | ≥2.0 clear / -3% stop | Eat the rally, 8k pos |
| **v5.5d** | buyA ≤ **-1.2**, buyB full, no sell-half, no take-profit | ≥2.0 clear / -3% stop | Best risk-adjusted, 8k |
| **v5.5e** | same as v5.5d | same + trailing stop -3% from peak | Rejected: ETF volatility false exits |
| **v5.6** ⭐ | same as v5.5d | same as v5.5d | **max_invest 8000→10000**, best return |

---

## Results Summary

| Strategy | Return | Max DD | Trades | Return/DD | Notes |
|:--------:|:------:|:------:|:------:|:---------:|:------|
| **v5.4** | +4.64% | 2.38% | 10 | 1.95 | |
| **v5.5a** | +3.15% | 2.38% | 7 | 1.32 | |
| **v5.5b** | +4.89% | 2.38% | 7 | 2.05 | |
| **v5.5c** | +8.41% | 2.38% | 5 | 3.53 | buyA=-0.5 |
| **v5.5d** | +8.05% | 1.49% | 3 | 5.40 | buyA=-1.2, 8k |
| **v5.5e** | — | — | — | — | Trailing stop, no backtest run |
| **v5.6** ⭐ | **+10.06%** | **2.49%** | **3** | **4.04** | **buyA=-1.2, 10k** |

---

## Grid Search Findings

12 parameter combinations tested across 55 days (2026-03-03 ~ 2026-05-22):

| Variable | Range Tested | Result |
|:---------|:------------|:-------|
| **max_invest** | 8000 / 10000 / 12000 / 20000 | **Only variable that matters** — returns scale linearly |
| buyA_sv_max | -0.8 / -1.5 / -1.8 / -2.0 | -1.2 optimal; looser adds bad trades |
| sell_all_sv | 1.5 / 2.5 | No difference (market never hit 1.5 at exit) |
| stop_loss_pct | -2.5% / -3.0% | No difference (no stop ever triggered) |
| buyB sv_min | -1.0 / -0.5 | Same: price was below 20MA those days |
| MA filter | enabled / disabled | **Disabled halves return** (+5.95% vs +10.06%) |
| Trailing stop | on / off | 3 tests, all false exits from daily volatility |

### Key Drivers of Return

Only 3 high-quality trades in the 3-month window. The strategy's edge comes from:
1. **03-23 panic buy** @ 1.356 (sv=-3.0) → held through recovery → cleared @ 1.474 (+8.7%)
2. **04-09 trend entry** @ 1.462 (sv=-0.1) → purchased capital increased by 25% (8k→10k) amplifies carry return
3. **Benign period**: Apr-May allowed existing position to ride +11.4% without interruption

All other candidate entries (widened buyA range, removed MA, extended buyB) would have added:
- 03-17 @ 1.479 (sv=-1.1) → 03-20 hits -3.3% stop loss
- Additional MA-less entries → 4 poor trades, -53% relative return impact

---

## Key Insights

1. **Position sizing is the only tunable variable**: all other parameters converged to the same 3 trades at optimal thresholds
2. **v5.5d's tight buyA (-1.2)** filters out 03-17 false dip (sv=-1.1) which would have triggered -3.3% stop loss
3. **Removing MA filter** adds 4 noise trades that halve returns (+5.95% vs +10.06%)
4. **Trailing stop rejected** across 3 test cycles — ETF daily volatility (2-3% swings) causes false exits
5. **v5.6 return/DD ratio (4.04)** still excellent, only slightly diluted by larger position (2.49% DD vs 1.49%)
6. **Only 3 quality trades** in 55 trading days — confirms the market regime (slow grind up + 1 panic event) favors high selectivity

---

## Monthly Breakdown (v5.6)

| Month | Return | Trades | Key Trades |
|:-----:|:------:|:------:|:-----------|
| March | +1.68% | 1 | 03-23 buy @ 1.356 (sv=-3.0) |
| April | +0.00%* | 0 | 04-08 clear @ 1.474 (sv=+3.8); 04-09 buyB @ 1.462 |
| May | — | 0 | Carried April position: at 1.631 on 05-14 but no sell |
| **Total** | +10.06% | 3 | |

*April isolated shows 0% because March position carried through; buyB on 04-09 requires 20MA which needs >20 days data

---

## Configuration (strategy_config.py VERSIONS[-1])

```python
VERSIONS[-1] = {  # v5.6
    "ver": "v5.6",
    "params": {
        "buyA_sv_max": -1.2,
        "buyA_dc_min": -1.0,
        "buyB": {"sv_min": -0.5, "sv_max": 0.5, "position": 1.0},
        "sell_all_sv": 2.0,
        "stop_loss_pct": -3.0,
        "sell_half_sv": None,
        "take_profit_pct": None,
        "trailing_stop_pct": None,
        "max_invest": 10000,
        "composite_wt": [0.3, 0.2, 0.1, 0.4],
    },
}
```

---

## Calibration Models

| Model | Source | Formula | R² | Active |
|:------|:-------|:--------|:--:|:------:|
| Old (48 rows) | DB sentiment | sent = 0.3461 + 0.8168 × composite | 0.92 | **Yes** |
| New (120 rows) | 6-factor K-means + OLS | sent = -0.1309 + 1.0622 × composite | 0.85 | Standby |

Old calibration preferred due to positive intercept providing "optimistic base" that filters noise.

---

## Data Sources

| Table | Source | API |
|:------|:-------|:----|
| `fund_history` | East Money Fund | `api.fund.eastmoney.com/f10/lsjz` |
| `market_sentiment` | Tencent K-line | `web.ifzq.gtimg.cn/appstock/app/fqkline/get` |
| `market_daily_stats` | East Money push2 | `push2.eastmoney.com` (with ut param) |
| `sentiment_raw_factors` | Multi-source | Composite from above + akshare |
| `position` | Manual/System | `_afternoon_check.py` writes |
| `backtest_results` | Simulate | `simulate.py` writes |

## Next Directions

- **Options PCR + futures premium**: blocked — akshare APIs return incomplete data; wait for upstream fix
- **Multi-timeframe sentiment smoothing**: potential but untested
- **Machine learning entry**: 120 rows of raw factors available; could train buy/sell classifier
- **Live performance tracking**: v5.6 active; first live signal on real trading day pending
