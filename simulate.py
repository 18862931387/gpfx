import sys, pymysql, requests, socket, datetime
sys.stdout.reconfigure(encoding='utf-8')
import requests.packages.urllib3.util.connection as urllib3_cn
urllib3_cn.allowed_gai_family = lambda: socket.AF_INET
sys.path.insert(0, __import__('os').path.dirname(__file__))
from config import DB, CAPITAL, TENCENT_KLINE, HDR, PRIMARY_FUND
from strategy_config import get_latest, VERSIONS
from logger import get_logger

log = get_logger('simulate')

VER = get_latest()
P = VER["params"]
VER_IDX = VERSIONS.index(VER) + 1

# ── 情绪字段选择 ──
USE_V5 = '--v5' in sys.argv or '-5' in sys.argv
SENT_FIELD = 'sentiment_v5' if USE_V5 else 'sentiment_value'
SENT_LABEL = 'v5算法' if USE_V5 else '旧算法'

# ── DB: 读情绪历史 ──
try:
    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    cur.execute(f"SELECT trade_date, {SENT_FIELD} FROM market_sentiment WHERE {SENT_FIELD} IS NOT NULL ORDER BY trade_date")
    db_sent = {str(r[0]): float(r[1]) for r in cur.fetchall()}
    log.info(f'读取情绪数据 {SENT_LABEL} {len(db_sent)} 条')
except Exception as e:
    log.error(f'DB连接失败: {e}')
    db_sent = {}

# ── K线: 优先读本地缓存 etf_kline ──
klines = []
try:
    cur.execute("SELECT trade_date,open,high,low,close,volume FROM etf_kline WHERE fund_code=%s AND is_adj=1 ORDER BY trade_date", (PRIMARY_FUND,))
    rows = cur.fetchall()
    if rows and len(rows) >= 30:
        klines = [[r[0].strftime('%Y-%m-%d'), str(r[1]), str(r[4]), str(r[3]), str(r[4]), str(r[5] or 0) if r[5] else None] for r in rows]
        log.info(f'K线从 etf_kline 缓存读取 {len(klines)} 条')
except Exception as e:
    log.warning(f'etf_kline 读取失败: {e}')

# 缓存不足时走API
if len(klines) < 30:
    try:
        r = requests.get(TENCENT_KLINE,
            params={'param': f'sh{PRIMARY_FUND},day,,,120,qfq'}, headers=HDR, timeout=10)
        data = r.json().get('data', {}).get(f'sh{PRIMARY_FUND}', {})
        klines = data.get('qfqday', data.get('day', []))
        log.info(f'K线从 API 获取 {len(klines)} 条')
    except Exception as e:
        log.error(f'K线API失败: {e}')

pv = {k[0]: float(k[2]) for k in klines if len(k) >= 5}
log.info(f'K线数据 {len(pv)} 条')

# ── 融资余额数据 (v5.8 margin_boost用) ──
margin_chg_5d = {}
if P.get("buyA_margin_boost"):
    try:
        cur.execute("SELECT trade_date,margin_balance FROM sentiment_raw_factors WHERE margin_balance IS NOT NULL ORDER BY trade_date")
        margins = [(str(r[0]), float(r[1])) for r in cur.fetchall()]
        for i in range(5, len(margins)):
            chg = (margins[i][1] - margins[i-5][1]) / margins[i-5][1] * 100
            margin_chg_5d[margins[i][0]] = chg
        log.info(f'融资余额数据 {len(margin_chg_5d)} 条')
    except Exception as e:
        log.warning(f'融资余额读取失败: {e}')

MAX_INVEST = P["max_invest"]

def ma20(dates, idx):
    if idx < 20: return None
    seg = dates[idx-20:idx]
    vals = [pv[d] for d in seg if d in pv]
    return sum(vals)/len(vals) if len(vals) >= 15 else None

def ma60(dates, idx):
    if idx < 60: return None
    seg = dates[idx-60:idx]
    vals = [pv[d] for d in seg if d in pv]
    return sum(vals)/len(vals) if len(vals) >= 45 else None

results = []

def run(label, start_date, end_date):
    dates = sorted(d for d in db_sent if start_date <= d <= end_date and d in pv)
    if len(dates) < 5:
        log.warning(f'{label}: 数据不足 ({len(dates)}天)，跳过')
        return 0, 0, 0

    cash = CAPITAL; shares = 0.0; invested = 0.0; prev = None
    peak = CAPITAL; mdd = 0.0; trades = 0; sold_half = False
    trail_hi = 0.0

    print(f'\n{"="*75}')
    print(f'  {VER["ver"]} {label} | {dates[0]}~{dates[-1]} ({len(dates)}天)')
    b = P["buyB"]
    if b:
        pos = b.get("position_max", b.get("position", 1.0))
        extras = []
        if b.get("sent_ma_days"): extras.append(f'SMA↗{b["sent_ma_days"]}d')
        if b.get("ma_deviation_max"): extras.append(f'乖离<{b["ma_deviation_max"]*100:.0f}%')
        extra_s = f' +{",".join(extras)}' if extras else ''
        b_desc = f'买B:情绪{b["sv_min"]}~{b["sv_max"]}&站上20日线{pos*100:.0f}%仓{extra_s}'
    else:
        b_desc = ''
        pos = 1.0
    print(f'  买A:情绪≤{P["buyA_sv_max"]}&跌≥{P["buyA_dc_min"]}% {b_desc}')
    print(f'  卖:≥{P["sell_all_sv"]}清仓', end='')
    if P["sell_half_sv"]: print(f'  {P["sell_half_sv"]}~{P["sell_all_sv"]}卖一半', end='')
    print(f' | 止损{P["stop_loss_pct"]}%', end='')
    if P["trailing_stop_pct"]: print(f' 回撤{P["trailing_stop_pct"]}%', end='')
    if P["take_profit_pct"]: print(f' 止盈+{P["take_profit_pct"]}%', end='')
    print()
    print(f'{"="*75}')
    print(f'{"日期":12} {"情绪":>5} {"净值":>7} {"日跌":>6} {"操作":<28} {"市值":>7} {"现金":>7} {"总资产":>7}')
    print('-' * 83)

    for i, d in enumerate(dates):
        sv = db_sent[d]; nav = pv[d]
        dc = (nav - prev) / prev * 100 if prev else 0; prev = nav
        pv2 = shares * nav; tot = cash + pv2
        pnl = (pv2 - invested) / invested * 100 if invested > 0 else 0
        act = ''
        m = ma20(dates, i)

        if shares > 0:
            trail_hi = max(trail_hi, nav)
            trail_pnl = (nav - trail_hi) / trail_hi * 100
            if sv >= P["sell_all_sv"]:
                cash += pv2; act = f'清仓(情绪{sv:+.1f}≥{P["sell_all_sv"]})'; shares = 0; invested = 0; trades += 1; trail_hi = 0
            elif P["sell_half_sv"] and sv >= P["sell_half_sv"] and not sold_half:
                half_v = pv2 * 0.5; cash += half_v; shares *= 0.5; invested *= 0.5
                act = f'卖一半(情绪{sv:+.1f}≥{P["sell_half_sv"]})'; trades += 1; sold_half = True
            elif P["trailing_stop_pct"] and trail_pnl <= P["trailing_stop_pct"]:
                cash += pv2; act = f'回撤止损(从峰值{trail_pnl:.1f}%)'; shares = 0; invested = 0; trades += 1; trail_hi = 0
            elif pnl <= P["stop_loss_pct"]:
                cash += pv2; act = f'止损({pnl:.1f}%)'; shares = 0; invested = 0; trades += 1; trail_hi = 0
            elif P["take_profit_pct"] and pnl >= P["take_profit_pct"] and not sold_half:
                half_v = pv2 * 0.5; cash += half_v; shares -= half_v / nav; invested *= 0.5
                act = f'止盈一半(+{pnl:.1f}%)'; trades += 1; sold_half = True

        if shares == 0 and cash > 0:
            amt = min(MAX_INVEST, cash)
            # v5.8 margin_boost: 融资去杠杆>1%时买A阈值从-1.2放宽到-1.0
            sv_a = P["buyA_sv_max"]
            margin_ok = P.get("buyA_margin_boost") and margin_chg_5d.get(d, 0) < -1.0
            if margin_ok:
                sv_a = -1.0
            if sv <= sv_a and dc <= P["buyA_dc_min"] and amt >= 100:
                shares = amt / nav; cash -= amt; invested = amt
                tag = f'融资去杠杆买A' if margin_ok else '买A抄底'
                act = f'{tag}(sv{sv:+.1f},跌{dc:.1f}%)'; trades += 1
            elif P["buyB"] and P["buyB"]["sv_min"] <= sv <= P["buyB"]["sv_max"] and m and nav > m and amt >= 100:
                b_conf = P["buyB"]
                # 动态仓位: 情绪越接近0仓位越大
                if "position_max" in b_conf:
                    sv_range = b_conf["sv_max"] - b_conf["sv_min"]
                    ratio = 1.0 - abs(sv) / (sv_range / 2) if sv_range > 0 else 0.5
                    pos = b_conf["position_min"] + (b_conf["position_max"] - b_conf["position_min"]) * ratio
                else:
                    pos = b_conf.get("position", 1.0)

                # 过滤1: 情绪动量 — 3日情绪均线上升 (v5.7+)
                sent_mom_ok = True
                if b_conf.get("sent_ma_days"):
                    sd = b_conf["sent_ma_days"]
                    sent_vals = [db_sent.get(dates[i - d], 0) for d in range(sd + 1) if (i - d) >= 0]
                    sent_avg = sum(sent_vals) / len(sent_vals)
                    sent_prev = sent_vals[1:] if len(sent_vals) > 1 else sent_vals  # exclude today
                    sent_prev_avg = sum(sent_prev) / len(sent_prev) if sent_prev else sent_avg
                    sent_mom_ok = sent_avg > sent_prev_avg  # sentiment recovering

                # 过滤2: 乖离率
                dev_ok = True
                if b_conf.get("ma_deviation_max"):
                    dev_ok = (nav - m) / m <= b_conf["ma_deviation_max"]

                if sent_mom_ok and dev_ok:
                    amt = amt * pos
                    shares = amt / nav; cash -= amt; invested = amt
                    pf = f'{pos*100:.0f}%'
                    extras = []
                    if b_conf.get("sent_ma_days"): extras.append(f'SMA↗{b_conf["sent_ma_days"]}d')
                    if b_conf.get("ma_deviation_max"): extras.append(f'乖离<{b_conf["ma_deviation_max"]*100:.0f}%')
                    act = f'买B趋势({pf}仓sv{sv:+.1f}{", "+",".join(extras) if extras else ""})'; trades += 1
                else:
                    blocks = []
                    if not sent_mom_ok: blocks.append('情绪均线未升')
                    if not dev_ok: blocks.append(f'乖离过大({(nav-m)/m*100:+.1f}%)')

        pv2 = shares * nav; tot = cash + pv2
        if tot > peak: peak = tot
        dd = (peak - tot) / peak * 100
        if dd > mdd: mdd = dd
        ps = f'{pv2:>7.0f}' if shares > 0 else f' 空仓 '
        a = act if act else ('持有' if shares > 0 else '观望')
        print(f'{d:12} {sv:>+5.1f} {nav:>7.4f} {dc:>+5.1f}% {a:<28} {ps:>7} {cash:>7.0f} {tot:>7.0f}')

    final = cash + shares * pv[dates[-1]]
    ret = (final / CAPITAL - 1) * 100
    print(f'  收益: {ret:+.2f}%  回撤: {mdd:.2f}%  交易: {trades}次')
    results.append((label, ret, mdd, trades))
    log.info(f'{VER["ver"]} {label}: 收益{ret:+.2f}% 回撤{mdd:.2f}% 交易{trades}次')
    return ret, mdd, trades

# ── 运行: 6个月回测 ──
r1, d1, t1 = run('全周期(6月)', '2025-12-01', '2026-06-01')
r2, d2, t2 = run('12月', '2025-12-01', '2025-12-31')
r3, d3, t3 = run('1月', '2026-01-01', '2026-01-31')
r4, d4, t4 = run('2月', '2026-02-01', '2026-02-28')
r5, d5, t5 = run('3月', '2026-03-01', '2026-03-31')
r6, d6, t6 = run('4月', '2026-04-01', '2026-04-30')
r7, d7, t7 = run('5月', '2026-05-01', '2026-05-31')

# ── 写入回测结果表 ──
if 'conn' in dir() and results:
    try:
        create_sql = """CREATE TABLE IF NOT EXISTS backtest_results (
            id INT AUTO_INCREMENT PRIMARY KEY,
            strategy_id INT NOT NULL, fund_code VARCHAR(10) NOT NULL,
            period_label VARCHAR(20), initial_capital DECIMAL(12,2),
            final_value DECIMAL(12,2), total_return DECIMAL(8,2),
            max_drawdown DECIMAL(8,2), trade_count INT,
            created_at DATETIME DEFAULT NOW(),
            UNIQUE KEY uk_sfp (strategy_id, fund_code, period_label)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
        cur.execute(create_sql)
        for label, ret, mdd, trades in results:
            final_val = CAPITAL * (1 + ret / 100)
            sql = """INSERT INTO backtest_results
                (strategy_id,fund_code,period_label,initial_capital,final_value,total_return,max_drawdown,trade_count,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                ON DUPLICATE KEY UPDATE total_return=VALUES(total_return),max_drawdown=VALUES(max_drawdown),
                trade_count=VALUES(trade_count),final_value=VALUES(final_value),created_at=NOW()"""
            cur.execute(sql, (VER_IDX, PRIMARY_FUND, label, CAPITAL, round(final_val,2), round(ret,2), round(mdd,2), trades))
        conn.commit()
        log.info(f'回测结果已写入 backtest_results ({len(results)}条)')
    except Exception as e:
        log.error(f'回测结果写入失败: {e}')
    finally:
        conn.close()
