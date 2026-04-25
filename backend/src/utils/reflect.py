"""
自动反思：读 docs/RUN_LOG.jsonl，按规则识别系统性问题，自动写入
docs/KNOWN_ISSUES.md 和 docs/AI_NOTES.md 反思日志。

设计原则（与 AGENTS.md「反思 Protocol」对齐）：
- 不调任何 LLM、不依赖网络、不依赖 secret，纯本地规则即可识别"重复 ≥ 2 次"模式
- 写入幂等：同一指纹 (fingerprint) 已在 KNOWN_ISSUES 出现则跳过，不重复堆
- 只追加，不删；旧条目永远保留（删除是人类决定）
- 输出全部走 stdout 一份，便于 workflow log 直接看；同时落盘文档供下次 AI 加载

触发方式（见 .github/workflows/reflect.yml）：
- schedule: 每 12h 一次（不依赖业务 cron 准点）
- workflow_run: backtest / predict / evaluate 跑完后立即触发，把发现追到事实尾巴上

不做的事：
- 不修代码（AI 自动改业务代码是巨大风险，必须人类 review）
- 不发通知（避免信噪比过低；KNOWN_ISSUES 自然沉淀就够了）
"""
from __future__ import annotations

import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_LOG = REPO_ROOT / "docs" / "RUN_LOG.jsonl"
KNOWN_ISSUES = REPO_ROOT / "docs" / "KNOWN_ISSUES.md"
AI_NOTES = REPO_ROOT / "docs" / "AI_NOTES.md"

# 分析窗口：最近多少条 run（够覆盖一周左右流量）
WINDOW = 200


def _load_runs() -> list[dict[str, Any]]:
    """
    @returns 最近 WINDOW 条 run 记录，按时间正序（旧→新）
    """
    if not RUN_LOG.exists():
        return []
    out: list[dict[str, Any]] = []
    with RUN_LOG.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out[-WINDOW:]


def _fingerprint(*parts: str) -> str:
    """
    给一条发现生成稳定指纹，用于 KNOWN_ISSUES 去重

    @returns 8 位 hex
    """
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return h[:8]


def _known_fingerprints() -> set[str]:
    """
    扫描 KNOWN_ISSUES.md，提取所有已记录条目的指纹

    约定：每条目首行格式 `## [fp:XXXXXXXX] [YYYY-MM-DD] ...`

    @returns 已存在指纹集合
    """
    if not KNOWN_ISSUES.exists():
        return set()
    fps: set[str] = set()
    for line in KNOWN_ISSUES.read_text(encoding="utf-8").splitlines():
        if line.startswith("## [fp:") and len(line) > 16:
            fp = line[7:15]
            fps.add(fp)
    return fps


# ============ 规则 ============

def rule_consecutive_failures(runs: list[dict[str, Any]]) -> list[dict[str, str]]:
    """
    规则 R1：同一 workflow 连续 ≥ 2 次 failure / cancelled

    @param runs 时间正序
    @returns 发现列表，每条含 title/body/fingerprint
    """
    findings: list[dict[str, str]] = []
    by_wf: dict[str, list[dict[str, Any]]] = {}
    for r in runs:
        by_wf.setdefault(r.get("workflow", "?"), []).append(r)

    for wf, rs in by_wf.items():
        if len(rs) < 2:
            continue
        last = rs[-1]
        prev = rs[-2]
        bad = {"failure", "cancelled"}
        if (last.get("outcome") in bad) and (prev.get("outcome") in bad):
            fp = _fingerprint("R1", wf, last.get("outcome", ""))
            urls = [r.get("run_url") for r in rs[-3:] if r.get("run_url")]
            findings.append({
                "fingerprint": fp,
                "title": f"{wf} 连续失败 ({prev.get('outcome')}, {last.get('outcome')})",
                "body": (
                    f"- 现象：workflow `{wf}` 最近两次 outcome 分别为 `{prev.get('outcome')}` / `{last.get('outcome')}`，"
                    f"已连续异常 ≥ 2 次\n"
                    f"- 证据：{', '.join(urls) if urls else '(run_url 缺失)'}\n"
                    f"- 根因：待人工确认（建议看最新 run 的 step logs）\n"
                    f"- 规避：暂未知；若是 dispatch 失败可手动 `gh workflow run {wf}.yml`\n"
                    f"- 修复：未\n"
                ),
            })
    return findings


def rule_backtest_progress_stuck(runs: list[dict[str, Any]]) -> list[dict[str, str]]:
    """
    规则 R2：backtest 连续 3 轮 processed 不增（进度卡死）

    @returns 发现列表
    """
    bt = [r for r in runs if r.get("workflow") == "backtest"]
    if len(bt) < 3:
        return []
    tail = bt[-3:]
    processed_seq = []
    for r in tail:
        extra = r.get("extra") or {}
        p = extra.get("processed")
        if p is None:
            return []
        processed_seq.append(p)
    if len(set(processed_seq)) == 1 and processed_seq[0] is not None:
        last = tail[-1]
        extra = last.get("extra") or {}
        if extra.get("done"):
            return []
        fp = _fingerprint("R2", str(processed_seq[0]))
        urls = [r.get("run_url") for r in tail if r.get("run_url")]
        return [{
            "fingerprint": fp,
            "title": f"backtest 进度卡在 processed={processed_seq[0]}（连续 3 轮未推进）",
            "body": (
                f"- 现象：最近 3 轮 backtest 的 `extra.processed` 都等于 `{processed_seq[0]}`，"
                f"但 `done=false`，说明续跑没在前进\n"
                f"- 证据：{', '.join(urls) if urls else '(run_url 缺失)'}\n"
                f"- 根因：可能是某期对某模型反复抛异常被吞、或 DB 写入失败、或 ONLY_MODELS 误设\n"
                f"- 规避：检查最新一次 backtest 的 step logs，找重复出现的 `[skip]` / `[error]`\n"
                f"- 修复：未\n"
            ),
        }]
    return []


def rule_backtest_duration_regression(runs: list[dict[str, Any]]) -> list[dict[str, str]]:
    """
    规则 R3：backtest 单轮 duration 比近 10 轮中位数高 ≥ 50%

    @returns 发现列表
    """
    bt = [r for r in runs if r.get("workflow") == "backtest" and r.get("duration_s")]
    if len(bt) < 6:
        return []
    history = [r["duration_s"] for r in bt[-11:-1]]
    if not history:
        return []
    median = statistics.median(history)
    last = bt[-1]
    last_dur = last.get("duration_s") or 0
    if median <= 0:
        return []
    if last_dur >= median * 1.5:
        fp = _fingerprint("R3", str(int(median)), str(int(last_dur)))
        return [{
            "fingerprint": fp,
            "title": f"backtest 性能退化：本轮 {last_dur}s vs 近 10 轮中位数 {int(median)}s",
            "body": (
                f"- 现象：本次 backtest run 用时 `{last_dur}s`，比近 10 轮中位数 `{int(median)}s` 高 ≥ 50%\n"
                f"- 证据：{last.get('run_url') or '(run_url 缺失)'}\n"
                f"- 根因：可能是 GitHub runner 抖动、或新加模型/超参变化、或 DB 体积增长\n"
                f"- 规避：观察接下来 2-3 轮，若持续高位再排查；偶发可忽略\n"
                f"- 修复：未\n"
            ),
        }]
    return []


RULES = [
    rule_consecutive_failures,
    rule_backtest_progress_stuck,
    rule_backtest_duration_regression,
]


# ============ 写入 ============

def _append_known_issue(finding: dict[str, str]) -> None:
    """
    把一条发现追加到 KNOWN_ISSUES.md

    @param finding 含 fingerprint/title/body
    """
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    block = (
        f"\n## [fp:{finding['fingerprint']}] [{today}] {finding['title']}\n"
        f"{finding['body']}\n"
        f"_由 `backend/src/utils/reflect.py` 自动写入。人工确认后请把 `根因` / `修复` 填实。_\n"
    )
    KNOWN_ISSUES.parent.mkdir(parents=True, exist_ok=True)
    if not KNOWN_ISSUES.exists():
        KNOWN_ISSUES.write_text("# KNOWN_ISSUES · 已知问题档案\n", encoding="utf-8")
    with KNOWN_ISSUES.open("a", encoding="utf-8") as f:
        f.write(block)


def _append_ai_notes_reflection(findings: list[dict[str, str]], scanned: int) -> None:
    """
    把本次反思总结追加到 AI_NOTES.md 的「反思日志」区
    遵守 AI_NOTES.md 自己写的规则：**无新发现就别污染**
    """
    if not AI_NOTES.exists():
        return
    if not findings:
        return  # 无新发现不写，避免反思日志变成流水账
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    lines = [f"### [{ts} reflect.py] 自动巡检：发现 {len(findings)} 个新模式 (scanned={scanned})"]
    for f in findings:
        lines.append(f"- `fp:{f['fingerprint']}` {f['title']}")
    lines.append("- 已写入 `KNOWN_ISSUES.md`，下次 AI 进来需人工 review 把根因 / 修复填实")
    block = "\n".join(lines) + "\n\n"

    text = AI_NOTES.read_text(encoding="utf-8")
    anchor = "## 反思日志（按时间倒序追加）"
    if anchor not in text:
        with AI_NOTES.open("a", encoding="utf-8") as f:
            f.write("\n" + anchor + "\n\n" + block)
        return
    head, tail = text.split(anchor, 1)
    new_text = head + anchor + "\n\n" + block + tail.lstrip("\n")
    AI_NOTES.write_text(new_text, encoding="utf-8")


def main() -> int:
    runs = _load_runs()
    print(f"[reflect] loaded {len(runs)} runs from {RUN_LOG}")
    if not runs:
        print("[reflect] RUN_LOG 为空或不存在，跳过")
        _append_ai_notes_reflection([], 0)
        return 0

    known = _known_fingerprints()
    print(f"[reflect] 已知指纹 {len(known)} 个")

    new_findings: list[dict[str, str]] = []
    for rule in RULES:
        try:
            for f in rule(runs):
                if f["fingerprint"] in known:
                    print(f"[reflect] skip 已知 fp:{f['fingerprint']} {f['title']}")
                    continue
                new_findings.append(f)
                known.add(f["fingerprint"])
        except Exception as e:
            print(f"[reflect] rule {rule.__name__} 异常被吞：{e}")

    for f in new_findings:
        print(f"[reflect] NEW fp:{f['fingerprint']} {f['title']}")
        _append_known_issue(f)

    _append_ai_notes_reflection(new_findings, len(runs))
    print(f"[reflect] done. new={len(new_findings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
