import requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')

headers = {'User-Agent': 'Mozilla/5.0'}
url = 'https://push2.eastmoney.com/api/qt/stock/get'

indices = [
    ('1.000001', '上证指数'),
    ('0.399001', '深证成指'),
    ('0.399006', '创业板指'),
    ('1.000688', '科创50'),
    ('0.399300', '沪深300'),
    ('0.000852', '中证1000'),
    ('0.000985', '中证2000'),
]

print('=== 今日A股指数 (2026-05-06) ===')
for secid, name in indices:
    params = {'secid': secid, 'fields': 'f43,f44,f45,f46,f47,f48,f170,f171'}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        d = r.json().get('data', {})
        price = d.get('f43')
        pct = d.get('f170')
        vol = d.get('f47')
        amount = d.get('f48')
        if price:
            pct_str = f'{pct/100:+.2f}%' if pct else 'N/A'
            vol_str = f'{vol/100000000:.2f}亿' if vol else 'N/A'
            amt_str = f'{amount/100000000:.2f}亿' if amount else 'N/A'
            print(f'{name}: {price/100:.2f}  涨跌幅:{pct_str}  成交量:{vol_str}  成交额:{amt_str}')
    except Exception as e:
        print(f'{name}: 获取失败 {e}')

etfs = [
    ('1.563300', '563300 中证2000ETF'),
    ('1.516330', '516330 物联网ETF'),
    ('1.588090', '588090 科创50ETF'),
]
print()
print('=== 三只ETF ===')
for secid, name in etfs:
    params = {'secid': secid, 'fields': 'f43,f44,f45,f46,f47,f48,f170,f171'}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        d = r.json().get('data', {})
        price = d.get('f43')
        pct = d.get('f170')
        vol = d.get('f47')
        amount = d.get('f48')
        if price:
            pct_str = f'{pct/100:+.2f}%' if pct else 'N/A'
            amt_str = f'{amount/100000000:.2f}亿' if amount else 'N/A'
            print(f'{name}: {price/100:.4f}  涨跌幅:{pct_str}  成交额:{amt_str}')
    except Exception as e:
        print(f'{name}: 获取失败 {e}')
