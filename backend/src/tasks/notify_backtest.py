"""
回测进度/完成/异常通知

由 GitHub Actions 在每一轮 workflow 结束时调用，读取 `data/.backtest_state.json`
并广播到 ServerChan / 企业微信 / PushPlus（未配置 SECRET 的通道会被 notifier 静默跳过）。

三种分支：
- done=True  → "✅ 回测完成"
- stopped_early=True 且 done=False → "⏳ 回测进度 X%，自动续跑下一轮"
- BACKTEST_OUTCOME 非 success → "❌ 回测异常"（不依赖 state 是否准确）
"""
from __future__ import annotations

import json
import os
import sys

from ..config import DATA_DIR
from ..utils.notifier import notify

STATE = DATA_DIR / ".backtest_state.json"


def _run_url() -> str:
    """
    拼接当前 workflow run 的 URL

    @returns 绝对 URL；非 Actions 环境返回空串
    """
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not (repo and run_id):
        return ""
    return f"{server}/{repo}/actions/runs/{run_id}"


def _format_hms(seconds: float) -> str:
    """
    把秒数格式化成 Hh Mm 字符串

    @param seconds 秒
    @returns 例如 "4h 50m"
    """
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def main() -> int:
    """
    入口：根据 state 与 env 发通知

    @returns 退出码（总是 0，不因通知失败影响 workflow）
    """
    outcome = os.environ.get("BACKTEST_OUTCOME", "success").lower()
    run_url = _run_url()

    state: dict | None = None
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception as e:  # 文件损坏也要兜底
            print(f"[notify_backtest] state 文件解析失败: {e}")
            state = None

    if outcome not in ("success", ""):
        title = f"❌ 回测异常（{outcome}）"
        lines = [
            f"**walk-forward backtest 本轮失败**",
            "",
            f"- backtest step outcome：`{outcome}`",
            f"- run：{run_url}",
        ]
        if state:
            lines += [
                f"- 最后成功入库的期：{state.get('last_issue')}",
                f"- 本轮已处理：{state.get('processed')}/{state.get('total')}",
            ]
        notify(title, "\n".join(lines))
        return 0

    if not state:
        print("[notify_backtest] state 不存在且 outcome=success，跳过通知")
        return 0

    done = bool(state.get("done"))
    processed = int(state.get("processed", 0))
    total = int(state.get("total", 0))
    last_issue = state.get("last_issue")
    elapsed = float(state.get("elapsed_seconds", 0))
    start_idx = state.get("start_idx")
    pct = (processed / total * 100) if total else 0.0

    if done:
        title = "✅ 回测完成"
        lines = [
            "**walk-forward backtest 全部完成**",
            "",
            f"- 总计：**{total}** 期",
            f"- 起始 idx：{start_idx}",
            f"- 最末期：{last_issue}",
            f"- 本轮耗时：{_format_hms(elapsed)}",
            f"- run：{run_url}",
        ]
    else:
        title = f"⏳ 回测 {pct:.1f}%（{processed}/{total}）"
        lines = [
            "**本轮主动停机，自动排队下一轮接力**",
            "",
            f"- 已处理：**{processed}/{total}** ({pct:.1f}%)",
            f"- 最末期：{last_issue}",
            f"- 本轮耗时：{_format_hms(elapsed)}",
            f"- run：{run_url}",
        ]

    notify(title, "\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
