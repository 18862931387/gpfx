# -*- coding: utf-8 -*-
"""
稳健策略 v3.0 模拟回测
基金：563300（中证2000ETF华泰柏瑞）
本金：20,000 元
仓位上限：50%（最多持仓 10,000 元）
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

raw_data = [
    ("2026-03-02", None,   1.5415),
    ("2026-03-03", -1.90, 1.4820),
    ("2026-03-04", -0.70, 1.4776),
    ("2026-03-05",  1.20, 1.5026),
    ("2026-03-06",  0.70, 1.5228),
    ("2026-03-09", -0.50, 1.5098),
    ("2026-03-10",  1.90, 1.5459),
    ("2026-03-11",  0.90, 1.5444),
    ("2026-03-12", -0.40, 1.5272),
    ("2026-03-13", -0.50, 1.5106),
    ("2026-03-16",  0.40, 1.5176),
    ("2026-03-17", -1.30, 1.4775),
    ("2026-03-18",  1.10, 1.5024),
    ("2026-03-19", -1.30, 1.4631),
    ("2026-03-20", -0.10, 1.4307),
    ("2026-03-23", -2.10, 1.3515),
    ("2026-03-24",  1.50, 1.4037),
    ("2026-03-25",  1.80, 1.4349),
    ("2026-03-26", -1.10, 1.4143),
    ("2026-03-27",  0.90, 1.4348),
    ("2026-03-30",  0.00, 1.4389),
    ("2026-03-31", -1.30, 1.4120),
    ("2026-04-01",  1.80, 1.4427),
    ("2026-04-02", -1.20, 1.4190),
    ("2026-04-03", -0.80, 1.3920),
    ("2026-04-07",  0.40, 1.4118),
    ("2026-04-08",  2.50, 1.4717),
    ("2026-04-09", -0.40, 1.4635),
    ("2026-04-10",  2.10, 1.4746),
    ("2026-04-13",  0.60, 1.4795),
    ("2026-04-14",  1.50, 1.4975),
    ("2026-04-15", -0.60, 1.4899),
    ("2026-04-16",  1.90, 1.5205),
    ("2026-04-17",  0.60, 1.5336),
    ("2026-04-20",  0.50, 1.5448),
    ("2026-04-21",  0.20, 1.5418),
    ("2026-04-22",  1.20, 1.5567),
    ("2026-04-23", -0.60, 1.5374),
    ("2026-04-24", -0.70, 1.5287),
    ("2026-04-27",  0.20, 1.5428),
    ("2026-04-28", -0.80, 1.5247),
    ("2026-04-29",  1.80, 1.5478),
    ("2026-04-30",  0.20, 1.5592),
]

CAPITAL = 20000.0
MAX_POS = 0.50
MAX_INVEST = CAPITAL * MAX_POS


def run_simulation(data_list, start_cash, label):
    """运行模拟，返回期末总资产和最大回撤"""
    print(f"\n{'='*65}")
    print(f"  {label}")
    print(f"{'='*65}")

    cash = start_cash
    shares = 0.0
    invested = 0.0
    prev_nav = None
    total_trades = 0
    max_drawdown = 0.0
    peak_value = start_cash
    loss_sell_today = False  # 当日亏损清仓后不再买入

    print(f"{'日期':<12} {'情绪':>5} {'净值':>8} {'涨跌%':>7} {'操作':<26} {'持仓市值':>10} {'现金':>10} {'总资产':>10}")
    print("-" * 92)

    for date, sentiment, nav in data_list:
        loss_sell_today = False  # 每个交易日开始时重置

        daily_change = 0.0
        if prev_nav is not None and prev_nav > 0:
            daily_change = (nav - prev_nav) / prev_nav * 100
        prev_nav = nav

        if sentiment is None:
            continue

        pos_value = shares * nav
        total_value = cash + pos_value

        profit_pct = 0.0
        if invested > 0:
            profit_pct = (pos_value - invested) / invested * 100

        action = ""

        # [Sell] priority
        if shares > 0:
            if sentiment >= 1.0:
                cash += pos_value
                action = f"清仓(情绪{sentiment:+.1f})"
                shares = 0.0
                invested = 0.0
                total_trades += 1
            elif profit_pct >= 2.0:
                half_value = pos_value * 0.5
                half_shares = half_value / nav
                cash += half_value
                shares -= half_shares
                invested *= 0.5
                action = f"卖一半(盈利+{profit_pct:.1f}%)"
                total_trades += 1
            elif profit_pct <= -3.0:
                cash += pos_value
                action = f"清仓(亏损{profit_pct:.1f}%)"
                shares = 0.0
                invested = 0.0
                loss_sell_today = True
                total_trades += 1

        pos_value = shares * nav
        total_value = cash + pos_value

        # [Buy] - 亏损清仓后当日不再重复买入
        if shares == 0 and cash > 0 and not loss_sell_today:
            if sentiment <= -0.8 and daily_change <= -1.0:
                buy_amount = min(MAX_INVEST, cash)
                if buy_amount >= 100:
                    buy_shares = buy_amount / nav
                    shares = buy_shares
                    cash -= buy_amount
                    invested = buy_amount
                    action = f"买入(情绪{sentiment:+.1f},跌{daily_change:.1f}%)"
                    total_trades += 1

        pos_value = shares * nav
        total_value = cash + pos_value

        if total_value > peak_value:
            peak_value = total_value
        dd = (peak_value - total_value) / peak_value * 100 if peak_value > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd

        pos_str = f"{pos_value:>8.2f}" if shares > 0 else f"{'空仓':>8}"
        action_str = action if action else ("持有" if shares > 0 else "观望")
        print(f"{date:<12} {sentiment:>+5.1f} {nav:>8.4f} {daily_change:>+6.1f}% {action_str:<26} {pos_str:>10} {cash:>10.2f} {total_value:>10.2f}")

    final_value = cash + shares * data_list[-1][2]
    total_return = (final_value / start_cash - 1) * 100

    print("-" * 92)
    print(f"  期末总资产:      {final_value:>10.2f} 元")
    print(f"  总收益率:        {total_return:>+8.2f}%")
    print(f"  收益额:          {final_value - start_cash:>+10.2f} 元")
    print(f"  交易次数:        {total_trades} 次")
    print(f"  最大回撤:        {max_drawdown:>6.2f}%")

    return final_value, max_drawdown


# ===== 运行 =====
mar_data = [d for d in raw_data if "2026-03-02" <= d[0] <= "2026-03-31"]
mar_end, mar_mdd = run_simulation(mar_data, CAPITAL, "3月回测 (2026-03-03 ~ 2026-03-31)")

apr_data = [d for d in raw_data if "2026-04-01" <= d[0] <= "2026-04-30"]
apr_end, apr_mdd = run_simulation(apr_data, CAPITAL, "4月回测 (2026-04-01 ~ 2026-04-30)")

print(f"\n\n{'='*65}")
print(f"  3-4月整体汇总")
print(f"{'='*65}")
print()
print(f"  {'指标':<20} {'3月':>12} {'4月':>12} {'合计':>12}")
print(f"  {'-'*56}")
print(f"  {'期初本金':<20} {CAPITAL:>12.2f} {CAPITAL:>12.2f} {CAPITAL:>12.2f}")
print(f"  {'期末总资产':<20} {mar_end:>12.2f} {apr_end:>12.2f} {apr_end:>12.2f}")
print(f"  {'月收益':<20} {mar_end-CAPITAL:>+12.2f} {apr_end-CAPITAL:>+12.2f} {apr_end-CAPITAL:>+10.2f}")
print(f"  {'月收益率':<20} {(mar_end/CAPITAL-1)*100:>+11.2f}% {(apr_end/CAPITAL-1)*100:>+11.2f}% {(apr_end/CAPITAL-1)*100:>+10.2f}%")
print(f"  {'最大回撤':<20} {mar_mdd:>11.2f}% {apr_mdd:>11.2f}%")

print()
mar_ret = (mar_end/CAPITAL-1)*100
apr_ret = (apr_end/CAPITAL-1)*100
print(f"  策略目标：月收益 2%~4%")
print(f"  3月收益 {mar_ret:+.2f}% - {'达标' if mar_ret>=2 else '未达标'}")
print(f"  4月收益 {apr_ret:+.2f}% - {'达标' if apr_ret>=2 else '未达标'}")
print(f"  合计 {mar_ret+apr_ret:+.2f}%")
