def calc_sentiment(sh_pct, sz_pct, cy_pct, kc_pct):
    avg = sh_pct * 0.4 + sz_pct * 0.3 + cy_pct * 0.2 + kc_pct * 0.1
    if avg >= 2.5:        return 2.2, '沸点'
    elif avg >= 1.5:      return 1.5, '过热'
    elif avg >= 1.0:      return 1.2, '过热'
    elif avg >= 0.5:      return 0.6, '微热'
    elif avg >= 0.2:      return 0.3, '微热'
    elif avg >= -0.2:     return 0,   '0分界'
    elif avg >= -0.8:     return -0.4, '微冷'
    elif avg >= -1.5:     return -1.2, '过冷'
    elif avg >= -2.5:     return -1.8, '过冷'
    else:                 return -2.1, '冰点'

def calc_sentiment_v2(sh_pct, limit_up, limit_down):
    base_val, zone = calc_sentiment(sh_pct, 0, 0, 0)
    if limit_up and limit_down:
        ratio = limit_up / max(limit_down, 1)
        if ratio > 3:
            base_val += 0.3
        elif ratio < 0.5:
            base_val -= 0.3
    base_val = max(-2.5, min(2.5, base_val))
    if base_val >= 2.0:   zone = '沸点'
    elif base_val >= 1.0: zone = '过热'
    elif base_val >= 0.1: zone = '微热'
    elif base_val > -0.1: zone = '0分界'
    elif base_val >= -0.9:zone = '微冷'
    elif base_val >= -1.9:zone = '过冷'
    else:                zone = '冰点'
    return round(base_val, 2), zone

def calc_sentiment_v3(sh_pct, limit_up, limit_down, turnover, main_force_net):
    val, zone = calc_sentiment_v2(sh_pct, limit_up, limit_down)
    if turnover:
        if turnover > 25000 and val != 0:
            val += 0.2 if val > 0 else -0.2
        elif turnover < 18000:
            val = val * 0.7
    if main_force_net:
        if main_force_net > 200_0000_0000 and val > 0:
            val += 0.2
        elif main_force_net < -200_0000_0000 and val < 0:
            val -= 0.2
    val = max(-2.5, min(2.5, val))
    if val >= 2.0:   zone = '沸点'
    elif val >= 1.0: zone = '过热'
    elif val >= 0.1: zone = '微热'
    elif val > -0.1: zone = '0分界'
    elif val >= -0.9:zone = '微冷'
    elif val >= -1.9:zone = '过冷'
    else:            zone = '冰点'
    return round(val, 2), zone
