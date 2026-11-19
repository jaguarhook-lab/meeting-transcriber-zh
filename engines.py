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
        # 常見安裝位置（不在 PATH 時用）：官方原生安裝、npm、winget
        "extra": (r"%USERPROFILE%\.local\bin\claude.exe", r"%APPDATA%\npm\claude.cmd",
                  r"%LOCALAPPDATA%\Microsoft\WindowsApps\claude.exe"),
        "strip": "ANTHROPIC_API_KEY",
        "login_args": (),   # 執行 claude 第一次會跳出瀏覽器登入；已登入時可輸入 /login 切換帳號
        "usage_url": "https://claude.ai/settings/usage",
    },
    "Codex": {
        "names": ("codex", "codex.cmd", "codex.exe"),
        "extra": (r"%LOCALAPPDATA%\Programs\OpenAI\Codex\bin\codex.exe", r"%APPDATA%\npm\codex.cmd",
                  r"%LOCALAPPDATA%\Microsoft\WindowsApps\codex.exe"),
        "strip": "OPENAI_API_KEY",
        "login_args": ("login",),
        "usage_url": "https://chatgpt.com/codex/settings/usage",
    },
}

# PowerShell 用完整路徑：PATH 不完整的電腦也叫得起來
POWERSHELL = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
if not os.path.exists(POWERSHELL):
    POWERSHELL = "powershell"

# ── 一鍵安裝設定表（官方改安裝方式時只改這裡；查證 2026-11-19，見 sdd/one-click-install/proposal.md）──
# 兩者都是官方獨立安裝程式：不需系統管理員、不需 Git、不需 Node.js，只支援 64 位元 Windows。
_PS_PRE = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ProgressPreference='SilentlyContinue'; "
INSTALLERS = {
    "Claude Code": {
        "script": "irm https://claude.ai/install.ps1 | iex",
        "host": "https://claude.ai",
        "dirs": (r"%USERPROFILE%\.local\bin",),                         # 官方安裝程式不保證加 PATH → 本程式補
        "doc": "https://code.claude.com/docs/en/setup",
        "after": "安裝後按「登入帳號」，用瀏覽器登入 claude.ai 帳號（需 Pro／Max／Team 等付費方案）。",
    },
    "Codex": {
        "script": "irm https://chatgpt.com/codex/install.ps1 | iex",
        "host": "https://chatgpt.com",
        "dirs": (r"%LOCALAPPDATA%\Programs\OpenAI\Codex\bin",),          # 官方安裝程式會自己加；本程式再確認
        "doc": "https://github.com/openai/codex",
        "after": "安裝後按「登入帳號」，用瀏覽器登入 ChatGPT 帳號。",
    },
}


def install_cmd(engine: str) -> list:
    return [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _PS_PRE + INSTALLERS[engine]["script"]]


def manual_help(engine: str) -> str:
    i = INSTALLERS[engine]
    return (f"在「開始」搜尋 PowerShell 並開啟，貼上下面這行後按 Enter：\n\n{i['script']}\n\n"
            f"{i['after']}\n裝好後關閉並重新開啟本程式。\n官方說明：{i['doc']}")


# ── 找 CLI（resolve_cli）───────────────────────────────────────────────
ENV_KEY = r"Environment"          # 使用者環境變數的登錄機碼（測試時可改成測試用機碼）


def _reg_path(user_key: str = None) -> str:
    """從登錄檔重讀 User＋Machine PATH（本程式開著時才裝好的工具，os.environ 裡還沒有）。"""
    import winreg
    parts = []
    for root, key in ((winreg.HKEY_CURRENT_USER, user_key or ENV_KEY),
                      (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
        try:
            with winreg.OpenKey(root, key) as k:
                v, _t = winreg.QueryValueEx(k, "Path")
                parts.append(os.path.expandvars(v))
        except OSError:
            pass
    return ";".join(parts)


def resolve_cli(engine: str, log=None) -> str | None:
    """依序：目前 PATH → 登錄檔重讀的 PATH → 常見安裝位置。找到的資料夾補進本程式 PATH，之後的子程序也找得到。"""
    e = ENGINES[engine]
    found, how = None, ""
    for n in e["names"]:
        found = shutil.which(n)
        if found:
            how = "目前 PATH"
            break
    if not found:
        rp = _reg_path()
        for n in e["names"]:
            found = shutil.which(n, path=rp)
            if found:
                how = "登錄檔 PATH"
                break
    if not found:
        for x in e["extra"]:
            p = Path(os.path.expandvars(x))
            if p.exists():
                found, how = str(p), "常見安裝位置"
                break
    if found:
        add_process_path(str(Path(found).parent))
        if found.lower().endswith(".cmd"):                       # npm 版要靠 node 才能跑
            _ensure_node(log)
        if log and how != "目前 PATH" and found not in _logged:     # 同一路徑只記一次
            _logged.add(found)
            log(f"找到 {engine}：{found}（{how}，已補進本程式 PATH）")
    return found


_logged = set()
NODE_EXTRA = (r"%ProgramFiles%\nodejs\node.exe", r"%ProgramFiles(x86)%\nodejs\node.exe",
              r"%LOCALAPPDATA%\Programs\nodejs\node.exe", r"%NVM_SYMLINK%\node.exe")


def _ensure_node(log=None) -> None:
    """npm 安裝的 claude.cmd／codex.cmd 會呼叫 node；node 不在本程式 PATH 時，同樣從登錄檔 PATH、常見位置找並補上。"""
    if shutil.which("node"):
        return
    p = shutil.which("node", path=_reg_path())
    if not p:
        p = next((str(Path(os.path.expandvars(x))) for x in NODE_EXTRA
                  if "%" not in os.path.expandvars(x) and Path(os.path.expandvars(x)).exists()), None)
    if p:
        add_process_path(str(Path(p).parent))
        if log and p not in _logged:
            _logged.add(p)
            log(f"找到 Node.js：{p}（已補進本程式 PATH）")
    elif log:
        log("注意：這個 AI 是用 npm 安裝的，需要 Node.js，但找不到 node。可按「安裝說明」改用官方安裝方式重裝。")


def find(engine: str) -> str | None:
    return resolve_cli(engine)


def other(engine: str) -> str:
    return "Codex" if engine == "Claude Code" else "Claude Code"


# ── PATH 處理 ─────────────────────────────────────────────────────────
def _norm(p: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.expandvars(p.strip().strip('"')))) if p.strip() else ""


def add_process_path(d: str) -> bool:
    """把資料夾加到本程式的 PATH（不用重開程式）。已在就不加。"""
    cur = os.environ.get("PATH", "")
    if _norm(d) in {_norm(x) for x in cur.split(";")}:
        return False
    os.environ["PATH"] = d + ";" + cur
    return True


def add_user_path(dirs, key: str = None) -> list:
    """把資料夾加進「使用者」PATH（HKCU\\Environment），已存在不重複；送 WM_SETTINGCHANGE 讓之後開的程式拿到新 PATH。
    回傳實際新增的資料夾。只新增，不刪除、不改順序。"""
    import winreg
    key = key or ENV_KEY
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ | winreg.KEY_WRITE) as k:
        try:
            cur, typ = winreg.QueryValueEx(k, "Path")
        except OSError:
            cur, typ = "", winreg.REG_EXPAND_SZ
        have = {_norm(x) for x in cur.split(";")}
        add = [d for d in dirs if _norm(d) and _norm(d) not in have]
        if add:
            new = ";".join([x for x in cur.split(";") if x.strip()] + add)
            winreg.SetValueEx(k, "Path", 0, typ if typ in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) else winreg.REG_EXPAND_SZ, new)
    if add and key == "Environment":                           # 測試用機碼不廣播
        _broadcast_env()
    for d in dirs:
        add_process_path(d)
    return add


def _broadcast_env() -> None:
    import ctypes
    from ctypes import wintypes
    res = wintypes.DWORD()
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, ctypes.byref(res))


# ── 登入視窗 ──────────────────────────────────────────────────────────
_login_proc = {}


def open_login(engine: str, log=None):
    """開登入視窗（PowerShell）。同一個 AI 的登入視窗還開著時不再開新的，回傳 None。"""
    old = _login_proc.get(engine)
    if old is not None and old.poll() is None:
        return None
    exe = resolve_cli(engine, log)
    if not exe:
        raise RuntimeError(f"找不到 {engine}，請先按「一鍵安裝」。")
    tip = ("已登入時可在 Claude Code 中輸入 /login 切換帳號，完成後輸入 /exit 離開。" if engine == "Claude Code"
           else "依畫面在瀏覽器完成登入後，此視窗可關閉。")
    q = "'" + exe.replace("'", "''") + "'"                     # 路徑可能有中文、空格
    args = " ".join(ENGINES[engine]["login_args"])
    ps = f"Write-Host '{tip}' -ForegroundColor Yellow; & {q} {args}"
    env = dict(os.environ)
    env["PATH"] = str(Path(exe).parent) + ";" + env.get("PATH", "")
    if log:
        log(f"登入視窗執行：{exe} {args}".rstrip())
    p = subprocess.Popen([POWERSHELL, "-NoExit", "-NoProfile", "-Command", ps], env=env,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
    _login_proc[engine] = p
    return p


# ── 一鍵安裝 ──────────────────────────────────────────────────────────
class InstallError(RuntimeError):
    def __init__(self, title: str, advice: str, output: str = "", logfile: str = ""):
        self.title, self.advice, self.output, self.logfile = title, advice, output, logfile
        super().__init__(f"{title}：{advice}")


def log_dir() -> Path:
    d = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "錄音轉文字" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def classify_failure(engine: str, text: str) -> tuple:
    """安裝輸出 → (標題, 給一般使用者的建議)。"""
    host = INSTALLERS[engine]["host"]
    t = text or ""
    if re.search(r"32-bit|32 位元", t, re.I):
        return "這台電腦是 32 位元 Windows", f"{engine} 只支援 64 位元 Windows，這台電腦無法安裝，請改用其他電腦。"
    if re.search(r"supported-countries|not available in your (country|region)|\b403\b|Forbidden", t, re.I):
        return "所在地區或網路無法下載", f"官方伺服器拒絕下載（403）。可能是所在地區不支援，或公司網路被擋。請 IT 協助確認可以連到 {host}。"
    if re.search(r"remote name could not be resolved|無法解析|Unable to connect|無法連線|could not connect|timed out|逾時|"
                 r"actively refused|拒絕連線|SSL|TLS|secure channel|安全通道|proxy|\b407\b|No such host|Name or service not known",
                 t, re.I):
        return "連不到官方網站", f"這台電腦連不到 {host}。請確認網路正常；公司防火牆或 Proxy 可能擋住，請 IT 協助開放。"
    if re.search(r"ExecutionPolicy|執行原則|digitally signed|數位簽章|disabled on this system|已停用指令碼|"
                 r"AuthorizationManager|group policy|群組原則|ConstrainedLanguage", t, re.I):
        return "PowerShell 被公司政策限制", "公司電腦的安全政策禁止執行安裝指令碼。請 IT 協助安裝，或用下方的手動安裝說明。"
    if re.search(r"checksum|hash mismatch|雜湊|SHA256", t, re.I):
        return "下載的檔案驗證失敗", "可能是網路不穩、檔案沒下載完整。請稍後再按一次「一鍵安裝」。"
    if re.search(r"Access is denied|存取被拒|UnauthorizedAccess|permission", t, re.I):
        return "沒有寫入權限", "安裝位置無法寫入（可能被防毒軟體或公司政策擋住）。請 IT 協助。"
    return "安裝失敗", "原因無法自動判斷。請按「複製錯誤訊息」傳給負責的同事，或用下方的手動安裝說明。"


def preflight(engine: str) -> None:
    """安裝前檢查：64 位元、連得到官網。不通過丟 InstallError。"""
    import urllib.request
    import urllib.error
    arch = os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE", "")
    if arch.upper() not in ("AMD64", "ARM64"):
        raise InstallError(*classify_failure(engine, "32-bit"))
    host = INSTALLERS[engine]["host"]
    try:
        urllib.request.urlopen(urllib.request.Request(host, method="HEAD", headers={"User-Agent": "Mozilla/5.0"}), timeout=15)
    except urllib.error.HTTPError:
        pass                                   # 有回應（即使 403/405）就代表連得到，交給安裝程式判斷
    except Exception as e:
        raise InstallError(*classify_failure(engine, f"Unable to connect: {e}"), output=str(e))


def install(engine: str, log, cancel=None, cmd: list = None) -> str:
    """背景安裝（不跳黑視窗）。輸出即時寫進 log 並另存 logs\\安裝_*.log；完成後補 PATH、驗證版本。
    回傳 CLI 完整路徑；失敗丟 InstallError，取消丟 Cancelled。cmd 只供測試替換安裝指令。"""
    import time
    if cmd is None:
        preflight(engine)
    logf = log_dir() / f"安裝_{engine.replace(' ', '')}_{time.strftime('%Y%m%d_%H%M%S')}.log"
    cmd = cmd or install_cmd(engine)
    lines = []
    with logf.open("w", encoding="utf-8") as lf:
        lf.write(f"指令：{' '.join(cmd)}\n\n")
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             creationflags=NOWIN)
        import threading as th

        def pump():
            for raw in iter(p.stdout.readline, b""):
                s = raw.decode("utf-8", errors="replace").rstrip()
                if not s:
                    continue
                lines.append(s)
                lf.write(s + "\n")
                lf.flush()
                log("  " + s)
        t = th.Thread(target=pump, daemon=True)
        t.start()
        while p.poll() is None:
            if cancel is not None and cancel.is_set():
                kill_tree(p)
                t.join(3)
                lf.write("\n使用者取消\n")
                raise Cancelled(f"已取消安裝 {engine}")
            time.sleep(0.3)
        t.join(5)
        out = "\n".join(lines)
        lf.write(f"\n結束代碼：{p.returncode}\n")
        failed = p.returncode != 0 or (re.search(r"(^|\n)\s*(Error|錯誤|Exception|例外)", out) and not _installed_dirs(engine))
        if failed:
            title, advice = classify_failure(engine, out)
            lf.write(f"判讀：{title}｜{advice}\n")
            raise InstallError(title, advice, out, str(logf))
        added = add_user_path(_installed_dirs(engine) or [])
        if added:
            log(f"已把 {'、'.join(added)} 加進使用者 PATH（不用重開程式）")
            lf.write(f"加入使用者 PATH：{added}\n")
        exe = resolve_cli(engine, log)
        if not exe:
            raise InstallError("安裝程式已結束，但找不到 " + engine,
                               "可能安裝沒有完成。請按「複製錯誤訊息」傳給負責的同事，或用下方的手動安裝說明。", out, str(logf))
        ver = version(engine, exe)
        lf.write(f"安裝完成：{exe}｜{ver}\n")
    log(f"{engine} 安裝完成：{ver}（{exe}）")
    return exe


def _installed_dirs(engine: str) -> list:
    """設定表列的安裝資料夾中，實際有 CLI 的那些。"""
    names = ENGINES[engine]["names"]
    out = []
    for d in INSTALLERS[engine]["dirs"]:
        dd = os.path.expandvars(d)
        if any((Path(dd) / n).exists() for n in names if "." in n):
            out.append(dd)
    return out


def version(engine: str, exe: str = None) -> str:
    exe = exe or resolve_cli(engine)
    r = subprocess.run([exe, "--version"], capture_output=True, timeout=60, creationflags=NOWIN)
    return (r.stdout or r.stderr).decode("utf-8", errors="replace").strip().splitlines()[0] if (r.stdout or r.stderr) else "（無版本資訊）"


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


class Cancelled(RuntimeError):
    """使用者按了「取消」。"""


import threading as _threading

# 取消旗標綁在執行緒上：主程式的背景工作執行緒用 set_cancel(event) 綁定；
# 其他執行緒（例如校正畫面的「請 AI 找疑問詞」）沒綁，不受主畫面「取消」影響
_local = _threading.local()


def set_cancel(event) -> None:
    _local.cancel = event


def kill_tree(p: subprocess.Popen) -> None:
    """結束程序與它開出來的子程序（claude／codex 會再開 node 等子程序）。"""
    subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, creationflags=NOWIN)
    try:
        p.kill()
    except OSError:
        pass


def run(engine: str, prompt: str, timeout: int = 1800, cancel=None) -> str:
    """碰到使用上限丟 LimitError，使用者取消丟 Cancelled，其他失敗丟 RuntimeError。
    cancel：threading.Event，未給則用本執行緒以 set_cancel() 綁定的旗標；每秒檢查一次，取消時結束整個程序樹。"""
    import time
    cancel = cancel or getattr(_local, "cancel", None)
    exe = find(engine)
    if not exe:
        raise RuntimeError(f"找不到 {engine}。請先按「一鍵安裝」並登入。")
    env = {k: v for k, v in os.environ.items() if k.upper() != ENGINES[engine]["strip"]}
    with tempfile.TemporaryDirectory() as td:
        if engine == "Claude Code":
            args = [exe, "-p", "請依照標準輸入中的指示完成工作，只輸出要求的內容。"]
            outfile = None
        else:
            outfile = Path(td) / "last.txt"
            args = [exe, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only",
                    "--color", "never", "-C", td, "-o", str(outfile), "-"]
        p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             env=env, cwd=td, creationflags=NOWIN)
        data, t0 = prompt.encode("utf-8"), time.time()
        while True:
            try:
                ob, eb = p.communicate(input=data, timeout=1)
                break
            except subprocess.TimeoutExpired:
                data = None                               # 輸入只送第一次
                if cancel is not None and cancel.is_set():
                    kill_tree(p)
                    p.communicate()
                    raise Cancelled(f"已取消 {engine}")
                if time.time() - t0 > timeout:
                    kill_tree(p)
                    p.communicate()
                    raise RuntimeError(f"{engine} 超過 {timeout // 60} 分鐘沒有完成，已停止。")
        out = ob.decode("utf-8", errors="replace").strip()
        err = eb.decode("utf-8", errors="replace").strip()
        if outfile is not None:
            out = outfile.read_text(encoding="utf-8", errors="replace").strip() if outfile.exists() else ""
    if p.returncode != 0 or not out:
        check_limit(engine, f"{err}\n{out}")
        raise RuntimeError(f"{engine} 執行失敗（代碼 {p.returncode}）：{(err or out or '無輸出')[-800:]}")
    if len(out) < 400:  # 正常的會議記錄不會這麼短；短輸出才可能是上限訊息
        check_limit(engine, out)
    return out
