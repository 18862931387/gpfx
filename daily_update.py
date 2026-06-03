# One-command daily market data update
# Pulls index/fund/fund-flow data from public APIs, writes to local MySQL

import requests, sys, pymysql, json, time, os, socket
sys.stdout.reconfigure(encoding='utf-8')
import requests.packages.urllib3.util.connection as urllib3_cn
urllib3_cn.allowed_gai_family = lambda: socket.AF_INET
sys.path.insert(0, os.path.dirname(__file__))
from config import DB, TENCENT_KLINE, EASTMONEY_FUND, EASTMONEY_UT, HDR, FUND_REFERER, PRIMARY_FUND
from logger import get_logger

log = get_logger('daily_update')
date_str = __import__('datetime').date.today().isoformat()

try:
    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    cur.execute(f"USE `{DB['database']}`")
except Exception as e:
    log.error(f'DB连接失败: {e}')
    sys.exit(1)

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
        create_time DATETIME, update_time DATETIME,
        UNIQUE KEY uk_fund_date (fund_code, net_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
    'market_sentiment': '''CREATE TABLE IF NOT EXISTS market_sentiment (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        trade_date DATE NOT NULL, sentiment_value DECIMAL(5,2), sentiment_zone VARCHAR(10),
        composite_idx DECIMAL(6,4) COMMENT 'original 4-index composite',
        calibrated TINYINT(1) DEFAULT 0 COMMENT '0=calc_sentiment, 1=regression',
        market_desc TEXT,
        week_day VARCHAR(10), holiday_note VARCHAR(50),
        create_time DATETIME, update_time DATETIME,
        UNIQUE KEY idx_trade_date (trade_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
    'strategy_signals': '''CREATE TABLE IF NOT EXISTS strategy_signals (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        trade_date DATE NOT NULL,
        signal_type VARCHAR(10) NOT NULL COMMENT 'buyA/buyB/sell_all/stop_loss/stop_ma/sell_half',
        sentiment_value DECIMAL(5,2),
        nav DECIMAL(10,4),
        reason VARCHAR(200),
        executed TINYINT(1) DEFAULT 0 COMMENT '0=signal only, 1=executed',
        create_time DATETIME DEFAULT NOW(),
        UNIQUE KEY uk_date_type (trade_date, signal_type)
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
    'etf_kline': '''CREATE TABLE IF NOT EXISTS etf_kline (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        fund_code VARCHAR(10) NOT NULL,
        trade_date DATE NOT NULL,
        open DECIMAL(10,4),
        high DECIMAL(10,4),
        low DECIMAL(10,4),
        close DECIMAL(10,4),
        volume DECIMAL(20,2),
        is_adj TINYINT(1) DEFAULT 1 COMMENT '1=前复权',
        create_time DATETIME DEFAULT NOW(),
        UNIQUE KEY uk_fund_date (fund_code, trade_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
    'index_daily': '''CREATE TABLE IF NOT EXISTS index_daily (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        trade_date DATE NOT NULL,
        sh_pct DECIMAL(6,2) COMMENT 'sh index %',
        sz_pct DECIMAL(6,2) COMMENT 'sz index %',
        cy_pct DECIMAL(6,2) COMMENT 'chinext %',
        zz2000_pct DECIMAL(6,2) COMMENT 'csi2000 %',
        create_time DATETIME DEFAULT NOW(),
        UNIQUE KEY uk_date (trade_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
    'market_news': '''CREATE TABLE IF NOT EXISTS market_news (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        trade_date DATE NOT NULL,
        title VARCHAR(500) NOT NULL,
        url VARCHAR(500),
        source VARCHAR(100),
        sentiment_score DECIMAL(5,2) DEFAULT 0,
        pos_words TEXT,
        neg_words TEXT,
        create_time DATETIME DEFAULT NOW(),
        KEY idx_date (trade_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
    'etf_fund_flow': '''CREATE TABLE IF NOT EXISTS etf_fund_flow (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        trade_date DATE NOT NULL,
        fund_code VARCHAR(10) NOT NULL,
        main_force_net DECIMAL(20,2),
        retail_net DECIMAL(20,2),
        medium_net DECIMAL(20,2),
        large_net DECIMAL(20,2),
        super_large_net DECIMAL(20,2),
        create_time DATETIME DEFAULT NOW(),
        UNIQUE KEY uk_fund_date (fund_code, trade_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
}
for t, s in tables_sql.items():
    cur.execute(s)

log.info(f'=== Data Update {date_str} ===')

# 1. Index K-line (Tencent)
indices_api = {
    'sh000001': 'SH Index', 'sz399001': 'SZ Component', 'sz399006': 'ChiNext',
    'sh000688': 'STAR 50', 'sh000300': 'CSI 300', 'sh000852': 'CSI 1000',
}
for code, name in indices_api.items():
    try:
        r = requests.get(TENCENT_KLINE,
            params={'param': f'{code},day,,,5,qfq'}, headers=HDR, timeout=10)
        items = r.json().get('data', {}).get(code, {}).get('day', [])
        if items:
            last = items[-1]
            log.info(f'  {name}: {last[0]} close={last[2]}')
    except Exception as e:
        log.warning(f'  {name}: 获取失败 {e}')

# 1b. Index daily % backup (write to index_daily for _afternoon_check fallback)
try:
    idx_pcts = {}
    idx_map = {'sh000001': 'sh_pct', 'sz399001': 'sz_pct', 'sz399006': 'cy_pct', 'sh000852': 'zz2000_pct'}
    for code, col in idx_map.items():
        r = requests.get(f'https://web.sqt.gtimg.cn/q={code}', headers=HDR, timeout=10)
        parts = r.text.replace('"', '').split('~')
        if len(parts) > 32:
            idx_pcts[col] = float(parts[32])
    if idx_pcts:
        sql = """INSERT INTO index_daily (trade_date,sh_pct,sz_pct,cy_pct,zz2000_pct,create_time)
        VALUES (%s,%s,%s,%s,%s,NOW())
        ON DUPLICATE KEY UPDATE sh_pct=VALUES(sh_pct),sz_pct=VALUES(sz_pct),cy_pct=VALUES(cy_pct),zz2000_pct=VALUES(zz2000_pct)"""
        cur.execute(sql, (date_str, idx_pcts.get('sh_pct'), idx_pcts.get('sz_pct'), idx_pcts.get('cy_pct'), idx_pcts.get('zz2000_pct')))
        log.info(f'  Index daily: SH{idx_pcts.get("sh_pct","?")}% SZ{idx_pcts.get("sz_pct","?")}% CY{idx_pcts.get("cy_pct","?")}% ZZ{idx_pcts.get("zz2000_pct","?")}%')
except Exception as e:
    log.warning(f'  Index daily backup 写入失败: {e}')

# 1c. Market daily stats (limit_up/down + turnover from push2)
try:
    # 涨跌停: 全A股, 统计涨跌幅>=9.9%和<=-9.9%
    clist_headers = {**HDR, 'Referer': 'https://quote.eastmoney.com/'}
    clist_params = {
        'pn': 1, 'pz': 5000, 'po': 1, 'np': 1,
        'ut': EASTMONEY_UT,
        'fltt': 2, 'invt': 2, 'fid': 'f3',
        'fs': 'm:0+t:6,m:0+t:13,m:1+t:2,m:1+t:23',
        'fields': 'f3',
    }
    r = requests.get('https://push2.eastmoney.com/api/qt/clist/get',
        params=clist_params, headers=clist_headers, timeout=15)
    items = r.json().get('data', {}).get('diff', [])
    zt = sum(1 for i in items if i.get('f3', 0) and float(i['f3']) >= 9.9)
    dt = sum(1 for i in items if i.get('f3', 0) and float(i['f3']) <= -9.9)

    # 成交额: 上证+深证
    tv_sh = 0.0
    tv_sz = 0.0
    for secid in ('1.000001', '0.399001'):
        try:
            r2 = requests.get('https://push2.eastmoney.com/api/qt/stock/get',
                params={'secid': secid, 'fields': 'f48'}, headers=clist_headers, timeout=10)
            tv_val = r2.json().get('data', {}).get('f48', 0) or 0
            if secid == '1.000001': tv_sh = tv_val
            else: tv_sz = tv_val
        except: pass
    tv_total = round((tv_sh + tv_sz) / 1e8, 2) if (tv_sh or tv_sz) else None

    if zt or dt or tv_total:
        sql = """INSERT INTO market_daily_stats (trade_date,limit_up,limit_down,turnover,create_time,update_time)
        VALUES (%s,%s,%s,%s,NOW(),NOW())
        ON DUPLICATE KEY UPDATE limit_up=VALUES(limit_up),limit_down=VALUES(limit_down),turnover=VALUES(turnover),update_time=NOW()"""
        cur.execute(sql, (date_str, zt, dt, tv_total))
        log.info(f'  Market Stats: {zt}涨停 {dt}跌停 {tv_total}亿')
except Exception as e:
    log.warning(f'  Market Stats 获取失败: {e}')

# 2. Fund NAV (East Money)
funds = [('563300','563300 CSI2000ETF'),('516330','516330 IoT ETF'),('588090','588090 STAR50 ETF')]
for code, name in funds:
    try:
        r = requests.get(EASTMONEY_FUND, params={'fundCode': code, 'pageIndex': 1, 'pageSize': 5},
            headers={**HDR, 'Referer': FUND_REFERER}, timeout=10)
        txt = r.text; s, e = txt.find('{'), txt.rfind('}')
        rows = json.loads(txt[s:e+1]).get('Data',{}).get('LSJZList',[]) if s>=0 else []
        for row in rows[:1]:
            dt, nav, acc, gr = row.get('FSRQ',''), row.get('DWJZ'), row.get('LJJZ'), row.get('JZZZL','')
            gr_val = gr.replace('%','') if gr else 'NULL'
            sql = """INSERT INTO fund_history (fund_code,fund_name,net_date,unit_nav,accum_nav,daily_growth,create_time,update_time)
            VALUES (%s,%s,%s,%s,%s,%s,NOW(),NOW())
            ON DUPLICATE KEY UPDATE unit_nav=VALUES(unit_nav),accum_nav=VALUES(accum_nav),daily_growth=VALUES(daily_growth),update_time=NOW()"""
            cur.execute(sql, (code, name, dt, float(nav), float(acc), float(gr_val)))
            log.info(f'  {name}: {dt} nav={nav} growth={gr}')
    except Exception as e:
        log.warning(f'  {name}: NAV获取失败 {e}')

# 3. ETF K-line cache (Tencent, 60日前复权)
etf_kline_count = 0
for code, name in funds:
    try:
        r = requests.get(TENCENT_KLINE,
            params={'param': f'sh{code},day,,,60,qfq'}, headers=HDR, timeout=10)
        data = r.json().get('data', {}).get(f'sh{code}', {})
        klines = data.get('qfqday', data.get('day', []))
        for k in klines:
            if len(k) < 5: continue
            sql = """INSERT INTO etf_kline (fund_code,trade_date,open,high,low,close,volume,is_adj,create_time)
            VALUES (%s,%s,%s,%s,%s,%s,%s,1,NOW())
            ON DUPLICATE KEY UPDATE open=VALUES(open),high=VALUES(high),low=VALUES(low),close=VALUES(close),volume=VALUES(volume)"""
            cur.execute(sql, (code, k[0], k[1], k[3], k[4], k[2], k[5] if len(k) >= 6 else None))
            etf_kline_count += 1
        log.info(f'  {name} K-line: {len(klines)} rows cached')
    except Exception as e:
        log.warning(f'  {name} K-line: 获取失败 {e}')
if etf_kline_count:
    log.info(f'  ETF K-line: {etf_kline_count} rows total')

# 4. Market capital flow (East Money push2his)
flow_ok = False
for attempt in range(3):
    try:
        r = requests.get('https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get',
            params={'secid':'1.000001','fields1':'f1,f2,f3,f4,f5',
                    'fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
                    'lmt':'5','ut':EASTMONEY_UT},
            headers={**HDR, 'Referer': 'https://data.eastmoney.com/'}, timeout=10)
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
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
                    ON DUPLICATE KEY UPDATE main_force_net=VALUES(main_force_net),retail_net=VALUES(retail_net),medium_net=VALUES(medium_net),large_net=VALUES(large_net),super_large_net=VALUES(super_large_net),main_force_pct=VALUES(main_force_pct),retail_pct=VALUES(retail_pct),medium_pct=VALUES(medium_pct),large_pct=VALUES(large_pct),super_large_pct=VALUES(super_large_pct),update_time=NOW()"""
                    cur.execute(sql, (dt, mf, rt, md, lg, sl, mp, rp, mdp, lp, slp))
            log.info(f'  Market Flow: {len(klines)} records updated')
            flow_ok = True
            break
    except Exception as e:
        if attempt < 2:
            time.sleep(2)
            continue
        log.error(f'  Market Flow API unavailable (3 retries): {e}')
        break

# 4b. ETF 个股资金流 (563300)
for code in [PRIMARY_FUND] + [f[0] for f in funds]:
    try:
        sid = f"1.{code}" if code[0] in ('5','6','9') else f"0.{code}"
        r = requests.get('https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get',
            params={'secid': sid, 'fields1': 'f1,f2,f3,f4,f5',
                    'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
                    'lmt': '5', 'ut': EASTMONEY_UT},
            headers={**HDR, 'Referer': 'https://data.eastmoney.com/'}, timeout=10)
        klines = r.json().get('data',{}).get('klines',[])
        cnt = 0
        for k in klines:
            p = k.split(',')
            if len(p) >= 11:
                sql = """INSERT INTO etf_fund_flow (trade_date,fund_code,main_force_net,retail_net,medium_net,large_net,super_large_net,create_time)
                VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())
                ON DUPLICATE KEY UPDATE main_force_net=VALUES(main_force_net),retail_net=VALUES(retail_net),medium_net=VALUES(medium_net),large_net=VALUES(large_net),super_large_net=VALUES(super_large_net)"""
                cur.execute(sql, (p[0], code, p[1], p[2], p[3], p[4], p[5]))
                cnt += 1
        if cnt:
            log.info(f'  {code} 个股资金流: {cnt} rows')
    except Exception as e:
        log.warning(f'  {code} 个股资金流: {e}')

conn.commit(); conn.close()
log.info('=== Update Complete ===')
if not flow_ok:
    log.warning('  (Market flow data was not updated - API will retry on next run)')

# 5. News sentiment (Sina feed)
try:
    from news_sentiment import save_to_db, fetch_news
    articles, today = fetch_news()
    if articles:
        n = save_to_db(articles, today)
        log.info(f'  News sentiment: {n} articles saved')
    else:
        log.warning('  News fetch returned 0 articles')
except Exception as e:
    log.warning(f'  News sentiment 获取失败: {e}')

# 数据库备份到 git
try:
    import subprocess
    backup_script = os.path.join(os.path.dirname(__file__), 'backup_db.py')
    result = subprocess.run([sys.executable, backup_script], capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        log.info('DB backup + git push OK')
    else:
        log.warning(f'Backup failed: {result.stderr.strip()[:100]}')
except Exception as e:
    log.warning(f'Backup skipped: {e}')
