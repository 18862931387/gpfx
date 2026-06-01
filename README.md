# A股数据分析与尾盘决策系统

> 项目路径：`D:\code\xlx\`
> 最后更新：2026-06-01
> MySQL 5.6 | 数据库：`data_analysis` | root/root123
> Git: `github.com/18862931387/gpfx` (SSH)
> 当前版本：**v5.6** — 复合情绪+双买入+精简卖出+仓位1万

---

## 一、项目概览

自动化A股数据采集 + 基金净值跟踪 + 复合情绪量化 + 双策略尾盘决策系统。

### 架构

```
数据源（东方财富/腾讯证券/同花顺/akshare）
    │
daily_update.py ─┬─ 指数涨跌停/成交额
                 ├─ 基金净值
                 ├─ 大盘资金流向
                 └─ 自动触发 backup_db.py
    │
sentiment_pipeline.py ─┬─ 每日采集多因子原始数据
                      ├─ akshare 融资融券余额+北向资金
                      └─ --calibrate: K-means聚类+回归标定
    │
MySQL 数据库 (data_analysis)
    │
├── market_daily_stats       大盘涨跌停+成交额 (57 rows)
├── market_capital_flow      大盘资金流向 (永久丢失)
├── market_sentiment         市场情绪 (120 rows, -2.5~2.5)
├── sentiment_raw_factors    多因子原始数据 (120 rows)
├── fund_history             基金净值 (216 rows)
├── position                 持仓记录 (real+system)
├── backtest_results         策略回测结果 (4 rows)
    │
strategy_config.py  ── VERSIONS[-1] = v5.6 参数中心
    │
_afternoon_check.py  ── 14:30后运行 → 尾盘买卖建议
    │
backup_db.py  ── daily_update.py 自动调用 → db_export_*.sql → git push
```

### 配置中心化

```
config.py  ─┬─ DB = {host, port, user, password, database}
            ├─ CAPITAL = 20000
            ├─ COMPOSITE_WT = {sh: 0.3, sz: 0.2, cy: 0.1, kc: 0.4}
            ├─ API URLs / headers / constants
            └─ 所有脚本 from config import ...
```

---

## 二、数据库结构

### 2.1 核心表

**position — 持仓记录**

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| fund_code | VARCHAR(10) | 基金代码 |
| fund_name | VARCHAR(100) | 基金名称 |
| trade_date | DATE | 交易日 |
| trade_type | VARCHAR(10) | buy/sell |
| shares | INT | 股数 |
| price | DECIMAL(10,4) | 成交价格 |
| amount | DECIMAL(15,2) | 成交金额 |
| shares_after | INT | 操作后持仓 |
| cash_after | DECIMAL(15,2) | 操作后现金 |
| note | TEXT | 备注（real / system 区分） |

**market_sentiment — 市场情绪**

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| trade_date | DATE | 交易日 |
| sentiment_value | DECIMAL(4,2) | -2.5~2.5 |
| sentiment_zone | VARCHAR(10) | 冷热区间 |
| composite_idx | DECIMAL(6,4) | 原始复合指数 |
| calibrated | TINYINT(1) | 是否校准 |

**sentiment_raw_factors — 多因子原始数据**

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| trade_date | DATE | 交易日 |
| sh_pct | DECIMAL(5,2) | 上证涨跌幅% |
| sz_pct | DECIMAL(5,2) | 深证涨跌幅% |
| cy_pct | DECIMAL(5,2) | 创业板涨跌幅% |
| kc_pct | DECIMAL(5,2) | 中证2000涨跌幅% |
| limit_up | INT | 涨停家数 |
| limit_down | INT | 跌停家数 |
| turnover | DECIMAL(15,2) | 成交额(亿) |
| main_force_net | DECIMAL(20,2) | 主力净流入 |
| margin_balance | DECIMAL(20,2) | 融资融券余额 |
| northbound_net | DECIMAL(20,2) | 北向资金净流入 |

---

## 三、核心文件

| 文件 | 说明 |
|:----|:------|
| `config.py` | **配置中心** — DB/API/常量，所有脚本 import |
| `strategy_config.py` | **版本管理中心** — 所有策略变体参数，`VERSIONS[-1]`=v5.6 |
| `_afternoon_check.py` | **尾盘决策 v5.6** — 复合情绪+双买入+清仓/止损+多因子实时修正 |
| `sentiment_pipeline.py` | **情绪流水线** — 每日采集多因子+akshare融资融券/北向+重标定 |
| `sentiment_calibrate.py` | 旧版情绪校准（单指数+涨跌停+成交额+资金流向） |
| `daily_update.py` | **一键更新** — 指数行情+基金净值+资金流向+自动备份 |
| `backup_db.py` | **自动备份** — 7表导出SQL → git add/commit/push，保留7天 |
| `simulate.py` | 策略回测引擎，从 `strategy_config.py` 读取参数 |
| `verify_db.py` | 数据库数据验证查询 |
| `logger.py` | 日志工具 — 控制台 + `logs/YYYYMMDD.log` |
| `query_mysql.py` | MySQL 交互查询入口 |

---

## 四、交易策略 v5.6 (2026-06-01)

### 买入条件

#### 买A — 恐慌抄底（全仓，max_invest=10000）

| # | 条件 | 说明 |
|:-:|:----|:-----|
| ① | 复合情绪 **≤ -1.2** | 极度恐慌 |
| ② | ETF 日跌幅 **≥ -1%** | 价格确认 |
| ③ | 成交额 ≥ 25000亿 **或** 跌停 > 涨停 | 量价确认 |

#### 买B — 趋势跟随（全仓，max_invest=10000）

| # | 条件 | 说明 |
|:-:|:----|:-----|
| ① | 复合情绪 **-0.5 ~ +0.5** | 市场中性 |
| ② | ETF 收盘价 **> 20日均线** | 趋势确立 |

### 卖出条件

| 规则 | 条件 |
|:----|:------|
| **情绪过热** | 复合情绪 ≥ **2.0** → 清仓 |
| **止损** | 日跌 ≥ **-3%** → 清仓 |

### 实时情绪修正（calc_sentiment）

| 因子 | 条件 | 修正值 |
|:----|:----|:------|
| margin_chg（融资变化率） | +0.72% → | +0.1 |
| 北向净流入 | > +80亿 → | +0.4 |
| 北向净流入 | < -60亿 → | -0.4 |
| 涨停/跌停比 > 3 || +0.3 |
| 涨停/跌停比 < 0.3 || -0.3 |
| 成交额 > 25000亿 || ±0.2 |
| 成交额 < 18000亿 || ×0.7 |
| 主力净流入 > 200亿 || +0.2 |
| 主力净流入 < -200亿 || -0.2 |
| 总计上限 || ±2.5 |

### 参数配置

```python
VERSIONS[-1] = {  # v5.6
    "ver": "v5.6",
    "params": {
        "buyA_sv_max": -1.2,
        "buyA_dc_min": -1.0,
        "buyB": {"sv_min": -0.5, "sv_max": 0.5, "position": 1.0},
        "sell_all_sv": 2.0,
        "stop_loss_pct": -3.0,
        "sell_half": None,
        "take_profit": None,
        "trailing_stop": None,
        "max_invest": 10000,
        "composite_wt": [0.3, 0.2, 0.1, 0.4],
    },
}
```

---

## 五、情绪量化模型

### 复合指数

4指数加权：**上证0.3 + 深证0.2 + 创业板0.1 + 中证2000 0.4**

中证2000权重最高，对齐持仓标的 563300（中证2000ETF）。

### 回归校准

两条校准线并存，旧校准为默认：

| 校准 | 数据量 | 公式 | R² | 回测收益 |
|:----|:-----:|:----|:--:|:-------:|
| **旧标定**（默认） | 48条 | sentiment = 0.3461 + 0.8168×composite | 0.92 | **+10.06%** |
| 新标定（备用） | 120条 | sentiment = -0.1309 + 1.0622×composite | 0.85 | +8.05% |

旧校准的"乐观基值"（0.3461截距）在回测中过滤噪声，收益更优。

### 多因子修正

实时修正因子在 `_afternoon_check.py` 的 `calc_sentiment()` 中执行（见上表），margin_chg 和 northbound_net 为 v5.6 新增。

---

## 六、回测结果对比

| 版本 | BuyA阈值 | 仓位 | 收益 | 最大回撤 | 交易次数 | 备注 |
|:---:|:--------:|:---:|:----:|:-------:|:-------:|:----|
| v5.4 | ≤-0.8 | 10000 | +4.64% | 2.38% | 10 | 单指数+卖一半+止盈 |
| v5.5a | ≤-0.8 | 10000 | +3.15% | 2.38% | 7 | 复合指数+买B半仓 |
| v5.5b | ≤-0.8 | 10000 | +4.89% | 2.38% | 7 | 去止盈 |
| v5.5c | ≤-0.5 | 8000 | +8.41% | 2.38% | 5 | 去卖一半+买B全仓 |
| v5.5d | ≤**-1.2** | 8000 | +8.05% | 1.49% | 3 | 最佳风控 |
| v5.5e | ≤-1.2 | 8000 | — | — | — | 加回撤止损→被ETF日波动误触 |
| **v5.6** | ≤-1.2 | **10000** | **+10.06%** | **2.49%** | **3** | **仅升仓位，其余不变** |

### 核心发现 (网格搜索)

- **仓位越大收益越高**（线性缩放 8000→10000→12000→20000，收益同比放大）
- **buyA阈值不可松**：放宽到≤-0.8 → 收益从+10.06%缩到+8.41%
- **去MA过滤**：收益腰斩（+5.95%），增加4笔噪声交易
- **buyB范围不变**：扩展到-1.0~0.5 → 0额外交易（价格在MA之下）
- **回撤止损被否**：ETF日内波动大，3次测试均导致假退出

### v5.6 交易明细（55天回测）

| 日期 | 操作 | 价格 | 情绪 | 盈亏 |
|:---:|:----|:----:|:----:|:----:|
| 03-23 | **买A** 恐慌抄底 | 1.356 | sv=-3.0 | — |
| 04-08 | **清仓** 情绪过热 | 1.474 | sv=+3.8 | +1.42%（10000→12410） |
| 04-09 | **买B** 趋势跟随 | 1.462 | sv=-0.1 | — |

03-23买入→04-08卖出（+8.7%大恐慌弹性反弹），04-09趋势跟随至今。

---

## 七、数据源

| 数据 | API | 说明 |
|:----|:----|:------|
| 实时行情 | `web.sqt.gtimg.cn` | 腾讯证券，不封IP |
| ETF日K线 | `web.ifzq.gtimg.cn/appstock/app/fqkline/get` | 前复权 |
| ETF净值 | `api.fund.eastmoney.com/f10/lsjz` | 东方财富基金历史净值 |
| 涨跌停/成交额 | `push2.eastmoney.com` | 需 IPv4 + Referer |
| 主力资金流向 | `push2.eastmoney.com/api/qt/ulist.np/get` | 需 Referer |
| 北向资金 | `data.hexin.cn/market/hsgtApi/method/dayChart/` | 同花顺 |
| **融资融券余额** | `akshare.stock_margin_detail_sse()` | 上交所数据 |
| **北向净流入** | `akshare.stock_hsgt_fund_flow_summary_em()` | akshare东方财富 |

---

## 八、操作流程

### 每日运行

```bash
# 1. 启动 MySQL（服务未注册时）
Start-Process -FilePath "C:\Program Files\MySQL\MySQL Server 5.6\bin\mysqld.exe" `
  -ArgumentList "--datadir=C:\PROGRA~3\MySQL\MYSQLS~1.6\data --port=3306" -WindowStyle Hidden

# 2. 数据更新（收盘后）
python daily_update.py
#    → 自动调用 backup_db.py → git push

# 3. 下午14:30后运行尾盘分析（有仓时）
python _afternoon_check.py

# 4. 情绪数据采集（每日）
python sentiment_pipeline.py
#    → --calibrate 参数触发重标定（建议60+交易日）

# 5. 回测验证参数（调参后）
python simulate.py
```

### 调参流程

```bash
1. 编辑 strategy_config.py，在 VERSIONS 末尾追加新版本
2. python simulate.py 对比新旧版本回测结果
3. 满意后，确保 get_latest() 返回新版本
4. python _afternoon_check.py 确认脚本生效
```

### 备份

```bash
# 每日自动（通过 daily_update.py）或手动：
python backup_db.py
# 导出 7 表 → db_export_YYYY-MM-DD.sql → git add/commit/push → 保留7天
```

---

## 九、注意事项

1. **IPv4 强制**：东方财富 push2 系列 API 必须 IPv4 访问（`import requests.packages.urllib3.util.connection as ucn; ucn.allowed_gai_family = lambda: socket.AF_INET`）
2. **push2 Referer**：资金流向类接口需 `Referer: https://quote.eastmoney.com/`
3. **MySQL 非服务**：MySQL 5.6 未注册为 Windows 服务，每次需手动启动 mysqld
4. **Git 推送**：需加载 `$env:Path += ";D:\Program Files\Git\bin"`
5. **情绪重标定**：`python sentiment_pipeline.py --calibrate` 触发 6 因子 K-means + OLS
6. **网格搜索结论**：当前参数组合已接近最优（55天窗口），新增信号源需等待 akshare 更新 options PCR / futures premium
