# -*- coding: utf-8 -*-
"""比對 AI 原稿與使用者改好的會議記錄，找出改過的詞（供「從我的修改學習」）。"""
import difflib
import re

Q = "（?）"
WORD = re.compile(r"[\w㐀-鿿]")       # 中文、英數字
ASCII = re.compile(r"[A-Za-z0-9]")
MAX_LEN = 12   # 超過這個長度的改寫視為整句改寫，不列為詞
GAP = 3        # 兩處修改之間只隔幾個字以內，視為同一個詞的修改（例如「王曉明（?）」→「王小明」）
# AI 原稿中標了（?）的詞：出現在清單符號、頓號、斜線、冒號、括號等之後
Q_WORD = re.compile(r"(?:^|[-\s、／/：:，,（(「])([\w㐀-鿿][\w㐀-鿿 .&-]{0,10}?)（\?）", re.M)


def _core(s: str) -> str:
    return s.replace(Q, "").replace("(?)", "").strip()


def _has_word(s: str) -> bool:
    return bool(WORD.search(s))


def _left_run(text: str, end: int, limit: int = 8) -> str:
    i = end
    while i > 0 and end - i < limit and WORD.match(text[i - 1]):
        i -= 1
    return text[i:end]


def _hunks(sm) -> list:
    """把相鄰的修改（中間只隔 GAP 個以內的中文或英數字）合併成一段。回傳 [(i1, i2, j1, j2)]。"""
    ops = sm.get_opcodes()
    out = []
    for k, (op, i1, i2, j1, j2) in enumerate(ops):
        if op == "equal":
            continue
        if out:
            pi1, pi2, pj1, pj2 = out[-1]
            gap = sm.a[pi2:i1]
            closed = sm.a[pi1:pi2].endswith(Q)  # 前一段以（?）結尾＝前一個詞已結束（例如「黃小明（?）跟協定（?）」）
            if not closed and i1 - pi2 <= GAP and all(WORD.match(c) for c in gap):
                out[-1] = (pi1, i2, pj1, j2)
                continue
        out.append((i1, i2, j1, j2))
    return out


def diff_edits(orig: str, edited: str) -> tuple[list, int]:
    """回傳（改過的詞清單, 未列出的長改寫數）。清單每項：{原, 改, 次數, 前後文}。
    - 「黃小明（?）」→「王小明」：原=黃小明、改=王小明
    - 只刪掉「（?）」：原=改=該詞（代表使用者確認寫法正確）
    - 只改一個中文字時往左補一個字，例如「協定」→「協理」；英數字則補成完整的英數字串"""
    q_words = set(Q_WORD.findall(orig))
    sm = difflib.SequenceMatcher(None, orig, edited, autojunk=False)
    found, skipped = {}, 0

    def add(a, b, i1, i2):
        key = (a, b)
        found.setdefault(key, {"原": a, "改": b, "次數": 0, "前後文": orig[max(0, i1 - 12):i2 + 8].replace("\n", " ")})
        found[key]["次數"] += 1

    for i1, i2, j1, j2 in _hunks(sm):
        a, b = orig[i1:i2], edited[j1:j2]
        ca, cb = _core(a), _core(b)
        if not ca and not cb:
            if Q in a:  # 只刪掉（?）：使用者確認前面那個詞寫法正確
                run = _left_run(orig, i1)
                cands = [run[k:] for k in range(len(run)) if run[k:] in q_words]
                w = cands[-1] if cands else run[-2:]  # 取最短的（例如「涉及大華」→「大華」）
                if w:
                    add(w, w, i1, i2)
            continue
        if not (_has_word(ca) or _has_word(cb)) or not cb:
            continue  # 只動標點、空白、項目符號，或整段刪除
        # 英數字：補成完整字串（例如 MSNC → MSMC）
        while i1 > 0 and j1 > 0 and ASCII.match(orig[i1 - 1]) and orig[i1 - 1] == edited[j1 - 1]:
            i1, j1 = i1 - 1, j1 - 1
        while i2 < len(orig) and j2 < len(edited) and ASCII.match(orig[i2]) and orig[i2] == edited[j2]:
            i2, j2 = i2 + 1, j2 + 1
        ca, cb = _core(orig[i1:i2]), _core(edited[j1:j2])
        if len(ca) > MAX_LEN or len(cb) > MAX_LEN:
            skipped += 1
            continue
        if len(ca) <= 1 or len(cb) <= 1:
            left = _left_run(orig, i1, 1)  # 只改一個字：往左補上相同的前一字
            ca, cb = left + ca, left + cb
        if ca != cb:
            add(ca, cb, i1, i2)
    items = sorted(found.values(), key=lambda x: (x["原"] == x["改"], -x["次數"]))
    return items, skipped
