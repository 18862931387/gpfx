---
name: "a-stock-data-pull"
description: "A股资金流向与行情数据拉取技能。覆盖东方财富push2/push2his、腾讯证券、MCP浏览器兜底三种方式，含字段映射、DB写入、排错指南。当用户需要拉取A股行情数据、查看资金流向、获取大盘成交额、或数据拉取失败需要修复时调用。"
---

# A股数据拉取技能

从东方财富、腾讯证券等数据源拉取 A 股行情、资金流向、涨跌停数据，支持三种方式自动降级。

## 数据源架构

| 优先级 | 方式 | 接口 | 适用场景 |
|--------|------|------|----------|
| 1 | Python push2 | `push2.eastmoney.com/api/qt/ulist.np/get` | 实时资金流向，首选 |
| 2 | Python push2his | `push2his.eastmoney.com/api/qt/stock/fflow/daykline/get` | 日线历史数据 |
| 3 | MCP 浏览器 | `browser_navigate` → `browser_evaluate` | IP 被限流时兜底 |
| 补充 | 腾讯证券 | `web.sqt.gtimg.cn/q=` | 指数/ETF 实时行情 |

## 快速开始

```bash
# 一键拉取所有数据（三种方式全量）
python mcp_pull_data.py

# 每日更新 + 入库
python daily_update.py

# 尾盘策略分析
python _afternoon_check.py
```

## 一、Python push2 实时接口（首选）

### 核心代码

```python
import requests

HDR = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Referer': 'https://data.eastmoney.com/zjlx/dpzjlx.html'
}
UT = 'b2884a393a59ad64002292a3e90d46a5'

url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
params = {
    "fltt": 2,
    "secids": "1.000001,0.399001",  # 上证 + 深证
    "fields": "f2,f3,f6,f62,f64,f66,f72,f78,f104,f105,f184",
    "ut": UT
}

r = requests.get(url, params=params, headers=HDR, timeout=15)
data = r.json()

sh = data["data"]["diff"][0]  # 上证
sz = data["data"]["diff"][1]  # 深证

# 沪深两市合并
main_net = float(sh['f62']) + float(sz['f62'])
turnover = float(sh['f6']) + float(sz['f6'])
```

### 字段映射

| 字段 | 含义 | 单位 |
|------|------|------|
| `f2` | 最新价 | — |
| `f3` | 涨跌幅 | % |
| `f6` | 成交额 | 元 |
| `f62` | 主力净流入 | 元 |
| `f64` | 超大单净流入 | 元 |
| `f66` | 大单净流入 | 元 |
| `f72` | 中单净流入 | 元 |
| `f78` | 小单(散户)净流入 | 元 |
| `f104` | 上涨家数 | — |
| `f105` | 下跌家数 | — |

### 主力资金判断规则

**优先使用 `f64` + `f66`（超大单+大单）**，仅当 `f62` ≈ `f64 + f66`（偏差 < 10亿）时直接使用 `f62`。

```python
def get_main_force(sh, sz):
    f62 = float(sh['f62']) + float(sz['f62'])
    f64_f66 = float(sh['f64']) + float(sz['f64']) + float(sh['f66']) + float(sz['f66'])
    if abs(f62 - f64_f66) < 10e8:
        return f62  # 一致性校验通过
    else:
        return f64_f66  # 使用大单+超大单
```

## 二、push2his 日线接口

```python
url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
params = {
    "secid": "1.000001",
    "secid2": "0.399001",
    "fields1": "f1,f2,f3,f7",
    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
    "lmt": 5,  # 最近N天
    "ut": UT
}

r = requests.get(url, params=params, headers=HDR, timeout=15)
data = r.json()
for line in data["data"]["klines"]:
    parts = line.split(",")
    # 0=日期, 1=收盘价, 2=涨跌幅, 3=主力净额
    # 4=小单, 5=中单, 6=大单, 7=超大单
    print(f"{parts[0]}: 主力{float(parts[3])/1e8:+.2f}亿")
```

**注意**：push2his 域名在 TRAE 环境可能连接失败（RemoteDisconnected），本地环境通常可用。

## 三、腾讯证券行情

```python
codes = ["sh000001", "sz399001", "sh510300"]
url = "https://web.sqt.gtimg.cn/q=" + ",".join(codes)

r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
r.encoding = "gbk"

for line in r.text.strip().split("\n"):
    if '="' not in line:
        continue
    code = line.split('="')[0].replace("v_", "")
    values = line.split('="')[1].strip('";').split("~")
    price = values[3]
    change_pct = values[32]
    print(f"{code}: {price} ({change_pct}%)")
```

支持格式：`sh000001`（上证）、`sz399001`（深证）、`sh510300`（ETF），可批量查询。

## 四、MCP 浏览器兜底

当 Python 直接请求被限流时，使用浏览器 MCP 方式：

### Step 1：导航到东方财富页面

```javascript
// MCP Exec 调用
const nav = await tools.browser_navigate({
  url: 'https://data.eastmoney.com/zjlx/dpzjlx.html'
});
await tools.browser_wait_for({ time: 4 });
```

### Step 2：在浏览器 JS 上下文中调用 API

```javascript
const result = await tools.browser_evaluate({
  script: `(async () => {
    const url = 'https://push2.eastmoney.com/api/qt/ulist.np/get' +
      '?fltt=2&secids=1.000001,0.399001' +
      '&fields=f2,f3,f6,f62,f64,f66,f72,f78,f104,f105,f184' +
      '&ut=b2884a393a59ad64002292a3e90d46a5';
    const resp = await fetch(url);
    return JSON.stringify(await resp.json());
  })()`
});
```

### Step 3：备选方案

当 `browser_evaluate` 返回 null 时：
- 使用 `browser_network_requests` 捕获页面自动发起的 API 请求
- 直接导航到 push2 API JSON URL 截图获取原始数据

## 五、数据库写入

```python
import pymysql

DB = {
    'host': '192.168.3.68', 'port': 3306,
    'user': 'root', 'password': 'root123',
    'database': 'data_analysis', 'charset': 'utf8mb4'
}

conn = pymysql.connect(**DB)
cur = conn.cursor()
cur.execute("""
    INSERT INTO market_capital_flow
    (trade_date, main_force_net, super_large_net, large_net, medium_net, retail_net)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
    main_force_net=VALUES(main_force_net), update_time=NOW()
""", (date, main_net, super_lg, large, medium, retail))
conn.commit()
```

### 核心数据表

| 表名 | 写入脚本 | 内容 |
|------|----------|------|
| `market_capital_flow` | `daily_update.py` | 主力/超大单/大单/中单/散户净额 |
| `market_daily_stats` | `daily_update.py` | 涨跌停家数、成交额 |
| `index_daily` | `daily_update.py` | 四指数日涨跌幅 |
| `sentiment_raw_factors` | `sentiment_pipeline.py` | 多因子原始数据 |

## 六、常见问题

### Q1: push2 API 返回空数据
**原因**：TRAE 环境出口 IP 被东方财富限流。
**解决**：切换到 MCP 浏览器方式（方式三）。

### Q2: push2his 连接被拒绝
**现象**：`RemoteDisconnected`
**解决**：使用 push2 实时接口代替，或在本地环境运行。

### Q3: EASTMONEY_UT Token 过期
**解决**：从东方财富页面抓取新 Token，更新 `config.py` 中的 `EASTMONEY_UT`。
当前有效值：`b2884a393a59ad64002292a3e90d46a5`

### Q4: 主力资金一致性校验不通过
**现象**：`f62` 与 `f64+f66` 偏差超过 10 亿。
**解决**：直接使用 `f64 + f66`（大单+超大单）作为主力净额。

## 七、输出格式

拉取数据后，按以下格式输出：

```
指标              上证           深证           合计
--------------------------------------------------------
最新价           3833.74      13936.87            —
涨跌幅             +0.51%        +1.18%            —
成交额         +8642.23亿     +8539.67亿    +17181.91亿
主力净额         +646.65亿       +21.82亿      +668.47亿
超大单          +1511.59亿      +975.69亿     +2487.28亿
大涨              +607.65亿        +8.15亿      +615.80亿
中单              +39.00亿       +13.67亿       +52.68亿
散户             -222.12亿       -86.55亿      -308.67亿
上涨/下跌         2002/310       2643/255       4645/565
```

## 配置参考

- **Token**: `config.py` → `EASTMONEY_UT`
- **数据库**: `192.168.3.68:3306` / `data_analysis`
- **主ETF**: `510300` 沪深300ETF
- **策略版本**: v6.7