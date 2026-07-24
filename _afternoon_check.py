# 尾盘决策脚本 — 14:30后运行
# python _afternoon_check.py
# 依赖: pymysql, requests

import requests, json, sys, socket, os, datetime, math
sys.stdout.reconfigure(encoding='utf-8')
import requests.packages.urllib3.util.connection as urllib3_cn
urllib3_cn.allowed_gai_family = lambda: socket.AF_INET
sys.path.insert(0, os.path.dirname(__file__))
from strategy_config import get_latest
from config import DB, CAPITAL, SYSTEM_BASE_CASH, PRIMARY_FUND, PRIMARY_FUND_NAME
from news_sentiment import read_sentiment_from_db

VER = get_latest()
P = VER["params"]

HDR = {'User-Agent': 'Mozilla/5.0'}
EM_HDR = {**HDR, 'Referer': 'https://data.eastmoney.com/'}
PUSH2_HDR = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Referer': 'https://quote.eastmoney.com/',
    'Origin': 'https://quote.eastmoney.com',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-site',
}
UT = 'fa5fd1943c7b386f172d6893dbbd1d0c'
FUND = PRIMARY_FUND; FUND_NAME = PRIMARY_FUND_NAME
SECONDARY_FUNDS = [('588090', '科创50ETF华泰柏瑞')]
def get_held_fund():
    try:
        import pymysql
        conn = pymysql.connect(**DB)
        cur = conn.cursor()
        cur.execute("SELECT fund_code,fund_name FROM position GROUP BY fund_code,fund_name HAVING SUM(CASE WHEN trade_type='buy' THEN shares ELSE -shares END) > 0")
        r = cur.fetchone()
        conn.close()
        if r: return r[0], r[1]
    except: pass
    return FUND, FUND_NAME
FUND, FUND_NAME = get_held_fund()
MAX_PER_TRADE = P["max_invest"]

TODAY = datetime.date.today().isoformat()

def get_pos_from_db(note_filter=None):
    """note_filter: 'system' for 系统决策, 'real' for others, None for all"""
    try:
        import pymysql
        conn = pymysql.connect(**DB)
        cur = conn.cursor()
        sys_note = "note LIKE CONCAT('系统决策', CHAR(37))"
        if note_filter == 'system':
            note_cond = "AND " + sys_note
        elif note_filter == 'real':
            note_cond = "AND (note IS NULL OR NOT(" + sys_note + "))"
        else:
            note_cond = ""
        cur.execute("SELECT fund_code,fund_name,SUM(CASE WHEN trade_type='buy' THEN shares ELSE -shares END) FROM position WHERE fund_code IS NOT NULL " + note_cond + " GROUP BY fund_code,fund_name")
        r = cur.fetchone()
        shares_hold = float(r[2]) if r and r[2] else 0
        if note_filter == 'real' or note_filter is None:
            cur.execute("SELECT cash_after FROM position WHERE note IS NULL OR NOT(" + sys_note + ") ORDER BY id DESC LIMIT 1")
            cash_r = cur.fetchone()
            cash = float(cash_r[0]) if cash_r else CAPITAL
        else:
            cash = 0
        if shares_hold > 0:
            if note_filter == 'system':
                note_cond2 = "AND " + sys_note
            else:
                note_cond2 = "AND (note IS NULL OR NOT(" + sys_note + "))"
            cur.execute("SELECT price FROM position WHERE fund_code=%s AND trade_type='buy' " + note_cond2 + " ORDER BY id DESC LIMIT 1", (r[0],))
            entry_r = cur.fetchone()
            entry = float(entry_r[0]) if entry_r else 0
            conn.close()
            return shares_hold, entry, cash
        conn.close()
        return 0, 0, cash
    except: pass
    return 0, 0, CAPITAL

real_shares, real_entry, real_cash = get_pos_from_db('real')
sys_shares, sys_entry, _ = get_pos_from_db('system')
shares = real_shares
entry = real_entry
cash = real_cash if real_cash >= 100 else CAPITAL

# 1. 实时行情 (腾讯API)
def get_rt(code):
    url = f'https://web.sqt.gtimg.cn/q=sh{code}'
    r = requests.get(url, headers=HDR, timeout=10)
    parts = r.text.replace('"','').split('~')
    return parts  # 0-index, [3]=当前价 [4]=昨收 [5]=最高 [6]=最低 [32]=涨跌幅% [31]=涨跌额

etf = get_rt(FUND)
idx = get_rt('000001')
cur_p = float(etf[3]) if len(etf) > 3 else 0
pre_p = float(etf[4]) if len(etf) > 4 else 0
pct = (cur_p - pre_p) / pre_p * 100 if pre_p else 0

if cur_p <= 0:
    print('ERROR: 无法获取实时行情(cur_p=0)，请检查腾讯API是否可达')
    sys.exit(1)

# 成交额: 腾讯行情(全天稳定)替代push2
try:
    sh_tv = float(idx[37]) if len(idx) > 37 and idx[37] else 0
    r_sz = requests.get('https://web.sqt.gtimg.cn/q=sz399001', headers=HDR, timeout=10)
    sz_parts = r_sz.text.replace('"','').split('~')
    sz_tv = float(sz_parts[37]) if len(sz_parts) > 37 and sz_parts[37] else 0
    tencent_tv = round((sh_tv + sz_tv) / 10000, 0)
    if tencent_tv > 0:
        tv = tencent_tv
except: pass

idx_cur = float(idx[3]) if len(idx) > 3 else 0
idx_pre = float(idx[4]) if len(idx) > 4 else 0
idx_pct = (idx_cur - idx_pre) / idx_pre * 100 if idx_pre else 0

# 2. 最近市场量价 — 四级策略: akshare > 新浪API > push2分页 > DB兜底
tv, lu, ld, db_today = 0, 0, 0, False
margin_chg = 0.0
today_str = TODAY.replace('-', '')
# 优先akshare获取涨停跌停股池
try:
    import akshare as ak
    zt_df = ak.stock_zt_pool_em(date=today_str)
    dt_df = ak.stock_zt_pool_dtgc_em(date=today_str)
    lu, ld = len(zt_df), len(dt_df)
    if lu > 0 or ld > 0:
        db_today = True
        print(f'  akshare实时: 涨停{lu} 跌停{ld}')
except:
    pass
# 二级: 新浪财经API获取涨停跌停
if lu == 0 and ld == 0:
    import json
    try:
        sina_hdr = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        r_sina = requests.get('https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=200&sort=changepercent&asc=-1&node=hs_a&symbol=&_s_r_a=init',
            headers=sina_hdr, timeout=20)
        if r_sina.status_code == 200 and r_sina.text.strip():
            text = r_sina.text
            if text.startswith('('): text = text[1:-1]
            data = json.loads(text)
            lu = sum(1 for d in data if float(d.get('changepercent',0)) >= 9.5)
        r_sina2 = requests.get('https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=200&sort=changepercent&asc=1&node=hs_a&symbol=&_s_r_a=init',
            headers=sina_hdr, timeout=20)
        if r_sina2.status_code == 200 and r_sina2.text.strip():
            text2 = r_sina2.text
            if text2.startswith('('): text2 = text2[1:-1]
            data2 = json.loads(text2)
            ld = sum(1 for d2 in data2 if float(d2.get('changepercent',0)) <= -9.5)
        if lu > 0 or ld > 0:
            db_today = True
            print(f'  新浪实时: 涨停{lu} 跌停{ld}')
    except: pass
# 成交额: 尝试push2获取
try:
    clist_h = {**HDR, 'Referer': 'https://quote.eastmoney.com/'}
    for sid in ('1.000001','0.399001'):
        try:
            r3 = requests.get('https://push2.eastmoney.com/api/qt/stock/get',
                params={'secid':sid,'fields':'f48'}, headers=clist_h, timeout=10)
            tv += (r3.json().get('data',{}).get('f48') or 0)
        except: pass
    tv = round(tv/1e8, 2) if tv else None
except: pass
# 成交额/涨停/跌停有缺失时→从DB兜底(仅当日数据)
if not tv or (lu == 0 and ld == 0):
    try:
        import pymysql
        conn = pymysql.connect(**DB)
        cur = conn.cursor()
        cur.execute("SELECT trade_date, turnover, limit_up, limit_down FROM market_daily_stats WHERE trade_date=%s", (TODAY,))
        r = cur.fetchone()
        if r:
            if not tv: tv = float(r[1] or 0)
            if lu == 0 and ld == 0:
                lu, ld = int(r[2] or 0), int(r[3] or 0)
                db_today = True
        conn.close()
    except: pass
# 融资余额
try:
    import pymysql
    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    cur.execute("SELECT trade_date, margin_balance FROM sentiment_raw_factors WHERE margin_balance IS NOT NULL ORDER BY trade_date DESC LIMIT 10")
    margins = [(str(r[0]), float(r[1])) for r in cur.fetchall()]
    if len(margins) >= 5:
        latest = margins[0][1]
        t5 = margins[-1][1] if len(margins) > 5 else margins[min(4, len(margins)-1)][1]
        if t5 > 0: margin_chg = (latest - t5) / t5 * 100
    conn.close()
except: pass

# 3. 大盘资金流向明细 (push2his日线)
import time
main_force_net = 0.0
large_net = super_large_net = retail_net = 0.0
main_force_pct = super_large_pct = 0.0
for retry in range(3):
    try:
        r = requests.get('https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get',
            params={'secid':'1.000001','secid2':'0.399001',
                'fields1':'f1,f2,f3,f7','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65',
                'lmt':'0','klt':'101'},
            headers={'User-Agent':'Mozilla/5.0','Referer':'https://data.eastmoney.com/'}, timeout=15)
        if r.status_code == 200:
            raw = r.json()
            klines = raw.get('data',{}).get('klines',[])
            if klines:
                parts = klines[-1].split(',')
                main_force_net = float(parts[1]) if len(parts) > 1 else 0
                retail_net = float(parts[2]) if len(parts) > 2 else 0
                large_net = float(parts[4]) if len(parts) > 4 else 0
                super_large_net = float(parts[5]) if len(parts) > 5 else 0
                main_force_pct = float(parts[6]) if len(parts) > 6 else 0
                super_large_pct = float(parts[10]) if len(parts) > 10 else 0
                break
            time.sleep(1 + retry)
        else:
            time.sleep(1 + retry)
    except Exception as e:
        time.sleep(1 + retry)

# 3b. 北向资金净流入
northbound_net = 0.0
try:
    r_nb = requests.get('https://push2.eastmoney.com/api/qt/kamt.kline/get',
        params={'fields1':'f1,f2,f3,f4','fields2':'f51,f52','klt':'101','lmt':1},
        headers=PUSH2_HDR, timeout=15)
    nb_data = r_nb.json().get('data',{})
    hgt = nb_data.get('hgt',{}).get('klines',[])
    sgt = nb_data.get('sgt',{}).get('klines',[])
    if hgt and sgt:
        hgt_net = float(hgt[0].split(',')[1]) if ',' in hgt[0] else 0
        sgt_net = float(sgt[0].split(',')[1]) if ',' in sgt[0] else 0
        northbound_net = hgt_net + sgt_net
except: pass

# 4. 全市场复合指数
def get_rt_market(code):
    url = f'https://web.sqt.gtimg.cn/q={code}'
    try:
        r = requests.get(url, headers=HDR, timeout=10)
        parts = r.text.replace('"','').split('~')
        if len(parts) > 32:
            try: return float(parts[32])
            except: return None
    except: pass
    return None
sz_pct = get_rt_market('sz399001')
cy_pct = get_rt_market('sz399006')
zz_pct = get_rt_market('sh000852')

if sz_pct is None or cy_pct is None or zz_pct is None:
    try:
        conn2 = pymysql.connect(**DB)
        cur2 = conn2.cursor()
        cur2.execute("SELECT sh_pct,sz_pct,cy_pct,zz2000_pct FROM index_daily ORDER BY trade_date DESC LIMIT 1")
        backup = cur2.fetchone()
        conn2.close()
        if backup:
            if idx_pct == 0: idx_pct = float(backup[0] or 0)
            if sz_pct is None: sz_pct = float(backup[1] or 0)
            if cy_pct is None: cy_pct = float(backup[2] or 0)
            if zz_pct is None: zz_pct = float(backup[3] or 0)
    except: pass

composite = idx_pct * 0.3 + (sz_pct or 0) * 0.2 + (cy_pct or 0) * 0.1 + (zz_pct or 0) * 0.4

# 5. 情绪估算
def calc_sentiment(composite, limit_up, limit_down, turnover, mf_net, margin_chg, northbound_net, news_score, data_is_today):
    val = -0.1920 + 0.7169 * composite
    if data_is_today:
        if limit_down and limit_up is not None:
            ratio = limit_up / max(limit_down, 1)
            if ratio > 3 and val < 0: val += 0.3
            elif ratio < 0.5 and val > 0: val -= 0.3
        if turnover:
            if turnover > 25000:
                delta = (turnover - 25000) / 5000 * 0.2
                val += delta if val >= 0 else -delta
            elif turnover < 18000:
                val *= 0.7
    if mf_net:
        flow = mf_net / 5e11
        if (flow > 0 and val > 0) or (flow < 0 and val < 0):
            val += flow
        else:
            val += flow * 0.5
    if margin_chg:
        if margin_chg > 1.0: val += 0.2
        elif margin_chg > 0.5: val += 0.1
        elif margin_chg < -1.0: val -= 0.3
        elif margin_chg < -0.5: val -= 0.1
    if northbound_net:
        if northbound_net > 80: val += 0.4
        elif northbound_net > 40: val += 0.2
        elif northbound_net < -60: val -= 0.4
        elif northbound_net < -20: val -= 0.2
    if news_score:
        val += news_score * 0.3
    val = max(-2.5, min(2.5, val))
    if val >= 2.0:   zone = '沸点'
    elif val >= 1.0: zone = '过热'
    elif val >= 0.1: zone = '微热'
    elif val > -0.1: zone = '0分界'
    elif val >= -0.9:zone = '微冷'
    elif val >= -1.9:zone = '过冷'
    else:            zone = '冰点'
    return round(val, 2), zone

news_score = read_sentiment_from_db()

# 避险仓位
haven_pv = {}; haven_ma = None; haven_above_ma = None
if P.get("haven_code"):
    try:
        import pymysql
        conn_h = pymysql.connect(**DB)
        cur_h = conn_h.cursor()
        ma_w = P.get("haven_ma_window", 20)
        limit = max(ma_w + 5, 25)
        if P["haven_code"] == '600900':
            cur_h.execute(f"SELECT trade_date, close FROM cjdl_kline ORDER BY trade_date DESC LIMIT {limit}")
        else:
            cur_h.execute(f"SELECT trade_date, close FROM haven_kline WHERE code=%s ORDER BY trade_date DESC LIMIT {limit}", (P["haven_code"],))
        rows = cur_h.fetchall()
        conn_h.close()
        if len(rows) >= ma_w:
            haven_pv = {str(r[0]): float(r[1]) for r in rows}
            haven_ma = sum(float(r[1]) for r in rows[:ma_w]) / ma_w
            haven_cur = float(rows[0][1])
            haven_above_ma = haven_cur > haven_ma
    except: pass

SENT, ZONE = calc_sentiment(composite, lu, ld, tv, main_force_net, margin_chg, northbound_net, news_score, db_today)

# 情绪落地
try:
    import pymysql
    conn_m = pymysql.connect(**DB)
    cur_m = conn_m.cursor()
    cur_m.execute("""INSERT INTO market_sentiment (trade_date,sentiment_value,sentiment_zone,composite_idx,create_time,update_time)
    VALUES (%s,%s,%s,%s,NOW(),NOW())
    ON DUPLICATE KEY UPDATE sentiment_value=VALUES(sentiment_value),sentiment_zone=VALUES(sentiment_zone),composite_idx=VALUES(composite_idx),update_time=NOW()""",
    (TODAY, SENT, ZONE, composite))
    try:
        cur_m.execute("""ALTER TABLE market_sentiment ADD COLUMN sentiment_v6 DECIMAL(5,2)""")
        conn_m.commit()
    except: pass
    cur_m.execute("""UPDATE market_sentiment SET sentiment_v6=%s WHERE trade_date=%s""",
        (SENT, TODAY))
    conn_m.commit()
    conn_m.close()
except: pass

# 资金流分钟数据
def eastmoney_fund_flow_minute(code):
    secid = f"1.{code}" if code[0] in ("5","6","9") else f"0.{code}"
    url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
    params = {"secid": secid, "klt": 1, "fields1": "f1,f2,f3,f7", "fields2": "f51,f52,f53,f54,f55,f56,f57"}
    try:
        r = requests.get(url, params=params, headers=PUSH2_HDR, timeout=10)
        d = r.json()
        klines = d.get("data", {}).get("klines", [])
        if klines:
            rows = []
            for line in klines:
                parts = line.split(",")
                if len(parts) >= 6:
                    rows.append({"time": parts[0], "main_net": float(parts[1])})
            return rows
    except: pass
    return []

def hsgt_realtime():
    url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
    try:
        r = requests.get(url, headers=HDR, timeout=10)
        d = r.json()
        hgt_list = [v for v in d.get("hgt", []) if v is not None]
        sgt_list = [v for v in d.get("sgt", []) if v is not None]
        if hgt_list and sgt_list:
            hgt_net = hgt_list[-1] - hgt_list[0]
            sgt_net = sgt_list[-1] - sgt_list[0]
            return (round(hgt_net, 1), round(sgt_net, 1))
    except: pass
    return (None, None)

def industry_ranking(top_n=5):
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {"pn": "1", "pz": "100", "po": "0", "np": "1", "fltt": "2", "invt": "2",
              "fs": "m:90+t:2", "fields": "f2,f3,f4,f12,f14,f104,f105"}
    try:
        r = requests.get(url, params=params, headers=PUSH2_HDR, timeout=10)
        d = r.json()
        items = d.get("data", {}).get("diff", [])
        rows = []
        for i, item in enumerate(items):
            rows.append({"name": item.get("f14",""), "change": item.get("f3",0),
                         "up": item.get("f104",0), "down": item.get("f105",0)})
        top = [r for r in rows if r["change"] is not None][:top_n]
        bot = [r for r in rows if r["change"] is not None][-top_n:]
        bot.reverse()
        return top, bot
    except: pass
    return [], []

fund_flow = eastmoney_fund_flow_minute(FUND)
hgt_val, sgt_val = hsgt_realtime()
ind_top, ind_bot = industry_ranking(5)

# 20日均线
ma20_val = None
try:
    import pymysql
    conn_tmp = pymysql.connect(**DB)
    cur_tmp = conn_tmp.cursor()
    cur_tmp.execute("SELECT close FROM etf_kline WHERE fund_code=%s AND is_adj=1 ORDER BY trade_date DESC LIMIT 20", (FUND,))
    rows = cur_tmp.fetchall()
    conn_tmp.close()
    if len(rows) >= 20:
        ma20_val = sum(float(r[0]) for r in rows) / 20
except: pass

if ma20_val is None:
    try:
        r = requests.get('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',
            params={'param':f'sh{FUND},day,,,120,qfq'}, headers=HDR, timeout=10)
        data = r.json()['data'][f'sh{FUND}']
        klines = data.get('qfqday', data.get('day', []))
        closes = [float(k[2]) for k in klines if len(k) >= 5]
        if len(closes) >= 20:
            ma20_val = sum(closes[-20:]) / 20
    except: pass
above_ma20 = ma20_val and cur_p > ma20_val

# buyB enhanced
buyB_sent_mom_ok = True
buyB_dev_ok = True
if VER["ver"] >= "v5.7" and P["buyB"]:
    b_conf = P["buyB"]
    if b_conf.get("sent_ma_days"):
        try:
            conn_tmp = pymysql.connect(**DB)
            cur_tmp = conn_tmp.cursor()
            cur_tmp.execute("SELECT trade_date, sentiment_value FROM market_sentiment ORDER BY trade_date DESC LIMIT 5")
            rows = cur_tmp.fetchall()
            conn_tmp.close()
            if len(rows) >= b_conf["sent_ma_days"]:
                recent_avg = sum(float(r[1] or 0) for r in rows[:b_conf["sent_ma_days"]]) / b_conf["sent_ma_days"]
                prev_avg = sum(float(r[1] or 0) for r in rows[1:b_conf["sent_ma_days"]+1]) / min(b_conf["sent_ma_days"], len(rows)-1)
                buyB_sent_mom_ok = recent_avg > prev_avg
        except: pass
    if b_conf.get("ma_deviation_max") and ma20_val and cur_p:
        buyB_dev_ok = (cur_p - ma20_val) / ma20_val <= b_conf["ma_deviation_max"]

# 判断信号
fund_flow_pos = False
if fund_flow and len(fund_flow) >= 5:
    recent = fund_flow[-5:]
    avg_main = sum(r["main_net"] for r in recent) / 5
    fund_flow_pos = avg_main > 0

sv_threshold = P["buyA_sv_max"]
margin_boost = P.get("buyA_margin_boost") and margin_chg < -1.0
if margin_boost:
    sv_threshold = -1.0

buy_cond1 = SENT <= sv_threshold
buy_cond2 = pct <= P["buyA_dc_min"]
buy_cond3 = ld > lu or tv >= 25000
buy_cond4 = fund_flow_pos if fund_flow else True
buy_signal = buy_cond1 and buy_cond2 and buy_cond3 and buy_cond4

pnl = (cur_p - entry) / entry * 100 if entry and shares > 0 else 0
sell_stop = pnl <= P["stop_loss_pct"] and shares > 0 and entry > 0
sell_sent = SENT >= P["sell_all_sv"] and shares > 0
sell_half = P["sell_half_sv"] and SENT >= P["sell_half_sv"] and SENT < P["sell_all_sv"] and shares > 0
sell_tp = P["take_profit_pct"] and pnl >= P["take_profit_pct"] and shares > 0

trail_peak = entry
sell_trail = False
trail_limit = None
if P.get("trailing_stop_pct") and shares > 0 and entry > 0:
    try:
        import pymysql
        conn_t = pymysql.connect(**DB)
        cur_t = conn_t.cursor()
        cur_t.execute("CREATE TABLE IF NOT EXISTS position_peak (fund_code VARCHAR(10) PRIMARY KEY, peak_price DECIMAL(10,4), update_time DATETIME)")
        conn_t.commit()
        cur_t.execute("SELECT peak_price FROM position_peak WHERE fund_code=%s", (FUND,))
        r = cur_t.fetchone()
        if r and r[0]:
            trail_peak = float(r[0])
            trail_peak = max(trail_peak, cur_p)
        else:
            trail_peak = max(entry, cur_p)
        cur_t.execute("INSERT INTO position_peak (fund_code,peak_price,update_time) VALUES (%s,%s,NOW()) ON DUPLICATE KEY UPDATE peak_price=%s,update_time=NOW()", (FUND, trail_peak, trail_peak))
        conn_t.commit()
        conn_t.close()
        trail_pnl = (cur_p - trail_peak) / trail_peak * 100
        trail_limit = P["trailing_stop_pct"]
        if P.get("profit_lock") and pnl >= P["profit_lock"]:
            trail_limit = P.get("lock_trailing_stop", -3.0)
        sell_trail = trail_pnl <= trail_limit
    except: pass
has_buyB = P["buyB"] and P["buyB"]["sv_min"] <= SENT <= P["buyB"]["sv_max"]

# 输出
print(f'\n{"="*55}')
print(f'  尾盘决策 {VER["ver"]} ({VER["desc"]})')
print(f'  {TODAY} | {idx_pct:+.2f}%')
print(f'{"="*55}')
print(f'  {FUND_NAME}({FUND}): {cur_p:.4f}  ({pct:+.2f}%)')
for sf_code, sf_name in SECONDARY_FUNDS:
    sf = get_rt(sf_code)
    if len(sf) > 4:
        sf_c = float(sf[3]); sf_p = float(sf[4])
        sf_pct = (sf_c - sf_p) / sf_p * 100 if sf_p else 0
        print(f'  {sf_name}({sf_code}): {sf_c:.4f}  ({sf_pct:+.2f}%)')
print(f'  上证指数: {idx_cur:.0f}  ({idx_pct:+.2f}%)')
sz_label = f'深证{sz_pct:+.2f}%' if sz_pct else '深证--'
cy_label = f'创业板{cy_pct:+.2f}%' if cy_pct else '创业板--'
zz_label = f'中证2000{zz_pct:+.2f}%' if zz_pct else '中证2000--'
print(f'  复合指数: {composite:+.2f}% ({sz_label} {cy_label} 中证2000{zz_pct:+.2f}%)')
print(f'  估算情绪: {SENT:+.1f}({ZONE})')
if ma20_val: print(f'  20日均线: {ma20_val:.4f}  现价{"↑" if above_ma20 else "↓"} ({cur_p:.4f})')
print(f'  成交额: {tv or "N/A"}  涨停{lu}  跌停{ld}')
if margin_chg:
    boost_tag = ' (buyA触发降至1.0!)' if margin_boost else ''
    print(f'  融资余额5日变化: {margin_chg:+.2f}%{boost_tag}')
if northbound_net: print(f'  北向资金: {northbound_net:+.1f}亿')
if news_score: print(f'  新闻情绪: {news_score:+.2f} (-2恐慌~+2亢奋)')
if haven_above_ma is not None:
    haven_hint = f'{P.get("haven_name","神华")}>MA{ma_w}: 避险减仓至{P["haven_scale"]*100:.0f}%' if haven_above_ma else f'{P.get("haven_name","神华")}≤MA{ma_w}: 风险加仓至{P["risk_scale"]*100:.0f}%'
    print(f'  避险仓位: {haven_hint}')
if main_force_net != 0:
    print(f'  今日资金: 主力{main_force_net/1e8:+.0f}亿  超大单{super_large_net/1e8:+.0f}亿  大单{large_net/1e8:+.0f}亿  散户{retail_net/1e8:+.0f}亿')

print(f'\n  ── 条件检查 ({VER["ver"]}) ──')
boost_label = f'(融资去杠杆放宽到{sv_threshold})' if margin_boost else ''
print(f'  ① 情绪≤{sv_threshold}: {"OK" if buy_cond1 else "NO"} ({SENT:+.1f}){boost_label}')
print(f'  ② ETF跌≥{P["buyA_dc_min"]}%: {"OK" if buy_cond2 else "NO"} ({pct:+.2f}%)')
tv_ok = (tv or 0) >= 25000; ld_ok = ld > lu
tv_label = f'成交{tv:.0f}亿≥25000' if tv_ok else f'成交{tv or "N/A"}亿<25000'
ld_label = f'跌停{ld}>涨停{lu}' if ld_ok else f'跌停{ld}≤涨停{lu}'
print(f'  ③ 放量/跌停:  {"OK" if buy_cond3 else "NO"} ({tv_label} {"或" if tv_ok or ld_ok else "且"} {ld_label})')
if fund_flow:
    flow_label = f'尾盘5分钟主力{"流入" if fund_flow_pos else "流出"}'
    print(f'  ④ 主力流入:  {"OK" if buy_cond4 else "NO"} ({flow_label})')

print(f'\n  === 操作建议 ===')
if shares > 0:
    if sell_stop:
        print(f'  STOP! 浮亏{pnl:+.1f}%≤{P["stop_loss_pct"]}%')
        print(f'  → 清仓 {shares:.0f}股 × {cur_p:.4f}')
    elif sell_trail:
        lock_tag = '(盈利锁定)' if P.get("profit_lock") and pnl >= P.get("profit_lock", 999) else ''
        print(f'  STOP回撤{lock_tag}! 从峰值{trail_peak:.4f}回落{trail_pnl:.1f}%≤{trail_limit}%')
    elif sell_sent:
        print(f'  STOP过热({SENT:+.1f}≥{P["sell_all_sv"]})，清仓')
    elif sell_half:
        half = math.floor(shares / 2 / 100) * 100
        print(f'  SELL一半({SENT:+.1f}≥{P["sell_half_sv"]})')
    elif sell_tp:
        half = math.floor(shares / 2 / 100) * 100
        print(f'  TP止盈! 浮盈{pnl:+.1f}%')
    else:
        print(f'  HOLD持仓不动')
elif buy_signal:
    max_amt = MAX_PER_TRADE
    if haven_above_ma is not None:
        max_amt = MAX_PER_TRADE * (P["haven_scale"] if haven_above_ma else P["risk_scale"])
    amt = min(max_amt, cash)
    bs = int(amt / cur_p / 100) * 100
    print(f'  BUY A抄底! {bs}股 × {cur_p:.4f} = {bs*cur_p:.0f}元')
else:
    print(f'  WAIT空仓等待')

# 信号落地
try:
    import pymysql
    conn_s = pymysql.connect(**DB); cur_s = conn_s.cursor()
    signal_type = 'buyA' if buy_signal else 'sell_all' if sell_sent else 'sell_half' if sell_half else 'stop_loss' if sell_stop else 'hold'
    cur_s.execute("INSERT INTO strategy_signals (trade_date,signal_type,sentiment_value,nav,reason,create_time) VALUES (%s,%s,%s,%s,%s,NOW()) ON DUPLICATE KEY UPDATE reason=VALUES(reason)",
        (TODAY, signal_type, SENT, cur_p, f'v6.7 sv={SENT:+.1f}'))
    conn_s.commit(); conn_s.close()
except: pass

# ETF资金流落地
try:
    import pymysql
    sid = f"1.{FUND}" if FUND[0] in ('5','6','9') else f"0.{FUND}"
    r = requests.get('https://push2.eastmoney.com/api/qt/ulist.np/get',
        params={'fltt':2,'secids':sid,'fields':'f12,f14,f62,f66,f72,f78'},
        headers=PUSH2_HDR, timeout=10)
    diff = r.json().get('data',{}).get('diff',[])
    if diff:
        d = diff[0]
        conn_f = pymysql.connect(**DB); cur_f = conn_f.cursor()
        cur_f.execute("""INSERT INTO etf_fund_flow (trade_date,fund_code,main_force_net,retail_net,large_net,super_large_net,create_time)
            VALUES (%s,%s,%s,%s,%s,%s,NOW())
            ON DUPLICATE KEY UPDATE main_force_net=VALUES(main_force_net),retail_net=VALUES(retail_net),
            large_net=VALUES(large_net),super_large_net=VALUES(super_large_net)""",
            (TODAY, FUND, d.get('f62'), d.get('f66'), d.get('f72'), d.get('f78')))
        conn_f.commit(); conn_f.close()
except: pass

real_asset = cash + real_shares * cur_p
print(f'  真实: 现金{cash:.0f}元  资产{real_asset:.0f}元')
print()
