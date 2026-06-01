# 项目统一配置
DB = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'root123',
    'database': 'data_analysis',
    'charset': 'utf8mb4',
}

CAPITAL = 20000.0  # 总资金
SYSTEM_BASE_CASH = 10181.0  # 系统跟踪基础现金

# API 配置
TENCENT_REALTIME = 'https://web.sqt.gtimg.cn/q={code}'
TENCENT_KLINE = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
EASTMONEY_PUSH2 = 'https://push2.eastmoney.com/api/qt/{endpoint}'
EASTMONEY_PUSH2HIS = 'https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get'
EASTMONEY_FUND = 'https://api.fund.eastmoney.com/f10/lsjz'
EASTMONEY_UT = 'fa5fd1943c7b386f172d6893dbbd1d0c'
HEXIN_HSGT = 'https://data.hexin.cn/market/hsgtApi/method/dayChart/'

# 默认请求头
HDR = {'User-Agent': 'Mozilla/5.0'}
PUSH2_REFERER = 'https://quote.eastmoney.com/'
FUND_REFERER = 'https://fund.eastmoney.com/'

# 默认ETF
PRIMARY_FUND = '563300'
PRIMARY_FUND_NAME = '中证2000ETF'

# 复合指数权重
COMPOSITE_WT = {'sh000001': 0.3, 'sz399001': 0.2, 'sz399006': 0.1, 'sh000852': 0.4}
