# -*- coding: utf-8 -*-
"""判斷錯誤是不是 Windows 擋住程式元件，組成一般使用者看得懂的中文說明；錯誤另存 log（sdd: blocked-dll-resilience）。

背景：Windows 11「智慧型應用程式控制」與公司的應用程式控制（WDAC／AppLocker）會擋沒有數位簽章、信譽不足的 DLL／pyd。
被擋時 Python 的訊息是「DLL load failed while importing X: 應用程式控制原則已封鎖此檔案」（WinError 4551）。
"""
import datetime as dt
import os
import re
from pathlib import Path

POLICY = re.compile(r"應用程式控制|Application Control|WinError 4551|0x800711C7|blocked by your organization|"
                    r"群組原則已封鎖|已封鎖此檔案|has blocked this file", re.I)
DLL_FAIL = re.compile(r"DLL load failed|could not be loaded|找不到指定的模組|The specified module could not be found", re.I)
WHICH = re.compile(r"(?:while importing|importing)\s+([\w.]+)|No module named '([\w.]+)'|([\w\-.]+\.(?:dll|pyd))", re.I)

# 元件 → 用在哪個功能（說明給使用者）
USE = {"ctranslate2": "語音辨識", "faster_whisper": "語音辨識", "av": "讀取音檔", "onnxruntime": "語音偵測",
       "tokenizers": "語音辨識", "numpy": "音檔處理", "opencc": "繁體轉換", "_mupdf": "轉 PDF（舊版）"}


def component(text: str) -> str:
    """從錯誤訊息找出被擋的元件名稱（找不到回空字串）。
    先看錯誤追蹤裡出現的已知套件（_ext、_core 這類子元件對使用者沒意義），再退回訊息中的模組名。"""
    t = text or ""
    pkgs = [p for p in USE if re.search(rf"[\\/\"'\s]{re.escape(p)}[\\/.]", t)]
    if pkgs:                                             # 取最後出現的（最接近出錯處）
        return max(pkgs, key=lambda p: max(m.start() for m in re.finditer(rf"[\\/\"'\s]{re.escape(p)}[\\/.]", t)))
    for m in WHICH.finditer(t):
        name = next(g for g in m.groups() if g)
        if name not in ("mupdf",):
            return name
    return ""


def kind(text: str) -> str:
    """policy＝確定被應用程式控制擋；dll＝元件載入失敗（原因不確定）；''＝其他錯誤。"""
    if POLICY.search(text or ""):
        return "policy"
    if DLL_FAIL.search(text or ""):
        return "dll"
    return ""


def explain(text: str, where: str = "") -> tuple:
    """→ (標題, 說明)。不是被擋的錯誤回 (where 或「發生錯誤」, 原訊息第一行)。"""
    k, comp = kind(text), component(text)
    where = (where or "").strip()
    where = where[:-1] if where.endswith("中") else where        # 「語音辨識中」→「語音辨識」
    base = comp.split(".")[0].lstrip("_") if comp else ""
    use = USE.get(comp.split(".")[0], USE.get(base, "")) if comp else ""
    what = f"「{comp}」" + (f"（{use}用）" if use else "") if comp else "程式的部分元件"
    if k == "policy":
        return ("Windows 擋住了程式元件",
                f"Windows 的應用程式控制擋住了{what}，所以{where or '這個功能'}無法執行。\n\n"
                "處理方式：\n"
                "・自己的電腦：開「Windows 安全性」→「應用程式與瀏覽器控制」→「智慧型應用程式控制」查看是否為「開啟」。"
                "關閉後即可使用（依 Windows 版本，關閉後可能無法再開回來，請自行評估）。\n"
                "・公司電腦：請 IT 允許本程式資料夾（錄音轉文字）裡的檔案執行。\n\n"
                "按「複製錯誤訊息」可把完整訊息傳給協助的人。")
    if k == "dll":
        return ("程式元件載入失敗",
                f"{what}載入失敗，所以{where or '這個功能'}無法執行。\n\n"
                "常見原因：被防毒軟體或 Windows 的應用程式控制擋住，或程式資料夾的檔案不完整。\n"
                "・請重新解壓縮完整的程式資料夾再試（不要只複製 exe）。\n"
                "・若仍失敗，開「Windows 安全性」查看「保護歷程記錄」與「智慧型應用程式控制」，或請 IT 協助。\n\n"
                "按「複製錯誤訊息」可把完整訊息傳給協助的人。")
    first = (text or "").strip().splitlines()[0] if (text or "").strip() else "（沒有訊息）"
    return (where or "發生錯誤", first)


COMPONENTS = (("numpy", "音檔處理"), ("av", "讀取音檔"), ("ctranslate2", "語音辨識"), ("onnxruntime", "語音偵測"),
              ("tokenizers", "語音辨識"), ("faster_whisper", "語音辨識"), ("opencc", "繁體轉換"))


def check_components() -> list:
    """逐一載入辨識元件 → [(名稱, 用途, 狀態, 說明)]；狀態：OK／被擋／失敗。"""
    import importlib
    import traceback
    out = []
    for name, use in COMPONENTS:
        try:
            importlib.import_module(name)
            out.append((name, use, "OK", ""))
        except Exception as e:
            t = f"{e}\n{traceback.format_exc(limit=3)}"
            k = kind(t)
            out.append((name, use, "被擋" if k == "policy" else "失敗", str(e).splitlines()[0][:160]))
    return out


def environment_report(engines_mod=None, asr_mod=None, pdf_mod=None) -> tuple:
    """環境檢查全文 → (文字報告, 是否全部正常)。"""
    lines, ok_all = [], True
    lines.append("【語音辨識元件】")
    for name, use, st, msg in check_components():
        ok_all &= st == "OK"
        lines.append(f"  {'✓' if st == 'OK' else '✗'} {name}（{use}）：{st}" + (f"｜{msg}" if msg else ""))
    if any("被擋" in l for l in lines):
        lines.append("  → 有元件被 Windows 應用程式控制擋住，語音辨識無法使用。處理方式見「Windows 安全性 → 應用程式與瀏覽器控制 →"
                     " 智慧型應用程式控制」，公司電腦請 IT 允許本程式資料夾。")
    if pdf_mod:
        lines.append("【轉 PDF】")
        for label, fn in (("Microsoft Edge", pdf_mod.find_edge), ("中文字型", lambda: "／".join(pdf_mod.find_fonts()[1:]))):
            try:
                lines.append(f"  ✓ {label}：{fn()}")
            except Exception as e:
                ok_all = False
                lines.append(f"  ✗ {label}：{e}")
    if asr_mod:
        ms = asr_mod.list_models()
        ok_all &= bool(ms)
        lines.append("【語音模型】")
        lines.append("  " + ("✓ " + "、".join(n for n, _p in ms) if ms else "✗ 還沒有語音模型，請按「下載模型」"))
    if engines_mod:
        lines.append("【AI 工具】（至少一個即可）")
        for e in engines_mod.ENGINES:
            p = engines_mod.resolve_cli(e)
            lines.append(f"  {'✓' if p else '－'} {e}：{p or '未安裝（可按「一鍵安裝」）'}")
    return "\n".join(lines), ok_all


def log_dir() -> Path:
    d = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "錄音轉文字" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_log(prefix: str, text: str) -> Path:
    p = log_dir() / f"{prefix}_{dt.datetime.now():%Y%m%d_%H%M%S}.log"
    try:
        p.write_text(text, encoding="utf-8")
    except OSError:
        pass
    return p
