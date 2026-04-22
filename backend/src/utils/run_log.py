"""
结构化运行日志：每次 GitHub Actions workflow 运行结束时追加一行 JSON 到 docs/RUN_LOG.jsonl

设计目标：
- 机器友好（JSONL，每行一个对象，天然可被 jq/python 流式读）
- 人类也能直接 grep
- 单调增长但可控：rotate 阈值 2000 行（约 60 天流量），超过时自动把老内容挪到 RUN_LOG.archive.jsonl
- 不依赖网络，不调用外部 API，由 workflow 在已 checkout 的仓库里直接调用
- AI 协作者被约定在每次进入项目时读最近 N 条做反思（见 AGENTS.md "反思 protocol" 一节）

写入内容（按需扩展，保持向后兼容）：
- ts          ISO 时间（带时区）
- workflow    "backtest" / "predict" / "evaluate" / …
- run_id      GITHUB_RUN_ID
- run_url     完整 URL
- commit      GITHUB_SHA 的前 7 位
- ref         GITHUB_REF_NAME
- outcome     "success" / "failure" / "cancelled" / …（由调用方传入，通常是 backtest step 的 outcome）
- duration_s  自 GITHUB_RUN_STARTED_AT 到现在的秒数
- extra       自由字段，调用方传入（比如 backtest 会把 state 摘要丢进来）
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
LOG_FILE = REPO_ROOT / "docs" / "RUN_LOG.jsonl"
ARCHIVE_FILE = REPO_ROOT / "docs" / "RUN_LOG.archive.jsonl"
ROTATE_THRESHOLD_LINES = 2000


def _duration_seconds() -> int | None:
    """
    从 GITHUB_RUN_STARTED_AT 推算本次 run 已经运行多久

    @returns 秒数；非 Actions 环境返回 None
    """
    started = os.environ.get("GITHUB_RUN_STARTED_AT")
    if not started:
        return None
    try:
        t0 = datetime.fromisoformat(started.replace("Z", "+00:00"))
        return int((datetime.now(timezone.utc) - t0).total_seconds())
    except Exception:
        return None


def _rotate_if_needed() -> None:
    """
    LOG_FILE 行数超阈值时把它挪到 ARCHIVE_FILE（拼接追加），保持 LOG_FILE 小
    """
    if not LOG_FILE.exists():
        return
    with LOG_FILE.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    if len(lines) < ROTATE_THRESHOLD_LINES:
        return
    ARCHIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ARCHIVE_FILE.open("a", encoding="utf-8") as f:
        f.writelines(lines)
    LOG_FILE.write_text("", encoding="utf-8")


def append_run_log(
    workflow: str,
    outcome: str,
    extra: dict[str, Any] | None = None,
) -> Path:
    """
    追加一条 run 记录到 docs/RUN_LOG.jsonl

    @param workflow workflow 名称（短标签，如 "backtest" / "predict" / "evaluate"）
    @param outcome  "success" / "failure" / "cancelled" / "skipped" / 其他
    @param extra    任意补充字段（只要能被 json.dumps 序列化），建议带上业务进度摘要
    @returns 日志文件路径
    """
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    sha = os.environ.get("GITHUB_SHA", "")
    ref = os.environ.get("GITHUB_REF_NAME", "")

    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "workflow": workflow,
        "run_id": run_id or None,
        "run_url": (f"{server}/{repo}/actions/runs/{run_id}"
                    if repo and run_id else None),
        "commit": sha[:7] if sha else None,
        "ref": ref or None,
        "outcome": outcome,
        "duration_s": _duration_seconds(),
    }
    if extra:
        record["extra"] = extra

    _rotate_if_needed()
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"[run_log] appended {record}")
    return LOG_FILE


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="追加一条 run 记录到 docs/RUN_LOG.jsonl")
    parser.add_argument("--workflow", required=True,
                        help="workflow 短标签，如 backtest / predict / evaluate")
    parser.add_argument("--outcome", required=True,
                        help="success / failure / cancelled / skipped")
    parser.add_argument("--extra-json", default="",
                        help="可选：任意扩展字段的 JSON 字符串（例如 backtest state 摘要）")
    args = parser.parse_args()

    extra: dict[str, Any] | None = None
    if args.extra_json:
        try:
            extra = json.loads(args.extra_json)
        except Exception as e:
            print(f"[run_log] --extra-json 解析失败，忽略: {e}")

    append_run_log(args.workflow, args.outcome, extra=extra)
