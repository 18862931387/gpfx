import requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')

headers = {'User-Agent': 'Mozilla/5.0'}
# 涨停家数
url = 'https://push2.eastmoney.com/api/qt/clist/get'
params = {
    'pn': 1, 'pz': 1, 'po': 1, 'np': 1,
    'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
    'fltt': 2, 'invt': 2, 'fid': 'f3',
    'fs': 'm:0+t:6,m:0+t:13,m:1+t:2,m:1+t:23',
    'fields': 'f1,f2,f3',
}
try:
    r = requests.get(url, params=params, headers=headers, timeout=10)
    total = r.json().get('data', {}).get('total', 0)
    print(f'今日涨停家数(估算): {total}')
except Exception as e:
    print(f'涨停家数获取失败: {e}')

# 跌停家数
params2 = {
    'pn': 1, 'pz': 1, 'po': 1, 'np': 1,
    'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
    'fltt': 2, 'invt': 2, 'fid': 'f3',
    'fs': 'm:0+t:6,m:0+t:13,m:1+t:2,m:1+t:23',
    'fields': 'f1,f2,f3',
}
# 跌停是f3<0的
params2['fs'] = 'm:0+t:6,m:0+t:13,m:1+t:2,m:1+t:23'
try:
    r = requests.get(url, params=params2, headers=headers, timeout=10)
    data = r.json().get('data', {})
    print(f'涨跌停统计: total={data.get("total",0)}')
except Exception as e:
    print(f'涨跌停统计获取失败: {e}')
