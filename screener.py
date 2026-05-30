#!/usr/bin/env python3
"""
尾盘选股 - 主脚本
每个交易日 14:30 自动运行，七步筛选 + 微信推送
数据源: mootdx（通达信协议）
"""
import os
import sys
import time
import traceback
from datetime import datetime, date

import pandas as pd
from mootdx.quotes import Quotes

import config
from conditions import screen_seven_steps
from notify import format_message, send_wechat

# ═══════════════════════════════════════════════════════════
# 交易日检查
# ═══════════════════════════════════════════════════════════

def is_trading_day() -> bool:
    """判断今天是否 A 股交易日"""
    try:
        from chinese_calendar import is_workday
        return is_workday(date.today())
    except ImportError:
        # 无 chinese_calendar 时，仅判断周一至周五
        return date.today().weekday() < 5


# ═══════════════════════════════════════════════════════════
# 股票列表获取与过滤
# ═══════════════════════════════════════════════════════════

def get_stock_list(client: Quotes) -> list:
    """获取 A 股列表，排除 ST/*ST/科创板/北交所"""
    all_stocks = []
    for market in [0, 1]:  # 0=上海, 1=深圳
        try:
            df = client.stocks(market=market)
            if df is None or df.empty:
                continue

            for _, row in df.iterrows():
                code = str(row.get('code', '')).zfill(6)
                name = str(row.get('name', '')).strip()
                if not code or not name:
                    continue

                # 排除科创板 688
                if config.EXCLUDE_KCB and code.startswith('688'):
                    continue
                # 排除北交所 8/4
                if config.EXCLUDE_BSE and (code.startswith('8') or code.startswith('4')):
                    continue
                # 排除 ST
                if config.EXCLUDE_ST and ('ST' in name.upper()):
                    continue

                all_stocks.append({
                    'code': code,
                    'name': name,
                    'market': market,
                })
        except Exception as e:
            print(f"[WARN] 获取 market={market} 股票列表失败: {e}")

    print(f"[INFO] 股票池: {len(all_stocks)} 只（已排除ST/科创/北交）")
    return all_stocks


# ═══════════════════════════════════════════════════════════
# 实时行情批量获取
# ═══════════════════════════════════════════════════════════

def get_quotes_batch(client: Quotes, stocks: list, batch_size: int = 80) -> dict:
    """
    批量获取实时行情。
    返回: {code: {...quote fields...}}
    """
    quotes = {}
    codes = [s['code'] for s in stocks]
    total = len(codes)

    for i in range(0, total, batch_size):
        batch = codes[i:i + batch_size]
        try:
            df = client.quotes(symbol=batch)
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    code = str(row.get('code', '')).zfill(6)
                    if code:
                        quotes[code] = row.to_dict()
        except Exception as e:
            print(f"[WARN] 行情批次 {i}-{i+batch_size} 失败: {e}")
        time.sleep(0.5)

    print(f"[INFO] 实时行情: {len(quotes)} 只")
    return quotes


# ═══════════════════════════════════════════════════════════
# K 线批量获取（仅对通过前4步的候选股）
# ═══════════════════════════════════════════════════════════

def get_kline(client: Quotes, code: str, market: int, count: int = 120) -> pd.DataFrame:
    """获取单只股票的日 K 线"""
    try:
        df = client.bars(symbol=code, frequency=9, offset=0, count=count)
        if df is not None and not df.empty and len(df) >= 60:
            return df
    except Exception:
        pass
    return pd.DataFrame()


# ═══════════════════════════════════════════════════════════
# 分时数据获取
# ═══════════════════════════════════════════════════════════

def get_minute_data(client: Quotes, code: str, today: str) -> pd.DataFrame:
    """获取当日分钟 K 线"""
    try:
        df = client.minutes(symbol=code, date=today)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    return pd.DataFrame()


def get_index_minute(client: Quotes, index_code: str, today: str) -> pd.DataFrame:
    """获取指数分钟 K 线"""
    try:
        df = client.index_minutes(symbol=index_code, date=today)
        if df is not None and not df.empty:
            return df
    except Exception:
        # 有些版本的 mootdx index_minutes 可能不存在，尝试 minutes
        try:
            df = client.minutes(symbol=index_code, date=today)
            if df is not None and not df.empty:
                return df
        except Exception:
            pass
    return pd.DataFrame()


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════

def main():
    print(f"\n{'=' * 60}")
    print(f"  尾盘选股 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")

    # ── 交易日检查 ──
    if not is_trading_day():
        print("[INFO] 今日非交易日，跳过选股。")
        return

    # ── 连接通达信 ──
    print("\n[1/8] 连接通达信行情...")
    try:
        client = Quotes.factory(market='std', bestip=True, timeout=15)
    except Exception as e:
        print(f"[FATAL] 连接通达信失败: {e}")
        send_wechat(f"❌ 尾盘选股异常\n连接通达信服务器失败: {e}")
        return
    print("[OK] 连接成功")

    # ── 获取股票列表 ──
    print("\n[2/8] 获取 A 股列表...")
    stocks = get_stock_list(client)
    if not stocks:
        send_wechat("⚠️ 尾盘选股：未能获取股票列表")
        return

    # ── 获取实时行情 ──
    print("\n[3/8] 批量获取实时行情...")
    quotes = get_quotes_batch(client, stocks)
    if not quotes:
        send_wechat("⚠️ 尾盘选股：未能获取实时行情数据")
        return

    # ── 第1-4步快速初筛（涨幅/量比/换手率/市值）──
    print("\n[4/8] 执行第1-4步初筛...")
    candidates = []
    for s in stocks:
        code = s['code']
        if code not in quotes:
            continue
        q = quotes[code]

        change_pct = float(q.get('change_pct', q.get('涨跌幅', 0)))
        vol_ratio = float(q.get('volume_ratio', q.get('量比', 0)))
        turnover = float(q.get('turnover_rate', q.get('换手率', 0)))
        mcap = float(q.get('market_cap', q.get('流通市值', q.get('circ_mv', 0))))
        if mcap > 100000:
            mcap = mcap / 1e8

        # Step 1: 涨幅 3-5%
        if not (config.FILTER['change_pct_min'] <= change_pct <= config.FILTER['change_pct_max']):
            continue
        # Step 2: 量比 >= 1
        if vol_ratio < config.FILTER['volume_ratio_min']:
            continue
        # Step 3: 换手率 5-10%
        if not (config.FILTER['turnover_min'] <= turnover <= config.FILTER['turnover_max']):
            continue
        # Step 4: 流通市值 50-200亿
        if not (config.FILTER['market_cap_min'] <= mcap <= config.FILTER['market_cap_max']):
            continue

        candidates.append(s)

    print(f"[INFO] 第1-4步初筛通过: {len(candidates)} 只")

    if not candidates:
        # 无候选股，也要发微信
        print("[RESULT] 无候选股，发送通知...")
        msg = format_message([])
        send_wechat(msg)
        return

    # ── 获取 K 线（仅候选股）──
    print(f"\n[5/8] 获取 {len(candidates)} 只候选股日K线...")
    kline_cache = {}
    today_str = datetime.now().strftime('%Y%m%d')

    for s in candidates:
        df = get_kline(client, s['code'], s['market'])
        if not df.empty:
            kline_cache[s['code']] = df
        time.sleep(0.15)

    print(f"[INFO] K线缓存: {len(kline_cache)} 只")

    # ── 获取上证指数分时 ──
    print(f"\n[6/8] 获取上证指数分时数据...")
    index_minute_df = get_index_minute(client, config.FILTER['index_code'], today_str)
    if index_minute_df.empty:
        print("[WARN] 上证指数分时数据获取失败，跳过第7步大盘比较")

    # ── 第5-7步深度筛选 ──
    print(f"\n[7/8] 执行第5-7步深度筛选...")
    results = []

    for s in candidates:
        code = s['code']
        if code not in kline_cache:
            continue
        kline_df = kline_cache[code]

        # 获取分时
        minute_df = get_minute_data(client, code, today_str)
        if minute_df.empty and len(results) < 5:  # 前几个没分时数据也宽容
            pass

        result = screen_seven_steps(
            stock=s,
            quote=quotes[code],
            kline_df=kline_df,
            minute_df=minute_df,
            index_minute_df=index_minute_df,
            cfg=config.FILTER,
        )
        results.append(result)
        time.sleep(0.1)

    # 按得分排序
    results.sort(key=lambda r: r['score'], reverse=True)

    passed_count = sum(1 for r in results if r['passed'])
    print(f"\n{'=' * 60}")
    print(f"  筛 选 完 成")
    print(f"  候选: {len(candidates)} → 通过: {passed_count}")
    print(f"{'=' * 60}")

    # 打印结果
    for i, r in enumerate(results):
        if r['passed']:
            s = r['stock']
            q = r['quote']
            cp = q.get('change_pct', q.get('涨跌幅', 0))
            print(f"  {i+1:2d}. {s['name']:8s} {s['code']}  "
                  f"涨幅{cp:+.2f}%  得分{r['score']:3d}  {r['summary']}")

    # ── 发送微信 ──
    print(f"\n[8/8] 推送企业微信...")
    msg = format_message(results)
    print(msg)  # 同时打印到日志
    success = send_wechat(msg)
    print(f"[{'OK' if success else 'FAIL'}] 推送{'成功' if success else '失败'}")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        send_wechat(f"❌ 尾盘选股异常\n{datetime.now().strftime('%Y-%m-%d %H:%M')}\n错误: {str(e)[:200]}")
        sys.exit(1)
（内容由AI生成，仅供参考）
