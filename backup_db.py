import pymysql, sys, os, json, datetime, subprocess
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from config import DB

OUTPUT_DIR = os.path.dirname(__file__)
TABLES = [
    'market_daily_stats', 'fund_history', 'market_sentiment',
    'market_capital_flow', 'sentiment_raw_factors', 'backtest_results',
    'position', 'strategy_signals', 'etf_kline', 'index_daily',
    'market_news',
]

now = datetime.datetime.now()
date_str = now.strftime('%Y-%m-%d')
output_file = os.path.join(OUTPUT_DIR, f'db_export_{date_str}.sql')

conn = pymysql.connect(**DB)
cur = conn.cursor()

lines = [
    f'-- DataExport: data_analysis  {date_str}',
    f'-- Time: {now.strftime("%Y-%m-%d %H:%M:%S")}',
    '',
]

for table in TABLES:
    try:
        cur.execute(f'SELECT COUNT(*) FROM {table}')
        row_count = cur.fetchone()[0]
        cur.execute(f'SHOW CREATE TABLE {table}')
        create_sql = cur.fetchone()[1]
        lines.append(f'-- === {table} ({row_count} rows) ===')
        lines.append(f'DROP TABLE IF EXISTS `{table}`;')
        lines.append(create_sql + ';')
        lines.append('')

        if row_count > 0:
            cur.execute(f'SELECT * FROM {table} ORDER BY 1')
            rows = cur.fetchall()
            cur.execute(f'DESCRIBE {table}')
            cols = [r[0] for r in cur.fetchall()]
            col_list = ', '.join([f'`{c}`' for c in cols])
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

size_kb = os.path.getsize(output_file) / 1024
print(f'Export: {output_file} ({size_kb:.1f} KB, {len(lines)} lines)')

# Rotate: keep only last 7 exports
import glob
olds = sorted(glob.glob(os.path.join(OUTPUT_DIR, 'db_export_*.sql')), reverse=True)
for f in olds[7:]:
    os.remove(f)
    print(f'  Removed: {os.path.basename(f)}')

cur.close()
conn.close()

# Git
os.chdir(OUTPUT_DIR)
subprocess.run(['git', 'add', '-f', f'db_export_{date_str}.sql'], capture_output=True)

# Remove old exports from git tracking
for f in olds[7:]:
    subprocess.run(['git', 'rm', '--cached', os.path.basename(f)], capture_output=True)

result = subprocess.run(['git', 'diff', '--cached', '--name-only'], capture_output=True, text=True)
if result.stdout.strip():
    msg = f'backup: DB export {date_str}'
    subprocess.run(['git', 'commit', '-m', msg], capture_output=True)
    push = subprocess.run(['git', 'push'], capture_output=True, text=True)
    if push.returncode == 0:
        print(f'Git push OK: {msg}')
    else:
        print(f'Git push FAIL: {push.stderr.strip()[:120]}')
else:
    print('No changes to commit')
