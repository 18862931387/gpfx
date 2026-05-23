import pymysql, requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = pymysql.connect(
    host='192.168.10.100', port=3306,
    user='root', password='root',
    database='data_analysis', charset='utf8mb4'
)
cursor = conn.cursor()

date_str = '2026-05-06'

# 获取涨跌停准确数据
headers = {'User-Agent': 'Mozilla/5.0'}

# 涨停家数（A股，涨跌幅>=9.9%）
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
print(f'涨停家数: {zt_count}')

# 跌停家数（A股，涨跌幅<=-9.9%）
params_dt = dict(params_zt)
r_dt = requests.get(url, params=params_dt, headers=headers, timeout=10)
dt_data = r_dt.json().get('data', {}).get('diff', [])
dt_count = sum(1 for item in dt_data if item.get('f3', 0) <= -9.9)
print(f'跌停家数: {dt_count}')

# 上证指数数据
url2 = 'https://push2.eastmoney.com/api/qt/stock/get'
params_sh = {'secid': '1.000001', 'fields': 'f43,f44,f45,f46,f47,f48,f170,f171'}
r_sh = requests.get(url2, params=params_sh, headers=headers, timeout=10)
sh = r_sh.json()['data']
sh_price = sh['f43'] / 100
sh_pct = sh['f170'] / 100
sh_vol = sh['f47']
sh_amount = sh['f48'] / 100000000  # 亿

# 深证成指
params_sz = {'secid': '0.399001', 'fields': 'f43,f170,f47,f48'}
r_sz = requests.get(url2, params=params_sz, headers=headers, timeout=10)
sz = r_sz.json()['data']
sz_pct = sz['f170'] / 100
sz_vol = sz['f47']
sz_amount = sz['f48'] / 100000000

# 创业板
params_cy = {'secid': '0.399006', 'fields': 'f43,f170,f47,f48'}
r_cy = requests.get(url2, params=params_cy, headers=headers, timeout=10)
cy = r_cy.json()['data']
cy_pct = cy['f170'] / 100

# 科创50
params_kc = {'secid': '1.000688', 'fields': 'f43,f170'}
r_kc = requests.get(url2, params=params_kc, headers=headers, timeout=10)
kc = r_kc.json()['data']
kc_pct = kc['f170'] / 100

print(f'上证: {sh_price:.2f} {sh_pct:+.2f}%')
print(f'深证: {sz_pct:+.2f}%')
print(f'创业板: {cy_pct:+.2f}%')
print(f'科创50: {kc_pct:+.2f}%')

# 更新 market_daily_stats
sql = '''INSERT INTO market_daily_stats
(date_idx, sh_close, sh_pct, sz_pct, cy_pct, kc_pct, zt_count, dt_count, sh_amount)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
sh_close=VALUES(sh_close), sh_pct=VALUES(sh_pct), sz_pct=VALUES(sz_pct),
cy_pct=VALUES(cy_pct), kc_pct=VALUES(kc_pct),
zt_count=VALUES(zt_count), dt_count=VALUES(dt_count), sh_amount=VALUES(sh_amount)'''

cursor.execute(sql, (date_str, sh_price, sh_pct, sz_pct, cy_pct, kc_pct, zt_count, dt_count, sh_amount))
conn.commit()
print(f'market_daily_stats 更新成功: {cursor.rowcount}行受影响')

cursor.close()
conn.close()
print('完成!')
