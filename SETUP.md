# A股数据分析系统 — 跨电脑使用指南

## 第一步：拉取代码

```bash
# 首次使用（需要 SSH key 已添加到 GitHub）
git clone git@github.com:18862931387/gpfx.git D:\code\xlx
```

## 第二步：同步数据库

### 导出（在源电脑上执行）
```bash
python export_db.py 2026-05-23
```
会在当前目录生成 `db_export_2026-05-23.sql`

### 导入（在新电脑上执行）
```bash
python import_db.py db_export_2026-05-23.sql
```

## 第三步：每日更新

```bash
python daily_update.py
```

会自动更新：指数数据 → 基金净值 → 大盘资金流向（含3次重试）

## 核心文件

| 文件 | 用途 |
|:----|:------|
| `daily_update.py` | **一键更新**：拉取数据到MySQL |
| `export_db.py` | 导出数据库为SQL |
| `import_db.py` | 导入SQL到本地MySQL |
| `simulate.py` | 策略回测 |
| `strategy_comparison.md` | 策略对比文档 |

## 前提条件

- Python 3 + pymysql + requests
- MySQL 8.0（localhost:3306, root/123456）
- Git + SSH key（推送到 `github.com/18862931387/gpfx`）
