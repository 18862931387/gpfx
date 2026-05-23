# A股数据分析与策略回测系统

> 项目路径：`D:\code\xlx\`
> 最后更新：2026-05-23
> MySQL 8.0 | 数据库：`data_analysis` | root/123456
> Git: `github.com/18862931387/gpfx` (SSH)

---

## 一、项目概览

自动化A股数据采集 + 基金净值跟踪 + 情绪量化 + 策略回测一站式系统。

### 架构

```
数据源（东方财富/腾讯证券）
    │
daily_update.py ← MAC调度/手动
    │
MySQL 数据库 (data_analysis)
    │
├── market_daily_stats    大盘涨跌停+成交额
├── market_sentiment      市场情绪（-2.5~2.5）
├── fund_history          基金净值
├── market_capital_flow   大盘资金流向（主力/散户）
    │
Python 回测引擎 (v3.0/v5.3)
    │
策略对比 → 买卖建议
```

---

## 二、数据库结构

### 2.1 当前数据量

| 表 | 记录数 | 覆盖范围 |
|:---|:------:|:---------|
| `fund_history` (563300) | 90条 | 2026-01-05 ~ 2026-05-22 |
| `fund_history` (516330) | 54条 | 2026-02-05 ~ 2026-04-30 |
| `fund_history` (588090) | 43条 | 2026-03-02 ~ 2026-04-30 |
| `market_sentiment` | 89条 | 2026-01-05 ~ 2026-05-22 |
| `market_daily_stats` | 57条 | 2026-02-11 ~ 2026-05-22 |
| `market_capital_flow` | 0条(空) | 需API恢复后重新拉取 |

### 2.2 表结构

#### market_daily_stats — 大盘涨跌停统计

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| trade_date | DATE | 交易日 |
| limit_up | INT | 涨停家数 |
| limit_down | INT | 跌停家数 |
| suspended | INT | 停牌家数 |
| turnover | DECIMAL(15,2) | 成交额（亿） |
| sh_up / sz_up / bj_up | INT | 沪/深/北上涨家数 |
| sh_down / sz_down / bj_down | INT | 沪/深/北下跌家数 |

**数据来源**：`push2.eastmoney.com/api/qt/stock/fflow/kline/get`（with `ut` param）

#### market_sentiment — 市场情绪

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| trade_date | DATE | 交易日 |
| sentiment_value | DECIMAL(5,2) | 情绪值（-2.5~2.5） |
| sentiment_zone | VARCHAR(10) | 冰点/过冷/微冷/0分界/微热/过热/沸点 |
| index_change | VARCHAR(10) | 指数涨跌幅 |
| market_desc | TEXT | 收盘总结 |

**情绪区间**：

| 区间 | 范围 | 含义 |
|:----|:----|:-----|
| 冰点 | ≤ -2.0 | 极度恐慌 |
| 过冷 | -1.9 ~ -1.0 | 明显恐慌 |
| 微冷 | -0.9 ~ -0.1 | 轻度低迷 |
| 0分界 | 0 | 中性 |
| 微热 | 0.1 ~ 0.9 | 温和积极 |
| 过热 | 1.0 ~ 1.9 | 明显乐观 |
| 沸点 | ≥ 2.0 | 极度亢奋 |

**计算方式**：基于上证指数日涨跌幅的加权计算（`daily_update.py` 自动校准）

#### fund_history — 基金净值

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| id | INT (PK, AUTO_INCREMENT) | 自增ID |
| fund_code | VARCHAR(10) | 基金代码 |
| fund_name | VARCHAR(100) | 基金名称 |
| net_date | DATE | 净值日期 |
| unit_nav | DECIMAL(10,4) | 单位净值 |
| accum_nav | DECIMAL(10,4) | 累计净值 |
| daily_growth | DECIMAL(6,2) | 日增长率(%) |

**数据来源**：`api.fund.eastmoney.com/f10/lsjz`（东方财富基金接口）

#### market_capital_flow — 大盘资金流向

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| trade_date | DATE (PK) | 交易日 |
| main_force_net | DECIMAL(15,2) | 主力净流入（元） |
| retail_net | DECIMAL(15,2) | 小单净流入（元） |
| medium_net | DECIMAL(15,2) | 中单净流入（元） |
| large_net | DECIMAL(15,2) | 大单净流入（元） |
| super_large_net | DECIMAL(15,2) | 超大单净流入（元） |
| main_force_pct ~ super_large_pct | DECIMAL(5,2) | 对应占比% |

**字段映射**（`push2his` API）：

| API字段 | 含义 | 数据库字段 |
|:-------|:----|:----------|
| f52 | 主力净流入（大单+超大单） | main_force_net |
| f53 | 小单净流入（散户） | retail_net |
| f54 | 中单净流入 | medium_net |
| f55 | 大单净流入 | large_net |
| f56 | 超大单净流入 | super_large_net |
| f57~f61 | 对应占比% | *_pct |

**验证**：主力净流入 = 大单 + 超大单（f52 ≈ f55 + f56）

**数据来源**：`push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?secid=1.000001`
- 需 `IPv4` 强制访问（服务端偶发阻断 IPv6）
- 带 `ut=fa5fd1943c7b386f172d6893dbbd1d0c` 参数
- 服务端间歇性不可用，`daily_update.py` 内置 3 次重试

**与情绪关联**：相关系数 0.725（情绪冰点时主力平均净流出-216亿）

---

## 三、核心文件

| 文件 | 说明 |
|:----|:------|
| `daily_update.py` | **一键更新**：指数+基金净值+资金流向（IPv4+重试） |
| `simulate.py` | v3.0 回测基准脚本 |
| `strategy_comparison.md` | 策略对比文档 |
| `export_db.py` | 导出数据库为SQL文件 |
| `import_db.py` | 导入SQL文件到本地MySQL |
| `a_stock_limits.py` | 拉取涨跌停数据 |
| `a_stock_indices.py` | 查看实时指数行情 |

---

## 四、交易策略

### v3.0（基准版 — 情绪驱动）

| 规则 | 条件 |
|:----|:-----|
| **仓位上限** | 50%（2万元本金最多1万） |
| **买入** | 情绪 ≤ -0.8 **且** ETF 日跌幅 ≥ 1% |
| **清仓** | 情绪 ≥ 1.0 |
| **止盈** | 持仓盈利 ≥ 2% → 卖一半 |
| **止损** | 持仓亏损 ≥ 3% → 全清 |

### v5.3 ⭐（综合版 — 最优）

| 规则 | 条件 |
|:----|:-----|
| **买入** | v3.0条件 +（成交额 ≥ 25000亿 **或** 跌停数 > 涨停数） |
| **卖出** | 同 v3.0 |

### 回测结果（563300, 2026/01/05 ~ 2026/05/22）

| 策略 | 收益率 | 最大回撤 | 交易次数 | 期末资产 |
|:----:|:------:|:--------:|:--------:|:--------:|
| **v5.3** ⭐ | **+7.63%** | **0.15%** | **10** | **21,525** |
| v3.0 | +5.90% | 3.69% | 18 | 21,179 |
| v5.2 (跌停确认) | +6.88% | 0.15% | 7 | 21,376 |
| v5.0 (放量) | +2.89% | 3.69% | 8 | 20,578 |

### 按月表现（v5.3）

| 月 | 基金 | v5.3 | 交易 |
|:--|:----:|:----:|:------|
| 1月 | +7.57% | +0.00% | 无数据，空仓 |
| 2月 | +7.62% | +0.00% | 信号被成交量过滤 |
| 3月 | **-8.40%** | **+2.60%** | 两笔抄底反弹 |
| 4月 | +8.08% | +3.49% | 两笔，节奏正确 |
| 5月 | +2.39% | +1.37% | 5/21买入→5/22卖出 |

---

## 五、API说明

| 数据 | API | 说明 |
|:----|:----|:------|
| ETF净值 | `api.fund.eastmoney.com/f10/lsjz` | 历史净值，稳定可用 |
| 指数K线 | `web.ifzq.gtimg.cn/appstock/app/fqkline/get` | 腾讯证券，稳定 |
| 涨跌停 | `push2.eastmoney.com/api/qt/stock/fflow/kline/get` | 需 `ut` 参数 |
| 资金流向 | `push2his.eastmoney.com/api/qt/stock/fflow/daykline/get` | 需 IPv4 + `ut`，间歇性不可用 |

**IPv4 强制方法**：
```python
import socket, requests.packages.urllib3.util.connection as urllib3_cn
urllib3_cn.allowed_gai_family = lambda: socket.AF_INET
```

---

## 六、注意事项

1. **IPv4**: 东方财富 `push2` 系列 API 必须 IPv4 访问，IPv6 会连接成功但服务器无响应
2. **`ut` 参数**: `fa5fd1943c7b386f172d6893dbbd1d0c`（从东方财富页面提取）
3. **数据回填**: `market_capital_flow` 为空表，需 API 恢复后运行 `daily_update.py` 自动填充
4. **情绪校准**: `market_sentiment` 基于上证指数涨跌幅加权计算，`daily_update.py` 自动完成
5. **Git 同步**: `git push` 前确保 SSH key 已添加到 GitHub
