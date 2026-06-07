# AI Budget Guard 🛡️

> **AI API 预算守卫** — 实时监控 Token 消耗、缓存命中率异常检测、自动冻结止损。

## 为什么需要它？

2026年6月6日，OpenClaw 6.1 的一个缓存 bug 导致 DeepSeek 用户在一小时内烧掉 **$5.5 USD（¥40+）**，缓存命中率从 50%+ 暴跌至 3%，而用户毫不知情。

本工具能在类似的"静默烧钱"事件发生 **30 秒内**检测并告警/冻结，防止损失扩大。

## 核心功能

| 功能 | 说明 |
|:----|:------|
| 💰 **预算跟踪** | 月度预算上限，分级警告（黄色/红色/冻结） |
| ⚠️ **异常燃烧检测** | 短时间内 token 消耗速率突然飙升（默认 3 倍阈值） |
| 🗄️ **缓存命中预警** | cache_hit_pct < 30% 时自动告警 |
| 🛑 **自动冻结** | 达到上限或检测到异常时，自动建议切换到省钱方案 |
| 🔄 **重试守卫** | `withRetryGuard()` 防止重试循环无限烧钱 |
| 📊 **Session 状态检测** | 接收 `session_status` 输入，实时分析 |

## 快速开始

```bash
# 检查当前状态
python3 scripts/budget.py check '{
  "model": "deepseek/deepseek-v4-flash",
  "tokens_in": 150000,
  "tokens_out": 5000,
  "cache_hit_pct": 96,
  "cost_usd": 0.02
}'

# 查看月预算报告
python3 scripts/budget.py report
```

## 配置

编辑 `references/pricing.yml` 或通过环境变量：

| 变量 | 默认值 | 说明 |
|:----|:------|:-----|
| `BUDGET_MONTHLY_USD` | 7.0 | 月预算上限 (USD) |
| `BUDGET_MONTHLY_CNY` | 50 | 月预算上限 (CNY) |
| `ALERT_RATE_THRESHOLD` | 3.0 | 异常速率倍数阈值 |
| `ALERT_CACHE_MIN` | 30 | 最低缓存命中率 (%) |

## 依赖

- Python 3.8+
- **零外部依赖**（仅标准库）

## License

MIT
