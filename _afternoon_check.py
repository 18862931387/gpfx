# 尾盘决策脚本 v5.3 — 14:30后运行
# python _afternoon_check.py
# 依赖: pymysql, requests

import requests, json, sys, socket, os, datetime, math
sys.stdout.reconfigure(encoding='utf-8')
import requests.packages.urllib3.util.connection as urllib3_cn
urllib3_cn.allowed_gai_family = lambda: socket.AF_INET

HDR = {'User-Agent': 'Mozilla/5.0'}
EM_HDR = {**HDR, 'Referer': 'https://data.eastmoney.com/'}
UT = 'fa5fd1943c7b386f172d6893dbbd1d0c'
FUND = '563300'; FUND_NAME = '中证2000ETF'
CAPITAL = 20000.0; MAX_PER_TRADE = 10000.0

TODAY = datetime.date.today().isoformat()
DIR = os.path.dirname(os.path.abspath(__file__))
POS_FILE = os.path.join(DIR, '_position.txt')

def read_pos():
    try:
        with open(POS_FILE) as f:
            parts = f.read().strip().split(',')
            return float(parts[0]), float(parts[1]), float(parts[2])
    except: return 0, 0, CAPITAL

def save_pos(shares, entry, cash):
    with open(POS_FILE, 'w') as f:
        f.write(f'{shares},{entry},{cash}')

shares, entry, cash = read_pos()
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
buy_cond1 = SENT <= -0.8
buy_cond2 = pct <= -1.0
buy_cond3 = ld > lu or tv >= 25000
buy_signal = buy_cond1 and buy_cond2 and buy_cond3

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
print(f'  上证指数: {idx_cur:.0f}  ({idx_pct:+.2f}%)')
print(f'  估算情绪: {SENT:+.1f}({ZONE})')
print(f'  成交额: {tv:.0f}亿  涨停{lu}  跌停{ld}')
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
    print(f'    理由: {ZONE}恐慌 + 跌{pct:.1f}% + 放量/跌停确认')
else:
    reasons = []
    if not buy_cond1: reasons.append(f'情绪不够低({SENT:+.1f}>-0.8)')
    if not buy_cond2: reasons.append(f'跌幅不够({pct:+.1f}%>-1%)')
    if not buy_cond3: reasons.append(f'量价条件不满足')
    if SENT >= 1.0: reasons.append(f'情绪过热{int(SENT)}持币观望')
    print(f'  ⏳ 空仓等待 — {"; ".join(reasons)}')

print(f'  ────────────────')
print(f'  现金: {cash:.0f}元  总资产: {cash+shares*cur_p:.0f}元')
print(f'  仓位: {shares*cur_p/(cash+shares*cur_p)*100:.0f}%')
print()
