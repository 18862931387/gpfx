# A股数据分析系统 — 跨电脑使用指南

## 第一步：Git 同步代码

```bash
# 在项目目录初始化
cd D:\code\xlx
git init
git add .
git commit -m "初始提交"

# 关联远程仓库（需先在 GitHub/Gitee 创建空仓库）
git remote add origin https://github.com/你的用户名/xlx.git
git push -u origin main
```

> 另一台电脑上 `git clone` 即可。

## 第二步：换电脑时同步数据库

### 导出（在源电脑上执行）
```bash
python export_db.py 2026-05-18
```
会在当前目录生成 `db_export_2026-05-18.sql`

### 导入（在新电脑上执行）
```bash
# 先确保 MySQL 已安装
python import_db.py db_export_2026-05-18.sql
```

## 第三步：每日更新

```bash
python daily_update.py
```

## 文件说明

| 文件 | 用途 |
|:----|:------|
| `daily_update.py` | **一键更新**：拉取指数+基金净值到MySQL |
| `export_db.py` | **导出数据库**为SQL文件，用于跨电脑同步 |
| `import_db.py` | **导入SQL文件**到本地MySQL |
| `a_stock_indices.py` | 查看实时指数行情 |
| `simulate.py` | 策略回测 |
| `_update_today.py` | 快速更新今日数据（含涨跌停+情绪） |
| `update_db.py` / `update_db_v2.py` | 完整数据更新 |

## 前提条件

- Python 3 + pymysql + requests
- MySQL 8.0（localhost:3306, root/123456）
