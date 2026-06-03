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

def api_get(url, params=None, headers=None, timeout=15, retries=2):
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
        except Exception as e:
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise e
    return None

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
    'sector_fund_flow': '''CREATE TABLE IF NOT EXISTS sector_fund_flow (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        trade_date DATE NOT NULL,
        sector_name VARCHAR(50) NOT NULL,
        sector_type VARCHAR(20) COMMENT '行业资金流/概念资金流',
        main_force_net DECIMAL(20,2) COMMENT '主力净流入',
        super_large_net DECIMAL(20,2) COMMENT '超大单净流入',
        large_net DECIMAL(20,2) COMMENT '大单净流入',
        medium_net DECIMAL(20,2) COMMENT '中单净流入',
        retail_net DECIMAL(20,2) COMMENT '散户净流入',
        create_time DATETIME DEFAULT NOW(),
        KEY idx_date (trade_date),
        UNIQUE KEY uk_sector_date (sector_name, sector_type, trade_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
}
for t, s in tables_sql.items():
    cur.execute(s)

log.info(f'=== Data Update {date_str} ===')

# 1. Index K-line (Tencent + baostock 双重保障)
indices_api = {
    'sh000001': ('SH Index', 'sh.000001'),
    'sz399001': ('SZ Component', 'sz.399001'),
    'sz399006': ('ChiNext', 'sz.399006'),
    'sh000688': ('STAR 50', 'sh.000688'),
    'sh000300': ('CSI 300', 'sh.000300'),
    'sh000852': ('CSI 1000', 'sh.000852'),
}
for code, (name, bs_code) in indices_api.items():
    got = None
    try:
        r = api_get(TENCENT_KLINE,
            params={'param': f'{code},day,,,1,qfq'}, headers=HDR, timeout=10)
        if r:
            items = r.json().get('data', {}).get(code, {}).get('day', [])
            if items:
                last = items[-1]
                got = f'{last[0]} close={last[2]}'
                log.info(f'  {name}: {got}')
    except: pass
    if not got:
        try:
            import baostock as bs
            lg = bs.login()
            if lg.error_code == '0':
                rs = bs.query_history_k_data_plus(bs_code,
                    "date,close", start_date="2026-05-20", end_date="2026-06-03",
                    frequency="d", adjustflag="2")
                rows = []
                while rs.next():
                    rows.append(rs.get_row_data())
                bs.logout()
                if rows:
                    log.info(f'  {name}: baostock兜底 {rows[-1][0]} close={rows[-1][1]}')
        except: pass

# 1b. Index daily % backup (write to index_daily for _afternoon_check fallback)
try:
    idx_pcts = {}
    idx_map = {'sh000001': 'sh_pct', 'sz399001': 'sz_pct', 'sz399006': 'cy_pct', 'sh000852': 'zz2000_pct'}
    for code, col in idx_map.items():
        r = api_get(f'https://web.sqt.gtimg.cn/q={code}', headers=HDR, timeout=10)
        if r:
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

# 1c. Market daily stats (limit_up/down + turnover)
zt, dt = 0, 0
try:
    import akshare as ak
    today_key = date_str.replace('-', '')
    zt_df = ak.stock_zt_pool_em(date=today_key)
    dt_df = ak.stock_zt_pool_dtgc_em(date=today_key)
    zt, dt = len(zt_df), len(dt_df)
    log.info(f'  akshare涨停跌停: {zt}涨停 {dt}跌停')
except Exception as e:
    log.warning(f'  akshare涨停跌停失败: {e}')
# 成交额: 上证+深证 (push2)
tv_total = None
try:
    clist_headers = {**HDR, 'Referer': 'https://quote.eastmoney.com/'}
    tv_sh, tv_sz = 0.0, 0.0
    for secid in ('1.000001', '0.399001'):
        try:
            r2 = api_get('https://push2.eastmoney.com/api/qt/stock/get',
                params={'secid': secid, 'fields': 'f48'}, headers=clist_headers, timeout=10)
            if r2:
                tv_val = r2.json().get('data', {}).get('f48', 0) or 0
                if secid == '1.000001': tv_sh = tv_val
                else: tv_sz = tv_val
        except: pass
    tv_total = round((tv_sh + tv_sz) / 1e8, 2) if (tv_sh or tv_sz) else None
except: pass
if zt > 0 or dt > 0 or tv_total:
    if tv_total:
        sql = """INSERT INTO market_daily_stats (trade_date,limit_up,limit_down,turnover,create_time,update_time)
        VALUES (%s,%s,%s,%s,NOW(),NOW())
        ON DUPLICATE KEY UPDATE limit_up=VALUES(limit_up),limit_down=VALUES(limit_down),turnover=VALUES(turnover),update_time=NOW()"""
        cur.execute(sql, (date_str, zt, dt, tv_total))
    else:
        sql = """INSERT INTO market_daily_stats (trade_date,limit_up,limit_down,create_time,update_time)
        VALUES (%s,%s,%s,NOW(),NOW())
        ON DUPLICATE KEY UPDATE limit_up=VALUES(limit_up),limit_down=VALUES(limit_down),update_time=NOW()"""
        cur.execute(sql, (date_str, zt, dt))
    log.info(f'  Market Stats: {zt}涨停 {dt}跌停 {tv_total or "沿用旧值"}亿')

# 2. Fund NAV (East Money, 只取最新净值)
funds = [('563300','563300 CSI2000ETF'),('516330','516330 IoT ETF'),('588090','588090 STAR50 ETF')]
for code, name in funds:
    try:
        r = api_get(EASTMONEY_FUND, params={'fundCode': code, 'pageIndex': 1, 'pageSize': 1},
            headers={**HDR, 'Referer': FUND_REFERER}, timeout=10)
        if r:
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
        else:
            log.warning(f'  {name}: API无返回')
    except Exception as e:
        log.warning(f'  {name}: NAV获取失败 {e}')

# 3. ETF K-line cache (Tencent + baostock 双重保障, 60日前复权)
etf_kline_count = 0
for code, name in funds:
    klines = []
    # 优先腾讯
    try:
        r = api_get(TENCENT_KLINE,
            params={'param': f'sh{code},day,,,60,qfq'}, headers=HDR, timeout=10)
        if r:
            data = r.json().get('data', {}).get(f'sh{code}', {})
            klines = data.get('qfqday', data.get('day', []))
    except: pass
    # 腾讯失败 → baostock 兜底
    if not klines:
        try:
            import baostock as bs
            lg = bs.login()
            if lg.error_code == '0':
                prefix = 'sh' if code[0] in ('5','6','9') else 'sz'
                rs = bs.query_history_k_data_plus(f"{prefix}.{code}",
                    "date,open,high,low,close,volume,adjustflag",
                    start_date="2026-03-01", end_date="2026-06-03",
                    frequency="d", adjustflag="2")
                while rs.next():
                    r = rs.get_row_data()
                    if r[0] and r[1]:
                        klines.append(r)
                bs.logout()
                if klines:
                    log.info(f'  {name} K-line: baostock兜底 {len(klines)} rows')
        except: pass
    for k in klines:
        if len(k) < 5: continue
        sql = """INSERT INTO etf_kline (fund_code,trade_date,open,high,low,close,volume,is_adj,create_time)
        VALUES (%s,%s,%s,%s,%s,%s,%s,1,NOW())
        ON DUPLICATE KEY UPDATE open=VALUES(open),high=VALUES(high),low=VALUES(low),close=VALUES(close),volume=VALUES(volume)"""
        cur.execute(sql, (code, k[0], k[1], k[3], k[4], k[2], k[5] if len(k) >= 6 else None))
        etf_kline_count += 1
    if klines:
        log.info(f'  {name} K-line: {len(klines)} rows cached')
    else:
        log.warning(f'  {name} K-line: 腾讯+baostock均失败')
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
        r = api_get('https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get',
            params={'secid': sid, 'fields1': 'f1,f2,f3,f4,f5',
                    'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
                    'lmt': '5', 'ut': EASTMONEY_UT},
            headers={**HDR, 'Referer': 'https://data.eastmoney.com/'}, timeout=10)
        if not r: continue
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

# 6. 板块资金流向 (akshare 行业+概念)
for stype in ('行业资金流', '概念资金流'):
    for attempt in range(2):
        try:
            import akshare as ak
            df = ak.stock_sector_fund_flow_rank(indicator='今日', sector_type=stype)
            cnt = 0
            for _, r in df.iterrows():
                sql = """INSERT INTO sector_fund_flow (trade_date,sector_name,sector_type,main_force_net,super_large_net,large_net,medium_net,retail_net,create_time)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                ON DUPLICATE KEY UPDATE main_force_net=VALUES(main_force_net),super_large_net=VALUES(super_large_net),large_net=VALUES(large_net),medium_net=VALUES(medium_net),retail_net=VALUES(retail_net)"""
                cur.execute(sql, (
                    date_str, r['名称'], stype,
                    float(r['今日主力净流入-净额']),
                    float(r['今日超大单净流入-净额']),
                    float(r['今日大单净流入-净额']),
                    float(r['今日中单净流入-净额']),
                    float(r['今日散户净流入-净额']),
                ))
                cnt += 1
            if cnt:
                log.info(f'  {stype}: {cnt} 个板块已入库')
            break
        except Exception as e:
            if attempt == 0: time.sleep(2)
            else: log.warning(f'  {stype} 采集失败: {e}')

conn.commit(); conn.close()
log.info('=== Update Complete ===')
if not flow_ok:
    log.warning('  (Market flow data was not updated - API will retry on next run)')

# 5. News sentiment (Sina feed, 带重试)
for _ in range(2):
    try:
        from news_sentiment import save_to_db, fetch_news
        articles, today = fetch_news()
        if articles:
            n = save_to_db(articles, today)
            log.info(f'  News sentiment: {n} articles saved')
        else:
            log.warning('  News fetch returned 0 articles')
        break
    except Exception as e:
        log.warning(f'  News sentiment 获取失败(重试): {e}')
        time.sleep(2)

# 数据库备份到 git
try:
    import subprocess
    backup_script = os.path.join(os.path.dirname(__file__), 'backup_db.py')
    result = subprocess.run([sys.executable, backup_script], capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        log.info('DB backup + git push OK')
    else:
        err = result.stderr.strip()[:150] or result.stdout.strip()[:150]
        log.warning(f'Backup issue: {err}')
except Exception as e:
    log.warning(f'Backup skipped: {e}')
