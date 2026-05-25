import pymysql, sys
sys.stdout.reconfigure(encoding='utf-8')
conn = pymysql.connect(host='localhost', port=3306, user='root', password='root123', database='data_analysis', charset='utf8mb4')
cur = conn.cursor()

print('=== fund_history latest ===')
cur.execute('SELECT fund_code, fund_name, net_date, unit_nav, daily_growth FROM fund_history WHERE (fund_code,net_date) IN (SELECT fund_code,MAX(net_date) FROM fund_history GROUP BY fund_code) ORDER BY fund_code')
for r in cur.fetchall(): print(f'  {r[1]}({r[0]}): {r[2]} nav={r[3]} growth={r[4]}%')

print()
print('=== market_sentiment top 3 ===')
cur.execute('SELECT trade_date, sentiment_value, sentiment_zone FROM market_sentiment ORDER BY trade_date DESC LIMIT 3')
for r in cur.fetchall(): print(f'  {r[0]}: {r[1]} ({r[2]})')

print()
cur.execute("SELECT table_name, (SELECT COUNT(*) FROM information_schema.columns WHERE table_name=t.table_name) cols, (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='data_analysis' AND table_name=t.table_name) tbl FROM (SELECT 'market_daily_stats' table_name UNION SELECT 'fund_history' UNION SELECT 'market_sentiment' UNION SELECT 'strategy_def' UNION SELECT 'backtest_results') t")
print('=== row count ===')
for t in ['market_daily_stats','fund_history','market_sentiment','strategy_def','backtest_results']:
    cur.execute(f'SELECT COUNT(*) FROM {t}')
    print(f'  {t}: {cur.fetchone()[0]} rows')
conn.close()
