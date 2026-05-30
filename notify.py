"""
尾盘选股 - 企业微信推送模块
"""
import json
import requests
from datetime import datetime

import config


def format_message(results: list) -> str:
    """
    格式化选股结果为微信消息。

    results: [screen_seven_steps() 返回的 dict, ...]，按 score 降序排列
    """
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    total = len([r for r in results if r['passed']])

    lines = [
        f"🔍 尾盘选股结果",
        f"📅 {now}",
        f"━━━━━━━━━━━━━━━━━━",
    ]

    if total == 0:
        lines.append("")
        lines.append("⚠️ 今日无符合条件的股票")
        lines.append("")
        lines.append("七步筛选条件：")
        lines.append("  ① 涨幅 3%-5%")
        lines.append("  ② 量比 ≥ 1.0")
        lines.append("  ③ 换手率 5%-10%")
        lines.append("  ④ 流通市值 50-200亿")
        lines.append("  ⑤ 阶梯式温和放量")
        lines.append("  ⑥ 均线多头排列")
        lines.append("  ⑦ 分时强势（VWAP上方70%+强于大盘）")
        lines.append("")
        lines.append("📌 明天继续监测")
        return '\n'.join(lines)

    show_count = min(total, config.MAX_PUSH)
    passed_results = [r for r in results if r['passed']][:show_count]

    lines.append(f"✅ 选出 {total} 只 | 展示 {show_count} 只")
    lines.append("")

    for i, r in enumerate(passed_results, 1):
        s = r['stock']
        q = r['quote']
        change_pct = q.get('change_pct', q.get('涨跌幅', 0))
        turnover = q.get('turnover_rate', q.get('换手率', 0))
        vol_ratio = q.get('volume_ratio', q.get('量比', 0))
        price = q.get('price', q.get('最新价', 0))
        mcap = q.get('market_cap', q.get('流通市值', 0))
        if mcap > 100000:
            mcap = mcap / 1e8

        sign = '+' if change_pct > 0 else ''
        lines.append(f"{'🥇' if i == 1 else '🥈' if i == 2 else '🥉' if i == 3 else f'{i}.'} "
                     f"{s['name']}({s['code']})")
        lines.append(f"   涨幅: {sign}{change_pct:.2f}% | "
                     f"量比: {vol_ratio:.2f} | "
                     f"换手: {turnover:.2f}%")
        lines.append(f"   市值: {mcap:.0f}亿 | "
                     f"现价: {price:.2f} | "
                     f"得分: {r['score']}")

        # 步骤摘要
        step_summary = []
        for step_num in [5, 6, 7]:
            if step_num in r['steps'] and r['steps'][step_num]['passed']:
                tag = {5: '阶梯放量', 6: '均线多头', 7: '分时强势'}[step_num]
                step_summary.append(tag)
        if r.get('entry_signal') and r['entry_signal']['triggered']:
            step_summary.append('尾盘买点')
        if step_summary:
            lines.append(f"   ✨ {' | '.join(step_summary)}")

        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(f"⏰ 筛选时间: {now}")
    lines.append(f"📊 策略: 七步尾盘选股法")
    lines.append("")
    lines.append("⚠️ 以上结果仅通过技术指标筛选，不构成投资建议。")
    lines.append("   进场时机：14:30 创新高 + 回踩均线不破 = 低吸机会。")

    return '\n'.join(lines)


def send_wechat(content: str) -> bool:
    """
    发送消息到企业微信机器人。
    返回: True=成功 / False=失败
    """
    webhook = config.WECHAT_WEBHOOK
    if not webhook:
        print("[WARN] 未配置企业微信 WECHAT_WEBHOOK_URL")
        return False

    # 超长消息分段发送（企业微信单条上限 2048 字节）
    max_len = 2000  # 留一些余量
    if len(content.encode('utf-8')) <= max_len:
        return _send_one(webhook, content)

    # 分段发送
    lines = content.split('\n')
    chunks = []
    current = []
    current_len = 0

    for line in lines:
        line_len = len(line.encode('utf-8')) + 1
        if current_len + line_len > max_len and current:
            chunks.append('\n'.join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len

    if current:
        chunks.append('\n'.join(current))

    success = True
    for i, chunk in enumerate(chunks):
        prefix = f"[{i+1}/{len(chunks)}]\n" if len(chunks) > 1 else ""
        if not _send_one(webhook, prefix + chunk):
            success = False

    return success


def _send_one(webhook: str, content: str) -> bool:
    """发送单条消息"""
    payload = {
        "msgtype": "text",
        "text": {"content": content}
    }
    try:
        resp = requests.post(webhook, json=payload, timeout=10)
        result = resp.json()
        if resp.status_code == 200 and result.get('errcode') == 0:
            return True
        else:
            print(f"[ERROR] 微信推送失败: {result}")
            return False
    except Exception as e:
        print(f"[ERROR] 微信推送异常: {e}")
        return False
（内容由AI生成，仅供参考）
