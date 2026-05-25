# One-command daily market data update
# Pulls index/fund/fund-flow data from public APIs, writes to local MySQL

import requests, sys, pymysql, json, time
sys.stdout.reconfigure(encoding='utf-8')

# Force IPv4 for eastmoney API
import socket, requests.packages.urllib3.util.connection as urllib3_cn
urllib3_cn.allowed_gai_family = lambda: socket.AF_INET

DB_HOST = 'localhost'
DB_USER = 'root'
DB_PASS = 'root123'
DB_NAME = 'data_analysis'

date_str = __import__('datetime').date.today().isoformat()
hdr = {'User-Agent': 'Mozilla/5.0'}

conn = pymysql.connect(host=DB_HOST, port=3306, user=DB_USER, password=DB_PASS, charset='utf8mb4')
cur = conn.cursor()
cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` DEFAULT CHARSET utf8mb4")
cur.execute(f"USE `{DB_NAME}`")

tables_sql = {
    'market_daily_stats': '''CREATE TABLE IF NOT EXISTS market_daily_stats (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        trade_date DATE NOT NULL, limit_up INT, limit_down INT, suspended INT,
        turnover DECIMAL(15,2),
        sh_up INT, sh_flat INT, sh_down INT,
        sz_up INT, sz_flat INT, sz_down INT,
        bj_up INT, bj_flat INT, bj_down INT,
        create_time DATETIME, update_time DATETIME,
        UNIQUE KEY idx_trade_date (trade_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
    'fund_history': '''CREATE TABLE IF NOT EXISTS fund_history (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        fund_code VARCHAR(10), fund_name VARCHAR(100),
        net_date DATE, unit_nav DECIMAL(10,4), accum_nav DECIMAL(10,4),
        daily_growth DECIMAL(6,2),
        purchase_status VARCHAR(20), redemption_status VARCHAR(20),
        dividend_status VARCHAR(20),
        create_time DATETIME, update_time DATETIME,
        UNIQUE KEY uk_fund_date (fund_code, net_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
    'market_sentiment': '''CREATE TABLE IF NOT EXISTS market_sentiment (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        trade_date DATE NOT NULL, sentiment_value DECIMAL(5,2), sentiment_zone VARCHAR(10),
        index_change VARCHAR(10), market_desc TEXT,
        week_day VARCHAR(10), holiday_note VARCHAR(50),
        create_time DATETIME, update_time DATETIME,
        UNIQUE KEY idx_trade_date (trade_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
    'market_capital_flow': '''CREATE TABLE IF NOT EXISTS market_capital_flow (
        trade_date DATE PRIMARY KEY,
        main_force_net DECIMAL(15,2) COMMENT 'main force net(yuan)',
        retail_net DECIMAL(15,2) COMMENT 'retail net(yuan)',
        medium_net DECIMAL(15,2) COMMENT 'medium order net(yuan)',
        large_net DECIMAL(15,2) COMMENT 'large order net(yuan)',
        super_large_net DECIMAL(15,2) COMMENT 'super large order net(yuan)',
        main_force_pct DECIMAL(5,2), retail_pct DECIMAL(5,2),
        medium_pct DECIMAL(5,2), large_pct DECIMAL(5,2), super_large_pct DECIMAL(5,2),
        create_time DATETIME DEFAULT NOW(), update_time DATETIME DEFAULT NOW()
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
}
for t, s in tables_sql.items():
    cur.execute(s)

print(f'=== Data Update {date_str} ===')

# 1. Index data (Tencent API)
indices_api = {
    'sh000001': 'SH Index', 'sz399001': 'SZ Component', 'sz399006': 'ChiNext',
    'sh000688': 'STAR 50', 'sh000300': 'CSI 300', 'sh000852': 'CSI 1000',
}
for code, name in indices_api.items():
    r = requests.get('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',
        params={'param': f'{code},day,,,5,qfq'}, headers=hdr, timeout=10)
    items = r.json().get('data', {}).get(code, {}).get('day', [])
    if items:
        last = items[-1]
        print(f'  {name}: {last[0]} close={last[2]}')

# 2. Fund NAV (East Money)
funds = [('563300','563300 CSI2000ETF'),('516330','516330 IoT ETF'),('588090','588090 STAR50 ETF')]
nav_url = 'https://api.fund.eastmoney.com/f10/lsjz'
for code, name in funds:
    r = requests.get(nav_url, params={'fundCode': code, 'pageIndex': 1, 'pageSize': 5},
        headers={**hdr, 'Referer': 'https://fund.eastmoney.com/'}, timeout=10)
    txt = r.text; s, e = txt.find('{'), txt.rfind('}')
    rows = json.loads(txt[s:e+1]).get('Data',{}).get('LSJZList',[]) if s>=0 else []
    for row in rows[:1]:
        dt, nav, acc, gr = row.get('FSRQ',''), row.get('DWJZ'), row.get('LJJZ'), row.get('JZZZL','')
        gr_val = gr.replace('%','') if gr else 'NULL'
        sql = """INSERT INTO fund_history (fund_code,fund_name,net_date,unit_nav,accum_nav,daily_growth,purchase_status,redemption_status,create_time,update_time)
VALUES (%s,%s,%s,%s,%s,%s,'buy','sell',NOW(),NOW())
ON DUPLICATE KEY UPDATE unit_nav=VALUES(unit_nav),accum_nav=VALUES(accum_nav),daily_growth=VALUES(daily_growth),update_time=NOW()"""
        cur.execute(sql, (code, name, dt, float(nav), float(acc), float(gr_val)))
        print(f'  {name}: {dt} nav={nav} growth={gr}')

# 3. Market capital flow (East Money push2his - 大盘资金流向)
ut = 'fa5fd1943c7b386f172d6893dbbd1d0c'
flow_params = {
    'secid': '1.000001',
    'fields1': 'f1,f2,f3,f4,f5',
    'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
    'lmt': '5', 'ut': ut
}
flow_ok = False
for attempt in range(3):
    try:
        r = requests.get('https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get',
            params=flow_params, headers={**hdr, 'Referer': 'https://data.eastmoney.com/'}, timeout=10)
        txt = r.text; s, e = txt.find('{'), txt.rfind('}')
        data = json.loads(txt[s:e+1]) if s >= 0 else {}
        klines = data.get('data', {}).get('klines', [])
        if klines:
            for k in klines:
                p = k.split(',')
                if len(p) >= 11:
                    dt, mf, rt, md, lg, sl = p[0], p[1], p[2], p[3], p[4], p[5]
                    mp, rp, mdp, lp, slp = p[6], p[7], p[8], p[9], p[10]
                    sql = """INSERT INTO market_capital_flow (trade_date,main_force_net,retail_net,medium_net,large_net,super_large_net,main_force_pct,retail_pct,medium_pct,large_pct,super_large_pct,create_time,update_time)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
ON DUPLICATE KEY UPDATE main_force_net=VALUES(main_force_net),retail_net=VALUES(retail_net),medium_net=VALUES(medium_net),large_net=VALUES(large_net),super_large_net=VALUES(super_large_net),update_time=NOW()"""
                    cur.execute(sql, (dt, mf, rt, md, lg, sl, mp, rp, mdp, lp, slp))
            print(f'  Market Flow: {len(klines)} records updated')
            flow_ok = True
            break
    except Exception as e:
        if attempt < 2:
            time.sleep(2)
            continue
        print(f'  Market Flow API unavailable (3 retries failed): {e}')
        break

conn.commit(); conn.close()
print('=== Update Complete ===')
if not flow_ok:
    print('  (Market flow data was not updated - API will retry on next run)')
