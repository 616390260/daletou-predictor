"""
通知模块 · 微信推送

支持通道：
- Server 酱 (sct.ftqq.com)：环境变量 SERVERCHAN_SENDKEY
- 企业微信群机器人：环境变量 WEWORK_WEBHOOK
- PushPlus：环境变量 PUSHPLUS_TOKEN

若均未配置，静默跳过（本地开发默认不发）
"""
from __future__ import annotations

import os
from typing import List, Optional

import requests


def repo_raw_url(rel_path: str) -> Optional[str]:
    """
    把 repo 内相对路径（如 data/img/xxx.png）转为 raw.githubusercontent.com URL

    @param rel_path 相对仓库根目录的文件路径
    @returns URL 字符串；若环境变量 GITHUB_REPOSITORY 不存在返回 None
    """
    repo = os.environ.get("GITHUB_REPOSITORY")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    if not repo:
        return None
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{rel_path.lstrip('/')}"


def _send_serverchan(title: str, content: str, sendkey: str) -> bool:
    """
    Server 酱推送（Markdown，支持图片 URL）
    """
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    try:
        resp = requests.post(
            url,
            data={"title": title[:32], "desp": content},
            timeout=15,
        )
        ok = resp.status_code == 200 and resp.json().get("code") == 0
        if not ok:
            print(f"[notify] Server酱 失败: {resp.text[:200]}")
        return ok
    except Exception as e:
        print(f"[notify] Server酱 异常: {e}")
        return False


def _send_wework(title: str, content: str, webhook: str) -> bool:
    """
    企业微信群机器人（markdown 格式）
    """
    try:
        resp = requests.post(
            webhook,
            json={
                "msgtype": "markdown",
                "markdown": {"content": f"### {title}\n\n{content}"},
            },
            timeout=10,
        )
        ok = resp.status_code == 200 and resp.json().get("errcode") == 0
        if not ok:
            print(f"[notify] 企业微信 失败: {resp.text[:200]}")
        return ok
    except Exception as e:
        print(f"[notify] 企业微信 异常: {e}")
        return False


def _send_pushplus(title: str, content: str, token: str) -> bool:
    """
    PushPlus 推送
    """
    try:
        resp = requests.post(
            "https://www.pushplus.plus/send",
            json={"token": token, "title": title, "content": content, "template": "markdown"},
            timeout=10,
        )
        ok = resp.status_code == 200 and resp.json().get("code") == 200
        if not ok:
            print(f"[notify] PushPlus 失败: {resp.text[:200]}")
        return ok
    except Exception as e:
        print(f"[notify] PushPlus 异常: {e}")
        return False


def notify(title: str, content: str) -> List[str]:
    """
    广播通知到所有已配置的通道

    @param title 标题
    @param content Markdown 正文
    @returns 成功的通道列表
    """
    channels: List[str] = []

    if key := os.environ.get("SERVERCHAN_SENDKEY"):
        if _send_serverchan(title, content, key):
            channels.append("ServerChan")

    if hook := os.environ.get("WEWORK_WEBHOOK"):
        if _send_wework(title, content, hook):
            channels.append("WeWork")

    if token := os.environ.get("PUSHPLUS_TOKEN"):
        if _send_pushplus(title, content, token):
            channels.append("PushPlus")

    if channels:
        print(f"[notify] 已推送到: {', '.join(channels)}")
    else:
        print("[notify] 未配置通道或推送失败，跳过")

    return channels
