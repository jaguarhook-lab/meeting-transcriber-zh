# -*- coding: utf-8 -*-
"""「從我的修改學習」：比對原稿和改好的會議記錄，找出改過的詞。

只列像名詞校正的修改。數字、日期、金額的修改和純插入的文字不列，
免得把內容修訂學成替換規則。以標了（?）的詞為單位；抓不到完整的詞就標「需確認」。
"""
import difflib
import re

Q = "（?）"
WORD = re.compile(r"[\w㐀-鿿]")     
ASCII = re.compile(r"[A-Za-z0-9]")
DIGIT = re.compile(r"\d")
MAX_LEN = 12   # 更長的算整句改寫
GAP = 3        # 兩處修改相隔幾個字以內算同一個詞，例如「王曉明（?）」→「王小明」
# 標了（?）的詞，前面是行首、清單符號、標點、括號、粗體或引號
Q_WORD = re.compile(r"(?:^|(?<=[-\s、／/：:，,。；;（(「『【《*_]))([\w㐀-鿿][\w㐀-鿿 .&-]{0,10}?)（\?）", re.M)
NEED_CHECK = "需確認：只差一個字或抓不到完整的詞，請修正原寫法與改為"


def _core(s: str) -> str:
    return s.replace(Q, "").replace("(?)", "").strip()


def _has_word(s: str) -> bool:
    return bool(WORD.search(s))


def _numeric_change(a: str, b: str) -> bool:
    da, db = "".join(DIGIT.findall(a)), "".join(DIGIT.findall(b))
    if (da or db) and da != db:
        return True
    return False


def _left_run(text: str, end: int, limit: int = 8) -> str:
    i = end
    while i > 0 and end - i < limit and WORD.match(text[i - 1]):
        i -= 1
    return text[i:end]


def _hunks(sm) -> list:
    """相隔 GAP 字以內的修改併成一段。"""
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        if out:
            pi1, pi2, pj1, pj2 = out[-1]
            gap = sm.a[pi2:i1]
            closed = sm.a[pi1:pi2].endswith(Q)  # 以（?）結尾表示前一個詞已結束
            if not closed and i1 - pi2 <= GAP and all(WORD.match(c) for c in gap):
                out[-1] = (pi1, i2, pj1, j2)
                continue
        out.append((i1, i2, j1, j2))
    return out


def pending_words(text: str) -> set:
    """待確認清單每項開頭就是完整的詞，比從正文抓可靠。"""
    words = set(Q_WORD.findall(text))
    for line in text.splitlines():
        m = re.match(r"^\s*[-*]\s+\**([\w㐀-鿿][\w㐀-鿿 .&-]{0,10}?)\**(?:（\?）|[（(：:、，,])", line)
        if m:
            words.add(m.group(1).strip())
    return words


def _q_spans(orig: str, pend: set) -> list:
    """[(開始, 結束, 詞, 是否可信)]。
    正文中文詞前面常沒有標點，抓到的可能多帶前面的字（例「今天王曉明」）：
    對得到待確認清單的詞就以清單為準；對不到時，交給 diff_edits 以實際修改的範圍為準並標需確認。"""
    out = []
    for m in Q_WORD.finditer(orig):
        s, e, w = m.start(1), m.end(1), m.group(1)
        hit = next((w[k:] for k in range(len(w)) if w[k:] in pend), None)
        if hit:
            out.append((e - len(hit), e + len(Q), hit, True))
        else:
            # 3 個字以內多半是人名或簡稱，直接當完整的詞
            out.append((s, e + len(Q), w, len(w) <= 3))
    return out


def diff_edits(orig: str, edited: str, pend: set = frozenset()) -> tuple[list, int]:
    """回傳（改過的詞清單, 未列出的修改數）。清單每項：{原, 改, 次數, 前後文, 提醒}。
    pend：AI 待確認清單中的詞（有的話，用來判斷完整的詞）。
    - 「王曉明（?）」→「王小明」：原=王曉明、改=王小明（以標了（?）的完整詞為單位）
    - 只刪掉「（?）」：原=改=該詞（代表使用者確認寫法正確）"""
    q_spans = _q_spans(orig, set(pend))
    sm = difflib.SequenceMatcher(None, orig, edited, autojunk=False)
    found, skipped = {}, 0

    def add(a, b, i1, i2, note=""):
        key = (a, b)
        it = found.setdefault(key, {"原": a, "改": b, "次數": 0, "提醒": note,
                                    "前後文": orig[max(0, i1 - 12):i2 + 8].replace("\n", " ")})
        it["次數"] += 1

    def q_span_of(i1, i2):
        for s, e, w, sure in q_spans:
            if i1 < e and i2 > s:
                return s, e, w, sure
        return None

    def narrow(span, i1):
        """不可信的詞只取「修改開始處～（?）」，至少 2 個字。"""
        s, e, w, sure = span
        if sure:
            return s, ""
        start = min(max(s, i1), e - len(Q) - 2) if e - len(Q) - s >= 2 else s
        start = max(start, s)
        return start, ("" if start == s else NEED_CHECK)

    for i1, i2, j1, j2 in _hunks(sm):
        a, b = orig[i1:i2], edited[j1:j2]
        ca, cb = _core(a), _core(b)
        if not ca and not cb:
            if Q in a:  # 只刪掉（?）：使用者確認前面那個詞寫法正確
                span = q_span_of(i1, i2)
                if span:
                    if span[3] or len(span[2]) <= 2:
                        add(span[2], span[2], span[0], span[1])
                    else:  # 不知道詞從哪裡開始：先取最後 2 個字，標需確認
                        add(span[2][-2:], span[2][-2:], span[0], span[1], NEED_CHECK)
                else:
                    run = _left_run(orig, i1)
                    if run:
                        add(run[-2:], run[-2:], i1, i2, NEED_CHECK)
            continue
        if not (_has_word(ca) or _has_word(cb)) or not cb:
            continue  # 只動標點、空白、項目符號，或整段刪除
        if not ca:
            skipped += 1  # 純插入文字（例如補上職稱）不是名詞校正
            continue
        if _numeric_change(ca, cb):
            skipped += 1  # 數字、日期、時間、金額的修改是內容修訂，不學
            continue
        note = ""
        span = q_span_of(i1, i2)
        if span:
            # 擴到整個標了（?）的詞
            s, note = narrow(span, i1)
            e = span[1]
            left, right = max(0, i1 - s), max(0, e - i2)
            ca = _core(orig[min(s, i1):max(e, i2)])
            cb = _core(edited[max(0, j1 - left):j2 + right])
        else:
            # 英數字補成完整字串，例如 MSNC → MSMC
            while i1 > 0 and j1 > 0 and ASCII.match(orig[i1 - 1]) and orig[i1 - 1] == edited[j1 - 1]:
                i1, j1 = i1 - 1, j1 - 1
            while i2 < len(orig) and j2 < len(edited) and ASCII.match(orig[i2]) and orig[i2] == edited[j2]:
                i2, j2 = i2 + 1, j2 + 1
            ca, cb = _core(orig[i1:i2]), _core(edited[j1:j2])
            if len(ca) <= 1 or len(cb) <= 1:
                left = _left_run(orig, i1, 1)  # 只改一個字：先帶上前一字當建議，並提醒使用者確認
                ca, cb = left + ca, left + cb
                note = NEED_CHECK
        if len(ca) > MAX_LEN or len(cb) > MAX_LEN:
            skipped += 1
            continue
        if ca != cb:
            add(ca, cb, i1, i2, note)
    items = sorted(found.values(), key=lambda x: (bool(x["提醒"]), x["原"] == x["改"], -x["次數"]))
    return items, skipped
