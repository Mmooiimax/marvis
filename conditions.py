"""
尾盘选股 - 七步筛选条件模块
"""
import numpy as np
import pandas as pd


# ═══════════════════════════════════════════════════════════
# 基础计算函数
# ═══════════════════════════════════════════════════════════

def calc_ma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def calc_vwap(df: pd.DataFrame) -> pd.Series:
    """成交量加权均价（从分钟数据计算）"""
    if 'price' not in df.columns or 'volume' not in df.columns:
        return pd.Series(dtype=float)
    cum_amount = (df['price'] * df['volume']).cumsum()
    cum_vol = df['volume'].cumsum()
    vwap = cum_amount / cum_vol.replace(0, np.nan)
    return vwap


# ═══════════════════════════════════════════════════════════
# 第1步：涨幅筛选
# ═══════════════════════════════════════════════════════════

def check_change_pct(change_pct: float, cmin: float, cmax: float) -> tuple:
    """
    涨幅在 3%-5% 之间
    返回: (是否通过, 描述)
    """
    if cmin <= change_pct <= cmax:
        return (True, f'涨幅 {change_pct:+.2f}% ✅')
    elif change_pct < cmin:
        return (False, f'涨幅 {change_pct:+.2f}% ❌（不足 {cmin}%）')
    else:
        return (False, f'涨幅 {change_pct:+.2f}% ❌（超过 {cmax}%）')


# ═══════════════════════════════════════════════════════════
# 第2步：量比筛选
# ═══════════════════════════════════════════════════════════

def check_volume_ratio(ratio: float, ratio_min: float) -> tuple:
    """
    量比 ≥ 1.0：有资金参与
    返回: (是否通过, 描述)
    """
    if ratio >= ratio_min:
        return (True, f'量比 {ratio:.2f} ✅')
    else:
        return (False, f'量比 {ratio:.2f} ❌（< {ratio_min}）')


# ═══════════════════════════════════════════════════════════
# 第3步：换手率筛选
# ═══════════════════════════════════════════════════════════

def check_turnover(turnover: float, tmin: float, tmax: float, exc_st: float = 3.0) -> tuple:
    """
    换手率 5%-10%
    tmin 用于 ST（不同阈值）
    返回: (是否通过, 描述)
    """
    if tmin <= turnover <= tmax:
        return (True, f'换手率 {turnover:.2f}% ✅')
    elif turnover < tmin:
        return (False, f'换手率 {turnover:.2f}% ❌（太低，无人关注）')
    else:
        return (False, f'换手率 {turnover:.2f}% ❌（太高，博弈激烈）')


# ═══════════════════════════════════════════════════════════
# 第4步：流通市值筛选
# ═══════════════════════════════════════════════════════════

def check_market_cap(mcap: float, cap_min: float, cap_max: float) -> tuple:
    """
    流通市值 50亿-200亿
    返回: (是否通过, 描述)
    """
    if cap_min <= mcap <= cap_max:
        return (True, f'流通市值 {mcap:.0f}亿 ✅')
    elif mcap < cap_min:
        return (False, f'流通市值 {mcap:.0f}亿 ❌（< {cap_min}亿，盘子太小）')
    else:
        return (False, f'流通市值 {mcap:.0f}亿 ❌（> {cap_max}亿，盘子偏大）')


# ═══════════════════════════════════════════════════════════
# 第5步：成交量结构（阶梯式温和放量）
# ═══════════════════════════════════════════════════════════

def check_volume_step(kline_df: pd.DataFrame, step_days: int = 5,
                      step_ups: int = 3, max_ratio: float = 3.0) -> tuple:
    """
    近 N 天成交量阶梯式温和放大
    规则：
      - 至少 step_ups 天量能递增
      - 相邻两天量变不超过 max_ratio 倍（防异常巨量）
      - 今天量是 N 天均量的 1.2 倍以上（相对放量）
    返回: (是否通过, 描述, 得分系数 0~1)
    """
    if len(kline_df) < step_days + 1:
        return (False, 'K线数据不足', 0.0)

    vols = kline_df['volume'].iloc[-(step_days + 1):].values

    # 检查阶梯式递增
    up_count = 0
    max_jump = 1.0
    for i in range(len(vols) - step_days, len(vols) - 1):
        prev = vols[i]
        curr = vols[i + 1]
        if curr > prev:
            up_count += 1
        ratio = curr / prev if prev > 0 else 999
        max_jump = max(max_jump, ratio)

    # 今天 vs 均量
    avg_vol = vols[:-1].mean()
    today_ratio = vols[-1] / avg_vol if avg_vol > 0 else 1.0

    if up_count >= step_ups and max_jump <= max_ratio and today_ratio >= 1.2:
        score_coef = min(1.0, (up_count / step_days) * 0.6 + min(today_ratio / 2, 1.0) * 0.4)
        detail = (f'阶梯放量 ✅（{up_count}/{step_days}递增，'
                  f'量比{today_ratio:.1f}x，跳变{max_jump:.1f}x）')
        return (True, detail, score_coef)
    else:
        reasons = []
        if up_count < step_ups:
            reasons.append(f'仅{up_count}天递增')
        if max_jump > max_ratio:
            reasons.append(f'量跳变{max_jump:.1f}x过大')
        if today_ratio < 1.2:
            reasons.append(f'今日相对均量仅{today_ratio:.1f}x')
        return (False, f'成交量异常 ❌（{"; ".join(reasons)}）', 0.0)


# ═══════════════════════════════════════════════════════════
# 第6步：均线多头排列
# ═══════════════════════════════════════════════════════════

def check_ma_bullish(kline_df: pd.DataFrame, min_days: int = 3) -> tuple:
    """
    MA5 > MA10 > MA20 > MA60，连续至少 min_days
    返回: (是否通过, 描述, 发散度 0~1)
    """
    if len(kline_df) < 60 + min_days:
        return (False, 'K线数据不足', 0.0)

    close = kline_df['close'].astype(float)
    ma5 = calc_ma(close, 5)
    ma10 = calc_ma(close, 10)
    ma20 = calc_ma(close, 20)
    ma60 = calc_ma(close, 60)

    # 检查最近 min_days 天是否连续多头排列
    consecutive = 0
    for i in range(len(close) - min_days, len(close)):
        if ma5.iloc[i] > ma10.iloc[i] > ma20.iloc[i] > ma60.iloc[i]:
            consecutive += 1

    if consecutive >= min_days:
        # 发散度 = MA间距 / 当前价格（越大越强势）
        last = -1
        spread = ((ma5.iloc[last] - ma60.iloc[last]) / close.iloc[last]) * 100
        score_coef = min(1.0, spread / 10)  # 10%发散度 = 满分
        return (True, f'均线多头 ✅（已{consecutive}天，发散{spread:.1f}%）', score_coef)
    else:
        return (False, f'均线未形成多头排列 ❌（仅{consecutive}天）', 0.0)


# ═══════════════════════════════════════════════════════════
# 第7步：分时强势分析
# ═══════════════════════════════════════════════════════════

def check_intraday_strength(minute_df: pd.DataFrame,
                            index_minute_df: pd.DataFrame = None,
                            above_ratio: float = 0.7,
                            stronger_index: bool = True) -> tuple:
    """
    股价始终在 VWAP 均价线上方且强于大盘
    返回: (是否通过, 描述, 得分系数 0~1)
    """
    if minute_df is None or minute_df.empty:
        return (False, '分时数据缺失', 0.0)

    # 确保有 price 列；mootdx 可能用不同命名
    price_col = 'price' if 'price' in minute_df.columns else minute_df.columns[1]
    vol_col = 'volume' if 'volume' in minute_df.columns else minute_df.columns[2]

    df = minute_df.copy()
    df['price'] = pd.to_numeric(df[price_col], errors='coerce')
    df['volume'] = pd.to_numeric(df[vol_col], errors='coerce')
    df = df.dropna(subset=['price'])

    if len(df) < 10:
        return (False, '分时数据不足', 0.0)

    # 计算 VWAP
    vwap = calc_vwap(df[['price', 'volume']])

    # 计算价格在 VWAP 上方的时间占比（取后 80% 数据，忽略开盘前几分钟）
    tail_start = max(0, int(len(df) * 0.2))
    above = (df['price'].iloc[tail_start:].values > vwap.iloc[tail_start:].values).sum()
    total = len(df) - tail_start
    above_pct = above / total if total > 0 else 0.0

    # 计算涨幅稳定性（价格波动率是否小）
    returns = df['price'].pct_change().dropna().iloc[tail_start:]
    stability = 1.0 - min(1.0, returns.std() * 100)  # 波动越小越稳定

    vwap_pass = above_pct >= above_ratio

    detail_parts = [f'均价线上方 {above_pct:.0%}']

    # 强于大盘判断
    index_stronger = False
    index_coef = 0.0
    if stronger_index and index_minute_df is not None and not index_minute_df.empty:
        idx_price_col = 'price' if 'price' in index_minute_df.columns else index_minute_df.columns[1]
        idx_prices = pd.to_numeric(index_minute_df[idx_price_col], errors='coerce').dropna()

        if len(idx_prices) > 1:
            stock_return = (df['price'].iloc[-1] / df['price'].iloc[0] - 1)
            idx_return = (idx_prices.iloc[-1] / idx_prices.iloc[0] - 1)
            relative = (stock_return - idx_return) * 100
            index_stronger = stock_return > idx_return
            detail_parts.append(f'相对大盘 {relative:+.2f}%')
            index_coef = min(1.0, max(0, relative / 3))  # 跑赢 3% = 满分

    if vwap_pass:
        score_coef = above_pct * 0.5 + stability * 0.3 + index_coef * 0.2
        detail_parts.append('✅')
        return (True, ' | '.join(detail_parts), score_coef)
    else:
        detail_parts.append('❌')
        return (False, ' | '.join(detail_parts), 0.0)


# ═══════════════════════════════════════════════════════════
# 附：尾盘买入信号（14:30 附近创新高 + 回踩不破）
# ═══════════════════════════════════════════════════════════

def check_tail_entry_signal(minute_df: pd.DataFrame) -> tuple:
    """
    14:30 左右创当天新高，且回踩 VWAP 均线不破
    返回: (是否触发, 描述, 得分系数)
    """
    if minute_df is None or minute_df.empty or len(minute_df) < 30:
        return (False, '数据不足', 0.0)

    price_col = 'price' if 'price' in minute_df.columns else minute_df.columns[1]
    vol_col = 'volume' if 'volume' in minute_df.columns else minute_df.columns[2]

    df = minute_df.copy()
    df['price'] = pd.to_numeric(df[price_col], errors='coerce')
    df['volume'] = pd.to_numeric(df[vol_col], errors='coerce')
    df = df.dropna(subset=['price'])

    if len(df) < 30:
        return (False, '数据不足', 0.0)

    vwap = calc_vwap(df[['price', 'volume']])

    # 取后 50% 数据（模拟 11:00-15:00 时段）
    half = len(df) // 2
    tail = df.iloc[half:]
    tail_vwap = vwap.iloc[half:]

    # 找最高点时间
    high_idx = tail['price'].idxmax() if hasattr(tail['price'], 'idxmax') else tail['price'].values.argmax() + half
    high_price = df['price'].iloc[high_idx]

    # 最高点之后的最低点
    after_high = df.iloc[high_idx:]
    if len(after_high) < 2:
        return (False, '数据不足以判断回踩', 0.0)

    after_low = after_high['price'].min()

    # 判断是否回踩均线不破
    vwap_at_low = vwap.iloc[after_high['price'].idxmin()] \
        if hasattr(after_high['price'], 'idxmin') else vwap.iloc[-1]
    bounce_off_vwap = after_low >= vwap_at_low * 0.99  # 允许 1% 误差

    # 收盘价接近高点（高位横盘）
    last_price = df['price'].iloc[-1]
    near_high = last_price >= high_price * 0.98

    if bounce_off_vwap and near_high:
        pullback_pct = (high_price - after_low) / high_price * 100
        return (True, f'尾盘买入信号 🎯（新高+回踩{pullback_pct:.1f}%+VWAP支撑）', 0.8)
    elif bounce_off_vwap:
        return (False, f'有VWAP支撑但未保持高位', 0.3)
    elif near_high:
        return (False, f'高位横盘但未确认VWAP支撑', 0.3)
    else:
        return (False, '无尾盘买入信号', 0.0)


# ═══════════════════════════════════════════════════════════
# 综合七步筛选入口
# ═══════════════════════════════════════════════════════════

def screen_seven_steps(stock: dict,
                       quote: dict,
                       kline_df: pd.DataFrame,
                       minute_df: pd.DataFrame,
                       index_minute_df: pd.DataFrame,
                       cfg: dict) -> dict:
    """
    执行七步筛选，返回完整结果字典。

    stock      = {'code': '600519', 'name': '贵州茅台', 'market': 0}
    quote      = real-time quote dict (from mootdx)
    kline_df   = 日K线 DataFrame
    minute_df  = 当日分钟K线 DataFrame
    index_minute_df = 上证指数分钟K线 DataFrame
    cfg        = FILTER 配置

    返回: {
        'passed': bool,
        'score': int,
        'steps': {1: {...}, 2: {...}, ...},
        'entry_signal': {...},
        'summary': str,
    }
    """
    result = {
        'passed': True,
        'score': 0,
        'steps': {},
        'entry_signal': None,
        'summary': '',
        'stock': stock,
        'quote': quote,
    }

    weights = {
        'volume_step': 20,
        'ma_bullish': 20,
        'above_vwap': 15,
        'stronger_index': 15,
        'volume_ratio': 10,
        'new_high_signal': 10,
        'change_stability': 10,
    }

    # ── Step 1: 涨幅 ──
    change_pct = quote.get('change_pct', quote.get('涨跌幅', 0))
    passed, desc = check_change_pct(change_pct, cfg['change_pct_min'], cfg['change_pct_max'])
    result['steps'][1] = {'passed': passed, 'desc': desc}
    if not passed:
        result['passed'] = False
        return result
    # 涨幅稳定性：越接近中间值越好
    stability = 1.0 - abs(change_pct - 4.0) / 1.0  # 4% 是最优
    result['score'] += int(weights['change_stability'] * max(0, stability))

    # ── Step 2: 量比 ──
    vol_ratio = quote.get('volume_ratio', quote.get('量比', 0))
    passed, desc = check_volume_ratio(vol_ratio, cfg['volume_ratio_min'])
    result['steps'][2] = {'passed': passed, 'desc': desc}
    if not passed:
        result['passed'] = False
        return result
    result['score'] += int(weights['volume_ratio'] * min(1.0, vol_ratio / 3))

    # ── Step 3: 换手率 ──
    turnover = quote.get('turnover_rate', quote.get('换手率', 0))
    passed, desc = check_turnover(turnover, cfg['turnover_min'], cfg['turnover_max'])
    result['steps'][3] = {'passed': passed, 'desc': desc}
    if not passed:
        result['passed'] = False
        return result

    # ── Step 4: 流通市值 ──
    mcap = quote.get('market_cap', quote.get('流通市值', 0))
    # mootdx 返回的市值单位可能是元，转为亿
    if mcap > 100000:
        mcap = mcap / 1e8
    passed, desc = check_market_cap(mcap, cfg['market_cap_min'], cfg['market_cap_max'])
    result['steps'][4] = {'passed': passed, 'desc': desc}
    if not passed:
        result['passed'] = False
        return result

    # ── Step 5: 成交量结构 ──
    passed, desc, coef = check_volume_step(
        kline_df, cfg['volume_step_days'], cfg['volume_step_ups'], cfg['volume_step_max_ratio']
    )
    result['steps'][5] = {'passed': passed, 'desc': desc}
    if not passed:
        result['passed'] = False
        return result
    result['score'] += int(weights['volume_step'] * coef)

    # ── Step 6: 均线多头 ──
    passed, desc, coef = check_ma_bullish(kline_df, cfg['ma_multiline_days'])
    result['steps'][6] = {'passed': passed, 'desc': desc}
    if not passed:
        result['passed'] = False
        return result
    result['score'] += int(weights['ma_bullish'] * coef)

    # ── Step 7: 分时强势 ──
    passed, desc, coef = check_intraday_strength(
        minute_df, index_minute_df, cfg['above_vwap_ratio'], cfg['stronger_than_index']
    )
    result['steps'][7] = {'passed': passed, 'desc': desc}
    if not passed:
        result['passed'] = False
        return result
    result['score'] += int(weights['above_vwap'] * coef)

    # ── 附：尾盘买入信号 ──
    sig, sig_desc, sig_coef = check_tail_entry_signal(minute_df)
    result['entry_signal'] = {'triggered': sig, 'desc': sig_desc}
    if sig:
        result['score'] += int(weights['new_high_signal'] * sig_coef)

    # 生成摘要
    passed_steps = [k for k, v in result['steps'].items() if v['passed']]
    result['summary'] = f"通过{len(passed_steps)}/7步 | 得分{result['score']}"

    return result
（内容由AI生成，仅供参考）
