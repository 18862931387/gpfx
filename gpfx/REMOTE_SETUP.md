项目代码在 /opt/xlx 或 D:\code\xlx，数据库在 192.168.3.68:3306，账号 root/root123。

远程服务器需要做以下数据落地改进，请逐条执行：

---

## 1. 尾盘分析结果写入 market_sentiment

当前 `_afternoon_check.py` 计算了情绪值（SENT, ZONE）但不存库。在文件末尾（约 line 570，`print()` 结束之前）追加：

```python
# ── 当日情绪落地 ──
try:
    conn_s = pymysql.connect(**DB); cur_s = conn_s.cursor()
    cur_s.execute("INSERT INTO market_sentiment (trade_date,sentiment_value,sentiment_zone,composite_idx,calibrated,market_desc,create_time,update_time) VALUES (%s,%s,%s,%s,1,%s,NOW(),NOW()) ON DUPLICATE KEY UPDATE sentiment_value=VALUES(sentiment_value),sentiment_zone=VALUES(sentiment_zone),composite_idx=VALUES(composite_idx),update_time=NOW()",
        (TODAY, SENT, ZONE, composite, f'{TODAY} 复合{composite:+.2f}% 情绪{SENT:+.1f}({ZONE})'))
    conn_s.commit(); conn_s.close()
except: pass
```

## 2. 补全 market_daily_stats 历史数据

服务器上跑（需交易时段 9:30-15:00，或盘后 16:00-18:00）：

```bash
cd /opt/xlx
python -c "
import pymysql, requests, json, sys, socket
sys.stdout.reconfigure(encoding='utf-8')
import requests.packages.urllib3.util.connection as ucn
ucn.allowed_gai_family = lambda: socket.AF_INET
from config import DB, EASTMONEY_UT, HDR

conn = pymysql.connect(**DB); cur = conn.cursor()
clist_h = {**HDR, 'Referer': 'https://quote.eastmoney.com/'}

# 从 push2his 拉所有交易日
r = requests.get('https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get',
    params={'secid':'1.000001','fields1':'f1,f2,f3,f4,f5','fields2':'f51','lmt':'120','ut':EASTMONEY_UT},
    headers={**HDR, 'Referer': 'https://data.eastmoney.com/'}, timeout=10)
trading_days = [k.split(',')[0] for k in r.json().get('data',{}).get('klines',[])]

for dt in trading_days:
    cur.execute('SELECT id FROM market_daily_stats WHERE trade_date=%s', (dt,))
    if cur.fetchone(): continue
    try:
        r2 = requests.get('https://push2.eastmoney.com/api/qt/clist/get',
            params={'pn':1,'pz':5000,'po':1,'np':1,'ut':EASTMONEY_UT,'fltt':2,'invt':2,'fid':'f3',
                    'fs':'m:0+t:6,m:0+t:13,m:1+t:2,m:1+t:23','fields':'f3'},
            headers=clist_h, timeout=15)
        items = r2.json().get('data',{}).get('diff',[])
        zt = sum(1 for i in items if i.get('f3') and float(i['f3']) >= 9.9)
        dtcnt = sum(1 for i in items if i.get('f3') and float(i['f3']) <= -9.9)
        tv = 0.0
        for sid in ('1.000001','0.399001'):
            try:
                r3 = requests.get('https://push2.eastmoney.com/api/qt/stock/get',
                    params={'secid':sid,'fields':'f48'}, headers=clist_h, timeout=10)
                tv += (r3.json().get('data',{}).get('f48') or 0)
            except: pass
        tv = round(tv/1e8, 2) if tv else None
        if zt or dtcnt or tv:
            cur.execute('INSERT INTO market_daily_stats (trade_date,limit_up,limit_down,turnover,create_time,update_time) VALUES (%s,%s,%s,%s,NOW(),NOW()) ON DUPLICATE KEY UPDATE limit_up=VALUES(limit_up),limit_down=VALUES(limit_down),turnover=VALUES(turnover)', (dt, zt, dtcnt, tv))
            print(f'{dt}: 涨停{zt} 跌停{dtcnt} 成交{tv}亿')
conn.commit(); conn.close()
"
```

## 3. 补全 etf_fund_flow 历史数据（盘后16:00后跑）

```bash
cd /opt/xlx
python -c "
import pymysql, requests, sys, socket
sys.stdout.reconfigure(encoding='utf-8')
import requests.packages.urllib3.util.connection as ucn
ucn.allowed_gai_family = lambda: socket.AF_INET
from config import DB, EASTMONEY_UT, HDR

conn = pymysql.connect(**DB); cur = conn.cursor()
for code in ['563300','516330','588090']:
    sid = f'1.{code}' if code[0] in ('5','6','9') else f'0.{code}'
    try:
        r = requests.get('https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get',
            params={'secid':sid,'fields1':'f1,f2,f3,f4,f5','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61','lmt':'120','ut':EASTMONEY_UT},
            headers={**HDR,'Referer':'https://data.eastmoney.com/'}, timeout=10)
        for k in r.json().get('data',{}).get('klines',[]):
            p = k.split(',')
            if len(p) >= 11:
                cur.execute('INSERT INTO etf_fund_flow (trade_date,fund_code,main_force_net,retail_net,medium_net,large_net,super_large_net,create_time) VALUES (%s,%s,%s,%s,%s,%s,%s,NOW()) ON DUPLICATE KEY UPDATE main_force_net=VALUES(main_force_net)',
                    (p[0], code, p[1], p[2], p[3], p[4], p[5]))
        conn.commit()
        cur.execute('SELECT COUNT(*) FROM etf_fund_flow WHERE fund_code=%s', (code,))
        print(f'{code}: {cur.fetchone()[0]} rows')
    except Exception as e:
        print(f'{code}: {e}')
conn.close()
"
```

## 4. 确认策略信号已落地

盘后跑一次尾盘分析（虽然无信号不会写表，但代码逻辑在）：

```bash
cd /opt/xlx
python _afternoon_check.py
```

然后检查 strategy_signals 有无数据（今天无持仓变动则无信号，正常）：

```bash
mysql -h 192.168.3.68 -u root -proot123 data_analysis -e "SELECT COUNT(*),MAX(trade_date) FROM strategy_signals"
```

## 5. 验证数据完整性

```bash
mysql -h 192.168.3.68 -u root -proot123 data_analysis -e "
SELECT 'market_daily_stats', MAX(trade_date) FROM market_daily_stats
UNION ALL SELECT 'etf_fund_flow', MAX(trade_date) FROM etf_fund_flow
UNION ALL SELECT 'market_capital_flow', MAX(trade_date) FROM market_capital_flow
UNION ALL SELECT 'market_sentiment', MAX(trade_date) FROM market_sentiment
UNION ALL SELECT 'strategy_signals', ifnull(MAX(trade_date),'无数据') FROM strategy_signals;
"
```

期望结果（2026-06-03 收盘后）：
- market_daily_stats → 2026-06-03
- market_capital_flow → 2026-06-03
- market_sentiment → 2026-06-03
- etf_fund_flow → 2026-06-03 (3只ETF各120条)
- strategy_signals → 2026-06-03 或无数据（今天有信号就是buyA/buyB/sell）

完成后执行 `python daily_update.py` 触发备份。
