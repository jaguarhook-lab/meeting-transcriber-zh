# -*- coding: utf-8 -*-
"""呼叫 Claude Code／Codex 命令列工具。

呼叫時移除 ANTHROPIC_API_KEY、OPENAI_API_KEY，讓它用訂閱帳號而不是 API 計費。
內容從標準輸入送進去，避免中文和換行在命令列參數裡被弄壞。
"""
import datetime as dt
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class LimitError(RuntimeError):
    """reset：預計恢復時間，不知道時為 None。"""

    def __init__(self, engine: str, message: str, reset: dt.datetime | None):
        self.engine, self.message, self.reset = engine, message, reset
        super().__init__(f"{engine} 已達使用上限：{message}")


ENGINES = {
    "Claude Code": {
        "names": ("claude", "claude.cmd", "claude.exe"),
        "extra": (r"%APPDATA%\npm\claude.cmd", r"%USERPROFILE%\.local\bin\claude.exe"),
        "strip": "ANTHROPIC_API_KEY",
        "login": "claude",  # 第一次執行會跳出瀏覽器登入；已登入時可輸入 /login 切換帳號
        "usage_url": "https://claude.ai/settings/usage",
        "install": "irm https://claude.ai/install.ps1 | iex\n（或已有 Node.js 時：npm install -g @anthropic-ai/claude-code）\n安裝後執行 claude 並用瀏覽器登入 claude.ai 帳號。",
    },
    "Codex": {
        "names": ("codex", "codex.cmd", "codex.exe"),
        "extra": (r"%APPDATA%\npm\codex.cmd",),
        "strip": "OPENAI_API_KEY",
        "login": "codex login",
        "usage_url": "https://chatgpt.com/codex/settings/usage",
        "install": "npm install -g @openai/codex\n（需先安裝 Node.js 18 以上：https://nodejs.org）\n安裝後執行 codex login 並用瀏覽器登入 ChatGPT 帳號。",
    },
}


def find(engine: str) -> str | None:
    e = ENGINES[engine]
    for n in e["names"]:
        p = shutil.which(n)
        if p:
            return p
    for x in e["extra"]:
        p = Path(os.path.expandvars(x))
        if p.exists():
            return str(p)
    return None


def other(engine: str) -> str:
    return "Codex" if engine == "Claude Code" else "Claude Code"


def open_login(engine: str) -> None:
    exe = find(engine)
    if not exe:
        raise RuntimeError(f"找不到 {engine}，請先安裝（按「安裝說明」）。")
    cmd = ENGINES[engine]["login"]
    tip = "已登入時可在 Claude Code 中輸入 /login 切換帳號，完成後輸入 /exit 離開。" if engine == "Claude Code" else "依畫面在瀏覽器完成登入後，此視窗可關閉。"
    ps = f"Write-Host '{tip}' -ForegroundColor Yellow; {cmd}"
    subprocess.Popen(["powershell", "-NoExit", "-NoProfile", "-Command", ps],
                     creationflags=subprocess.CREATE_NEW_CONSOLE)


# 只比對英文訊息；逐字稿裡常有「額度」「上限」，放中文會誤判
LIMIT_PAT = re.compile(r"usage limit|rate limit|hit your (?:usage )?limit|limit reached|limit has been reached|"
                       r"too many requests|status(?: code)?:? 429|\b429 too many|quota exceeded|out of credits", re.I)


def _at_clock(text: str, now: dt.datetime) -> dt.datetime | None:
    """'3pm'、'3:05 PM'、'15:00' → 下一個該時刻"""
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?", text, re.I)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower().replace(".", "")
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if h > 23 or mi > 59 or (not ap and not m.group(2)):
        return None
    t = now.replace(hour=h, minute=mi, second=0, microsecond=0)
    return t if t > now else t + dt.timedelta(days=1)


def parse_reset(msg: str, now: dt.datetime | None = None) -> dt.datetime | None:
    now = now or dt.datetime.now()
    m = re.search(r"\|\s*(\d{10})\b", msg)  # 舊版 Claude Code：「...limit reached|1731250800」
    if m:
        return dt.datetime.fromtimestamp(int(m.group(1)))
    m = re.search(r"(?:try again|retry|resets?|available again)\s+in\s+((?:\d+\s*(?:days?|d|hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)[\s,]*(?:and\s+)?)+)", msg, re.I)
    if m:
        secs = 0
        for n, u in re.findall(r"(\d+)\s*([a-z]+)", m.group(1), re.I):
            u = u.lower()
            secs += int(n) * (86400 if u.startswith("d") else 3600 if u.startswith("h") else 60 if u.startswith("m") else 1)
        return now + dt.timedelta(seconds=secs)
    m = re.search(r"(?:resets?|try again|available again)\s*(?:at|on)?\s*([^\n.;()]{1,40})", msg, re.I)
    if m:
        return _at_clock(m.group(1), now)
    return None


def check_limit(engine: str, text: str) -> None:
    text = text[-1500:]  # Codex 會把輸入回顯在錯誤輸出前段，只看結尾的錯誤訊息
    if LIMIT_PAT.search(text):
        raise LimitError(engine, text.strip()[-500:], parse_reset(text))


def run(engine: str, prompt: str, timeout: int = 1800) -> str:
    """碰到使用上限丟 LimitError，其他失敗丟 RuntimeError。"""
    exe = find(engine)
    if not exe:
        raise RuntimeError(f"找不到 {engine}。請先安裝並登入（按「安裝說明」）。")
    env = {k: v for k, v in os.environ.items() if k.upper() != ENGINES[engine]["strip"]}
    with tempfile.TemporaryDirectory() as td:
        if engine == "Claude Code":
            args = [exe, "-p", "請依照標準輸入中的指示完成工作，只輸出要求的內容。"]
            outfile = None
        else:
            outfile = Path(td) / "last.txt"
            args = [exe, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only",
                    "--color", "never", "-C", td, "-o", str(outfile), "-"]
        r = subprocess.run(args, input=prompt.encode("utf-8"), capture_output=True, env=env,
                           cwd=td, timeout=timeout, creationflags=NOWIN)
        out = r.stdout.decode("utf-8", errors="replace").strip()
        err = r.stderr.decode("utf-8", errors="replace").strip()
        if outfile is not None:
            out = outfile.read_text(encoding="utf-8", errors="replace").strip() if outfile.exists() else ""
    if r.returncode != 0 or not out:
        check_limit(engine, f"{err}\n{out}")
        raise RuntimeError(f"{engine} 執行失敗（代碼 {r.returncode}）：{(err or out or '無輸出')[-800:]}")
    if len(out) < 400:  # 正常的會議記錄不會這麼短；短輸出才可能是上限訊息
        check_limit(engine, out)
    return out
