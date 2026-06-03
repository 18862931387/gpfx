# 情绪自动标定流水线
# python sentiment_pipeline.py
#
# 功能：
#   1. 每日采集多因子原始数据写入 sentiment_raw_factors
#   2. 按周运行 K-means 聚类生成情绪标签
#   3. 线性回归校准系数
#   4. 更新 strategy_config.py
#
# 使用方式：
#   python sentiment_pipeline.py          # 采集今日数据
#   python sentiment_pipeline.py --calibrate  # 触发重标定

import sys, os, json, requests, datetime, math, socket, time
import requests.packages.urllib3.util.connection as urllib3_cn
urllib3_cn.allowed_gai_family = lambda: socket.AF_INET
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
import pymysql, pandas as pd
import akshare as ak
from config import DB, HDR, COMPOSITE_WT

DB_CONN = dict(host=DB['host'], port=DB['port'], user=DB['user'], password=DB['password'], database=DB['database'], charset=DB['charset'])
PUSH2_HDR = {**HDR, 'Referer': 'https://quote.eastmoney.com/', 'Origin': 'https://quote.eastmoney.com'}
TODAY = datetime.date.today().isoformat()

conn = pymysql.connect(**DB)
cur = conn.cursor()

# ── 建表 ──────────────────────────────────────────────
cur.execute("""CREATE TABLE IF NOT EXISTS sentiment_raw_factors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    trade_date DATE NOT NULL UNIQUE,
    composite_index DECIMAL(10,4) COMMENT '4指数加权涨跌幅',
    sector_up INT COMMENT '行业板块上涨数',
    sector_down INT COMMENT '行业板块下跌数',
    sector_ad_ratio DECIMAL(6,4) COMMENT '板块涨跌比',
    limit_up INT, limit_down INT,
    turnover DECIMAL(15,2) COMMENT '成交额(亿)',
    main_force_net DECIMAL(15,2) COMMENT '主力净流入(万)',
    volume_pctile_60d DECIMAL(5,2) COMMENT '60日成交量百分位',
    margin_balance DECIMAL(20,2) COMMENT '融资融券余额(亿)',
    northbound_net DECIMAL(15,2) COMMENT '北向资金净流入(亿)',
    sentiment_label DECIMAL(5,2) COMMENT '聚类标签',
    create_time DATETIME DEFAULT NOW(), update_time DATETIME DEFAULT NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
conn.commit()
# 新增字段兼容
for col, typ in [('margin_balance','DECIMAL(20,2)'), ('northbound_net','DECIMAL(15,2)')]:
    try:
        cur.execute(f"ALTER TABLE sentiment_raw_factors ADD COLUMN {col} {typ}")
        conn.commit()
    except: pass

# ── 1. 采集今日多因子数据 ──────────────────────────────
def fetch_all():
    factors = {'trade_date': TODAY}

    # 4指数实时行情
    def get_idx_change(code):
        try:
            r = requests.get(f'https://web.sqt.gtimg.cn/q={code}', headers=HDR, timeout=10)
            p = r.text.replace('"','').split('~')
            return float(p[32]) if len(p) > 32 else 0
        except: return 0
    sh = get_idx_change('sh000001')
    sz = get_idx_change('sz399001')
    cy = get_idx_change('sz399006')
    zz = get_idx_change('sh000852')
    factors['composite_index'] = round(sh * 0.3 + sz * 0.2 + cy * 0.1 + zz * 0.4, 4)

    # 行业板块涨跌家数
    try:
        r = requests.get('https://push2.eastmoney.com/api/qt/clist/get',
            params={"pn":"1","pz":"200","po":"0","np":"1","fltt":"2","invt":"2",
                    "fs":"m:90+t:2","fields":"f2,f3,f4,f12,f14,f104,f105"},
            headers=PUSH2_HDR, timeout=10)
        items = r.json().get('data',{}).get('diff',[])
        sector_up = sum(1 for it in items if it.get('f3') and float(it['f3']) > 0)
        sector_down = sum(1 for it in items if it.get('f3') and float(it['f3']) < 0)
        factors['sector_up'] = sector_up
        factors['sector_down'] = sector_down
        factors['sector_ad_ratio'] = round(sector_up / max(sector_down, 1), 4)
    except: pass

    # 涨跌停/成交额 (优先akshare实时, 兜底DB)
    try:
        import akshare as ak
        today_key = TODAY.replace('-', '')
        zt_df = ak.stock_zt_pool_em(date=today_key)
        dt_df = ak.stock_zt_pool_dtgc_em(date=today_key)
        if len(zt_df) > 0: factors['limit_up'] = len(zt_df)
        if len(dt_df) > 0: factors['limit_down'] = len(dt_df)
    except: pass
    if 'limit_up' not in factors or 'limit_down' not in factors:
        try:
            cur.execute("SELECT turnover, limit_up, limit_down FROM market_daily_stats WHERE trade_date=%s", (TODAY,))
            r = cur.fetchone()
            if r:
                if 'limit_up' not in factors: factors['limit_up'] = int(r[1]) if r[1] else 0
                if 'limit_down' not in factors: factors['limit_down'] = int(r[2]) if r[2] else 0
                if 'turnover' not in factors: factors['turnover'] = float(r[0]) if r[0] else 0
        except: pass

    # 主力净流入 (push2实时, 带重试)
    for attempt in range(2):
        try:
            r = requests.get('https://push2.eastmoney.com/api/qt/ulist.np/get',
                params={'fltt':2,'secids':'1.000001,0.399001','fields':'f62'},
                headers=PUSH2_HDR, timeout=10)
            diff = r.json().get('data',{}).get('diff',[])
            if diff:
                factors['main_force_net'] = sum(d['f62'] for d in diff)
                break
        except:
            if attempt == 0: time.sleep(2)

    # 60日成交量百分位
    try:
        sql = """SELECT turnover FROM market_daily_stats
                 WHERE trade_date <= %s AND turnover IS NOT NULL
                 ORDER BY trade_date DESC LIMIT 60"""
        cur.execute(sql, (TODAY,))
        rows = [float(r[0]) for r in cur.fetchall() if r[0]]
        if len(rows) >= 20:
            today_tv = factors.get('turnover', rows[0])
            below = sum(1 for v in rows if v < today_tv)
            factors['volume_pctile_60d'] = round(below / len(rows) * 100, 2)
    except: pass

    # 融资融券余额 (akshare SSE+SZSE, 最近5天窗口容错)
    try:
        from datetime import timedelta
        d_start = (datetime.date.today() - timedelta(days=5)).strftime('%Y%m%d')
        sh_margin = ak.stock_margin_sse(start_date=d_start, end_date=TODAY.replace('-',''))
        sz_margin = ak.stock_margin_szse(date=TODAY.replace('-',''))  # 仅支持单日
        if len(sh_margin) > 0:
            sh_col = sh_margin.columns[-1]  # 融资融券余额
            date_col = sh_margin.columns[0]
            sh_row = sh_margin[sh_margin[date_col].astype(str) == TODAY.replace('-','')]
            if len(sh_row) == 0:
                sh_row = sh_margin.iloc[[-1]]
            sh_val = float(sh_row[sh_col].iloc[0]) / 1e8 if len(sh_row) > 0 else 0
            sz_val = float(sz_margin.iloc[0, 1]) / 1e8 if len(sz_margin) > 0 else 0
            if sh_val > 0:
                factors['margin_balance'] = round(sh_val + sz_val, 2)
    except: pass

    # 北向资金净流入 (akshare 沪深港通实时汇总)
    try:
        hsgt = ak.stock_hsgt_fund_flow_summary_em()
        if len(hsgt) > 0:
            type_col = hsgt.columns[2]  # 类型列
            net_col = hsgt.columns[5]   # 当日成交净买额
            # 筛选 陆股通(沪) + 陆股通(深) 行
            nb_mask = hsgt[type_col].astype(str).str.contains('陆股', na=False)
            nb_vals = hsgt.loc[nb_mask, net_col].dropna()
            if len(nb_vals) > 0 and nb_vals.abs().sum() > 0:
                factors['northbound_net'] = round(float(nb_vals.sum()), 2)
    except: pass

    return factors


factors = fetch_all()
print(f'[{TODAY}] 采集完成: 复合指数={factors.get("composite_index","-"):+}')

# 写入 DB
cols = ', '.join(factors.keys())
vals_ph = ', '.join(['%s'] * len(factors))
upd = ', '.join([f'{k}=VALUES({k})' for k in factors.keys() if k != 'trade_date'])
sql = f"INSERT INTO sentiment_raw_factors ({cols}) VALUES ({vals_ph}) ON DUPLICATE KEY UPDATE {upd}"
cur.execute(sql, list(factors.values()))
conn.commit()

# ── 2. 标定（--calibrate 或 数据量>=30时自动触发） ───────
def run_calibrate():
    cur.execute("SELECT trade_date, composite_index, sector_ad_ratio, volume_pctile_60d, main_force_net, "
                "margin_balance, northbound_net "
                "FROM sentiment_raw_factors WHERE composite_index IS NOT NULL "
                "ORDER BY trade_date")
    raw = cur.fetchall()
    if len(raw) < 20:
        print(f'  数据不足: {len(raw)}条 (需≥20)，跳过标定')
        return

    import numpy as np

    dates = [r[0] for r in raw]
    X_raw = np.array([[float(r[1] or 0), float(r[2] or 1), float(r[3] or 50), float(r[4] or 0),
                       float(r[5] or 0), float(r[6] or 0)] for r in raw])

    # 特征工程
    ad_ratio = np.clip(X_raw[:, 1], 0.01, 100)
    log_ad = np.log(ad_ratio)
    log_ad = (log_ad - np.mean(log_ad)) / np.std(log_ad) if np.std(log_ad) > 0 else log_ad
    vol_norm = (X_raw[:, 2] - 50) / 25
    flow_norm = X_raw[:, 3] / 5e11

    # margin: 5日变化率
    margin = np.array([r5 or 0 for r5 in X_raw[:, 4]])
    margin_chg = np.zeros_like(margin)
    for i in range(5, len(margin)):
        if margin[i-5] and margin[i-5] != 0:
            margin_chg[i] = (margin[i] - margin[i-5]) / abs(margin[i-5]) * 100
    margin_norm = margin_chg / max(np.std(margin_chg) * 3, 1)

    # northbound: 标准化
    nb = np.array([r6 or 0 for r6 in X_raw[:, 5]])
    nb_norm = nb / max(np.std(nb) * 3, 1.0)

    # 综合得分：等权组合 (含新因子)
    score = (X_raw[:, 0] * 0.35 + log_ad * 0.20 + vol_norm * 0.15 +
             flow_norm * 0.10 + margin_norm * 0.10 + nb_norm * 0.10)

    # 按综合得分分5组，每组映射到 -2 ~ +2
    order = np.argsort(score)
    n = len(order)
    groups = np.empty(n, dtype=int)
    for i, idx in enumerate(order):
        groups[idx] = int(i * 5 / n)  # 0~4
        if groups[idx] > 4: groups[idx] = 4
    mapping = {0: -2.0, 1: -1.0, 2: 0.0, 3: 1.0, 4: 2.0}
    labels = np.array([mapping[g] for g in groups])

    # 更新 DB
    for d, lbl in zip(dates, labels):
        cur.execute("UPDATE sentiment_raw_factors SET sentiment_label=%s WHERE trade_date=%s", (float(lbl), d))

    # 线性回归：sentiment = β₀ + β₁ × composite_index
    composites = X_raw[:, 0].reshape(-1, 1)
    # 手动最小二乘
    X_design = np.column_stack([np.ones(n), composites[:, 0]])
    beta = np.linalg.lstsq(X_design, labels, rcond=None)[0]
    b0, b1 = beta[0], beta[1]
    pred = X_design @ beta
    ss_res = np.sum((labels - pred) ** 2)
    ss_tot = np.sum((labels - np.mean(labels)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    print(f'\n{"="*50}')
    print(f'  情绪标定完成 ({len(raw)}条)')
    print(f'  sentiment = {b0:.4f} + {b1:.4f} × composite')
    print(f'  R² = {r2:.4f}')
    print(f'  簇映射: {dict(sorted(mapping.items()))}')
    print(f'{"="*50}\n')

    # 更新 strategy_config.py
    cfg_path = os.path.join(os.path.dirname(__file__), 'strategy_config.py')
    with open(cfg_path, 'r', encoding='utf-8') as f:
        old = f.read()

    # 找到当前最新版本，注入新系数
    marker = 'sentiment = '
    new_coeff = f'    sentiment = {b0:.4f} + {b1:.4f} * composite  # auto-calibrated on {TODAY}\n'
    # 替换 _afternoon_check.py 中的系数行
    check_path = os.path.join(os.path.dirname(__file__), '_afternoon_check.py')
    with open(check_path, 'r', encoding='utf-8') as f:
        check_old = f.read()
    import re
    check_new = check_old
    # 更新自动标定注释行 (替换已有 auto-calibrated 行)
    if 'auto-calibrated' in check_new:
        check_new = re.sub(
            r'# sentiment = .*auto-calibrated.*\n',
            f'# sentiment = {b0:.4f} + {b1:.4f} * composite  # auto-calibrated on {TODAY}\n',
            check_new
        )
    # 更新实际使用的 val = ... 行
    check_new = re.sub(
        r'^    val = [-+]?[\d.]+ \+ [-+]?[\d.]+ \* composite.*$',
        f'    val = {b0:.4f} + {b1:.4f} * composite  # auto-calibrated {TODAY}',
        check_new,
        flags=re.MULTILINE
    )
    with open(check_path, 'w', encoding='utf-8') as f:
        f.write(check_new)
    print(f'  _afternoon_check.py 已更新')

    conn.commit()


# ── 3. 自动触发 ──────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM sentiment_raw_factors WHERE sentiment_label IS NOT NULL")
calibrated = cur.fetchone()[0]

# ── 4. 历史回填 ──────────────────────────────────────
def backfill():
    """从baostock拉取120天指数数据（全天可用，不需交易时段），计算复合指数回填"""
    indices_map = {'sh.000001':(0.3,'sh000001'),'sz.399001':(0.2,'sz399001'),
                   'sz.399006':(0.1,'sz399006'),'sh.000852':(0.4,'sh000852')}
    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code != '0': raise Exception(lg.error_msg)
        all_data = {}
        for bs_code, (wt, orig_code) in indices_map.items():
            rs = bs.query_history_k_data_plus(bs_code,
                "date,close", start_date="2025-12-01", end_date=TODAY,
                frequency="d", adjustflag="2")
            prev = None
            while rs.next():
                r = rs.get_row_data()
                d, c = r[0], float(r[1]) if r[1] and r[1] != 'None' else 0
                if prev:
                    pct = (c - prev) / prev * 100
                    if d not in all_data: all_data[d] = {}
                    all_data[d][orig_code] = pct
                prev = c
        bs.logout()
        for d, vals in sorted(all_data.items()):
            comp = sum(vals.get(orig_code, 0) * wt for wt, orig_code in indices_map.values())
            sql = """INSERT INTO sentiment_raw_factors (trade_date, composite_index, create_time, update_time)
                     VALUES (%s, %s, NOW(), NOW())
                     ON DUPLICATE KEY UPDATE composite_index=VALUES(composite_index), update_time=NOW()"""
            cur.execute(sql, (d, round(comp, 4)))
        print(f'  baostock复合指数回填: {len(all_data)}个交易日')
    except Exception as e:
        print(f'  baostock回填失败({e}), 改用腾讯API...')
        indices = {'sh000001':0.3,'sz399001':0.2,'sz399006':0.1,'sh000852':0.4}
        all_data = {}
        for code in indices:
            try:
                r = requests.get('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',
                    params={'param':f'{code},day,,,120,qfq'}, headers=HDR, timeout=10)
                items = r.json().get('data',{}).get(code,{}).get('day',[])
                prev = None
                for k in items:
                    d, c = k[0], float(k[2])
                    if prev:
                        pct = (c - prev) / prev * 100
                        if d not in all_data: all_data[d] = {}
                        all_data[d][code] = pct
                    prev = c
            except: pass
        for d, vals in sorted(all_data.items()):
            comp = sum(vals.get(c, 0) * w for c, w in indices.items())
            sql = """INSERT INTO sentiment_raw_factors (trade_date, composite_index, create_time, update_time)
                     VALUES (%s, %s, NOW(), NOW())
                     ON DUPLICATE KEY UPDATE composite_index=VALUES(composite_index), update_time=NOW()"""
            cur.execute(sql, (d, round(comp, 4)))

    # 从 market_daily_stats 回填 涨跌停/成交额
    try:
        cur.execute("SELECT trade_date, turnover, limit_up, limit_down FROM market_daily_stats")
        for r in cur.fetchall():
            sql = "UPDATE sentiment_raw_factors SET turnover=%s, limit_up=%s, limit_down=%s WHERE trade_date=%s"
            cur.execute(sql, (float(r[1] or 0), int(r[2] or 0), int(r[3] or 0), str(r[0])))
    except: pass
    # 从 market_capital_flow 回填资金流
    try:
        cur.execute("SELECT trade_date, main_force_net FROM market_capital_flow")
        for r in cur.fetchall():
            cur.execute("UPDATE sentiment_raw_factors SET main_force_net=%s WHERE trade_date=%s",
                       (float(r[1] or 0), str(r[0])))
    except: pass
    # 融资融券余额回填 (akshare SSE)
    try:
        end_d = TODAY.replace('-','')
        start_d = (datetime.date.today() - datetime.timedelta(days=180)).strftime('%Y%m%d')
        sh_margin = ak.stock_margin_sse(start_date=start_d, end_date=end_d)
        if len(sh_margin) > 0:
            sh_col = sh_margin.columns[-1]; date_col = sh_margin.columns[0]
            for _, row in sh_margin.iterrows():
                d = str(row[date_col])[:10]
                sh_v = float(row[sh_col]) / 1e8 if pd.notna(row[sh_col]) else 0
                if sh_v > 0:
                    cur.execute("UPDATE sentiment_raw_factors SET margin_balance=%s WHERE trade_date=%s",
                               (round(sh_v, 2), d))
            print(f'  融资余额回填: {len(sh_margin)}条')
    except Exception as e:
        print(f'  融资余额回填跳过: {e}')
    print(f'  提示: 北向资金需每日运行 pipeline 累积')

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM sentiment_raw_factors")
    print(f'回填完成: {cur.fetchone()[0]} 条')


if '--backfill' in sys.argv:
    backfill()
elif '--calibrate' in sys.argv:
    run_calibrate()
elif '--collect-only' in sys.argv:
    pass
else:
    cur.execute("SELECT COUNT(*) FROM sentiment_raw_factors WHERE composite_index IS NOT NULL")
    total = cur.fetchone()[0]
    print(f'  累计 {total} 条因子数据，已标定 {calibrated} 条')
    if total >= 30 and calibrated < total:
        print('  数据量达30条，自动触发标定...')
        run_calibrate()
    else:
        print(f'  {"待数据达30条后自动标定" if total < 30 else "已标定，无需重新运行"}')

conn.close()
