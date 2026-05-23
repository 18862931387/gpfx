import sqlite3

db_path = r"C:\Users\Administrator\.workbuddy\workbuddy.db"
output_file = r"d:\code\xlx\db_result3.txt"

def log(m):
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(str(m) + "\n")

with open(output_file, "w", encoding="utf-8") as f:
    f.write("")

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 1. Automation run records (corrected)
log("=" * 80)
log("  1. 自动化任务运行记录 (最近20条)")
log("=" * 80)
try:
    cur.execute("""
        SELECT a.name, r.created_at, r.status, r.thread_title, r.runs_json, r.result_success
        FROM automation_runs r
        JOIN automations a ON r.automation_id = a.id
        ORDER BY r.created_at DESC
        LIMIT 20
    """)
    rows = cur.fetchall()
    if rows:
        log("{:<30} {:<22} {:<10} {:<40} {}".format("任务名称", "创建时间(Unix)", "状态", "Thread标题", "结果"))
        log("-" * 120)
        for r in rows:
            name = r["name"] or ""
            created = str(r["created_at"]) if r["created_at"] else ""
            status = r["status"] or ""
            title = r["thread_title"] or ""
            if len(title) > 38: title = title[:35] + "..."
            success = r["result_success"]
            suc_str = "成功" if success == 1 else ("失败" if success == 0 else "-")
            log("{:<30} {:<22} {:<10} {:<40} {}".format(name, created, status, title, suc_str))
    else:
        log("(无记录)")
except Exception as e:
    log("错误: " + str(e))

# 2. Active automation definitions
log("")
log("=" * 80)
log("  2. 自动化任务定义 (ACTIVE)")
log("=" * 80)
try:
    cur.execute("""
        SELECT id, name, status, schedule_type, prompt, last_run_at, next_run_at, rrule, cwds
        FROM automations
        WHERE status = 'ACTIVE'
    """)
    rows = cur.fetchall()
    if rows:
        for r in rows:
            log("")
            log("ID: " + str(r["id"]))
            log("名称: " + (r["name"] or ""))
            log("状态: " + (r["status"] or ""))
            log("调度类型: " + (r["schedule_type"] or ""))
            log("RRULE: " + (r["rrule"] or ""))
            log("工作目录: " + (r["cwds"] or ""))
            log("上次执行(unix): " + str(r["last_run_at"] or "无"))
            log("下次执行(unix): " + str(r["next_run_at"] or "无"))
            prompt_text = r["prompt"] or "(空)"
            if len(prompt_text) > 300:
                prompt_text = prompt_text[:297] + "..."
            log("Prompt:")
            log("  " + prompt_text.replace("\n", "\n  "))
    else:
        log("(无ACTIVE状态的自动化任务)")
except Exception as e:
    log("错误: " + str(e))

# 3. Runtime state
log("")
log("=" * 80)
log("  3. 运行时状态 (automation_runtime_state)")
log("=" * 80)
try:
    cur.execute("SELECT * FROM automation_runtime_state")
    rows = cur.fetchall()
    if rows:
        for r in rows:
            log(dict(r))
    else:
        log("(无记录)")
except Exception as e:
    log("错误: " + str(e))

conn.close()
log("")
log("查询完成。")
