import sqlite3

db_path = r"C:\Users\Administrator\.workbuddy\workbuddy.db"
output_file = r"d:\code\xlx\db_result2.txt"

def log(msg):
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

with open(output_file, "w", encoding="utf-8") as f:
    f.write("")

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# First, get table schemas
log("=== 数据库表结构 ===")
cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name LIKE 'automation%'")
for r in cur.fetchall():
    log(r[0])
    log("")

# 1. Fix the query - check actual column names first
log("=== automation_runs 列名 ===")
cur.execute("PRAGMA table_info(automation_runs)")
for c in cur.fetchall():
    log("  " + c["name"] + " (" + c["type"] + ")")

log("")
log("=== automations 列名 ===")
cur.execute("PRAGMA table_info(automations)")
for c in cur.fetchall():
    log("  " + c["name"] + " (" + c["type"] + ")")

# 2. Now query with correct column names
log("")
log("=" * 80)
log("  查询1: 自动化任务运行记录 (最近20条)")
log("=" * 80)

# Check if run_at exists or what the timestamp column is called
try:
    cur.execute("SELECT * FROM automation_runs LIMIT 1")
    cols = [desc[0] for desc in cur.description]
    log("可用列: " + ", ".join(cols))
    
    # Try different column name possibilities for timestamp
    time_col = None
    for possible in ["run_at", "created_at", "scheduled_at", "started_at", "timestamp", "executed_at"]:
        if possible in cols:
            time_col = possible
            break
    
    if time_col:
        sql = "SELECT a.name, r.{} as run_time, r.status, r.result_summary FROM automation_runs r JOIN automations a ON r.automation_id = a.id ORDER BY r.{} DESC LIMIT 20".format(time_col, time_col)
        cur.execute(sql)
    else:
        # No time column found - just use all rows
        cur.execute("SELECT a.name, r.status, r.result_summary FROM automation_runs r JOIN automations a ON r.automation_id = a.id LIMIT 20")
    
    rows = cur.fetchall()
    if rows:
        log("{:<30} {:<25} {:<10} {}".format("任务名称", "运行时间", "状态", "结果摘要"))
        log("-" * 80)
        for r in rows:
            name = r["name"] or ""
            run_time = str(r["run_time"]) if time_col and r["run_time"] else (str(r[1]) if not time_col else "")
            status = r["status"] if "status" in r.keys() else (r[1] if not time_col else "")
            summary = r["result_summary"] if "result_summary" in r.keys() else ""
            
            summary = str(summary) if summary else ""
            if len(summary) > 40:
                summary = summary[:37] + "..."
            log("{:<30} {:<25} {:<10} {}".format(name, run_time[:25] if len(run_time) > 25 else run_time, status, summary))
    else:
        log("(无记录)")
except Exception as e:
    log("查询1失败: " + str(e))

conn.close()
log("")
log("查询完成。")
