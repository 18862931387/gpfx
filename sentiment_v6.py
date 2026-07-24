# V6 情绪标定: K-means 聚类 + 去循环论证
# 
# 核心改进:
#   1. 等频分箱 → 真正 K-means 聚类 (k=5), 数据自驱动分组
#   2. 去掉复合指数作为聚类因子, 只用5个纯资金/结构指标
#   3. 聚类后回归到复合指数, 得到实时可用系数
#   4. 2024年8月起北向资金日频数据已停止披露，移除northbound_net因子 (6→5因子)
#
# 使用:
#   python sentiment_v6.py              # 标定 + 打印结果
#   python sentiment_v6.py --store      # 标定 + 写入DB (market_sentiment.sentiment_v6)
#   python sentiment_v6.py --backfill   # 仅回填历史 v6 情绪值

import sys, os, pymysql, numpy as np, datetime
sys.path.insert(0, os.path.dirname(__file__))
from config import DB

TODAY = datetime.date.today().isoformat()


def load_data():
    """从 sentiment_raw_factors 读取所有历史数据"""
    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT trade_date, composite_index, sector_ad_ratio, volume_pctile_60d,
               main_force_net, margin_balance
        FROM sentiment_raw_factors
        WHERE composite_index IS NOT NULL
        ORDER BY trade_date
    """)
    raw = cur.fetchall()
    conn.close()
    return raw


def kmeans(X, k=5, max_iter=200, n_init=10):
    """手写 K-means++ 初始化, 多次运行取最优"""
    n = X.shape[0]
    best_inertia = float('inf')
    best_labels = None
    best_centroids = None

    for seed in range(n_init):
        np.random.seed(seed)
        # K-means++ 初始化
        centroids = [X[np.random.randint(n)].copy()]
        for _ in range(1, k):
            dists = np.min([np.sum((X - c) ** 2, axis=1) for c in centroids], axis=0)
            dists = np.clip(dists, 0, None)
            if dists.sum() == 0:
                dists = np.ones(n)
            probs = dists / dists.sum()
            centroids.append(X[np.random.choice(n, p=probs)].copy())
        centroids = np.array(centroids)

        for _ in range(max_iter):
            dists = np.array([np.sum((X - c) ** 2, axis=1) for c in centroids])
            labels = np.argmin(dists, axis=0)
            new_centroids = np.array([
                X[labels == j].mean(axis=0) if (labels == j).sum() > 0
                else centroids[j]
                for j in range(k)
            ])
            if np.allclose(centroids, new_centroids, rtol=1e-6):
                break
            centroids = new_centroids

        inertia = np.sum(np.min(np.array([np.sum((X - c) ** 2, axis=1) for c in centroids]), axis=0))
        if inertia < best_inertia:
            best_inertia = inertia
            best_labels = labels.copy()
            best_centroids = centroids.copy()

    return best_labels, best_centroids


def calibrate_v6():
    raw = load_data()
    if len(raw) < 20:
        print(f'数据不足: {len(raw)}条 (需≥20)')
        return None

    dates = [r[0] for r in raw]
    composites = np.array([float(r[1] or 0) for r in raw])

    # 提取原始数据 (4因子: sector_ad_ratio, volume_pctile_60d, main_force_net, margin_balance)
    X_raw = np.array([
        [float(r[2] or 1), float(r[3] or 50), float(r[4] or 0),
         float(r[5] or 0)]
        for r in raw
    ])

    # 特征工程
    ad_ratio = np.clip(X_raw[:, 0], 0.01, 100)
    log_ad = np.log(ad_ratio)
    vol_pct = X_raw[:, 1]
    flow = X_raw[:, 2]
    margin = np.array([r4 or 0 for r4 in X_raw[:, 3]])
    margin_chg = np.zeros_like(margin)
    for i in range(5, len(margin)):
        if margin[i - 5] and margin[i - 5] != 0:
            margin_chg[i] = (margin[i] - margin[i - 5]) / abs(margin[i - 5]) * 100

    # 纯市场指标聚类 (4因子, 不含composite, 避免循环论证)
    all_features = np.column_stack([log_ad, vol_pct, flow, margin_chg])
    feature_names = ['log_ad', 'vol_pct', 'flow', 'margin_chg']

    means = np.mean(all_features, axis=0)
    stds = np.std(all_features, axis=0)
    stds = np.where(stds < 1e-10, 1.0, stds)
    X_std = (all_features - means) / stds

    print(f'  聚类特征矩阵: {X_std.shape} (样本×4特征, 全部z-score标准化)')
    var_info = ', '.join([f'{feature_names[i]}={np.var(X_std[:,i]):.2f}' for i in range(4)])
    print(f'  标准化后方差: {var_info}')

    labels, centroids = kmeans(X_std, k=5, n_init=20)

    cluster_composite = np.array([composites[labels == i].mean() for i in range(5)])
    cluster_order = np.argsort(cluster_composite)
    mapping = {int(cluster_order[i]): float(i - 2) for i in range(5)}

    sentiment_labels = np.array([mapping[int(l)] for l in labels])

    print(f'\n{"=" * 70}')
    print(f'  V6 K-means 聚类结果 ({len(raw)}条, k=5, 4纯市场因子z-score标准化, 20次初始化)')
    print(f'  (v5对比: 强制均分20%每档, 复合指数占35%权重)')
    print(f'  (2024年8月起北向资金日频数据停发，已移除northbound_net)')
    print(f'  (composite_index不参与聚类，仅用于回归映射，避免循环论证)')
    print(f'{"=" * 70}')
    print(f'  {"情绪":>5} {"样本数":>6} {"占比":>6} {"平均复合指数":>12}  簇中心(z-score)')
    print(f'  {"-" * 65}')
    for i in range(5):
        orig_i = int(cluster_order[i])
        count = int((labels == orig_i).sum())
        pct = count / len(labels) * 100
        avg_comp = cluster_composite[orig_i]
        sent = mapping[orig_i]
        c = centroids[orig_i]
        print(f'  {sent:>+5.0f} {count:>6} {pct:>5.1f}% {avg_comp:>+12.2f}%   '
              f'ad:{c[0]:+.2f} vol:{c[1]:+.2f} '
              f'flow:{c[2]:+.2f} mar:{c[3]:+.2f}')

    print(f'\n  各簇 composite 分布:')
    for i in range(5):
        orig_i = int(cluster_order[i])
        mask = labels == orig_i
        cluster_vals = composites[mask]
        sent = mapping[orig_i]
        print(f'    情绪{sent:+.0f}: min={cluster_vals.min():+.2f}%  '
              f'median={np.median(cluster_vals):+.2f}%  max={cluster_vals.max():+.2f}%')

    X_design = np.column_stack([np.ones(len(composites)), composites])
    beta = np.linalg.lstsq(X_design, sentiment_labels, rcond=None)[0]
    b0, b1 = float(beta[0]), float(beta[1])
    pred = X_design @ beta
    ss_res = np.sum((sentiment_labels - pred) ** 2)
    ss_tot = np.sum((sentiment_labels - np.mean(sentiment_labels)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    print(f'\n  {"=" * 55}')
    print(f'  回归: sentiment = {b0:.4f} + {b1:.4f} × composite')
    print(f'  R² = {r2:.4f}')
    print(f'  (v5: 0.3461 + 0.8168 × composite, R²=0.92 [循环论证虚高])')
    print(f'  {"=" * 55}')

    old_b0, old_b1 = 0.3461, 0.8168
    diffs = []
    for i in range(len(composites)):
        v5_val = old_b0 + old_b1 * composites[i]
        v6_val = b0 + b1 * composites[i]
        diffs.append(abs(v5_val - v6_val))
    print(f'\n  与v5偏差: 平均{np.mean(diffs):.2f} 最大{np.max(diffs):.2f}')

    return {
        'b0': b0, 'b1': b1, 'r2': r2,
        'dates': dates, 'labels': sentiment_labels,
        'composites': composites, 'mapping': mapping
    }


def generate_v6_history(result):
    if result is None:
        print('标定失败, 无法生成历史')
        return

    b0, b1 = result['b0'], result['b1']

    conn = pymysql.connect(**DB)
    cur = conn.cursor()

    try:
        cur.execute("ALTER TABLE market_sentiment ADD COLUMN sentiment_v6 DECIMAL(5,2)")
        conn.commit()
        print('  已添加 market_sentiment.sentiment_v6 列')
    except:
        pass

    cur.execute("SELECT trade_date, composite_idx, sentiment_value FROM market_sentiment ORDER BY trade_date")
    rows = cur.fetchall()
    print(f'  读取 market_sentiment: {len(rows)} 条')

    updated = 0
    for trade_date, composite, old_sv in rows:
        if composite is None:
            continue
        v6_val = b0 + b1 * float(composite)
        v6_val = round(max(-2.5, min(2.5, v6_val)), 2)
        cur.execute(
            "UPDATE market_sentiment SET sentiment_v6=%s WHERE trade_date=%s",
            (v6_val, str(trade_date))
        )
        updated += 1

    conn.commit()
    conn.close()
    print(f'  V6 情绪历史已生成: {updated} 条 → market_sentiment.sentiment_v6')
    print(f'  公式: sentiment_v6 = {b0:.4f} + {b1:.4f} × composite')


def backfill_v6():
    conn = pymysql.connect(**DB)
    cur = conn.cursor()

    b0, b1 = 0.0, 0.8
    try:
        cur.execute("SELECT b0, b1 FROM sentiment_v6_config ORDER BY id DESC LIMIT 1")
        r = cur.fetchone()
        if r:
            b0, b1 = float(r[0]), float(r[1])
            print(f'  读取已保存系数: b0={b0:.4f}, b1={b1:.4f}')
    except:
        print('  无已保存系数, 使用默认值')

    try:
        cur.execute("ALTER TABLE market_sentiment ADD COLUMN sentiment_v6 DECIMAL(5,2)")
        conn.commit()
    except:
        pass

    cur.execute("SELECT trade_date, composite_idx FROM market_sentiment ORDER BY trade_date")
    rows = cur.fetchall()

    updated = 0
    for trade_date, composite in rows:
        if composite is None:
            continue
        v6_val = b0 + b1 * float(composite)
        v6_val = round(max(-2.5, min(2.5, v6_val)), 2)
        cur.execute("UPDATE market_sentiment SET sentiment_v6=%s WHERE trade_date=%s",
                    (v6_val, str(trade_date)))
        updated += 1

    conn.commit()
    conn.close()
    print(f'  回填完成: {updated} 条')


def save_config(result):
    if result is None:
        return
    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sentiment_v6_config (
            id INT AUTO_INCREMENT PRIMARY KEY,
            b0 DECIMAL(10,6), b1 DECIMAL(10,6), r2 DECIMAL(6,4),
            sample_count INT, calibrated_on DATE,
            create_time DATETIME DEFAULT NOW()
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(
        "INSERT INTO sentiment_v6_config (b0, b1, r2, sample_count, calibrated_on) VALUES (%s,%s,%s,%s,%s)",
        (round(result['b0'], 6), round(result['b1'], 6), round(result['r2'], 4),
         len(result['dates']), TODAY)
    )
    conn.commit()
    conn.close()
    print(f'  标定结果已保存到 sentiment_v6_config')


if __name__ == '__main__':
    print(f'V6 情绪标定 | {TODAY}')
    print('=' * 65)

    if '--backfill' in sys.argv:
        backfill_v6()
    else:
        result = calibrate_v6()
        if result and '--store' in sys.argv:
            save_config(result)
            generate_v6_history(result)
        elif result:
            print(f'\n  提示: 使用 --store 将结果写入数据库')
            print(f'  提示: 使用 --backfill 仅回填历史数据')
