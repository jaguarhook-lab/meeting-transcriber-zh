# -*- coding: utf-8 -*-
"""請選定的 AI（Claude Code 或 Codex）依逐字稿寫會議記錄與專題整理（Markdown）。"""
import re

import ai_engines

COMMON_RULES = """寫作規則：
- 繁體中文（台灣用字），Markdown 格式，只輸出文件內容本身，不要前言、不要程式碼框。
- 只寫逐字稿中實際講到的內容，不臆測、不補充會議沒講的事。
- 錄音沒有區分發言者：以職務或角色描述（如主持人、業務、會計），人名用逐字稿中的寫法。
- 每個議題、決議、待辦都附錄音時間點（hh:mm 或 hh:mm:ss）方便回查。
- 聽不清楚或判斷不出的內容加「（?）」；寧可標待確認，不要寫錯。
- 閒聊、與會議無關的段落省略。
- 若錄音在討論中途截止，要註明。"""

MINUTES_PROMPT = """請依下方逐字稿，寫一份會議記錄（整理版）。
會議名稱：{name}
{pending}
結構：
# {name} 會議記錄（整理版）
- 錄音檔、逐字稿檔名（{audio}、{transcript}）與說明（語音辨識產生、以錄音為準、（?）的意義）
- 「整理工具：本記錄由 {engine} 依逐字稿整理」
## 一、決議與待辦總表
（表格：# / 議題 / 決議／待辦 / 負責 / 時間；負責人不明寫「待確認」）
## 二、討論內容
（依議題分節，### 標題附時間範圍，條列要點）
## 三、待確認事項（人名與專有名詞）
（列出所有加了（?）的人名、公司名、專有名詞，以及上面指定的待確認詞）
{topic_note}
{rules}

逐字稿：
"""

TOPIC_PROMPT = """請依下方逐字稿，針對主題「{topic}」寫一份專題整理。
會議名稱：{name}
{pending}
要求：
- 說明中註明「本專題由 {engine} 依逐字稿整理」。
- 先找出逐字稿中討論此主題的段落，標明起訖時間；只整理這些段落實際講到的內容。
- 結構建議：說明（出處時間、說明文字）→ 為什麼要討論 → 現況與實例 → 討論出的做法或流程（依步驟條列，標出負責角色）→ **沒有定案、需要再決定的事（表格，列出各方意見與時間點）** → 會議中提到的待辦（- [ ] 清單）。
- 有爭議或沒定論的地方，一定要列在「沒有定案」那一節，不要寫成決議。
{rules}

逐字稿：
"""


def _clean(md: str) -> str:
    md = md.strip()
    m = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```$", md, re.S)
    return (m.group(1) if m else md).strip() + "\n"


def _pending(words: list) -> str:
    if not words:
        return ""
    return "以下詞語使用者已標為待確認，請在文中照原樣使用並加（?），並列入待確認區：" + "、".join(words) + "\n"


def minutes(name: str, audio: str, transcript_name: str, text: str, pending: list, topic: str, log,
            engine: str = "Claude Code") -> str:
    log(f"請 {engine} 撰寫會議記錄（約需數分鐘）…")
    note = f"（另有專題整理「{topic}」，討論內容中該主題只需簡述並註明見專題。）" if topic else ""
    p = MINUTES_PROMPT.format(name=name, audio=audio, transcript=transcript_name, pending=_pending(pending),
                              topic_note=note, rules=COMMON_RULES, engine=engine)
    return _clean(ai_engines.run(engine, p + text))


def topic_report(name: str, topic: str, text: str, pending: list, log, engine: str = "Claude Code") -> str:
    log(f"請 {engine} 撰寫專題「{topic}」（約需數分鐘）…")
    p = TOPIC_PROMPT.format(name=name, topic=topic, pending=_pending(pending), rules=COMMON_RULES, engine=engine)
    return _clean(ai_engines.run(engine, p + text))
