# 尾盘决策脚本 v5.3 — 14:30后运行
# python _afternoon_check.py
# 依赖: pymysql, requests

import requests, json, sys, socket, os, datetime, math
sys.stdout.reconfigure(encoding='utf-8')
import requests.packages.urllib3.util.connection as urllib3_cn
urllib3_cn.allowed_gai_family = lambda: socket.AF_INET

HDR = {'User-Agent': 'Mozilla/5.0'}
EM_HDR = {**HDR, 'Referer': 'https://data.eastmoney.com/'}
PUSH2_HDR = {**HDR, 'Referer': 'https://quote.eastmoney.com/', 'Origin': 'https://quote.eastmoney.com'}
UT = 'fa5fd1943c7b386f172d6893dbbd1d0c'
FUND = '563300'; FUND_NAME = '中证2000ETF'
SECONDARY_FUNDS = [('588090', '科创50ETF华泰柏瑞')]
def get_held_fund():
    try:
        import pymysql
        conn = pymysql.connect(host='localhost',port=3306,user='root',password='root123',database='data_analysis',charset='utf8mb4')
        cur = conn.cursor()
        cur.execute("SELECT fund_code,fund_name FROM position GROUP BY fund_code HAVING SUM(CASE WHEN trade_type='buy' THEN shares ELSE -shares END) > 0")
        r = cur.fetchone()
        conn.close()
        if r: return r[0], r[1]
    except: pass
    return FUND, FUND_NAME
FUND, FUND_NAME = get_held_fund()
CAPITAL = 20000.0; MAX_PER_TRADE = 10000.0

TODAY = datetime.date.today().isoformat()

def get_pos_from_db():
    try:
        import pymysql
        conn = pymysql.connect(host='localhost',port=3306,user='root',password='root123',database='data_analysis',charset='utf8mb4')
        cur = conn.cursor()
        cur.execute("SELECT fund_code,fund_name,SUM(CASE WHEN trade_type='buy' THEN shares ELSE -shares END) shares_hold FROM position GROUP BY fund_code")
        r = cur.fetchone()
        if r and r[2] > 0:
            cur.execute("SELECT price FROM position WHERE fund_code=%s AND trade_type='buy' ORDER BY id DESC LIMIT 1", (r[0],))
            entry = cur.fetchone()[0]
            cur.execute("SELECT cash_after FROM position ORDER BY id DESC LIMIT 1")
            cash = float(cur.fetchone()[0])
            conn.close()
            return float(r[2]), float(entry), cash
        conn.close()
    except: pass
    return 0, 0, CAPITAL

def get_cost_from_db(fund_code):
    try:
        import pymysql
        conn = pymysql.connect(host='localhost',port=3306,user='root',password='root123',database='data_analysis',charset='utf8mb4')
        cur = conn.cursor()
        cur.execute("SELECT price FROM position WHERE fund_code=%s AND trade_type='buy' ORDER BY id DESC LIMIT 1", (fund_code,))
        r = cur.fetchone()
        conn.close()
        if r: return float(r[0])
    except: pass
    return 0

shares, entry, cash = get_pos_from_db()
if cash < 100: cash = CAPITAL

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

idx_cur = float(idx[3]) if len(idx) > 3 else 0
idx_pre = float(idx[4]) if len(idx) > 4 else 0
idx_pct = (idx_cur - idx_pre) / idx_pre * 100 if idx_pre else 0

# 2. 情绪估算 (基于历史校准: SH涨跌幅→情绪值)
# 使用DB中历史数据校准
def get_sent_calibration():
    try:
        import pymysql
        conn = pymysql.connect(host='localhost',port=3306,user='root',password='root123',database='data_analysis',charset='utf8mb4')
        cur = conn.cursor()
        cur.execute("SELECT index_change,sentiment_value FROM market_sentiment WHERE index_change IS NOT NULL AND index_change!='None' AND index_change!='' ORDER BY trade_date DESC LIMIT 20")
        rows = cur.fetchall()
        conn.close()
        if len(rows) >= 5:
            x = []; y = []
            for r in rows:
                try: x.append(float(str(r[0]).replace('%',''))); y.append(float(r[1]))
                except: pass
            if len(x) >= 5:
                n = len(x); mx = sum(x)/n; my = sum(y)/n
                b = sum((x[i]-mx)*(y[i]-my) for i in range(n)) / sum((x[i]-mx)**2 for i in range(n))
                a = my - b * mx
                return a, b
    except: pass
    return 0.1, 0.6  # 默认 fallback: sv = 0.1 + 0.6 * sh_pct

a, b = get_sent_calibration()
SENT = round(a + b * idx_pct, 1)

def zone(sv):
    if sv <= -2.0: return '冰点'
    if sv <= -1.0: return '过冷'
    if sv <= -0.1: return '微冷'
    if sv < 0.1: return '0分界'
    if sv <= 0.9: return '微热'
    if sv <= 1.9: return '过热'
    return '沸点'

ZONE = zone(SENT)

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
    """同花顺北向资金实时分钟流向"""
    url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
    try:
        r = requests.get(url, headers=HDR, timeout=10)
        d = r.json()
        hgt_list = d.get("hgt", []); sgt_list = d.get("sgt", [])
        hgt_v = [v for v in hgt_list if v is not None]
        sgt_v = [v for v in sgt_list if v is not None]
        return (hgt_v[-1], sgt_v[-1]) if hgt_v and sgt_v else (None, None)
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

# 3. 最近市场量价 (从DB取最新)
tv, lu, ld = 0, 0, 0
try:
    import pymysql
    conn = pymysql.connect(host='localhost',port=3306,user='root',password='root123',database='data_analysis',charset='utf8mb4')
    cur = conn.cursor()
    cur.execute("SELECT turnover, limit_up, limit_down FROM market_daily_stats ORDER BY trade_date DESC LIMIT 1")
    r = cur.fetchone()
    if r: tv, lu, ld = float(r[0] or 0), int(r[1] or 0), int(r[2] or 0)
    conn.close()
except: pass

# 4. 判断信号
fund_flow_pos = False
if fund_flow and len(fund_flow) >= 5:
    recent = fund_flow[-5:]  # 尾盘最近5分钟
    avg_main = sum(r["main_net"] for r in recent) / 5
    fund_flow_pos = avg_main > 0  # 尾盘5分钟主力平均净流入为正

buy_cond1 = SENT <= -0.8
buy_cond2 = pct <= -1.0
buy_cond3 = ld > lu or tv >= 25000
buy_cond4 = fund_flow_pos if fund_flow else True  # 无资金流数据时不阻塞信号
buy_signal = buy_cond1 and buy_cond2 and buy_cond3 and buy_cond4

sell_stop = pct <= -3.0 and shares > 0
sell_sent = SENT >= 1.0 and shares > 0
pnl = (cur_p - entry) / entry * 100 if entry and shares > 0 else 0
sell_tp = pnl >= 2.0 and shares > 0

# 5. 输出
print(f'\n{"="*55}')
print(f'  尾盘决策 v5.3')
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
print(f'  估算情绪: {SENT:+.1f}({ZONE})')
print(f'  成交额: {tv:.0f}亿  涨停{lu}  跌停{ld}')
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
print(f'  持仓: {shares:.0f}股 @ {entry:.4f}', end='')
if shares>0: print(f'  浮盈: {pnl:+.2f}%', end='')
print()

print(f'\n  ── 条件检查 ──')
print(f'  ① 情绪≤-0.8: {"✅" if buy_cond1 else "❌"} ({SENT:+.1f})')
print(f'  ② ETF跌≥1%:  {"✅" if buy_cond2 else "❌"} ({pct:+.2f}%)')
tv_ok = tv >= 25000; ld_ok = ld > lu
tv_label = f'成交{tv:.0f}亿≥25000' if tv_ok else f'成交{tv:.0f}亿<25000'
ld_label = f'跌停{ld}>涨停{lu}' if ld_ok else f'跌停{ld}≤涨停{lu}'
print(f'  ③ 放量/跌停:  {"✅" if buy_cond3 else "❌"} ({tv_label} {"或" if tv_ok or ld_ok else "且"} {ld_label})')
if fund_flow:
    flow_label = f'尾盘5分钟主力{"流入" if fund_flow_pos else "流出"}'
    print(f'  ④ 主力流入:  {"✅" if buy_cond4 else "❌"} ({flow_label})')

print(f'\n  ═══ 操作建议 ═══')
if shares > 0:
    if sell_stop:
        print(f'  ❗ 止损! 日跌{pct:+.1f}%≤-3%')
        print(f'  → 清仓 {shares:.0f}股 × {cur_p:.4f}')
    elif sell_sent:
        print(f'  ❗ 情绪过热({SENT:+.1f})，清仓')
        print(f'  → 卖出 {shares:.0f}股 × {cur_p:.4f}')
    elif sell_tp:
        half = math.floor(shares / 2 / 100) * 100
        print(f'  ✅ 止盈! 浮盈{pnl:+.1f}%')
        print(f'  → 卖一半 {half}股 ({half*cur_p:.0f}元)')
    else:
        print(f'  🔄 持仓不动')
elif buy_signal:
    amt = min(MAX_PER_TRADE, cash)
    bs = int(amt / cur_p / 100) * 100
    print(f'  ✅ 买入! {bs}股 × {cur_p:.4f} = {bs*cur_p:.0f}元')
    print(f'    理由: {ZONE}恐慌 + 跌{pct:.1f}% + 放量/跌停确认{" + 主力抄底" if fund_flow_pos else ""}')
else:
    reasons = []
    if not buy_cond1: reasons.append(f'情绪不够低({SENT:+.1f}>-0.8)')
    if not buy_cond2: reasons.append(f'跌幅不够({pct:+.1f}%>-1%)')
    if not buy_cond3: reasons.append(f'量价条件不满足')
    if fund_flow and not buy_cond4: reasons.append(f'主力未抄底')
    if SENT >= 1.0: reasons.append(f'情绪过热{int(SENT)}持币观望')
    print(f'  ⏳ 空仓等待 — {"; ".join(reasons)}')

print(f'  ────────────────')
print(f'  现金: {cash:.0f}元  总资产: {cash+shares*cur_p:.0f}元')
print(f'  仓位: {shares*cur_p/(cash+shares*cur_p)*100:.0f}%')
print()
