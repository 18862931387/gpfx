# 📊 数据分析项目文档

> 项目路径：`D:\code\xlx\`  
> 最后更新：2026-05-01  
> MySQL 8.0.25 | 数据库：`data_analysis` | root/123456

---

## 一、项目概览

自动化A股市场数据采集 + 基金净值跟踪 + 情绪量化 + 策略回测一站式系统。

### 架构图

```
数据源（搜狐/天天基金/财联社）
        │
    [自动化任务]  ← 每个交易日自动触发
        │
    MySQL 数据库 (data_analysis)
        │
    ┌───┼───────────┐
    │   │           │
  大盘数据 基金净值  市场情绪
        │
    [Python回测引擎]
        │
  策略对比 → 买卖建议
```

---

## 二、数据库结构

### 2.1 数据表总览

```sql
data_analysis/
├── market_daily_stats    -- 大盘涨跌停统计（自动化更新）
├── market_sentiment      -- 市场情绪（自动化更新）
├── fund_history          -- 基金净值（自动化更新）
├── strategy_def          -- 策略定义（手动维护）
└── backtest_results      -- 回测结果（自动入库）
```

### 2.2 表结构详解

#### 📈 market_daily_stats — 大盘涨跌停日度统计

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| trade_date | date | 交易日 |
| limit_up | int | 涨停家数 |
| limit_down | int | 跌停家数 |
| suspended | int | 停牌家数 |
| turnover | decimal(15,2) | 成交额（亿） |
| sh_up / sz_up / bj_up | int | 沪/深/北上涨家数 |
| sh_down / sz_down / bj_down | int | 沪/深/北下跌家数 |

**数据量**：50条 (2026-02-11 ~ 2026-04-30)

#### 🧠 market_sentiment — 市场情绪

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| trade_date | date | 交易日 |
| sentiment_value | decimal(4,2) | 情绪值（-2.1~2.5） |
| sentiment_zone | varchar(10) | 情绪区间（冰点/过冷/微冷/0分界/微热/过热/沸点） |
| market_desc | text | 收盘总结（财联社收评） |

**数据量**：42条 (2026-03-03 ~ 2026-04-30)

**情绪区间对照**：

| 区间 | 值范围 | 含义 |
|:----|:------|:-----|
| 冰点 | ≤ -2.0 | 极度恐慌 |
| 过冷 | -1.9 ~ -1.0 | 明显恐慌 |
| 微冷 | -0.9 ~ -0.1 | 轻度低迷 |
| 0分界 | 0 | 中性 |
| 微热 | 0.1 ~ 0.9 | 温和积极 |
| 过热 | 1.0 ~ 2.4 | 明显乐观 |
| 沸点 | ≥ 2.5 | 极度亢奋 |

#### 💰 fund_history — 基金净值

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| id | int (PK, AUTO_INCREMENT) | 自增ID |
| fund_code | varchar(10) | 基金代码 |
| fund_name | varchar(100) | 基金名称 |
| net_date | date | 净值日期 |
| unit_nav | decimal(10,4) | 单位净值 |
| accum_nav | decimal(10,4) | 累计净值 |
| daily_growth | decimal(6,2) | 日增长率(%) |
| purchase_status / redemption_status | varchar(20) | 申赎状态 |
| create_time / update_time | datetime | 时间戳 |

**唯一索引**：`(fund_code, net_date)`  
**数据量**：

| 基金代码 | 基金名称 | 记录数 | 覆盖范围 |
|:-------:|:--------|:-----:|:--------|
| **563300** | 中证2000ETF华泰柏瑞 | 43条 | 03-02 ~ 04-30 |
| **516330** | 物联网ETF华泰柏瑞 | 54条 | 02-05 ~ 04-30 |
| **588090** | 科创50ETF华泰柏瑞 | 43条 | 03-02 ~ 04-30 |

#### 📋 strategy_def — 策略定义

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| id | int (PK) | 策略ID |
| strategy_name | varchar(100) | 策略名 |
| version | varchar(20) | 版本号 |
| description | text | 简介 |
| buy_rules / sell_rules | text | 买卖规则描述 |
| position_rules | text | 仓位规则 |
| special_rules | text | 特殊规则 |

**已登记策略**（5个）：

| ID | 版本 | 核心差异 |
|:--:|:----:|:---------|
| 1 | v3.0 | 基础版：冰点买入，过热卖出 |
| 2 | v3.1 | 亏损清仓当日不重复买入 |
| 3 | v3.2 | 分批建仓（首批5000，浮亏3%再补） |
| 4 | v3.3 | 止损线放宽到-5% |
| 5 | v3.4 | 按情绪深度分档建仓 |

#### 📊 backtest_results — 回测结果

| 字段 | 类型 | 说明 |
|:----|:----|:-----|
| id | int (PK) | 自增ID |
| strategy_id | int | 关联 strategy_def.id |
| fund_code | varchar(10) | 基金代码 |
| period_label | varchar(20) | 期间（3月/4月/3-4月） |
| initial_capital | decimal(12,2) | 初始本金 |
| final_value | decimal(12,2) | 期末总资产 |
| total_return | decimal(8,2) | 收益率(%) |
| total_profit | decimal(12,2) | 收益额(元) |
| max_drawdown | decimal(8,2) | 最大回撤(%) |
| trade_count | int | 交易次数 |

**唯一索引**：`(strategy_id, fund_code, period_label)`  
**数据量**：30条（5策略 × 2基金 × 3期间）

---

## 三、自动化任务说明

系统通过 WorkBuddy 的 `automation_update` 工具注册了 **3个自动化任务**，每个交易日自动运行。

### 3.1 任务清单

| ID | 名称 | 调度 | 数据源 | 目标表 | 状态 |
|:--:|:-----|:----:|:-------|:------|:----:|
| automation-1777623529126 | 每日大盘数据更新 | 周一到周五 | 搜狐财经 | market_daily_stats | ACTIVE |
| automation-1777624507137 | 每日基金净值更新 | 周一到周五 | 天天基金 | fund_history | ACTIVE |
| automation-1777625239716 | 每日收盘总结更新 | 周一到周五 | 财联社 | market_sentiment | ACTIVE |

### 3.2 任务详细说明

#### 任务1：每日大盘数据更新

```
名称：每日大盘数据更新
来源：https://q.stock.sohu.com/cn/zdt.shtml
目标：market_daily_stats 表
调度：FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
执行逻辑：
  WebFetch 抓取搜狐页面涨停/跌停/成交额等数据
  → 提取最新交易日统计数据
  → INSERT ON DUPLICATE KEY UPDATE 入库
```

**抓取内容**：涨停家数、跌停家数、停牌家数、成交额、沪/深/北三市上涨/下跌/平盘家数。

#### 任务2：每日基金净值更新 (重要！)

```
名称：每日基金净值更新
来源：天天基金（东方财富）
目标：fund_history 表
调度：FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
```

**关键执行步骤**：

```
1. WebFetch 分别抓取三只基金的详情页：
   https://fund.eastmoney.com/563300.html  → 中证2000ETF
   https://fund.eastmoney.com/516330.html  → 物联网ETF
   https://fund.eastmoney.com/588090.html  → 科创50ETF

2. 提取页面"净值数据"表格：日期、单位净值、累计净值、日增长率
   日期格式 MM/DD → 转换为 YYYY-MM-DD（当前年份2026）

3. 生成 INSERT SQL，写入临时文件 D:\code\xlx\_auto_fund.sql
   注意：日增长率去掉%符号（如"+0.74%"→0.74）

4. 执行导入（必须带 --default-character-set=utf8mb4 参数，否则中文报错）
   mysql -u root -p123456 --default-character-set=utf8mb4 -D data_analysis < _auto_fund.sql

5. 验证最新记录并清理临时文件
```

**SQL 示例**：
```sql
INSERT INTO fund_history (fund_code,fund_name,net_date,unit_nav,accum_nav,daily_growth,purchase_status,redemption_status,create_time,update_time)
VALUES ('563300','中证2000ETF华泰柏瑞','2026-04-30',1.5592,1.5592,0.74,'场内买入','场内卖出',NOW(),NOW())
ON DUPLICATE KEY UPDATE unit_nav=VALUES(unit_nav),accum_nav=VALUES(accum_nav),daily_growth=VALUES(daily_growth),update_time=NOW();
```

#### 任务3：每日收盘总结更新

```
名称：每日收盘总结更新
来源：https://www.cls.cn/subject/1139（财联社主题）
目标：market_sentiment 表
调度：FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
执行逻辑：
  WebFetch 抓取财联社当日收评
  → 提取指数涨跌幅、成交额、热点板块
  → 综合判断情绪值和区间
  → INSERT/UPDATE 到 market_sentiment
```

---

## 四、市场情绪计算规则

### 4.1 计算方式

情绪值（sentiment_value）**不是通过数学公式计算**，而是由「每日收盘总结更新」自动化任务读取财联社收评后，**综合多个维度人为判断打分**（类似于一个经验丰富的交易员凭感觉给市场情绪打分）。

### 4.2 判断维度（5个）

| 维度 | 数据来源 | 参考指标 |
|:----|:---------|:---------|
| ① **指数表现** | 上证指数涨跌幅 | 大涨/小涨/平盘/小跌/大跌 |
| ② **赚钱效应** | 涨跌家数比、涨停数量 | 普涨还是普跌 |
| ③ **成交量** | 沪深两市成交额 | 放量/缩量/持平 |
| ④ **热点强度** | 领涨板块及涨停个股 | 是否有明确主线 |
| ⑤ **市场情绪关键词** | 财联社收评原文 | "恐慌""观望""亢奋""分化"等 |

### 4.3 打分规则

| 区间 | 值范围 | 触发条件 |
|:----|:------|:---------|
| **冰点** 🧊 | -2.0 ~ -2.5 | 指数暴跌（如-3%+）+ 全面普跌 + 恐慌放量 + 无热点 |
| **过冷** ❄️ | -1.0 ~ -1.9 | 指数明显下跌（-1%~-3%）+ 亏钱效应显著 + 缩量 |
| **微冷** 🌥️ | -0.1 ~ -0.9 | 小幅回调（-0.5%~-1%）+ 分化行情 + 成交平淡 |
| **0分界** ➖ | 0 | 平盘震荡（±0.3%以内）+ 方向不明 + 观望 |
| **微热** ☀️ | 0.1 ~ 0.9 | 小幅上涨（+0.3%~+1%）+ 局部热点 + 温和放量 |
| **过热** 🔥 | 1.0 ~ 1.9 | 明显上涨（+1%~+2%）+ 普涨格局 + 放量 + 热点清晰 |
| **沸点** ♨️ | 2.0 ~ 2.5 | 暴涨（+2%+）+ 全面爆发 + 巨量 + 涨停潮 |

### 4.4 判断示例

**3月23日（冰点 -2.1）**：
```
指数：  上证 -3.63%  → 暴跌 ✅
涨跌：  几乎全跌     → 普跌 ✅
成交：  放量          → 恐慌性抛售 ✅
热点：  无            → 全线溃败 ✅
关键词："全球市场恐慌" → 恐慌 ✅
综合：  → 冰点 (-2.1)
```

**4月8日（沸点 +2.5）**：
```
指数：  上证 +2.7%   → 暴涨 ✅
涨跌：  个股普涨     → 普涨 ✅
成交：  放大          → 资金活跃 ✅
热点：  科技领涨     → 主线清晰 ✅
关键词："全面爆发"   → 亢奋 ✅
综合：  → 沸点 (+2.5)
```

**4月30日（微热 +0.20）**：
```
指数：  上证 +0.11%  → 平偏涨 ✅
涨跌：  涨跌互现     → 分化 ✅
成交：  持平          → 观望 ✅
热点：  局部轮动     → 不明确 ✅
关键词："交投平稳"   → 中性 ✅
综合：  → 微热 (+0.20)
```

### 4.5 说明

- 情绪值本质是 **AI模拟人脑判断**，不是纯客观的数学公式
- 但通过 **指数涨跌幅 + 涨跌家数 + 成交量** 这几个客观数据做约束，结果比较稳定
- 如果希望纯公式计算，可基于 `market_daily_stats` 表的涨跌停数据另建量化模型

---

## 五、投资策略体系

### 4.1 稳健策略 v3.0（当前最佳）

| 维度 | 规则 |
|:----|:-----|
| **仓位上限** | 50%（2万本金最多投1万） |
| **买入信号** | 情绪≤-0.8 **且** ETF当日跌幅≥1% |
| **卖出信号1** | 情绪≥1.0 → 全部清仓 |
| **卖出信号2** | 持仓盈利≥2% → 卖出一半 |
| **卖出信号3** | 持仓亏损≥3% → 全部清仓 |
| **不动区间** | 情绪在-0.7~0.9之间，什么都不做 |

**3-4月回测结果**：

| 基金 | 3月 | 4月 | 合计 |
|:----|:---:|:---:|:----:|
| 中证2000ETF(563300) | -0.43% | +2.61% | **+2.58%** |
| 科创50ETF(588090) | -1.69% | +3.73% | **+3.04%** |

### 4.2 策略对比速查

参阅独立文档 `D:\code\xlx\strategy_comparison.md` 获取5个策略变种的完整对比分析。

### 4.3 新增策略的方法

想试新策略，按以下步骤：

```sql
-- 1. 在 strategy_def 中登记新策略
INSERT INTO strategy_def (strategy_name, version, description, buy_rules, sell_rules, position_rules, special_rules)
VALUES ('稳健网格', 'v4.0', '你的策略描述', '买入条件', '卖出条件', '仓位规则', '备注');

-- 2. 记下返回的 strategy_id

-- 3. 在 batch_backtest.py 的 strategies 字典中加入新配置
--    strategies = { 6: { ... }, ... }

-- 4. 运行 python batch_backtest.py → 自动生成SQL → 导入数据库

-- 5. 查询对比
SELECT s.version, r.fund_code, r.period_label, r.total_return, r.max_drawdown
FROM backtest_results r JOIN strategy_def s ON r.strategy_id = s.id
WHERE r.period_label = '3-4月'
ORDER BY r.total_return DESC;
```

---

## 六、数据源与API

| 数据 | 来源 | 获取方式 | 频率 |
|:----|:----|:---------|:----:|
| 涨跌停统计 | 搜狐财经 `q.stock.sohu.com/cn/zdt.shtml` | WebFetch | 每日 |
| ETF净值 | 天天基金 `fund.eastmoney.com/{code}.html` | WebFetch | 每日 |
| 收盘总结 | 财联社 `cls.cn/subject/1139` | WebFetch | 每日 |
| 历史净值API | 东方财富 `api.fund.eastmoney.com/f10/lsjz` | PowerShell+API | 一次性补充 |

---

## 七、文件清单

| 文件 | 说明 |
|:----|:-----|
| `simulate.py` | 单策略回测脚本 |
| `strategy_comparison.md` | 策略对比文档 |
| `import_csv_data.sql` | CSV初始导入SQL |
| `.workbuddy/memory/2026-05-01.md` | 完整工作日志 |

---

## 八、常用查询

```sql
-- 最新基金净值
SELECT fund_code, fund_name, net_date, unit_nav, daily_growth
FROM fund_history
WHERE (fund_code, net_date) IN (
  SELECT fund_code, MAX(net_date) FROM fund_history GROUP BY fund_code
);

-- 某日市场情绪
SELECT trade_date, sentiment_value, sentiment_zone, market_desc
FROM market_sentiment
ORDER BY trade_date DESC LIMIT 5;

-- 最优策略排名
SELECT s.version, r.fund_code, r.total_return, r.max_drawdown
FROM backtest_results r
JOIN strategy_def s ON r.strategy_id = s.id
WHERE r.period_label = '3-4月'
ORDER BY r.total_return DESC;

-- 某基金历史走势
SELECT net_date, unit_nav, daily_growth
FROM fund_history
WHERE fund_code = '563300'
ORDER BY net_date;
```

---

## 九、注意事项

1. **MySQL 编码**：执行SQL必须带 `--default-character-set=utf8mb4`，否则中文报错(ERROR 1366)
2. **自动化失效排查**：如自动化任务未执行，检查 `~/.workbuddy/workbuddy.db` 中的 `automation_runtime_state` 表
3. **数据日期**：当前数据截止 2026-04-30，5月6日复盘后自动化会继续更新
4. **净值 vs 市价**：数据库存储的是基金净值(NAV)，非盘中交易价格，两者可能有差异
