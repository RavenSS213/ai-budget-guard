#!/usr/bin/env python3
"""
AI Budget Guard v1.1 — 预算守卫核心脚本
实时监控 API Token 消耗、缓存命中率异常检测、预测性耗尽警告。

用法:
  python3 budget.py check '{"model":"xxx","tokens_in":150000,"cache_hit_pct":96}'
  python3 budget.py report
  python3 budget.py history
  python3 budget.py freeze
  python3 budget.py forecast
"""

import json
import sys
import os
import time
import csv
from datetime import datetime, timedelta
from pathlib import Path

# === 默认配置 ===
DEFAULT_CONFIG = {
    "budget_monthly_usd": float(os.environ.get("BUDGET_MONTHLY_USD", "7.0")),
    "budget_monthly_cny": float(os.environ.get("BUDGET_MONTHLY_CNY", "50")),
    "alert_rate_threshold": float(os.environ.get("ALERT_RATE_THRESHOLD", "3.0")),
    "alert_cache_min": float(os.environ.get("ALERT_CACHE_MIN", "30")),
}

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = BASE_DIR / "references" / "state.json"
HISTORY_FILE = BASE_DIR / "references" / "history.csv"
PRICING_FILE = BASE_DIR / "references" / "pricing.yml"

# === 模型定价 (USD/M tokens) ===
PRICING = {
    "deepseek/deepseek-v4-flash": {"input": 0.14, "output": 0.28, "cache_read": 0.028},
    "deepseek/deepseek-chat": {"input": 0.28, "output": 0.42, "cache_read": 0.028},
    "deepseek/deepseek-reasoner": {"input": 0.28, "output": 1.10, "cache_read": 0.028},
    "openai/gpt-4o": {"input": 2.50, "output": 10.00, "cache_read": 1.25},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60, "cache_read": 0.075},
    "openai/o3-mini": {"input": 1.10, "output": 4.40, "cache_read": 0.55},
    "anthropic/claude-sonnet-4": {"input": 3.00, "output": 15.00, "cache_read": 1.50, "cache_write": 3.75},
    "anthropic/claude-opus-4": {"input": 15.00, "output": 75.00, "cache_read": 7.50, "cache_write": 18.75},
    "default": {"input": 0.14, "output": 0.28, "cache_read": 0.028},
}

# === CHEAPER MODEL SUGGESTIONS ===
DOWNGRADE_PATH = {
    "anthropic/claude-opus-4": "anthropic/claude-sonnet-4",
    "anthropic/claude-sonnet-4": "openai/gpt-4o",
    "openai/gpt-4o": "openai/gpt-4o-mini",
    "openai/gpt-4o-mini": "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-reasoner": "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-v4-pro": "deepseek/deepseek-v4-flash",
}


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "monthly_input_tokens": 0,
        "monthly_output_tokens": 0,
        "monthly_cost_usd": 0.0,
        "session_start_time": int(time.time()),
        "last_check_time": 0,
        "last_cache_hit_pct": 100,
        "alerts": [],
        "frozen": False,
    }


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def append_history(entry):
    """追加一条历史记录到 CSV"""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    fresh = not HISTORY_FILE.exists()
    with open(HISTORY_FILE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "timestamp", "model", "tokens_in", "tokens_out",
            "cache_hit_pct", "cost_usd", "cumulative_usd", "alert_level"
        ])
        if fresh:
            w.writeheader()
        w.writerow(entry)


def get_pricing(model_id):
    return PRICING.get(model_id, PRICING["default"])


def suggest_cheaper_model(current_model):
    """返回更省钱模型建议"""
    if current_model in DOWNGRADE_PATH:
        target = DOWNGRADE_PATH[current_model]
        current_price = PRICING.get(current_model, PRICING["default"])["input"]
        target_price = PRICING.get(target, PRICING["default"])["input"]
        savings = (1 - target_price / current_price) * 100
        return {
            "suggested": target,
            "current_price_per_m": current_price,
            "suggested_price_per_m": target_price,
            "savings_pct": round(savings),
        }
    return None


def forecast_exhaustion(state, config):
    """预测预算耗尽时间"""
    elapsed = time.time() - state.get("session_start_time", time.time())
    if elapsed < 60 or state["monthly_cost_usd"] == 0:
        return None

    hourly_rate = state["monthly_cost_usd"] / (elapsed / 3600)
    remaining = config["budget_monthly_usd"] - state["monthly_cost_usd"]

    if hourly_rate <= 0:
        return None

    hours_remaining = remaining / hourly_rate
    return {
        "hourly_rate": round(hourly_rate, 4),
        "remaining": round(remaining, 2),
        "hours_remaining": round(hours_remaining, 1),
        "estimated_exhaustion": (datetime.now() + timedelta(hours=hours_remaining)).strftime("%Y-%m-%d %H:%M"),
        "daily_cost_estimate": round(hourly_rate * 24, 2),
        "monthly_cost_estimate": round(hourly_rate * 30 * 24, 2),
    }


def check(data, config=None):
    if config is None:
        config = DEFAULT_CONFIG

    state = load_state()
    now = time.time()
    model = data.get("model", "default")
    tokens_in = data.get("tokens_in", 0)
    tokens_out = data.get("tokens_out", 0)
    cache_hit_pct = data.get("cache_hit_pct", 100)
    cost_usd = data.get("cost_usd", 0.0)
    pricing = get_pricing(model)

    # 计算本次费用
    effective_input = tokens_in * (1 - cache_hit_pct / 100)
    cost_input = effective_input / 1_000_000 * pricing["input"]
    cost_output = tokens_out / 1_000_000 * pricing["output"]
    actual_cost = cost_input + cost_output
    if cost_usd > 0:
        actual_cost = cost_usd

    # 更新统计
    prev_cost = state["monthly_cost_usd"]
    state["monthly_input_tokens"] += tokens_in
    state["monthly_output_tokens"] += tokens_out
    state["monthly_cost_usd"] += actual_cost
    state["last_cache_hit_pct"] = cache_hit_pct

    # 燃烧速率
    elapsed = now - state.get("last_check_time", now - 60)
    rate = tokens_in / max(elapsed, 1) if elapsed > 0 else 0
    prev_rate = state.get("last_rate", rate)
    rate_ratio = rate / max(prev_rate, 1) if prev_rate > 0 else 1.0
    state["last_rate"] = rate

    alerts = []
    alert_level = "ok"

    # 检查1: 缓存命中率异常
    if cache_hit_pct < config["alert_cache_min"]:
        alerts.append({
            "level": "warning",
            "type": "cache_drop",
            "message": f"缓存命中率 {cache_hit_pct:.0f}% < 阈值 {config['alert_cache_min']:.0f}%",
        })
        alert_level = "warning"

    # 检查2: 燃烧速率异常
    if rate_ratio > config["alert_rate_threshold"] and prev_rate > 0:
        alerts.append({
            "level": "critical",
            "type": "rate_spike",
            "message": f"燃烧速率飙升 {rate_ratio:.1f}x ({prev_rate:.0f} → {rate:.0f} tok/s)",
        })
        alert_level = "critical"

    # 检查3: 预算超限
    remaining = config["budget_monthly_usd"] - state["monthly_cost_usd"]
    usage_pct = state["monthly_cost_usd"] / config["budget_monthly_usd"] * 100

    if remaining <= 0:
        alerts.append({
            "level": "frozen",
            "type": "budget_exhausted",
            "message": f"月预算已用尽 (${state['monthly_cost_usd']:.2f})",
        })
        state["frozen"] = True
        alert_level = "frozen"
    elif usage_pct > 80:
        alerts.append({
            "level": "critical",
            "type": "budget_near_limit",
            "message": f"预算已用 {usage_pct:.0f}%，剩余 ${remaining:.2f}",
        })
        if alert_level == "ok":
            alert_level = "warning"
    elif usage_pct > 50:
        alerts.append({
            "level": "info",
            "type": "budget_mid",
            "message": f"预算已用 {usage_pct:.0f}%，剩余 ${remaining:.2f}",
        })

    # 检查4: 预测耗尽 (每次check时更新)
    forecast = forecast_exhaustion(state, config)
    if forecast and forecast["hours_remaining"] < 24 and forecast["hours_remaining"] > 0:
        alerts.append({
            "level": "critical",
            "type": "forecast_imminent",
            "message": f"按当前速率 {forecast['hours_remaining']:.0f} 小时后耗尽 ({forecast['estimated_exhaustion']})",
        })

    state["last_check_time"] = now
    state["alerts"] = state.get("alerts", []) + alerts
    save_state(state)

    # 记录历史
    append_history({
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cache_hit_pct": round(cache_hit_pct, 1),
        "cost_usd": round(actual_cost, 6),
        "cumulative_usd": round(state["monthly_cost_usd"], 4),
        "alert_level": alert_level,
    })

    result = {
        "status": alert_level,
        "alerts": alerts,
        "stats": {
            "monthly_cost_usd": round(state["monthly_cost_usd"], 4),
            "monthly_input_tokens": state["monthly_input_tokens"],
            "monthly_output_tokens": state["monthly_output_tokens"],
            "remaining_usd": round(remaining, 2),
            "usage_pct": round(usage_pct, 1),
            "frozen": state["frozen"],
        },
    }

    # 预算紧张时 + 模型建议
    if usage_pct > 50:
        suggestion = suggest_cheaper_model(model)
        if suggestion:
            result["model_suggestion"] = suggestion

    # 预测
    if forecast:
        result["forecast"] = forecast

    return result


def main():
    if len(sys.argv) < 2:
        print("用法: budget.py <check|report|history|forecast|freeze|unfreeze|reset> [json_data]")
        sys.exit(1)

    action = sys.argv[1]

    if action == "check":
        data = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.loads(sys.stdin.read())
        result = check(data)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif action == "report":
        state = load_state()
        config = DEFAULT_CONFIG
        forecast = forecast_exhaustion(state, config)

        print(f"📊 AI Budget Guard — 月度报告")
        print(f"{'='*50}")
        print(f"  已用:        ${state['monthly_cost_usd']:.2f} / ${config['budget_monthly_usd']:.2f}")
        print(f"  剩余:        ${config['budget_monthly_usd'] - state['monthly_cost_usd']:.2f}")
        print(f"  输入 Token:  {state['monthly_input_tokens']:>10,}")
        print(f"  输出 Token:  {state['monthly_output_tokens']:>10,}")
        print(f"  状态:        {'❄️ 已冻结' if state.get('frozen') else '✅ 正常'}")

        if forecast:
            print(f"\n🔮 预测（按当前速率）")
            print(f"  时均:        ${forecast['hourly_rate']:.4f}/h")
            print(f"  日均:        ${forecast['daily_cost_estimate']:.2f}/天")
            print(f"  月均(估):    ${forecast['monthly_cost_estimate']:.2f}/月")
            if forecast['hours_remaining'] > 0:
                print(f"  预计耗尽:    {forecast['estimated_exhaustion']} ({forecast['hours_remaining']:.1f}h)")

        if state.get("alerts"):
            print(f"\n⚠️ 最近告警 ({len(state['alerts'])} 条)")
            for a in state["alerts"][-5:]:
                icon = {"frozen": "❄️", "critical": "🔴", "warning": "🟡", "info": "ℹ️"}.get(a["level"], "•")
                print(f"  {icon} [{a['type']}] {a['message']}")

    elif action == "history":
        if not HISTORY_FILE.exists():
            print("暂无历史记录")
            return
        with open(HISTORY_FILE) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        print(f"📈 历史记录 ({len(rows)} 条)")
        print(f"{'='*70}")
        print(f"  {'时间':<20} {'模型':<25} {'输入':>8} {'缓存%':>6} {'费用':>8}")
        print(f"  {'-'*70}")
        for r in rows[-15:]:
            print(f"  {r['timestamp'][:19]:<20} {r['model'][:25]:<25} "
                  f"{r['tokens_in']:>8} {r['cache_hit_pct']:>6} ${r['cost_usd']:>6}")

    elif action == "forecast":
        state = load_state()
        config = DEFAULT_CONFIG
        f = forecast_exhaustion(state, config)
        if not f:
            print("数据不足，请先运行几次 check")
            return
        print(f"🔮 预算预测")
        print(f"{'='*40}")
        print(f"  当前时均:    ${f['hourly_rate']:.4f}/h")
        print(f"  日均预估:    ${f['daily_cost_estimate']:.2f}/天")
        print(f"  月均预估:    ${f['monthly_cost_estimate']:.2f}/月")
        print(f"  剩余:        ${f['remaining']:.2f}")
        if f['hours_remaining'] > 0:
            print(f"  预计耗尽:    {f['estimated_exhaustion']}")

    elif action == "freeze":
        state = load_state()
        state["frozen"] = True
        save_state(state)
        print("❄️ 已冻结 — 后续请求将触发警告")
        print("  解冻: python3 budget.py unfreeze")

    elif action == "unfreeze":
        state = load_state()
        state["frozen"] = False
        save_state(state)
        print("✅ 已解冻")

    elif action == "reset":
        save_state({
            "monthly_input_tokens": 0,
            "monthly_output_tokens": 0,
            "monthly_cost_usd": 0.0,
            "session_start_time": int(time.time()),
            "last_check_time": 0,
            "last_cache_hit_pct": 100,
            "alerts": [],
            "frozen": False,
        })
        if HISTORY_FILE.exists():
            HISTORY_FILE.unlink()
        print("✅ 已重置（月度统计 + 历史记录）")


if __name__ == "__main__":
    main()
