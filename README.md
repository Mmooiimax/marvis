---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 8432f6f29525aa9d6b7b46ddffafdbe6_6cf99e5d5be811f19299525400d9a7a1
    ReservedCode1: q/VLISDim7U26OUUy6aww2SFyt4ZliCmrGPxsuGIqYNELrEf6KqKBUtEbIs5kV3mbnq9Ii5lPiEH1afKdNvaftxpFwAZk4ePo0wGbi4k7sGGbGlVFkol6x9TIK2GmyA5XHO+5rTeuVDP97dOT/wc2+slqQB/fVw6+bhG4e82vKB6qhKj7AbTHZJUgwU=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 8432f6f29525aa9d6b7b46ddffafdbe6_6cf99e5d5be811f19299525400d9a7a1
    ReservedCode2: q/VLISDim7U26OUUy6aww2SFyt4ZliCmrGPxsuGIqYNELrEf6KqKBUtEbIs5kV3mbnq9Ii5lPiEH1afKdNvaftxpFwAZk4ePo0wGbi4k7sGGbGlVFkol6x9TIK2GmyA5XHO+5rTeuVDP97dOT/wc2+slqQB/fVw6+bhG4e82vKB6qhKj7AbTHZJUgwU=
---

# 尾盘选股 Skill

每个交易日 **14:30** 自动运行，基于通达信实时数据（mootdx），执行七步筛选后推送到企业微信。

## 一、七步筛选逻辑

| 步骤 | 条件 | 阈值 | 原理 |
|------|------|------|------|
| ① 涨幅 | 3%-5% | 涨太少无资金，涨太多易砸盘 |
| ② 量比 | ≥ 1.0 | 无量股次日难冲高 |
| ③ 换手率 | 5%-10% | 太低无人关注，太高博弈激烈 |
| ④ 流通市值 | 50-200亿 | 中小盘最易被游资盯上 |
| ⑤ 成交量结构 | 阶梯式温和放量 | 避免忽大忽小的坑票 |
| ⑥ K线形态 | 均线多头排列 MA5>MA10>MA20>MA60 | 趋势健康无压力 |
| ⑦ 分时图 | VWAP上方≥70% + 强于大盘 | 逆势拉升有资金 |

**进场细节**：14:30 左右创当天新高且回踩均线不破 = 低吸机会。

## 二、部署步骤

### 第1步：准备企业微信 Webhook

参考之前教程，在企业微信创建群聊 → 添加自定义机器人 → 复制 Webhook 地址。

### 第2步：创建 GitHub 仓库

```bash
# 在 GitHub 上新建仓库，如 tail_stock_screener
# 将本目录所有文件上传到仓库根目录
```

### 第3步：配置 Secret

```
Settings → Secrets and variables → Actions → New repository secret

Name:  WECHAT_WEBHOOK_URL
Value: 你的企业微信 Webhook 地址
```

### 第4步：启用 Actions

```
Actions → I understand my workflows, go ahead and enable them
```

### 第5步：手动测试

```
Actions → 尾盘选股 → Run workflow → Run workflow
```

## 三、修改筛选条件

编辑 `config.py`：

```python
FILTER = {
    'change_pct_min': 3.0,    # 调低/调高涨幅底线
    'change_pct_max': 5.0,
    'volume_ratio_min': 1.0,
    'turnover_min': 5.0,      # 换手率底线
    'turnover_max': 10.0,
    'market_cap_min': 50,     # 市值底线（亿）
    'market_cap_max': 200,
    ...
}
```

## 四、运行时间

- **自动**：周一至周五 14:30（北京时间）
- **手动**：Actions 页面随时触发
- **非交易日**：自动跳过（基于 chinese_calendar）

## 五、文件结构

```
tail_stock_screener/
├── screener.py              # 主脚本
├── conditions.py            # 七步筛选条件
├── config.py                # 可调参数
├── notify.py                # 微信推送
├── requirements.txt         # Python 依赖
└── .github/workflows/
    └── screen.yml           # GitHub Actions 定时
```

## 六、注意事项

- **不构成投资建议**：仅基于技术指标筛选，需人工二次验证
- **数据延迟**：通达信免费数据约 3-5 秒延迟
- **免费额度**：GitHub Actions 每月 2000 分钟，每天运行约 5 分钟，完全够用
*（内容由AI生成，仅供参考）*
