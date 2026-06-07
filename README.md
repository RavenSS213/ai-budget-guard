# AI Budget Guard 🛡️

> **AI API 预算守卫** — 实时监控 Token 消耗、缓存命中率异常检测、预测性耗尽警告、自动冻结止损。

## 为什么需要它？

2026年6月6日，OpenClaw 6.1 的一个缓存 bug 导致 DeepSeek 用户在一小时内烧掉 **$5.5 USD（¥40+）**，缓存命中率从 50%+ 暴跌至 3%，而用户毫不知情。

更可怕的是预测值——如果按 GPT-4o 价格，同样场景一小时烧 **$7,800**；按 Claude Opus 价格，一小时 **$47,000**。

本工具能在类似的"静默烧钱"事件发生 **30 秒内**检测并告警/冻结，防止损失扩大。

[真实案例 →](https://github.com/openclaw/openclaw/issues/91018)

## 核心功能

| 功能 | 说明 |
|:----|:------|
| 💰 **预算跟踪** | 月度预算上限，三级告警（黄色/红色/冻结） |
| ⚠️ **异常燃烧检测** | 短时间内 token 消耗速率突然飙升（默认 3 倍） |
| 🗄️ **缓存命中预警** | cache_hit_pct < 30% 自动告警（独家功能） |
| 🛑 **自动冻结** | 达到上限或异常时自动建议切换省钱方案 |
| 🔮 **预测性耗尽** | "按当前速率，N小时后花光" 提前预警 |
| 💡 **省钱建议** | 预算紧张时自动推荐更便宜的模型 |
| 📊 **历史追踪** | 每次 check 记录 CSV，方便复盘 |
| 🔄 **重试守卫** | 防止重试循环无限烧钱 |

## 快速开始

```bash
# 安装
curl -fsSL https://raw.githubusercontent.com/RavenSS213/ai-budget-guard/main/install.sh | bash

# 检查当前状态
budget-guard check '{
  "model": "deepseek/deepseek-v4-flash",
  "tokens_in": 150000,
  "tokens_out": 5000,
  "cache_hit_pct": 96
}'

# 查看月度报告
budget-guard report

# 预测预算耗尽时间
budget-guard forecast

# 查看历史趋势
budget-guard history
```

## 环境变量配置

| 变量 | 默认值 | 说明 |
|:----|:------|:-----|
| `BUDGET_MONTHLY_USD` | 7.0 | 月预算上限 (USD) |
| `BUDGET_MONTHLY_CNY` | 50 | 月预算上限 (CNY) |
| `ALERT_RATE_THRESHOLD` | 3.0 | 异常速率倍数阈值 |
| `ALERT_CACHE_MIN` | 30 | 最低缓存命中率 (%) |

## 与同类工具对比

| 功能 | Budget Guard | ComputeCFO | Spend Firewall |
|:----|:-----------:|:----------:|:--------------:|
| 缓存命中率检测 | ✅ **独家** | ❌ | ❌ |
| 预算跟踪 | ✅ | ✅ | ✅ |
| 异常速率检测 | ✅ | ✅ | ✅ |
| 预测性耗尽 | ✅ v1.1 | ✅ | ❌ |
| 模型切换建议 | ✅ v1.1 | ✅ | ❌ |
| 历史 CSV | ✅ v1.1 | ✅ | ✅ |
| 零外部依赖 | ✅ | ❌ (需要DB) | ❌ (需要DB) |
| 实时仪表盘 | ⏳ 计划中 | ✅ | ✅ |

## License

MIT

## 真实案例

- **2026-06-06**: OpenClaw 6.1 缓存 bug 导致 DeepSeek 用户一小时烧 $5.5 — [Issue #91018](https://github.com/openclaw/openclaw/issues/91018)
