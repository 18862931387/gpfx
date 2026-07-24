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