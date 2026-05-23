import pymysql, requests, sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

try:
    # Database connection
    conn = pymysql.connect(
        host='192.168.10.100', port=3306,
        user='root', password='root',
        database='data_analysis', charset='utf8mb4'
    )
    cursor = conn.cursor()

    date_str = '2026-05-06'
    headers = {'User-Agent': 'Mozilla/5.0'}

    print("Fetching market data...")

    # Get limit up/down data
    url = 'https://push2.eastmoney.com/api/qt/clist/get'
    params_zt = {
        'pn': 1, 'pz': 5000, 'po': 1, 'np': 1,
        'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
        'fltt': 2, 'invt': 2, 'fid': 'f3',
        'fs': 'm:0+t:6,m:0+t:13,m:1+t:2,m:1+t:23',
        'fields': 'f1,f2,f3',
    }

    r_zt = requests.get(url, params=params_zt, headers=headers, timeout=10)
    zt_data = r_zt.json().get('data', {}).get('diff', [])
    zt_count = sum(1 for item in zt_data if item.get('f3', 0) >= 9.9)
    print(f'Limit Up: {zt_count}')

    r_dt = requests.get(url, params=params_zt, headers=headers, timeout=10)
    dt_data = r_dt.json().get('data', {}).get('diff', [])
    dt_count = sum(1 for item in dt_data if item.get('f3', 0) <= -9.9)
    print(f'Limit Down: {dt_count}')

    # Get index data
    url2 = 'https://push2.eastmoney.com/api/qt/stock/get'

    params_sh = {'secid': '1.000001', 'fields': 'f43,f44,f45,f46,f47,f48,f170,f171'}
    r_sh = requests.get(url2, params=params_sh, headers=headers, timeout=10)
    sh = r_sh.json()['data']
    sh_price = sh['f43'] / 100
    sh_pct = sh['f170'] / 100
    sh_amount = sh['f48'] / 100000000

    params_sz = {'secid': '0.399001', 'fields': 'f43,f170,f47,f48'}
    r_sz = requests.get(url2, params=params_sz, headers=headers, timeout=10)
    sz_pct = r_sz.json()['data']['f170'] / 100

    params_cy = {'secid': '0.399006', 'fields': 'f43,f170,f47,f48'}
    r_cy = requests.get(url2, params=params_cy, headers=headers, timeout=10)
    cy_pct = r_cy.json()['data']['f170'] / 100

    params_kc = {'secid': '1.000688', 'fields': 'f43,f170'}
    r_kc = requests.get(url2, params=params_kc, headers=headers, timeout=10)
    kc_pct = r_kc.json()['data']['f170'] / 100

    print(f'Shanghai: {sh_price:.2f} {sh_pct:+.2f}%')
    print(f'Shenzhen: {sz_pct:+.2f}%')
    print(f'ChiNext: {cy_pct:+.2f}%')
    print(f'STAR 50: {kc_pct:+.2f}%')

    # Update market_daily_stats
    sql = '''INSERT INTO market_daily_stats
    (date_idx, sh_close, sh_pct, sz_pct, cy_pct, kc_pct, zt_count, dt_count, sh_amount)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
    sh_close=VALUES(sh_close), sh_pct=VALUES(sh_pct), sz_pct=VALUES(sz_pct),
    cy_pct=VALUES(cy_pct), kc_pct=VALUES(kc_pct),
    zt_count=VALUES(zt_count), dt_count=VALUES(dt_count), sh_amount=VALUES(sh_amount)'''

    cursor.execute(sql, (date_str, sh_price, sh_pct, sz_pct, cy_pct, kc_pct, zt_count, dt_count, sh_amount))
    print(f'market_daily_stats SUCCESS: {cursor.rowcount} rows affected')

    # Update fund_history
    etfs = [
        ('563300', '1.563300'),
        ('516330', '1.516330'),
        ('588090', '1.588090'),
    ]

    for code, secid in etfs:
        params = {'secid': secid, 'fields': 'f43,f44,f45,f46,f47,f48,f170,f171'}
        r = requests.get(url2, params=params, headers=headers, timeout=10)
        d = r.json()['data']
        price = d['f43'] / 10000
        pct = d['f170'] / 100
        amount = d['f48'] / 100000000

        cursor.execute('SELECT fund_name FROM fund_history WHERE fund_code=%s LIMIT 1', (code,))
        row = cursor.fetchone()
        name = row[0] if row else code

        sql = '''INSERT INTO fund_history (fund_code, fund_name, date_idx, nav, nav_growth, volume)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        nav=VALUES(nav), nav_growth=VALUES(nav_growth), volume=VALUES(volume)'''

        cursor.execute(sql, (code, name, date_str, price, pct, amount))
        print(f'{code} {name}: nav={price:.4f} pct={pct:+.2f}% vol={amount:.2f}B')

    # Update market_sentiment
    sentiment_score = 1.5
    sentiment_label = '过热'
    summary = '科创50暴涨5.47%领涨全场，创业板+2.75%，上证+1.17%。AI算力主线爆发，市场做多情绪高涨。科创50ETF(588090)+5%，中证2000ETF+1.86%。但中证2000指数本身-1.73%，小盘偏弱。'

    sql = '''INSERT INTO market_sentiment (date_idx, sentiment_score, sentiment_label, summary)
    VALUES (%s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
    sentiment_score=VALUES(sentiment_score), sentiment_label=VALUES(sentiment_label), summary=VALUES(summary)'''

    cursor.execute(sql, (date_str, sentiment_score, sentiment_label, summary))
    print(f'market_sentiment SUCCESS: {cursor.rowcount} rows affected')

    conn.commit()
    cursor.close()
    conn.close()
    print('ALL UPDATES COMPLETE!')
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
