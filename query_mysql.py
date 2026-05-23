import pymysql, sys, io

# Redirect output to a file
out_path = 'd:/code/xlx/query_result.txt'
sys.stdout = io.open(out_path, 'w', encoding='utf-8')

conn = pymysql.connect(
    host='localhost', port=3306,
    user='root', password='123456',
    database='data_analysis', charset='utf8mb4'
)
cursor = conn.cursor()

print('=== 1. market_daily_stats 最新5条 ===')
cursor.execute('SELECT trade_date, limit_up, limit_down, turnover FROM market_daily_stats ORDER BY trade_date DESC LIMIT 5')
for row in cursor.fetchall():
    print(row)

print()
print('=== 2. fund_history 每只基金最新1条 ===')
cursor.execute('''SELECT fund_code, fund_name, net_date, unit_nav, daily_growth 
FROM fund_history 
WHERE (fund_code, net_date) IN (
  SELECT fund_code, MAX(net_date) FROM fund_history GROUP BY fund_code
) ORDER BY fund_code''')
for row in cursor.fetchall():
    print(row)

print()
print('=== 3. market_sentiment 最新5条 ===')
cursor.execute('SELECT trade_date, sentiment_value, sentiment_zone, LEFT(market_desc,50) AS desc_short FROM market_sentiment ORDER BY trade_date DESC LIMIT 5')
for row in cursor.fetchall():
    print(row)

if pymysql.__version__:
    print(f'\npymysql version: {pymysql.__version__}')

cursor.close()
conn.close()
