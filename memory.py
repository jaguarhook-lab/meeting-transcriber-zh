# -*- coding: utf-8 -*-
"""長期記憶：跨會議累積對使用者的理解（sdd: user-memory，2026-11-24）。

記憶.md（程式資料夾，個人檔案，不上傳、不打包）分四節，每條一行，附來源與日期：
  - 內容 〔2026-11-24 從 ＜會議名稱＞ 的修改學到〕
每次送給 AI 的提示附上「長期記憶」段落（來源標記不送，節省字數）。
AI 只「提議」新增／修改／刪除，使用者核可後才寫入；每次寫入前備份到 記憶備份\\，並記到 記憶變更紀錄.md。
"""
import datetime as dt
import difflib
import json
import re
import shutil
from pathlib import Path

from common import base_dir

SECTIONS = ("關於我們", "寫作偏好", "常見修正", "不要做的事")
SECTION_HINT = {"關於我們": "公司、船隊、人物與角色、往來單位等背景",
                "寫作偏好": "結構、用詞、詳略、格式",
                "常見修正": "AI 常寫錯、使用者常改的地方",
                "不要做的事": "使用者不要的寫法或內容"}
LIMIT = 3000                                             # 記憶太長會吃掉額度：超過就提醒整理
TAG = re.compile(r"\s*〔[^〕]*〕\s*$")


def path() -> Path:
    return base_dir() / "記憶.md"


def template() -> str:
    return ("# 長期記憶\n\n" + "這份檔案會隨每次提示送給 AI（Claude Code／Codex）。請不要寫入不想交給 AI 服務的個人資料。\n\n"
            + "\n\n".join(f"## {s}\n<!-- {SECTION_HINT[s]} -->\n" for s in SECTIONS) + "\n")


def load_text() -> str:
    p = path()
    try:
        return p.read_text(encoding="utf-8").replace("\r\n", "\n") if p.exists() else template()
    except OSError:
        return template()


def parse(text: str) -> dict:
    """→ {節名: [條目原文（含來源標記）]}；不認得的節照收。"""
    out, cur = {s: [] for s in SECTIONS}, None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            cur = m.group(1)
            out.setdefault(cur, [])
            continue
        m = re.match(r"^\s*[-*]\s+(.+)$", line)
        if cur and m:
            out[cur].append(m.group(1).strip())
    return out


def render(secs: dict) -> str:
    lines = ["# 長期記憶", "", "這份檔案會隨每次提示送給 AI（Claude Code／Codex）。請不要寫入不想交給 AI 服務的個人資料。", ""]
    for s in list(SECTIONS) + [k for k in secs if k not in SECTIONS]:
        lines.append(f"## {s}")
        if s in SECTION_HINT:
            lines.append(f"<!-- {SECTION_HINT[s]} -->")
        lines += [f"- {x}" for x in secs.get(s, [])]
        lines.append("")
    return "\n".join(lines)


def items_count(text: str = None) -> int:
    return sum(len(v) for v in parse(text if text is not None else load_text()).values())


def prompt_text(text: str = None) -> str:
    """送給 AI 的記憶本文（不含來源標記、註解）。"""
    secs = parse(text if text is not None else load_text())
    parts = []
    for s, items in secs.items():
        items = [TAG.sub("", x) for x in items if TAG.sub("", x)]
        if items:
            parts.append(f"【{s}】\n" + "\n".join(f"- {x}" for x in items))
    return "\n".join(parts)


def prompt_block() -> str:
    """提示詞 {長期記憶} 欄位：沒有記憶時回空字串（提示與沒有此功能時相同）。"""
    body = prompt_text()
    if not body:
        return ""
    return ("長期記憶（使用者過去的修改與說明累積而成；寫作時請遵守，與逐字稿衝突時以逐字稿為準）：\n" + body + "\n\n")


def size() -> int:
    return len(prompt_text())


# ── 寫入（備份＋變更紀錄）──────────────────────────────────────────────
def _backup():
    p = path()
    if p.exists():
        bk = base_dir() / "記憶備份"
        bk.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, bk / f"記憶_{dt.datetime.now():%Y%m%d_%H%M%S}.md")


def _changelog(lines: list, why: str):
    p = base_dir() / "記憶變更紀錄.md"
    head = "" if p.exists() else "# 記憶變更紀錄\n\n"
    with p.open("a", encoding="utf-8") as f:
        f.write(head + f"## {dt.datetime.now():%Y-%m-%d %H:%M}｜{why}\n" + "\n".join(f"- {x}" for x in lines) + "\n\n")


def save_text(text: str, why: str = "手動修改"):
    """整份寫入（手動編輯、整理記憶）：先備份，變更紀錄寫出前後差異的條目。"""
    old = load_text()
    _backup()
    path().write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    a, b = set(sum(parse(old).values(), [])), set(sum(parse(text).values(), []))
    _changelog([f"刪除：{x}" for x in sorted(a - b)] + [f"新增：{x}" for x in sorted(b - a)] or ["（只改了格式或註解）"], why)


def stamp(source: str) -> str:
    return f"〔{dt.date.today():%Y-%m-%d} {source}〕"


def apply(changes: list, source: str) -> int:
    """changes：[{op: 新增/修改/刪除, section, text, old}]（使用者已核可）。→ 實際套用的條數。"""
    secs = parse(load_text())
    n, log = 0, []
    for c in changes:
        sec = c.get("section") if c.get("section") in secs else "常見修正"
        items = secs.setdefault(sec, [])
        old = (c.get("old") or "").strip()
        idx = next((i for i, x in enumerate(items) if TAG.sub("", x) == old or x == old), None) if old else None
        if c["op"] == "新增" and c.get("text"):
            items.append(f"{c['text'].strip()} {stamp(source)}")
            log.append(f"新增〔{sec}〕{c['text'].strip()}")
        elif c["op"] == "修改" and idx is not None and c.get("text"):
            items[idx] = f"{c['text'].strip()} {stamp(source)}"
            log.append(f"修改〔{sec}〕{old} → {c['text'].strip()}")
        elif c["op"] == "刪除" and idx is not None:
            items.pop(idx)
            log.append(f"刪除〔{sec}〕{old}")
        else:
            continue
        n += 1
    if n:
        _backup()
        path().write_text(render(secs), encoding="utf-8")
        _changelog(log, f"核可 AI 提議（{source}）")
    return n


def add_one(section: str, text: str, source: str = "手動記住"):
    return apply([dict(op="新增", section=section, text=text)], source)


# ── 給 AI 的「記憶更新提議」與「整理記憶」──────────────────────────────
def edit_diff(orig: str, edited: str, limit: int = 15000) -> str:
    """AI 原稿 → 使用者定稿 的差異（只列改過的行），太長就截斷。"""
    d = [l for l in difflib.unified_diff(orig.splitlines(), edited.splitlines(), "AI原稿", "使用者定稿", n=1, lineterm="")
         if not l.startswith(("---", "+++"))]
    s = "\n".join(d)
    return s if len(s) <= limit else s[:limit] + f"\n（差異太長，以下省略；全部約 {len(s):,} 字）"


def proposal_prompt(orig: str, edited: str, pending_note: str = "") -> str:
    import prompts
    tpl = "【會議記錄】\n" + prompts.load("會議記錄")[0] + "\n\n【寫作規則】\n" + prompts.load("寫作規則")[0]
    return prompts.build("記憶更新提議", {"現有記憶": prompt_text() or "（目前沒有）", "修改差異": edit_diff(orig, edited) or "（沒有差異）",
                                         "待確認處理": pending_note or "（沒有資料）", "目前範本": tpl})


def propose(engine: str, orig: str, edited: str, pending_note: str = "") -> dict:
    """請 AI 提議記憶更新與範本修改建議（使用者核可後才套用）。格式不符丟 RuntimeError。"""
    import engines
    out = engines.run(engine, proposal_prompt(orig, edited, pending_note), timeout=900)
    try:
        return parse_proposal(out)
    except (ValueError, json.JSONDecodeError) as e:
        raise RuntimeError(f"{engine} 回傳的提議格式不符（{e}）：{out[:200]}")


def consolidate(engine: str) -> str:
    """請 AI 整理記憶 → 新的記憶全文（使用者看過差異、核可後才取代）。"""
    import engines
    import prompts
    old = load_text()
    out = engines.run(engine, prompts.build("記憶整理", {"現有記憶": old, "字數上限": str(LIMIT)}), timeout=900).strip()
    out = re.sub(r"^```(?:markdown|md)?\s*\n|\n```$", "", out).strip()
    if not any(f"## {s}" in out for s in SECTIONS) or items_count(out) == 0:
        raise RuntimeError(f"{engine} 回傳的整理結果格式不符：{out[:200]}")
    return out + "\n"


def parse_proposal(text: str) -> dict:
    """AI 回傳 → {"memory": [...], "template": [...]}；格式不符丟 ValueError。"""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("回傳內容不是 JSON")
    d = json.loads(m.group(0))
    mem = []
    for x in d.get("memory", []) or []:
        op = {"add": "新增", "modify": "修改", "delete": "刪除"}.get(str(x.get("op", "")).lower(), x.get("op"))
        if op in ("新增", "修改", "刪除") and (x.get("text") or op == "刪除"):
            mem.append(dict(op=op, section=x.get("section") if x.get("section") in SECTIONS else "常見修正",
                            text=str(x.get("text") or "").strip(), old=str(x.get("old") or "").strip(),
                            reason=str(x.get("reason") or "").strip()))
    tpl = []
    for x in d.get("template", []) or []:
        if x.get("name") and x.get("find") and x.get("replace") is not None:
            tpl.append(dict(name=str(x["name"]), find=str(x["find"]), replace=str(x["replace"]),
                            reason=str(x.get("reason") or "").strip()))
    return dict(memory=mem, template=tpl)
