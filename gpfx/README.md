# A股数据分析与尾盘决策系统

> 最后更新：2026-07-27
> MySQL: 192.168.3.68 | 数据库：`data_analysis` | root/root123
> Git: `github.com/18862931387/gpfx`
> 当前版本：**v6.7** — K-means情绪聚类 + 510300专用 + 网格搜索优化阈值
> 服务器部署：详见 [DEPLOY.md](DEPLOY.md)

---

## 一、项目概览

自动化A股数据采集 + 基金净值跟踪 + 情绪量化(K-means++) + 双策略尾盘决策系统。

**标的**: `510300` 沪深300ETF（原 563300 中证2000ETF，2026-07-23 切换）

### 架构

```
数据源（东方财富/腾讯证券/同花顺/akshare）
    │
daily_update.py ─┬─ 指数涨跌停/成交额
                 ├─ 基金净值
                 ├─ 大盘资金流向 (push2his日线)
                 ├─ ETF K线缓存
                 └─ 自动触发 backup_db.py
    │
sentiment_pipeline.py ─┬─ 每日采集多因子原始数据
                      ├─ akshare 融资融券余额
                      └─ --calibrate: K-means聚类+回归标定
    │
sentiment_v6.py ── K-means++ 聚类标定(4纯市场因子，去循环论证)
    │               → sentiment = -0.2917 + 0.3861 × composite
    │
MySQL 数据库 (data_analysis)
    │
├── market_daily_stats       大盘涨跌停+成交额
├── market_capital_flow      大盘资金流向 (push2his日线)
├── market_sentiment         市场情绪 (v5/v6双字段)
├── index_daily              四大指数日涨跌幅备份
├── market_news              每日新闻标题+情绪打分
├── sentiment_raw_factors    多因子原始数据 (4聚类因子)
├── fund_history             基金净值
├── etf_kline                ETF日K线缓存
├── position                 持仓记录 (real+system)
├── backtest_results         策略回测结果
├── strategy_signals         策略信号日志
├── near_miss_signals        近失信号记录
    │
strategy_config.py  ── VERSIONS 版本管理，get_latest()=v6.7
    │
_afternoon_check.py  ── 14:30后运行 → 尾盘买卖建议
    │
simulate.py  ── 策略回测引擎
```

### 配置中心化

```
config.py  ─┬─ DB = {host, port, user, password, database}
            ├─ CAPITAL = 20000
            ├─ PRIMARY_FUND = '510300'
            ├─ COMPOSITE_WT = {sh: 0.3, sz: 0.2, cy: 0.1, zz2000: 0.4}
            ├─ EASTMONEY_UT = 'b2884a393a59ad64002292a3e90d46a5'
            ├─ API URLs / headers / constants
            └─ 所有脚本 from config import ...
```

---

## 二、数据库结构

### 2.1 核心表

**fund_history — 基金净值**

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| fund_code | VARCHAR(10) | 基金代码 |
| net_date | DATE | 净值日期 |
| unit_nav | DECIMAL(10,4) | 单位净值 |
| accum_nav | DECIMAL(10,4) | 累计净值 |
| daily_growth | DECIMAL(6,2) | 日增长率% |

**etf_kline — ETF日K线缓存**

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| fund_code | VARCHAR(10) | 基金代码 |
| trade_date | DATE | 交易日 |
| open/high/low/close | DECIMAL(10,4) | OHLC |
| volume | DECIMAL(20,2) | 成交量 |
| is_adj | TINYINT(1) | 1=前复权 |

**position — 持仓记录**

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| fund_code | VARCHAR(10) | 基金代码 |
| trade_date | DATE | 交易日 |
| trade_type | VARCHAR(10) | buy/sell |
| shares | INT | 股数 |
| price | DECIMAL(10,4) | 成交价格 |
| cash_after | DECIMAL(15,2) | 操作后现金 |
| note | TEXT | 备注（real / system 区分） |

**market_sentiment — 市场情绪**

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| trade_date | DATE | 交易日 |
| sentiment_value | DECIMAL(5,2) | 旧版情绪值 (-2.5~2.5) |
| sentiment_v6 | DECIMAL(5,2) | v6 K-means情绪值 (-2.5~2.5) |
| sentiment_zone | VARCHAR(10) | 冷热区间 |
| composite_idx | DECIMAL(6,4) | 4指数加权值 |

**sentiment_raw_factors — 多因子原始数据**

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| trade_date | DATE | 交易日 |
| composite_index | DECIMAL(10,4) | 4指数加权涨跌幅 |
| sector_ad_ratio | DECIMAL(6,4) | 板块涨跌比 |
| volume_pctile_60d | DECIMAL(5,2) | 60日成交量百分位 |
| main_force_net | DECIMAL(15,2) | 主力净流入 |
| margin_balance | DECIMAL(20,2) | 融资融券余额 |
| sentiment_label | DECIMAL(5,2) | 聚类标签 (-2~+2) |

> 2024年8月起北向资金日频数据已停止披露，northbound_net 因子已移除

**market_capital_flow — 大盘资金流向**

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| trade_date | DATE | 交易日 |
| main_force_net | DECIMAL(15,2) | 主力净额(元) |
| super_large_net | DECIMAL(15,2) | 超大单净额 |
| large_net | DECIMAL(15,2) | 大单净额 |
| retail_net | DECIMAL(15,2) | 散户净额 |

**near_miss_signals — 近失信号记录**

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| trade_date | DATE | 交易日 |
| cond1~cond4 | TINYINT | 四项条件分别满足状态 |
| miss_reason | VARCHAR(100) | 未触发原因 |

---

## 三、核心文件

| 文件 | 说明 |
|:----|:------|
| `config.py` | **配置中心** — DB/API/常量/TOKEN，所有脚本 import |
| `strategy_config.py` | **版本管理中心** — v5.4~v6.7 共18个策略变体，`get_latest()`=v6.7 |
| `_afternoon_check.py` | **尾盘决策** — 实时情绪+4条件买A+买B趋势+信号落地 |
| `sentiment_v6.py` | **V6情绪标定** — K-means++ 聚类(4纯市场因子z-score标准化)+回归 |
| `sentiment_pipeline.py` | **情绪流水线** — 每日采集多因子+自动标定+历史回填 |
| `news_sentiment.py` | **新闻情绪因子** — 新浪财经头条抓取+关键词打分 |
| `daily_update.py` | **一键更新** — 指数行情+净值+K线缓存+资金流向+自动备份 |
| `simulate.py` | **策略回测引擎** — 多版本对比+月度统计+结果入库 |
| `backup_db.py` | **自动备份** — 7表导出SQL → git add/commit/push |
| `a_stock_indices.py` | 指数行情查询工具 |
| `logger.py` | 日志工具 — 控制台 + `logs/YYYYMMDD.log` |
| `zjlx_history.csv` | 历史资金流向数据 (CSV格式) |

---

## 四、交易策略 v6.7 (2026-07-24)

**标的**: `510300` 沪深300ETF | **仓位上限**: 20000

### 买入条件

#### 买A — 恐慌抄底

| # | 条件 | 阈值 |
|:-:|:----|:-----|
| ① | 情绪值 **≤ -0.4** | 恐慌区间 |
| ② | ETF 日跌幅 **≥ -0.3%** | 价格确认 |
| ③ | 成交额 ≥ 25000亿 **或** 跌停 > 涨停 | 量价确认 |
| ④ | 尾盘5分钟主力资金 **净流入** | 抄底确认 |

极端恐慌(情绪≤-2.0)时条件④放宽至主力>-500亿。

融资去杠杆(5日融资余额变化<-1%)时，条件①阈值从-0.4放宽至-1.0。

#### 买B — 趋势跟随

| # | 条件 | 阈值 |
|:-:|:----|:-----|
| ① | 情绪值 **-0.2 ~ +0.2** | 市场中性 |
| ② | ETF 收盘价 **> 20日均线** | 趋势确立 |

### 卖出条件

| 规则 | 条件 | 操作 |
|:----|:------|:-----|
| **情绪偏高** | 情绪 ≥ **0.3** | 卖一半 |
| **情绪过热** | 情绪 ≥ **0.6** | 清仓 |
| **止损** | 浮亏 ≥ **-3%** | 清仓 |
| **回撤止损** | 从峰值回落 ≥ **-5%** | 清仓 |
| **盈利锁定** | 盈利≥5%后，回撤止损收紧至 **-2.5%** | 清仓 |

### 避险仓位 (中国神华 601088)

| 条件 | 仓位缩放 |
|:----|:------|
| 神华 > MA5 | 避险减仓至 50% |
| 神华 ≤ MA5 | 风险加仓至 150% |

### 参数配置

```python
{
    "ver": "v6.7",
    "active": "2026-07-24~",
    "desc": "510300专用: 新情绪尺度网格搜索优化(买A≤-0.4/跌≥-0.3%), 卖半0.3/清仓0.6",
    "params": {
        "buyA_sv_max": -0.4,
        "buyA_dc_min": -0.3,
        "buyA_margin_boost": True,
        "buyB": {"sv_min": -0.2, "sv_max": 0.2, "position": 1.0},
        "sell_half_sv": 0.3,
        "sell_all_sv": 0.6,
        "stop_loss_pct": -3.0,
        "trailing_stop_pct": -5.0,
        "profit_lock": 5.0,
        "lock_trailing_stop": -2.5,
        "max_invest": 20000,
        "composite_wt": [0.3, 0.2, 0.1, 0.4],
        "sentiment_formula": "sentiment = -0.2917 + 0.3861 × composite",
        "sentiment_source": "sentiment_v6",
        "haven_code": "601088",
        "haven_name": "中国神华",
        "haven_ma_window": 5,
        "haven_scale": 0.5,
        "risk_scale": 1.5,
    },
}
```

---

## 五、情绪量化模型 (V6)

### 核心改进 (vs v5)

| 维度 | v5 (旧) | v6 (新) |
|:----|:-----|:-----|
| 分组方式 | 等频分箱(强制20%每档) | K-means++ 聚类(数据自驱动) |
| 聚类因子 | 含复合指数(循环论证) | 4纯市场指标(去循环论证) |
| 因子数 | 6因子(含北向) | 4因子(北向数据停发) |
| 轮廓系数 | 0.36 | 0.45 (+25%) |
| 情绪尺度 | 压缩[-0.5, +0.5] | 拉伸[-2.2, +1.3] |

### 4聚类因子 (z-score标准化)

| 因子 | 说明 | 来源 |
|:----|:-----|:-----|
| log_ad | 板块涨跌比对数值 | 东财行业板块 |
| vol_pct | 60日成交量百分位 | market_daily_stats |
| flow | 主力净流入 | push2/push2his |
| margin_chg | 融资余额5日变化率 | akshare SSE |

### 回归映射

聚类后按各簇平均复合指数排序，映射到 -2~+2 情绪标签，再回归到复合指数：

```
sentiment = -0.2917 + 0.3861 × composite
R² = 0.1786 (v5循环论证R²=0.92为虚高)
```

### 多因子实时修正 (_afternoon_check.py)

| 因子 | 条件 | 修正值 |
|:----|:----|:------|
| 涨停/跌停比 > 3 | 情绪<0时 | +0.3 |
| 涨停/跌停比 < 0.5 | 情绪>0时 | -0.3 |
| 成交额 > 25000亿 | — | ±0.2 |
| 成交额 < 18000亿 | — | ×0.7 |
| 主力净流入 | 与情绪同向 | 比例加成 |
| 融资5日变化 > +1% | — | +0.2 |
| 融资5日变化 < -1% | — | -0.3 |
| 新闻情绪 | score×0.3 | ±0.6 |
| 总计上限 | — | ±2.5 |

---

## 六、策略版本演进

### v6.x 系列 (K-means情绪 + 510300)

| 版本 | 关键参数 | 收益 | 回撤 | 交易 | 备注 |
|:---:|:--------|:----:|:----:|:---:|:----|
| v6.0 | v5.6参数+K-means | — | — | — | 新情绪基线 |
| v6.1 | 仓位15000 | — | — | — | 网格搜索最优 |
| v6.4 | 回撤-7%+盈利锁8% | +21.66% | 5.97% | — | R/R=3.6 |
| v6.5 | +神华避险 | +27.35% | 4.70% | — | R/R=5.8 |
| v6.6 | 510300切换+阈值放宽 | — | — | — | 买A≤-0.8 |
| v6.6a | v6.6 + 神华避险 | -0.47% | — | 7 | 跑赢buy&hold+1.19% |
| **v6.7** | **新情绪尺度网格搜索** | **+11.80%** | **4.66%** | — | **买A≤-0.4/卖半0.3/清仓0.6** |

### v5.x 系列 (旧情绪 + 563300 中证2000ETF)

| 版本 | BuyA阈值 | 仓位 | 收益 | 最大回撤 | 交易 |
|:---:|:--------:|:---:|:----:|:-------:|:---:|
| v5.5d | ≤-1.2 | 8000 | +8.05% | 1.49% | 3 |
| v5.6 | ≤-1.2 | 10000 | +10.06% | 2.49% | 3 |
| v5.8 | ≤-1.2 | 10000 | — | — | — | +margin_boost |

### v6.7 800天长期回测 (2023-04-06 ~ 2026-07-24)

| 指标 | v6.7 | buy&hold |
|:----|:----:|:-------:|
| 总收益 | +6.63% | +24.74% |
| 最大回撤 | 4.66% | 25.04% |
| 风险收益比 | 1.42 | 0.99 |

> 长期回测中 v6.7 在熊市保护出色，但牛市因卖阈值偏低(0.3/0.6)过早离场，错过了部分涨幅。

### 近半年表现 (2026-01-24 ~ 2026-07-24)

| 指标 | v6.7 | buy&hold | 超额 |
|:----|:----:|:-------:|:---:|
| 收益 | +2.90% | +0.81% | **+2.09%** |
| 回撤 | 0.84% | 8.56% | — |
| 交易 | 25次 | — | — |

---

## 七、数据源

| 数据 | API | 说明 |
|:----|:----|:------|
| 实时行情 | `web.sqt.gtimg.cn` | 腾讯证券，不封IP |
| ETF日K线 | `web.ifzq.gtimg.cn/appstock/app/fqkline/get` | 前复权 |
| ETF净值 | `api.fund.eastmoney.com/f10/lsjz` | 东方财富基金历史净值 |
| 涨跌停/成交额 | `push2.eastmoney.com` | 需 IPv4 + Referer |
| 主力资金流向(日线) | `push2his.eastmoney.com` | 沪深两市合并，稳定不受限流 |
| 主力资金流向(个股) | `push2.eastmoney.com/api/qt/ulist.np/get` | 尾盘实时 |
| 北向资金 | `data.hexin.cn` | 同花顺，需去偏移 |
| 融资融券余额 | `akshare.stock_margin_sse()` | 上交所数据 |
| 行业板块资金 | `akshare.stock_sector_fund_flow_rank()` | 行业+概念 |
| 涨停跌停池 | `akshare.stock_zt_pool_em()` | 实时涨停池 |

> **注意**: push2 实时接口存在IP限流，主力资金数据优先使用 push2his 日线接口；
> 当 push2his 不可用时，使用 `data.eastmoney.com/zjlx/dpzjlx.html` 页面解析作为兜底。

---

## 八、操作流程

### 每日运行

```bash
# 1. 数据更新（收盘后）
python daily_update.py
#    → 自动调用 backup_db.py

# 2. 下午14:30后运行尾盘分析
python _afternoon_check.py

# 3. 情绪数据采集（每日）
python sentiment_pipeline.py

# 4. 回测验证参数
python simulate.py                   # 使用最新版本
python simulate.py --ver=v6.6a       # 指定版本对比
```

### 情绪标定

```bash
# 标定 + 打印结果
python sentiment_v6.py

# 标定 + 写入DB
python sentiment_v6.py --store

# 仅回填历史数据
python sentiment_v6.py --backfill
```

### 调参流程

```bash
1. 编辑 strategy_config.py，在 VERSIONS 末尾追加新版本
2. 更新 get_latest() 返回新版本索引
3. python simulate.py 对比新旧版本回测结果
4. 满意后 git commit & push
```

---

## 九、注意事项

1. **IPv4 强制**：东方财富 push2 系列 API 必须 IPv4 访问
2. **push2 Referer**：资金流向类接口需 `Referer: https://quote.eastmoney.com/`
3. **push2 限流**：实时接口受IP限制，主力资金使用 push2his 日线接口兜底
4. **EASTMONEY_UT Token**：定期更新 config.py 中的 token 值
5. **北向资金**：2024年8月起日频数据停止披露，相关因子已移除
6. **情绪重标定**：建议每累积30+交易日数据后运行 `python sentiment_v6.py --store`
7. **策略版本**：`get_latest()` 手动维护，新增版本后需同步更新索引
8. **数据库备份**：`db_export_*.sql` 文件较大(3-4MB)，推送时注意超时