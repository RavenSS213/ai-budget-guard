#!/usr/bin/env python3
"""
AI Budget Guard — 预算守卫核心脚本
实时监控 API Token 消耗、缓存命中率异常检测。

用法:
  python3 budget.py check '{"model":"xxx","tokens_in":150000,"cache_hit_pct":96}'
  python3 budget.py report
  python3 budget.py freeze
"""

import json
import sys
import os
import time
from pathlib import Path

# === 默认配置 ===
DEFAULT_CONFIG = {
    "budget_monthly_usd": float(os.environ.get("BUDGET_MONTHLY_USD", "7.0")),
    "budget_monthly_cny": float(os.environ.get("BUDGET_MONTHLY_CNY", "50")),
    "alert_rate_threshold": float(os.environ.get("ALERT_RATE_THRESHOLD", "3.0")),
    "alert_cache_min": float(os.environ.get("ALERT_CACHE_MIN", "30")),
}

STATE_FILE = Path(__file__).parent / "references" / "state.json"

# === 模型定价 (USD/M tokens) ===
PRICING = {
    "deepseek/deepseek-v4-flash": {"input": 0.14, "output": 0.28, "cache_read": 0.028},
    "deepseek/deepseek-chat": {"input": 0.28, "output": 0.42, "cache_read": 0.028},
    "deepseek/deepseek-reasoner": {"input": 0.28, "output": 1.10, "cache_read": 0.028},
    "gpt-4o": {"input": 2.50, "output": 10.00, "cache_read": 1.25},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cache_read": 0.075},
    "claude-sonnet-4": {"input": 3.00, "output": 15.00, "cache_read": 1.50},
    "default": {"input": 0.14, "output": 0.28, "cache_read": 0.028},
}


def load_state():
    """加载持久化状态"""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "monthly_input_tokens": 0,
        "monthly_output_tokens": 0,
        "monthly_cost_usd": 0.0,
        "last_check_time": 0,
        "last_cache_hit_pct": 100,
        "alerts": [],
        "frozen": False,
    }


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_pricing(model_id):
    return PRICING.get(model_id, PRICING["default"])


def check(data, config=None):
    """检查一次 session_status 数据，返回状态报告"""
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

    # 计算本次请求费用
    effective_input = tokens_in * (1 - cache_hit_pct / 100)
    cost_input = effective_input / 1_000_000 * pricing["input"]
    cost_output = tokens_out / 1_000_000 * pricing["output"]
    actual_cost = cost_input + cost_output
    if cost_usd > 0:
        actual_cost = cost_usd

    # 更新月度统计
    state["monthly_input_tokens"] += tokens_in
    state["monthly_output_tokens"] += tokens_out
    state["monthly_cost_usd"] += actual_cost
    state["last_check_time"] = now

    # 计算燃烧速率 (tokens/秒)
    elapsed = now - state.get("last_check_time", now - 60)
    rate = tokens_in / max(elapsed, 1) if elapsed > 0 else 0
    prev_rate = state.get("last_rate", rate)
    rate_ratio = rate / max(prev_rate, 1)

    alerts = []

    # 检查1: 缓存命中率异常
    if cache_hit_pct < config["alert_cache_min"]:
        alerts.append({
            "level": "warning",
            "type": "cache_drop",
            "message": f"缓存命中率 {cache_hit_pct:.0f}% < 阈值 {config['alert_cache_min']:.0f}%",
            "cache_hit_pct": cache_hit_pct,
        })

    # 检查2: 燃烧速率异常
    if rate_ratio > config["alert_rate_threshold"] and prev_rate > 0:
        alerts.append({
            "level": "critical",
            "type": "rate_spike",
            "message": f"燃烧速率飙升 {rate_ratio:.1f}x (正常 {prev_rate:.0f} → 当前 {rate:.0f} tok/s)",
            "rate_ratio": rate_ratio,
        })

    # 检查3: 预算超限
    remaining = config["budget_monthly_usd"] - state["monthly_cost_usd"]
    usage_pct = state["monthly_cost_usd"] / config["budget_monthly_usd"] * 100

    if remaining <= 0:
        alerts.append({
            "level": "frozen",
            "type": "budget_exhausted",
            "message": f"月预算已用尽 (${state['monthly_cost_usd']:.2f} / ${config['budget_monthly_usd']:.2f})",
            "remaining": remaining,
        })
        state["frozen"] = True
    elif usage_pct > 80:
        alerts.append({
            "level": "warning",
            "type": "budget_near_limit",
            "message": f"月预算已用 {usage_pct:.0f}%，剩余 ${remaining:.2f}",
            "remaining": remaining,
            "usage_pct": usage_pct,
        })
    elif usage_pct > 50:
        alerts.append({
            "level": "info",
            "type": "budget_mid",
            "message": f"月预算已用 {usage_pct:.0f}%，剩余 ${remaining:.2f}",
            "remaining": remaining,
            "usage_pct": usage_pct,
        })

    # 更新状态
    state["alerts"] = state.get("alerts", []) + alerts
    state["last_cache_hit_pct"] = cache_hit_pct
    state["last_rate"] = rate
    save_state(state)

    return {
        "status": "frozen" if state["frozen"] else ("alert" if alerts else "ok"),
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


def main():
    if len(sys.argv) < 2:
        print("用法: budget.py <check|report|freeze> [json_data]")
        sys.exit(1)

    action = sys.argv[1]

    if action == "check":
        if len(sys.argv) < 3:
            data = json.loads(sys.stdin.read())
        else:
            data = json.loads(sys.argv[2])
        result = check(data)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif action == "report":
        state = load_state()
        config = DEFAULT_CONFIG
        remaining = config["budget_monthly_usd"] - state["monthly_cost_usd"]
        print(f"📊 月度报告")
        print(f"  已用: ${state['monthly_cost_usd']:.2f} / ${config['budget_monthly_usd']:.2f}")
        print(f"  剩余: ${remaining:.2f}")
        print(f"  输入 Token: {state['monthly_input_tokens']:,}")
        print(f"  输出 Token: {state['monthly_output_tokens']:,}")
        print(f"  状态: {'❄️ 已冻结' if state.get('frozen') else '✅ 正常'}")
        if state.get("alerts"):
            print(f"  告警: {len(state['alerts'])} 条")
            for a in state["alerts"][-3:]:
                print(f"    [{a['level']}] {a['message']}")

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
            "last_check_time": 0,
            "last_cache_hit_pct": 100,
            "alerts": [],
            "frozen": False,
        })
        print("✅ 月度统计已重置")


if __name__ == "__main__":
    main()
