# A股数据分析与尾盘决策系统

> 项目路径：`D:\code\xlx\`
> 最后更新：2026-05-26
> MySQL 5.6 | 数据库：`data_analysis` | root/root123
> Git: `github.com/18862931387/gpfx` (SSH)

---

## 一、项目概览

自动化A股数据采集 + 基金净值跟踪 + 情绪量化 + 尾盘决策一站式系统。

### 架构

```
数据源（东方财富/腾讯证券/同花顺）
    │
daily_update.py ← 手动运行
    │
MySQL 数据库 (data_analysis)
    │
├── market_daily_stats      大盘涨跌停+成交额
├── market_sentiment        市场情绪（-2.5~2.5）
├── fund_history            基金净值
├── position                持仓记录
├── backtest_results        策略回测结果
├── strategy_def            策略定义
    │
_afternoon_check.py ← 14:30后运行
    │
尾盘决策 → 买卖建议
```

---

## 二、数据库结构

### 2.1 当前数据量

| 表 | 记录数 | 说明 |
|:---|:------:|:-----|
| `fund_history` | 113条 | 3只ETF净值（516330/563300/588090） |
| `market_sentiment` | 50条 | 2026-01-05 ~ 2026-05-25 |
| `market_daily_stats` | 59条 | 2026-02-11 ~ 2026-05-25 |
| `position` | 3条 | 5/21建仓→5/25清仓 563300 (含5/25更新) |
| `backtest_results` | 36条 | 6策略×2基金×3时段 |

### 2.2 核心表

#### position — 持仓记录

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
| note | TEXT | 备注 |

---

## 三、核心文件

| 文件 | 说明 |
|:----|:------|
| `_afternoon_check.py` | **尾盘决策 v5.4** — 实时行情+情绪+资金流向+交易信号 |
| `daily_update.py` | 一键更新：指数行情+基金净值 |
| `sentiment_calibrate.py` | 情绪计算核心算法 |
| `verify_db.py` | 数据库数据验证 |
| `strategy_comparison.md` | 策略对比文档 |

---

## 四、交易策略 v5.4

### 买入条件（全部满足）

| # | 条件 | 说明 |
|:-:|:----|:-----|
| ① | 情绪 ≤ -0.8 | 市场恐慌 |
| ② | ETF 日跌幅 ≥ 1% | 个股跟随下跌 |
| ③ | 成交额 ≥ 25000亿 **或** 跌停 > 涨停 | 量价确认 |
| ④ | 尾盘5分钟主力净流入 | 主力抄底确认（2026-05-25 新增） |

### 卖出条件

| 规则 | 条件 |
|:----|:------|
| **情绪过热** | 情绪 ≥ **1.5** → 清仓（v5.4从1.0上调） |
| **止盈** | 浮盈 ≥ 2% → 卖一半 |
| **止损** | 日跌 ≥ 3% → 清仓 |

---

## 五、外部数据源（a-stock-data 集成）

| 数据 | API | 说明 |
|:----|:----|:------|
| 实时行情 | `web.sqt.gtimg.cn` | 腾讯证券，不封IP |
| ETF净值 | `api.fund.eastmoney.com/f10/lsjz` | 东方财富基金历史净值 |
| 涨跌停/成交额 | `push2.eastmoney.com/api/qt/stock/fflow/kline/get` | 需 `ut` 参数 |
| **主力资金流向** | `push2.eastmoney.com/api/qt/stock/fflow/kline/get` | 分钟级，需 `Referer: quote.eastmoney.com` |
| **北向资金** | `data.hexin.cn/market/hsgtApi/method/dayChart/` | 同花顺，沪/深股通实时 |
| **行业板块排名** | `push2.eastmoney.com/api/qt/clist/get` | 东财全行业涨跌排名 |
| **情绪校准** | `market_sentiment` DB历史数据 | 线性回归 SH涨跌幅→情绪值 |

---

## 六、操作流程

### 每日运行

```bash
# 1. 启动 MySQL
Start-Process -FilePath "C:\Program Files\MySQL\MySQL Server 5.6\bin\mysqld.exe" `
  -ArgumentList "--datadir=C:\PROGRA~3\MySQL\MYSQLS~1.6\data --port=3306" -WindowStyle Hidden

# 2. 下午14:30后运行尾盘分析
python _afternoon_check.py

# 3. 收盘后更新净值（可选）
python daily_update.py
```

### 记录交易

```sql
INSERT INTO position (fund_code, fund_name, trade_date, trade_type, shares, price, amount, shares_after, cash_after, note)
VALUES ('563300', '中证2000ETF华泰柏瑞', '2026-05-25', 'sell', 1000, 1.636, 1636, 0, 20039, '清仓: 情绪过热+1.8(v5.4阈值1.5)');
```

---

## 七、注意事项

1. **IPv4**: 东方财富 `push2` 系列 API 必须 IPv4 访问
2. **`ut` 参数**: `fa5fd1943c7b386f172d6893dbbd1d0c`
3. **push2 Referer**: 资金流向类接口需 `Referer: https://quote.eastmoney.com/`
4. **MySQL**: 未注册为服务，每次需手动启动
5. **Git**: `git push` 前需加载 PATH: `$env:Path += ";D:\Program Files\Git\bin"`
