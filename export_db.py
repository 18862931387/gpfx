import pymysql, sys, os, json
sys.stdout.reconfigure(encoding='utf-8')

# ========== 配置 ==========
DB_HOST = 'localhost'
DB_PORT = 3306
DB_USER = 'root'
DB_PASS = '123456'
DB_NAME = 'data_analysis'
OUTPUT_DIR = r'D:\code\xlx'
# ==========================

conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database=DB_NAME, charset='utf8mb4')
cur = conn.cursor()

tables = ['market_daily_stats', 'fund_history', 'market_sentiment', 'strategy_def', 'backtest_results']
output_file = os.path.join(OUTPUT_DIR, f'db_export_{sys.argv[1] if len(sys.argv) > 1 else "full"}.sql')

lines = [
    f'-- DataExport: {DB_NAME}  {sys.argv[1] if len(sys.argv) > 1 else "full"}',
    f'-- Time: {__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
    '',
]

for table in tables:
    try:
        cur.execute(f'SELECT * FROM {table} ORDER BY 1')
        rows = cur.fetchall()
        cur.execute(f'SHOW CREATE TABLE {table}')
        create_sql = cur.fetchone()[1]
        lines.append(f'-- === {table} ({len(rows)} rows) ===')
        lines.append(f'DROP TABLE IF EXISTS `{table}`;')
        lines.append(create_sql + ';')
        lines.append('')
        if rows:
            # Get column names
            cur.execute(f'DESCRIBE {table}')
            cols = [r[0] for r in cur.fetchall()]
            col_list = ', '.join([f'`{c}`' for c in cols])
            placeholders = ', '.join(['%s'] * len(cols))
            for row in rows:
                vals = []
                for v in row:
                    if v is None:
                        vals.append('NULL')
                    elif isinstance(v, (int, float)):
                        vals.append(str(v))
                    elif isinstance(v, bytes):
                        vals.append(f"'{v.decode('utf-8', errors='replace')}'")
                    else:
                        sv = str(v).replace("'", "\\'")
                        vals.append(f"'{sv}'")
                lines.append(f"INSERT INTO `{table}` ({col_list}) VALUES ({', '.join(vals)});")
        lines.append('')
    except Exception as e:
        lines.append(f'-- ERROR {table}: {e}')

content = '\n'.join(lines)
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'导出完成: {output_file}')
print(f'共 {len(lines)} 行, {os.path.getsize(output_file)/1024:.1f} KB')

cur.close()
conn.close()
