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
PUSH2_HDR = {**HDR, 'Referer': 'https://quote.eastmoney.com/', 'Origin': 'https://quote.eastmoney.com'}
UT = 'fa5fd1943c7b386f172d6893dbbd1d0c'
FUND = PRIMARY_FUND; FUND_NAME = PRIMARY_FUND_NAME
SECONDARY_FUNDS = [('588090', '科创50ETF华泰柏瑞')]
def get_held_fund():
    try:
        import pymysql
        conn = pymysql.connect(**DB)
        cur = conn.cursor()
        cur.execute("SELECT fund_code,fund_name FROM position GROUP BY fund_code HAVING SUM(CASE WHEN trade_type='buy' THEN shares ELSE -shares END) > 0")
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
        cur.execute("SELECT fund_code,fund_name,SUM(CASE WHEN trade_type='buy' THEN shares ELSE -shares END) FROM position WHERE fund_code IS NOT NULL " + note_cond + " GROUP BY fund_code")
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

idx_cur = float(idx[3]) if len(idx) > 3 else 0
idx_pre = float(idx[4]) if len(idx) > 4 else 0
idx_pct = (idx_cur - idx_pre) / idx_pre * 100 if idx_pre else 0

# 2. 最近市场量价 — 三级策略: DB今日 > push2实时 > DB昨日兜底
tv, lu, ld, db_today = 0, 0, 0, False
margin_chg = 0.0  # 融资余额5日变化率
try:
    import pymysql
    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    cur.execute("SELECT trade_date, turnover, limit_up, limit_down FROM market_daily_stats ORDER BY trade_date DESC LIMIT 1")
    r = cur.fetchone()
    if r:
        db_today = str(r[0]) == TODAY
        if db_today:
            tv, lu, ld = float(r[1] or 0), int(r[2] or 0), int(r[3] or 0)
        else:
            # 今日无DB → 实时抓push2
            print(f'  🔄 DB无今日数据，实时抓取push2...', end='')
            try:
                clist_h = {**HDR, 'Referer': 'https://quote.eastmoney.com/'}
                p = {'pn':1,'pz':5000,'po':1,'np':1,'ut':UT,'fltt':2,'invt':2,'fid':'f3',
                     'fs':'m:0+t:6,m:0+t:13,m:1+t:2,m:1+t:23','fields':'f3'}
                r2 = requests.get('https://push2.eastmoney.com/api/qt/clist/get', params=p, headers=clist_h, timeout=15)
                items = r2.json().get('data',{}).get('diff',[])
                lu = sum(1 for i in items if i.get('f3') and float(i['f3']) >= 9.9)
                ld = sum(1 for i in items if i.get('f3') and float(i['f3']) <= -9.9)
                # 成交额: 上证+深证
                tv = 0.0
                for sid in ('1.000001','0.399001'):
                    try:
                        r3 = requests.get('https://push2.eastmoney.com/api/qt/stock/get',
                            params={'secid':sid,'fields':'f48'}, headers=clist_h, timeout=10)
                        tv += (r3.json().get('data',{}).get('f48') or 0)
                    except: pass
                tv = round(tv/1e8, 2) if tv else None
                print(f' 涨停{lu} 跌停{ld} 成交{tv}亿')
            except Exception as e:
                # push2失败 → 用昨日DB兜底
                tv, lu, ld = float(r[1] or 0), int(r[2] or 0), int(r[3] or 0)
                print(f' push2异常({e}), 用DB最近交易日({r[0]})兜底')
    # 融资余额: 取最近两条，计算5日变化率
    cur.execute("SELECT trade_date, margin_balance FROM sentiment_raw_factors WHERE margin_balance IS NOT NULL ORDER BY trade_date DESC LIMIT 10")
    margins = [(str(r[0]), float(r[1])) for r in cur.fetchall()]
    if len(margins) >= 5:
        latest = margins[0][1]
        t5 = margins[-1][1] if len(margins) > 5 else margins[min(4, len(margins)-1)][1]
        if t5 > 0: margin_chg = (latest - t5) / t5 * 100  # 5日变化率%
    conn.close()
except: pass

# 3. 大盘主力净流入 (push2实时)
main_force_net = 0.0
try:
    r = requests.get('https://push2.eastmoney.com/api/qt/ulist.np/get',
        params={'fltt':2,'secids':'1.000001,0.399001','fields':'f62'},
        headers=PUSH2_HDR, timeout=10)
    diff = r.json().get('data',{}).get('diff',[])
    if diff: main_force_net = sum(d['f62'] for d in diff)
except: pass

# 3b. 北向资金净流入 (akshare 实时)
northbound_net = 0.0
try:
    import akshare as ak
    hsgt = ak.stock_hsgt_fund_flow_summary_em()
    if len(hsgt) > 0:
        type_col = hsgt.columns[2]  # 类型: 陆股通/港股通
        net_col = hsgt.columns[5]   # 当日成交净买额
        nb_mask = hsgt[type_col].astype(str).str.contains('陆股', na=False)
        nb_vals = hsgt.loc[nb_mask, net_col].dropna()
        if len(nb_vals) > 0: northbound_net = float(nb_vals.sum())
except: pass

# 4. 全市场复合指数 (上证×0.4 + 深证×0.3 + 创业板×0.2 + 科创50×0.1)
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
zz_pct = get_rt_market('sh000852')  # 中证2000

# 复合指数兜底: 实时API失败时从 index_daily 读取最近一条
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

# 5. 情绪估算 (复合指数回归 + 多因子修正)
def calc_sentiment(composite, limit_up, limit_down, turnover, mf_net, margin_chg, northbound_net, news_score, data_is_today):
    # 基础分: 复合指数回归
    # sentiment = 0.3461 + 0.8168 * composite  # 48条旧标定 (回测更优, 手动切换)
    # sentiment = -0.1309 + 1.0622 * composite  # auto-calibrated on 2026-06-01
    val = 0.3461 + 0.8168 * composite

    # 以下修正仅当量价数据为今日实时数据时才启用
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

    # 资金流修正 (实时)
    if mf_net:
        flow = mf_net / 5e11
        if (flow > 0 and val > 0) or (flow < 0 and val < 0):
            val += flow
        else:
            val += flow * 0.5

    # 融资余额5日变化率修正
    if margin_chg:
        if margin_chg > 1.5:
            val += 0.2  # 加杠杆加速 → 情绪升温
        elif margin_chg > 0.5:
            val += 0.1
        elif margin_chg < -1.5:
            val -= 0.3  # 急剧去杠杆 → 恐慌
        elif margin_chg < -0.5:
            val -= 0.1

    # 北向资金修正 (实时累计)
    if northbound_net:
        if northbound_net > 80:
            val += 0.4  # 外资大幅涌入
        elif northbound_net > 40:
            val += 0.2
        elif northbound_net < -60:
            val -= 0.4  # 外资大幅出逃
        elif northbound_net < -20:
            val -= 0.2

    # 新闻情绪修正 (keyword scored, -2~+2 → ±0.6)
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

# 新闻情绪分 (从 market_news 读取)
news_score = read_sentiment_from_db()

SENT, ZONE = calc_sentiment(composite, lu, ld, tv, main_force_net, margin_chg, northbound_net, news_score, db_today)

# ===== a-stock-data 集成模块 =====

def eastmoney_fund_flow_minute(code):
    """东财 push2 个股资金流向（分钟级，当日盘中）"""
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
    """同花顺北向资金实时分钟流向（返回今日净流入，去除非零起点偏移）"""
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
    """东财行业板块涨跌幅排名（按涨幅降序）"""
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

# 4b. 20日均线 (优先读 etf_kline 缓存, 缓存不足走API)
ma20_val = None
try:
    import pymysql
    conn_tmp = pymysql.connect(**DB)
    cur_tmp = conn_tmp.cursor()
    cur_tmp.execute("SELECT close FROM etf_kline WHERE fund_code='563300' AND is_adj=1 ORDER BY trade_date DESC LIMIT 20")
    rows = cur_tmp.fetchall()
    conn_tmp.close()
    if len(rows) >= 20:
        ma20_val = sum(float(r[0]) for r in rows) / 20
except: pass

if ma20_val is None:
    try:
        r = requests.get('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',
            params={'param':'sh563300,day,,,120,qfq'}, headers=HDR, timeout=10)
        data = r.json()['data']['sh563300']
        klines = data.get('qfqday', data.get('day', []))
        closes = [float(k[2]) for k in klines if len(k) >= 5]
        if len(closes) >= 20:
            ma20_val = sum(closes[-20:]) / 20
    except: pass
above_ma20 = ma20_val and cur_p > ma20_val

# 5. 判断信号
fund_flow_pos = False
if fund_flow and len(fund_flow) >= 5:
    recent = fund_flow[-5:]  # 尾盘最近5分钟
    avg_main = sum(r["main_net"] for r in recent) / 5
    fund_flow_pos = avg_main > 0  # 尾盘5分钟主力平均净流入为正

buy_cond1 = SENT <= P["buyA_sv_max"]
buy_cond2 = pct <= P["buyA_dc_min"]
buy_cond3 = ld > lu or tv >= 25000
buy_cond4 = fund_flow_pos if fund_flow else True  # 无资金流数据时不阻塞信号
buy_signal = buy_cond1 and buy_cond2 and buy_cond3 and buy_cond4

sell_stop = pct <= P["stop_loss_pct"] and shares > 0
sell_sent = SENT >= P["sell_all_sv"] and shares > 0
sell_half = P["sell_half_sv"] and SENT >= P["sell_half_sv"] and SENT < P["sell_all_sv"] and shares > 0
pnl = (cur_p - entry) / entry * 100 if entry and shares > 0 else 0
sell_tp = P["take_profit_pct"] and pnl >= P["take_profit_pct"] and shares > 0
has_buyB = P["buyB"] and P["buyB"]["sv_min"] <= SENT <= P["buyB"]["sv_max"]

# 5. 输出
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
print(f'  成交额: {tv:.0f}亿  涨停{lu}  跌停{ld}')
if margin_chg: print(f'  融资余额5日变化: {margin_chg:+.2f}%')
if northbound_net: print(f'  北向资金: {northbound_net:+.1f}亿')
if news_score: print(f'  新闻情绪: {news_score:+.2f} (-2恐慌~+2亢奋)')
if fund_flow:
    last_f = fund_flow[-1]
    total_main = sum(r["main_net"] for r in fund_flow)
    flow_signal = '流入' if last_f['main_net'] > 0 else '流出'
    print(f'  主力资金: 尾盘{last_f["main_net"]/1e4:.0f}万{flow_signal} (全天{total_main/1e4:.0f}万)')
if hgt_val is not None:
    print(f'  北向资金: 沪+{hgt_val:.1f}亿  深+{sgt_val:.1f}亿')
if ind_top:
    top_str = '  '.join([f'{r["name"]}{r["change"]:+.1f}%' for r in ind_top[:3]])
    bot_str = '  '.join([f'{r["name"]}{r["change"]:+.1f}%' for r in ind_bot[:3]])
    print(f'  领涨板块: {top_str}')
    print(f'  领跌板块: {bot_str}')
print(f'  ├ 真实持仓: {real_shares:.0f}股 @ {real_entry:.4f}', end='')
if real_shares>0:
    real_pnl = (cur_p - real_entry) / real_entry * 100 if real_entry else 0
    print(f'  浮盈: {real_pnl:+.2f}%', end='')
print()
if sys_shares>0:
    sys_pnl = (cur_p - sys_entry) / sys_entry * 100 if sys_entry else 0
    print(f'  └ 系统持仓: {sys_shares:.0f}股 @ {sys_entry:.4f}  浮盈: {sys_pnl:+.2f}%')

print(f'\n  ── 条件检查 ({VER["ver"]}) ──')
print(f'  ① 情绪≤{P["buyA_sv_max"]}: {"✅" if buy_cond1 else "❌"} ({SENT:+.1f})')
print(f'  ② ETF跌≥{P["buyA_dc_min"]}%: {"✅" if buy_cond2 else "❌"} ({pct:+.2f}%)')
tv_ok = tv >= 25000; ld_ok = ld > lu
tv_label = f'成交{tv:.0f}亿≥25000' if tv_ok else f'成交{tv:.0f}亿<25000'
ld_label = f'跌停{ld}>涨停{lu}' if ld_ok else f'跌停{ld}≤涨停{lu}'
print(f'  ③ 放量/跌停:  {"✅" if buy_cond3 else "❌"} ({tv_label} {"或" if tv_ok or ld_ok else "且"} {ld_label})')
if fund_flow:
    flow_label = f'尾盘5分钟主力{"流入" if fund_flow_pos else "流出"}'
    print(f'  ④ 主力流入:  {"✅" if buy_cond4 else "❌"} ({flow_label})')

print(f'\n  ═══ 操作建议 ═══')
buyB_signal = has_buyB and above_ma20 and shares == 0 and cash >= 100

if shares > 0:
    if sell_stop:
        print(f'  ❗ 止损! 日跌{pct:+.1f}%≤{P["stop_loss_pct"]}%')
        print(f'  → 清仓 {shares:.0f}股 × {cur_p:.4f}')
    elif sell_sent:
        print(f'  ❗ 情绪过热({SENT:+.1f}≥{P["sell_all_sv"]})，清仓')
        print(f'  → 卖出 {shares:.0f}股 × {cur_p:.4f}')
    elif sell_half:
        half = math.floor(shares / 2 / 100) * 100
        print(f'  ⚠️ 情绪偏高({SENT:+.1f}≥{P["sell_half_sv"]})，卖一半')
        print(f'  → 卖一半 {half}股 ({half*cur_p:.0f}元)')
    elif sell_tp:
        half = math.floor(shares / 2 / 100) * 100
        print(f'  ✅ 止盈! 浮盈{pnl:+.1f}%')
        print(f'  → 卖一半 {half}股 ({half*cur_p:.0f}元)')
    else:
        print(f'  🔄 持仓不动')
elif buy_signal:
    amt = min(MAX_PER_TRADE, cash)
    bs = int(amt / cur_p / 100) * 100
    print(f'  ✅ 买A抄底! {bs}股 × {cur_p:.4f} = {bs*cur_p:.0f}元')
    print(f'    理由: {ZONE}恐慌 + 跌{pct:.1f}% + 放量/跌停确认{" + 主力抄底" if fund_flow_pos else ""}')
elif buyB_signal:
    amt = min(MAX_PER_TRADE * P["buyB"]["position"], cash)
    bs = int(amt / cur_p / 100) * 100
    pf = '全' if P["buyB"]["position"] >= 1 else f'{P["buyB"]["position"]*100:.0f}%'
    print(f'  📈 买B趋势({pf}仓)! {bs}股 × {cur_p:.4f} = {bs*cur_p:.0f}元')
    print(f'    理由: 情绪{SENT:+.1f}中性 + 价{cur_p:.4f}>20MA{ma20_val:.4f}')
else:
    reasons = []
    if not buy_cond1: reasons.append(f'情绪不够低({SENT:+.1f}>{P["buyA_sv_max"]})')
    if not buy_cond2: reasons.append(f'跌幅不够({pct:+.1f}%>{P["buyA_dc_min"]}%)')
    if not buy_cond3: reasons.append(f'量价条件不满足')
    if fund_flow and not buy_cond4: reasons.append(f'主力未抄底')
    if has_buyB and not above_ma20:
        print(f'  📈 趋势信号: 情绪{SENT:+.1f}在买B范围，但价{cur_p:.4f}<20MA{ma20_val:.4f}，等待站上')
    elif has_buyB:
        print(f'  📈 趋势信号: 情绪{SENT:+.1f}在买B范围+价在20MA上，但现金不足(需≥100)')
    print(f'  ⏳ 空仓等待 — {"; ".join(reasons)}')

print(f'  ────────────────')
real_asset = cash + real_shares * cur_p
sys_asset = SYSTEM_BASE_CASH + sys_shares * cur_p  # system base cash
print(f'  ────────────────')
print(f'  真实: 现金{cash:.0f}元  资产{real_asset:.0f}元  仓位{real_shares*cur_p/real_asset*100:.0f}%')
if sys_shares>0:
    print(f'  系统: 现金{SYSTEM_BASE_CASH:.0f}元  资产{sys_asset:.0f}元  仓位{sys_shares*cur_p/sys_asset*100:.0f}%')
print()
