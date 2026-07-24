# A股数据系统 — 服务器部署方案

---

## 一、系统架构

```
┌─────────────────────────────────────────────────────┐
│                    服务器任务                          │
│                                                       │
│  14:30 ─── run_check.py ──→ _afternoon_check.py       │
│  (尾盘分析)             └─→ 写 strategy_signals        │
│                           └─→ 写 etf_fund_flow         │
│                                                       │
│  16:00 ─── run_update.py ──→ daily_update.py          │
│  (收盘更新)             └─→ 写 market_daily_stats      │
│                           └─→ 写 market_capital_flow   │
│                           └─→ 写 etf_fund_flow         │
│                           └─→ 写 fund_history          │
│                           └─→ 写 index_daily           │
│                           └─→ 写 etf_kline             │
│                           └─→ 写 market_news           │
│                           └─→ backup_db.py → git push  │
│                                                       │
│  每周 ──── sentiment_pipeline.py --calibrate           │
│  (情绪标定)             └─→ 写 market_sentiment        │
│                           └─→ 写 sentiment_raw_factors │
│                                                       │
└─────────────────────────────────────────────────────┘
```

---

## 二、数据库表结构

### 2.1 行情类

#### market_daily_stats — 大盘量价

```sql
CREATE TABLE market_daily_stats (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  trade_date   DATE NOT NULL,
  limit_up     INT COMMENT '涨停家数',
  limit_down   INT COMMENT '跌停家数',
  suspended    INT COMMENT '停牌家数',
  turnover     DECIMAL(15,2) COMMENT '成交额(亿)',
  sh_up INT, sh_flat INT, sh_down INT COMMENT '上证上涨/平/跌',
  sz_up INT, sz_flat INT, sz_down INT COMMENT '深证上涨/平/跌',
  bj_up INT, bj_flat INT, bj_down INT COMMENT '北证上涨/平/跌',
  create_time DATETIME,
  update_time DATETIME,
  UNIQUE KEY idx_trade_date (trade_date)
) ENGINE=InnoDB;
```
- **数据源**: `push2.eastmoney.com/api/qt/clist/get`（盘中实时）
- **更新**: daily_update.py #1c, 交易日有效
- **回填**: `_backfill_all.py`（交易时段运行）

#### etf_kline — ETF日K线缓存

```sql
CREATE TABLE etf_kline (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  fund_code  VARCHAR(10) NOT NULL,
  trade_date DATE NOT NULL,
  open DECIMAL(10,4), high DECIMAL(10,4),
  low DECIMAL(10,4), close DECIMAL(10,4),
  volume DECIMAL(20,2),
  is_adj TINYINT(1) DEFAULT 1 COMMENT '1=前复权',
  create_time DATETIME DEFAULT NOW(),
  UNIQUE KEY uk_fund_date (fund_code, trade_date)
) ENGINE=InnoDB;
```
- **数据源**: `web.ifzq.gtimg.cn/appstock/app/fqkline/get`（腾讯，全天可用）
- **更新**: daily_update.py #3

#### fund_history — 基金净值

```sql
CREATE TABLE fund_history (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  fund_code    VARCHAR(10),
  fund_name    VARCHAR(100),
  net_date     DATE,
  unit_nav     DECIMAL(10,4) COMMENT '单位净值',
  accum_nav    DECIMAL(10,4) COMMENT '累计净值',
  daily_growth DECIMAL(6,2) COMMENT '日增长率%',
  create_time  DATETIME,
  update_time  DATETIME,
  UNIQUE KEY uk_fund_date (fund_code, net_date)
) ENGINE=InnoDB;
```
- **数据源**: `api.fund.eastmoney.com/f10/lsjz`（东方财富，全天可用）
- **更新**: daily_update.py #2

#### index_daily — 四大指数日涨跌幅

```sql
CREATE TABLE index_daily (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  trade_date   DATE NOT NULL,
  sh_pct DECIMAL(6,2),    -- 上证涨跌幅%
  sz_pct DECIMAL(6,2),    -- 深证涨跌幅%
  cy_pct DECIMAL(6,2),    -- 创业板涨跌幅%
  zz2000_pct DECIMAL(6,2),-- 中证2000涨跌幅%
  create_time  DATETIME DEFAULT NOW(),
  UNIQUE KEY uk_date (trade_date)
) ENGINE=InnoDB;
```
- **数据源**: `web.sqt.gtimg.cn`（腾讯实时行情，全天可用）
- **更新**: daily_update.py #1b

---

### 2.2 资金流

#### market_capital_flow — 大盘资金流向

```sql
CREATE TABLE market_capital_flow (
  trade_date      DATE PRIMARY KEY,
  main_force_net  DECIMAL(15,2) COMMENT '主力净流入(元)',
  retail_net      DECIMAL(15,2) COMMENT '散户净流入(元)',
  medium_net      DECIMAL(15,2) COMMENT '中单净流入(元)',
  large_net       DECIMAL(15,2) COMMENT '大单净流入(元)',
  super_large_net DECIMAL(15,2) COMMENT '超大单净流入(元)',
  main_force_pct  DECIMAL(5,2),
  retail_pct      DECIMAL(5,2),
  medium_pct      DECIMAL(5,2),
  large_pct       DECIMAL(5,2),
  super_large_pct DECIMAL(5,2),
  create_time     DATETIME DEFAULT NOW(),
  update_time     DATETIME DEFAULT NOW()
) ENGINE=InnoDB;
```
- **数据源**: `push2his.eastmoney.com/api/qt/stock/fflow/daykline/get`（盘后可用）
- **盘中实时**: `push2.eastmoney.com/api/qt/ulist.np/get`（仅交易时段）
- **更新**: daily_update.py #4（盘后）+ _afternoon_check.py（盘中）

#### etf_fund_flow — 个股资金流

```sql
CREATE TABLE etf_fund_flow (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  trade_date    DATE NOT NULL,
  fund_code     VARCHAR(10) NOT NULL,
  main_force_net  DECIMAL(20,2) COMMENT '主力净流入(元)',
  retail_net      DECIMAL(20,2) COMMENT '散户净流入(元)',
  medium_net      DECIMAL(20,2) COMMENT '中单净流入(元)',
  large_net       DECIMAL(20,2) COMMENT '大单净流入(元)',
  super_large_net DECIMAL(20,2) COMMENT '超大单净流入(元)',
  create_time   DATETIME DEFAULT NOW(),
  UNIQUE KEY uk_fund_date (fund_code, trade_date)
) ENGINE=InnoDB;
```
- **数据源**: `push2his.eastmoney.com/api/qt/stock/fflow/daykline/get`（盘后可用）
- **更新**: daily_update.py #4b + _afternoon_check.py

---

### 2.3 情绪

#### market_sentiment — 市场情绪

```sql
CREATE TABLE market_sentiment (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  trade_date      DATE NOT NULL,
  sentiment_value DECIMAL(5,2) COMMENT '-2.5~2.5',
  sentiment_zone  VARCHAR(10) COMMENT '冷热区间',
  composite_idx   DECIMAL(6,4) COMMENT '原始4指数加权值',
  calibrated      TINYINT(1) DEFAULT 0 COMMENT '0=calc_sentiment, 1=回归公式',
  market_desc     TEXT,
  week_day        VARCHAR(10),
  holiday_note    VARCHAR(50),
  create_time     DATETIME,
  update_time     DATETIME,
  UNIQUE KEY idx_trade_date (trade_date)
) ENGINE=InnoDB;
```
- **数据源**: 复合指数回归 + 多因子修正（盘中实时）
- **更新**: `sentiment_pipeline.py`（日级）+ `_afternoon_check.py`（盘中实时）

#### sentiment_raw_factors — 多因子原始数据

```sql
CREATE TABLE sentiment_raw_factors (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  trade_date        DATE NOT NULL,
  composite_index   DECIMAL(10,4) COMMENT '4指数加权涨跌幅',
  sector_up INT, sector_down INT,
  sector_ad_ratio   DECIMAL(6,4) COMMENT '板块涨跌比',
  limit_up INT, limit_down INT,
  turnover          DECIMAL(15,2) COMMENT '成交额(亿)',
  main_force_net     DECIMAL(15,2) COMMENT '主力净流入(万)',
  volume_pctile_60d DECIMAL(5,2) COMMENT '60日成交量百分位',
  margin_balance    DECIMAL(20,2) COMMENT '融资融券余额(亿)',
  northbound_net    DECIMAL(15,2) COMMENT '北向资金净流入(亿)',
  sentiment_label   DECIMAL(5,2) COMMENT '聚类标签',
  create_time       DATETIME DEFAULT NOW(),
  update_time       DATETIME DEFAULT NOW(),
  UNIQUE KEY trade_date (trade_date)
) ENGINE=InnoDB;
```
- **数据源**: akshare（融资融券/北向）+ push2（成交额/涨跌停）+ 腾讯（指数）
- **更新**: `sentiment_pipeline.py`

---

### 2.4 策略

#### position — 持仓记录

```sql
CREATE TABLE position (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  fund_code   VARCHAR(10) NOT NULL,
  fund_name   VARCHAR(100),
  trade_date  DATE NOT NULL,
  trade_type  VARCHAR(10) COMMENT 'buy/sell',
  shares      INT NOT NULL,
  price       DECIMAL(10,4) NOT NULL,
  amount      DECIMAL(12,2) NOT NULL,
  shares_after INT NOT NULL,
  cash_after  DECIMAL(12,2) NOT NULL,
  note        VARCHAR(200) COMMENT 'real/system标识',
  create_time DATETIME DEFAULT NOW(),
  KEY idx_fund (fund_code),
  KEY idx_date (trade_date)
) ENGINE=InnoDB;
```
- **数据源**: 手工写入 + 系统回溯
- **更新**: 用户手动 `_update_pos.py` 或 `_afternoon_check.py` 自动

#### strategy_signals — 策略信号日志

```sql
CREATE TABLE strategy_signals (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  trade_date      DATE NOT NULL,
  signal_type     VARCHAR(10) COMMENT 'buyA/buyB/sell_all/stop_loss',
  sentiment_value DECIMAL(5,2),
  nav             DECIMAL(10,4),
  reason          VARCHAR(200),
  executed        TINYINT(1) DEFAULT 0 COMMENT '0=仅信号,1=已执行',
  create_time     DATETIME DEFAULT NOW(),
  UNIQUE KEY uk_date_type (trade_date, signal_type)
) ENGINE=InnoDB;
```
- **数据源**: `_afternoon_check.py` 决策输出
- **更新**: 每次尾盘分析时自动写入

#### backtest_results — 回测结果

```sql
CREATE TABLE backtest_results (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  strategy_id     INT NOT NULL,
  fund_code       VARCHAR(10) NOT NULL,
  period_label    VARCHAR(20),
  initial_capital DECIMAL(12,2),
  final_value     DECIMAL(12,2),
  total_return    DECIMAL(8,2),
  max_drawdown    DECIMAL(8,2),
  trade_count     INT,
  created_at      DATETIME DEFAULT NOW(),
  UNIQUE KEY uk_sfp (strategy_id, fund_code, period_label)
) ENGINE=InnoDB;
```
- **数据源**: `simulate.py`
- **更新**: 手动运行回测时写入

---

### 2.5 辅助

#### market_news — 每日新闻情绪

```sql
CREATE TABLE market_news (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  trade_date      DATE NOT NULL,
  title           VARCHAR(500) NOT NULL,
  url             VARCHAR(500),
  source          VARCHAR(100),
  sentiment_score DECIMAL(5,2) DEFAULT 0 COMMENT '-2~+2',
  pos_words       TEXT COMMENT '命中利好关键词',
  neg_words       TEXT COMMENT '命中利空关键词',
  create_time     DATETIME DEFAULT NOW(),
  KEY idx_date (trade_date)
) ENGINE=InnoDB;
```
- **数据源**: `feed.mix.sina.com.cn/api/roll/get`（新浪财经，全天可用）
- **更新**: daily_update.py #5 + news_sentiment.py

---

## 三、数据源可用性

| API | 域名 | 盘中使用 | 盘后可用 | 备注 |
|:----|:-----|:--------:|:--------:|:-----|
| 腾讯实时行情 | `web.sqt.gtimg.cn` | ✅ | ✅ | 全天最稳定 |
| 腾讯K线 | `web.ifzq.gtimg.cn` | ✅ | ✅ | 全天稳定 |
| 东方财富涨跌停 | `push2.eastmoney.com/api/qt/clist/get` | ✅ | ❌ | 域名需IPv4 |
| 东方财富实时资金 | `push2.eastmoney.com/api/qt/ulist.np/get` | ✅ | ⚠️ | 需Referer |
| 东方财富历史资金 | `push2his.eastmoney.com/api/qt/stock/fflow/daykline/get` | ❌ | ✅ | 盘后才返回 |
| 东方财富基金净值 | `api.fund.eastmoney.com/f10/lsjz` | ✅ | ✅ | 全天 |
| 东方财富主力流 | `push2.eastmoney.com/api/qt/stock/fflow/kline/get` | ✅ | ⚠️ | 需Referer |
| 新浪财经新闻 | `feed.mix.sina.com.cn/api/roll/get` | ✅ | ✅ | 全天 |
| akshare 北向 | `ak.stock_hsgt_fund_flow_summary_em()` | ✅ | ⚠️ | 盘后缓存 |
| akshare 板块资金 | `ak.stock_sector_fund_flow_rank()` | ✅ | ⚠️ | 盘后缓存 |

> **关键规律**: push2 系列仅在交易时段(9:30-15:00)和盘后2小时内可用。22:00-次日8:00全部断连。腾讯系全天稳定。

---

## 四、服务器环境要求

### 硬件
| 项目 | 最低 | 推荐 |
|:----|:----|:----|
| CPU | 1核 | 2核 |
| 内存 | 2GB | 4GB |
| 磁盘 | 10GB | 20GB |
| 网络 | 能访问腾讯/东方财富 | 国内云服务器 |

### 软件
| 项目 | 版本 |
|:----|:----|
| Python | 3.9+ |
| MySQL | 5.6+ / 8.0 |
| Git | 2.x |
| 操作系统 | Linux(推荐) / Windows Server |

### Python依赖
```
pymysql == 1.4.6
requests
pandas
numpy
akshare
```

---

## 五、服务器部署步骤

### 5.1 安装基础环境

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y python3 python3-pip mysql-server git

# CentOS / RHEL
sudo yum install -y python3 python3-pip mysql-server git

# Windows Server
# 下载并安装 Python 3.11+, MySQL 8.0, Git for Windows
```

### 5.2 拉取代码

```bash
git clone git@github.com:18862931387/gpfx.git /opt/xlx
# 或: git clone https://github.com/18862931387/gpfx.git /opt/xlx
cd /opt/xlx
pip install -r requirements.txt
```

### 5.3 创建数据库

```bash
mysql -u root -p
```

```sql
CREATE DATABASE data_analysis CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'xlx'@'localhost' IDENTIFIED BY 'your_password_here';
GRANT ALL PRIVILEGES ON data_analysis.* TO 'xlx'@'localhost';
FLUSH PRIVILEGES;
```

### 5.4 配置参数

编辑 `config.py`：

```python
DB = {
    'host': 'localhost',
    'port': 3306,
    'user': 'xlx',
    'password': 'your_password_here',
    'database': 'data_analysis',
    'charset': 'utf8mb4',
}
CAPITAL = 20000.0
```

### 5.5 首次建表 & 回填

```bash
# 建表 (运行一次即可)
python daily_update.py

# 回填历史数据 (需在交易时段运行)
python _backfill_all.py
```

### 5.6 设置定时任务

**Linux (crontab):**
```bash
crontab -e
```

添加以下内容：
```cron
# 尾盘分析 14:30 (交易日)
30 14 * * 1-5 cd /opt/xlx && python _afternoon_check.py >> logs/cron_check.log 2>&1

# 收盘数据更新 16:00 (交易日)
00 16 * * 1-5 cd /opt/xlx && python daily_update.py >> logs/cron_update.log 2>&1
```

**Windows Server (Task Scheduler):**
```powershell
# 管理员 PowerShell
schtasks /create /tn "xlx_check" /tr "python D:\code\xlx\_afternoon_check.py" /sc daily /st 14:30 /f
schtasks /create /tn "xlx_update" /tr "python D:\code\xlx\daily_update.py" /sc daily /st 16:00 /f
```

### 5.7 验证

```bash
# 检查表是否已创建
mysql -u xlx -p data_analysis -e "SHOW TABLES;"

# 检查数据
python verify_db.py
```

---

## 六、定时任务说明

| 任务 | 时间 | 命令 | 条件 |
|:----|:----|:----|:----|
| 尾盘分析 | 每个交易日 14:30 | `python _afternoon_check.py` | MySQL已启动 |
| 数据更新 | 每个交易日 16:00 | `python daily_update.py` | MySQL已启动 |
| 情绪标定 | 每周(可选) | `python sentiment_pipeline.py --calibrate` | 60+交易日数据 |
| 回测验证 | 调参后 | `python simulate.py` | 手动运行 |

> **注意**: MySQL 需设置为开机自启 (Linux: `systemctl enable mysql`, Windows: `sc config MySQL start=auto`)

---

## 七、首次回填

新服务器首次部署后，需回填历史数据：

| 表 | 回填范围 | 命令 | 时机 |
|:---|:--------|:----|:----|
| market_capital_flow | 近120个交易日 | `_backfill_all.py` | 交易时段 |
| etf_fund_flow | 近120个交易日 | `_backfill_all.py` | 盘后 |
| market_daily_stats | 近120个交易日 | `_backfill_all.py` | 交易时段 |
| etf_kline | 近320个交易日 | `python _fill_kline.py` | 全天 |
| market_sentiment | 同步最新 | `sentiment_pipeline.py` | 全天 |
| market_news | 当日 | `python news_sentiment.py` | 全天 |
| index_daily | 当日 | `daily_update.py` | 全天 |

> 回填脚本 `_backfill_all.py` 需要在**交易时段**或**盘后2小时内**运行，否则 push2 接口断连。

---

## 八、监控 & 维护

### 8.1 每日检查
```bash
# 检查今日是否更新
mysql -u xlx -p data_analysis -e "
SELECT 'market_daily_stats' as t, MAX(trade_date) FROM market_daily_stats
UNION ALL
SELECT 'market_capital_flow', MAX(trade_date) FROM market_capital_flow
UNION ALL
SELECT 'fund_history', MAX(net_date) FROM fund_history;
"
```

### 8.2 磁盘清理
```bash
# 日志保留7天，自动清理
find logs/ -name "*.log" -mtime +7 -delete
```

### 8.3 数据库备份
```bash
# 每日自动备份 (已集成到 daily_update.py)
python backup_db.py
# 导出为 db_export_YYYY-MM-DD.sql → git push
```

### 8.4 常见问题

| 问题 | 原因 | 解决 |
|:----|:----|:-----|
| push2连接失败 | 非交易时段或被墙 | 确认交易时段运行，检查IPv4 |
| 腾讯行情为空 | 代码需前复权参数 | 加 `&fqt=1` 参数 |
| 基金净值不更新 | 非交易日无新数据 | 确认今天是否为交易日 |
| akshare报错 | 接口变动 | `pip install --upgrade akshare` |

---

## 九、文件清单

```
D:\code\xlx\
├── config.py            # 配置中心 (DB/API/常量)
├── strategy_config.py   # 策略版本管理
├── _afternoon_check.py  # 尾盘决策 (14:30 运行)
├── daily_update.py      # 收盘数据更新 (16:00 运行)
├── simulate.py          # 策略回测
├── sentiment_pipeline.py# 情绪采集流水线
├── sentiment_calibrate.py # 情绪校准算法
├── news_sentiment.py    # 新闻情绪因子
├── backup_db.py         # 数据库备份 + git推送
├── logger.py            # 日志工具
├── verify_db.py         # 数据库验证
├── requirements.txt     # Python依赖
│
├── run_check.ps1        # 尾盘分析启动脚本
├── run_update.ps1       # 数据更新启动脚本  
├── run_daemon.ps1       # 常驻定时任务(无管理员时)
├── setup_tasks.cmd      # Windows定时任务配置
│
├── create_signals_table.sql  # strategy_signals DDL
├── create_kline_table.sql    # etf_kline DDL
├── create_position.sql       # position DDL
├── create_results_table.sql  # backtest_results DDL
│
├── strategy_comparison.md # 策略对比文档
├── README.md            # 项目文档
├── SETUP.md             # 跨电脑配置指南
└── DEPLOY.md            # 服务器部署方案 (本文件)
```
