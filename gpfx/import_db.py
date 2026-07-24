import pymysql, sys, os, re
sys.stdout.reconfigure(encoding='utf-8')

# ========== 配置 ==========
DB_HOST = 'localhost'
DB_PORT = 3306
DB_USER = 'root'
DB_PASS = 'root123'
DB_NAME = 'data_analysis'
# ==========================

def find_sql_file():
    for f in sorted(os.listdir(r'D:\code\xlx'), reverse=True):
        if f.startswith('db_export_') and f.endswith('.sql'):
            return os.path.join(r'D:\code\xlx', f)
    return None

sql_file = sys.argv[1] if len(sys.argv) > 1 else find_sql_file()
if not sql_file or not os.path.exists(sql_file):
    print(f'用法: python import_db.py <sql文件>')
    print(f'或在 {r"D:\code\xlx"} 下放 db_export_*.sql 文件')
    sys.exit(1)

print(f'导入文件: {sql_file}')
with open(sql_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Split by semicolons, execute each statement
statements = re.split(r';\s*', content)
conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database=DB_NAME, charset='utf8mb4')
cur = conn.cursor()

for stmt in statements:
    stmt = stmt.strip()
    if not stmt or stmt.startswith('--') or stmt.startswith('#'):
        continue
    try:
        cur.execute(stmt)
        if stmt.upper().startswith('INSERT'):
            print(f'  OK: {stmt[:60]}... ({cur.rowcount}行)')
    except Exception as e:
        print(f'  SKIP: {e}')
        continue
conn.commit()

# Verify
print()
print('=== 验证 ===')
for t in ['market_daily_stats', 'fund_history', 'market_sentiment']:
    cur.execute(f'SELECT COUNT(*) FROM {t}')
    print(f'  {t}: {cur.fetchone()[0]} 行')

cur.close()
conn.close()
print('导入完成!')
