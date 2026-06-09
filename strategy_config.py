# 策略版本管理
# 每次修改参数后，在底部追加一条记录，不要修改历史记录
# 运行 _afternoon_check.py 或 simulate.py 时自动读取最新版本参数

VERSIONS = [
    {
        "ver": "v5.4",
        "active": "2026-05-20~2026-05-31",
        "desc": "单指数情绪+买A抄底+卖一半+止盈+止损",
        "params": {
            "buyA_sv_max": -0.8,
            "buyA_dc_min": -1.0,
            "buyB": None,
            "sell_half_sv": 1.5,
            "sell_all_sv": 2.0,
            "stop_loss_pct": -3.0,
            "take_profit_pct": 2.0,
            "max_invest": 10000,
            "composite_wt": [1.0],  # 仅上证
        },
    },
    {
        "ver": "v5.5a",
        "active": "2026-06-01~",
        "desc": "复合指数+买A抄底+买B趋势全仓+卖一半1.8+止盈",
        "params": {
            "buyA_sv_max": -0.8,
            "buyA_dc_min": -1.0,
            "buyB": {"sv_min": -0.5, "sv_max": 0.5, "position": 0.5},
            "sell_half_sv": 1.8,
            "sell_all_sv": 2.0,
            "stop_loss_pct": -3.0,
            "take_profit_pct": 2.0,
            "max_invest": 10000,
            "composite_wt": [0.3, 0.2, 0.1, 0.4],
        },
    },
    {
        "ver": "v5.5b",
        "active": "2026-06-01~",
        "desc": "复合指数+买A抄底+买B趋势全仓+卖一半1.8+去止盈",
        "params": {
            "buyA_sv_max": -0.8,
            "buyA_dc_min": -1.0,
            "buyB": {"sv_min": -0.5, "sv_max": 0.5, "position": 1.0},
            "sell_half_sv": 1.8,
            "sell_all_sv": 2.0,
            "stop_loss_pct": -3.0,
            "take_profit_pct": None,
            "max_invest": 10000,
            "composite_wt": [0.3, 0.2, 0.1, 0.4],
        },
    },
    {
        "ver": "v5.5c",
        "active": "2026-06-01~",
        "desc": "复合指数+买A≤-0.5+买B全仓+去止盈+去卖一半+8000仓",
        "params": {
            "buyA_sv_max": -0.5,
            "buyA_dc_min": -1.0,
            "buyB": {"sv_min": -0.5, "sv_max": 0.5, "position": 1.0},
            "sell_half_sv": None,
            "sell_all_sv": 2.0,
            "stop_loss_pct": -3.0,
            "take_profit_pct": None,
            "max_invest": 8000,
            "composite_wt": [0.3, 0.2, 0.1, 0.4],
        },
    },
    {
        "ver": "v5.5d",
        "active": "2026-06-01~",
        "desc": "复合指数+买A≤-1.2+买B全仓+去止盈+去卖一半+8000仓(当前最佳)",
        "params": {
            "buyA_sv_max": -1.2,
            "buyA_dc_min": -1.0,
            "buyB": {"sv_min": -0.5, "sv_max": 0.5, "position": 1.0},
            "sell_half_sv": None,
            "sell_all_sv": 2.0,
            "stop_loss_pct": -3.0,
            "trailing_stop_pct": None,
            "take_profit_pct": None,
            "max_invest": 8000,
            "composite_wt": [0.3, 0.2, 0.1, 0.4],
        },
    },
    {
        "ver": "v5.5e",
        "active": "2026-06-01~",
        "desc": "v5.5d + 回撤止损(从峰值-3%)",
        "params": {
            "buyA_sv_max": -1.2,
            "buyA_dc_min": -1.0,
            "buyB": {"sv_min": -0.5, "sv_max": 0.5, "position": 1.0},
            "sell_half_sv": None,
            "sell_all_sv": 2.0,
            "stop_loss_pct": -3.0,
            "trailing_stop_pct": -3.0,
            "take_profit_pct": None,
            "max_invest": 8000,
            "composite_wt": [0.3, 0.2, 0.1, 0.4],
        },
    },
    {
        "ver": "v5.6",
        "active": "2026-06-01~",
        "desc": "v5.5d + 仓位升级1万 (回测+10.06%/-2.49%)",
        "params": {
            "buyA_sv_max": -1.2,
            "buyA_dc_min": -1.0,
            "buyB": {"sv_min": -0.5, "sv_max": 0.5, "position": 1.0},
            "sell_half_sv": None,
            "sell_all_sv": 2.0,
            "stop_loss_pct": -3.0,
            "trailing_stop_pct": None,
            "take_profit_pct": None,
            "max_invest": 10000,
            "composite_wt": [0.3, 0.2, 0.1, 0.4],
        },
    },
    {
        "ver": "v5.7",
        "active": "2026-06-01~",
        "desc": "v5.6 + 买B情绪动量增强(3日情绪均线↑ + 动态仓位 + 乖离)",
        "params": {
            "buyA_sv_max": -1.2,
            "buyA_dc_min": -1.0,
            "buyB": {
                "sv_min": -0.5, "sv_max": 0.5,
                "position_max": 1.0,
                "position_min": 0.5,
                "sent_ma_days": 3,
                "ma_deviation_max": 0.03,
            },
            "sell_half_sv": None,
            "sell_all_sv": 2.0,
            "stop_loss_pct": -3.0,
            "trailing_stop_pct": None,
            "take_profit_pct": None,
            "max_invest": 10000,
            "composite_wt": [0.3, 0.2, 0.1, 0.4],
        },
    },
    {
        "ver": "v5.8",
        "active": "2026-06-03~",
        "desc": "v5.6 + margin_boost(融资去杠杆>1%时买A阈值从-1.2放宽到-1.0)",
        "params": {
            "buyA_sv_max": -1.2,
            "buyA_dc_min": -1.0,
            "buyA_margin_boost": True,
            "buyB": {"sv_min": -0.5, "sv_max": 0.5, "position": 1.0},
            "sell_half_sv": None,
            "sell_all_sv": 2.0,
            "stop_loss_pct": -3.0,
            "trailing_stop_pct": None,
            "take_profit_pct": None,
            "max_invest": 10000,
            "composite_wt": [0.3, 0.2, 0.1, 0.4],
        },
    },
]


def get_latest():
    return VERSIONS[6]  # v5.6 (回测最优: +9.53%)


def find(ver_str):
    for v in VERSIONS:
        if v["ver"] == ver_str:
            return v
    return None


# ── 513530 港股通红利ETF 独立策略 ──
# 均线乖离策略: MA20乖离 -2.5%买入 / +5%卖出，中间持有吃月分红
STRATEGY_513530 = {
    "ver": "h1.0",
    "active": "2026-06-09~",
    "desc": "港股红利513530: MA20乖离-2.5%买入/+5%卖出+持有吃息",
    "fund_code": "513530",
    "fund_name": "港股通红利ETF",
    "params": {
        "ma_fast": 20,
        "buy_deviation": -3.0,       # 收盘价比MA20低3.0%时买入
        "sell_deviation": 5.0,       # 收盘价比MA20高5%时卖出
        "stop_loss_pct": -8.0,       # 从持仓成本-8%止损
        "max_invest": 10000,
        "position_pct": 0.95,        # 买入用95%可用资金
    },
}
