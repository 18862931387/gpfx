# 新闻情绪因子模块
# python news_sentiment.py          # 抓取今日新闻 + 存入DB
# python news_sentiment.py --test   # 只打分，不存储
# from news_sentiment import get_daily_news_sentiment  # 导入使用

import sys, os, requests, datetime, re, pymysql
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from config import DB, HDR

POS_KW = [
    '利好', '涨停', '突破', '大涨', '反弹', '增长', '政策支持',
    '刺激', '扩产', '分红', '回购', '增持', '盈利', '新高',
    '改善', '复苏', '超预期', '签约', '合作', '投资', '研发',
    '创新', '获批', '中标', '订单', '放量', '拐点', '加仓',
    '净流入', '降息', '降准', '宽松', '维稳',
]
NEG_KW = [
    '利空', '跌停', '暴跌', '下跌', '崩盘', '危机', '制裁',
    '处罚', '查处', '监管', '立案', '风险', '警告', '萎缩',
    '衰退', '亏损', '减持', '套现', '破产', '违约', '退市',
    '诉讼', '爆雷', '下滑', '预亏', '踩雷', 'ST', 'ST',
    '净流出', '加息', '收紧', '去杠杆', '暴雷',
    '索赔', '起诉', '调查', '问询', '冻结', '跌超',
    '停牌', '重组失败', '终止', '暂停', '巨额亏损',
]

SINA_LIDS = {
    '2510': '宏观财经',
    '2515': 'A股市场',
    '2516': '科技产经',
}


def score_article(title):
    """对单条新闻标题打分, 返回 (score, pos_matches, neg_matches)"""
    title_lower = title.lower()
    pos_match = [kw for kw in POS_KW if kw in title]
    neg_match = [kw for kw in NEG_KW if kw in title]
    total = len(pos_match) + len(neg_match)
    if total == 0:
        return 0.0, [], []
    score = (len(pos_match) - len(neg_match)) / total * 2.0
    return round(score, 2), pos_match, neg_match


def fetch_news():
    """从新浪财经抓取今日头条, 返回 [(title, url, source, score, pos, neg), ...]"""
    today = datetime.date.today().isoformat()
    articles = {}
    for lid, label in SINA_LIDS.items():
        try:
            url = f'https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid={lid}&num=30'
            r = requests.get(url, headers=HDR, timeout=10)
            items = r.json().get('result', {}).get('data', [])
            for item in items:
                title = (item.get('title', '') or '').strip()
                if not title or len(title) < 6:
                    continue
                # 用标题去重
                if title in articles:
                    continue
                score, pos, neg = score_article(title)
                articles[title] = (
                    item.get('url', ''),
                    item.get('media_name', label),
                    score, ','.join(pos), ','.join(neg),
                )
        except Exception as e:
            print(f'  [WARN] lid={lid} ({label}): {e}')
    result = [(k, v[0], v[1], v[2], v[3], v[4]) for k, v in articles.items()]
    result.sort(key=lambda x: x[3], reverse=True)
    return result, today


def get_daily_news_sentiment():
    """计算当日新闻情绪综合分 (-2.0 ~ +2.0)"""
    articles, today = fetch_news()
    if not articles:
        return 0.0

    # 加权: 高绝对值文章权重更高
    total_w = 0.0
    total_s = 0.0
    for _, _, _, score, _, _ in articles:
        w = abs(score) + 0.5  # 中性文章权重低(0.5), 极端文章权重高
        total_s += score * w
        total_w += w
    return round(total_s / total_w, 2) if total_w > 0 else 0.0


def save_to_db(articles, today):
    """将新闻存入 market_news 表"""
    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    # 先清今日旧数据
    cur.execute("DELETE FROM market_news WHERE trade_date=%s", (today,))
    count = 0
    for title, url, source, score, pos, neg in articles:
        cur.execute(
            "INSERT INTO market_news (trade_date,title,url,source,sentiment_score,pos_words,neg_words) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (today, title[:500], url[:500] if url else None, source[:100], score,
             pos if pos else None, neg if neg else None),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def read_sentiment_from_db():
    """从 DB 读取当日新闻情绪综合分"""
    today = datetime.date.today().isoformat()
    try:
        conn = pymysql.connect(**DB)
        cur = conn.cursor()
        # 尝试今日
        cur.execute("SELECT sentiment_score FROM market_news WHERE trade_date=%s AND sentiment_score IS NOT NULL", (today,))
        rows = cur.fetchall()
        if not rows:
            # 退到最近一天
            cur.execute("SELECT sentiment_score FROM market_news WHERE sentiment_score IS NOT NULL ORDER BY trade_date DESC LIMIT 30")
            rows = cur.fetchall()
        conn.close()
        if rows:
            scores = [float(r[0]) for r in rows]
            return round(sum(scores) / len(scores), 2)
    except:
        pass
    return 0.0


# ── CLI ──
if __name__ == '__main__':
    is_test = '--test' in sys.argv
    articles, today = fetch_news()
    print(f'\n=== {today} 新闻情绪分析 ({len(articles)}条) ===')
    aggregate = 0.0
    if articles:
        total_w = sum(abs(s) + 0.5 for _, _, _, s, _, _ in articles)
        aggregate = sum(s * (abs(s) + 0.5) for _, _, _, s, _, _ in articles) / total_w
    print(f'  综合情绪分: {aggregate:+.2f}  (-2 恐慌 ~ +2 亢奋)\n')

    for title, _, src, score, pos, neg in articles[:15]:
        marker = '🟢' if score > 0.3 else ('🔴' if score < -0.3 else '⚪')
        print(f'  {marker} [{score:+.1f}] {title[:65]}')
        if pos:
            print(f'     利好词: {pos}')
        if neg:
            print(f'     利空词: {neg}')

    if not is_test:
        n = save_to_db(articles, today)
        print(f'\n  已存入 market_news ({n}条)')
