# A股数据分析系统 — 跨电脑使用指南

## 第一步：拉取代码

```bash
# 首次使用（需要 SSH key 已添加到 GitHub）
git clone git@github.com:18862931387/gpfx.git D:\code\xlx
```

## 第二步：同步数据库

### 导出（在源电脑上执行）

```bash
python backup_db.py
# 或在 daily_update.py 运行后自动导出
```

会在当前目录生成 `db_export_YYYY-MM-DD.sql`

### 导入（在新电脑上执行）

```bash
# 方式一：使用 import_db.py（如存在）
python import_db.py db_export_2026-06-01.sql

# 方式二：直接 mysql 命令行
mysql -u root -proot123 data_analysis < db_export_2026-06-01.sql
```

## 第三步：安装依赖

```bash
pip install pymysql requests pandas numpy akshare
```

## 第四步：配置中心

编辑 `config.py`，确认以下参数与本机一致：

```python
DB = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'root123',
    'database': 'data_analysis',
    'charset': 'utf8mb4',
}
CAPITAL = 20000.0        # 总资金
SYSTEM_BASE_CASH = 10181.0  # 系统跟踪现金
```

## 核心文件

| 文件 | 用途 |
|:----|:------|
| `config.py` | **配置中心** — DB连接/API/常量 |
| `daily_update.py` | **一键更新** — 拉取数据到MySQL + 自动备份 |
| `sentiment_pipeline.py` | **情绪采集流水线** — 多因子+融资融券+北向 |
| `_afternoon_check.py` | **尾盘决策 v5.6** — 复合情绪+策略执行 |
| `simulate.py` | 策略回测 |
| `backup_db.py` | 数据库导出为SQL并git推送 |
| `verify_db.py` | 数据库验证查询 |

## 前提条件

- Python 3 + pymysql + requests + pandas + numpy + akshare
- MySQL 5.6（localhost:3306, root/root123）
- Git + SSH key（推送到 `github.com/18862931387/gpfx`）
- 网络访问：腾讯证券 `web.sqt.gtimg.cn` / `web.ifzq.gtimg.cn`、东方财富 `push2.eastmoney.com`、同花顺 `data.hexin.cn`

## 每日运行

```bash
# 1. 启动 MySQL（如未注册为服务）
Start-Process -FilePath "C:\Program Files\MySQL\MySQL Server 5.6\bin\mysqld.exe" `
  -ArgumentList "--datadir=C:\PROGRA~3\MySQL\MYSQLS~1.6\data --port=3306" -WindowStyle Hidden

# 2. 数据更新（收盘后）
python daily_update.py

# 3. 尾盘决策（14:30后，有仓时）
python _afternoon_check.py
```
