# -*- coding: utf-8 -*-
"""會議資料（議程、簡報、文件）讀出文字，供 AI 核對人名、文號、數字與議題（sdd: meeting-materials，2026-11-24）。

全部用純 Python（zipfile＋XML、pypdf），不加會被 Windows 應用程式控制擋的編譯元件。原檔只讀、不搬動、不修改。
讀出的文字快取在 _工作檔\\<會議>\\會議資料快取\\，原檔大小或修改時間變了才重讀。
"""
import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

TEXT_EXT = {".txt", ".md", ".csv", ".tsv"}
OLD_EXT = {".doc": "docx", ".ppt": "pptx", ".xls": "xlsx"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".webp"}
SUPPORTED = ("*.txt *.md *.csv *.tsv *.docx *.pptx *.xlsx *.pdf")
DEFAULT_LIMIT = 60000

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}


# ── 各格式讀文字 ─────────────────────────────────────────────────────
def _read_text_file(p: Path) -> str:
    data = p.read_bytes()
    for enc in ("utf-8-sig", "cp950", "big5", "utf-16"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _docx(p: Path) -> str:
    with zipfile.ZipFile(p) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    out = []
    body = root.find("w:body", NS)
    for el in (body if body is not None else []):
        tag = el.tag.split("}")[1]
        if tag == "p":
            t = "".join(x.text or "" for x in el.iter(f"{{{NS['w']}}}t")).strip()
            if t:
                out.append(t)
        elif tag == "tbl":                               # 表格：每列一行，儲存格用 | 隔開
            for tr in el.iter(f"{{{NS['w']}}}tr"):
                cells = ["".join(x.text or "" for x in tc.iter(f"{{{NS['w']}}}t")).strip() for tc in tr.findall("w:tc", NS)]
                if any(cells):
                    out.append(" | ".join(cells))
    return "\n".join(out)


def _xml_paras(xml: bytes) -> list:
    root = ET.fromstring(xml)
    paras = []
    for ap in root.iter(f"{{{NS['a']}}}p"):
        t = "".join(x.text or "" for x in ap.iter(f"{{{NS['a']}}}t")).strip()
        if t:
            paras.append(t)
    return paras


def _pptx(p: Path) -> str:
    out = []
    with zipfile.ZipFile(p) as z:
        names = set(z.namelist())
        slides = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.search(r"(\d+)", n.split("/")[-1]).group(1)))
        for i, s in enumerate(slides, 1):
            out.append(f"【投影片 {i}】")
            out += _xml_paras(z.read(s))
            rel = f"ppt/slides/_rels/{s.split('/')[-1]}.rels"      # 備忘稿：由投影片關聯找對應的 notesSlide
            if rel in names:
                for r in ET.fromstring(z.read(rel)).findall("rel:Relationship", NS):
                    if r.get("Type", "").endswith("/notesSlide"):
                        target = "ppt/" + r.get("Target").replace("../", "")
                        if target in names:
                            notes = [t for t in _xml_paras(z.read(target)) if not t.isdigit()]
                            if notes:
                                out.append("（備忘稿）" + " ".join(notes))
    return "\n".join(out)


def _xlsx(p: Path, max_rows: int = 2000) -> str:
    out = []
    with zipfile.ZipFile(p) as z:
        names = set(z.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("s:si", NS):
                shared.append("".join(x.text or "" for x in si.iter(f"{{{NS['s']}}}t")))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).findall("rel:Relationship", NS)}
        for sh in wb.iter(f"{{{NS['s']}}}sheet"):
            target = rels.get(sh.get(f"{{{NS['r']}}}id"), "")
            path = "xl/" + target.lstrip("/").replace("xl/", "") if target else ""
            if path not in names:
                continue
            out.append(f"【工作表：{sh.get('name')}】")
            n = 0
            for row in ET.fromstring(z.read(path)).iter(f"{{{NS['s']}}}row"):
                vals = []
                for c in row.findall("s:c", NS):
                    t, v = c.get("t"), c.find("s:v", NS)
                    if t == "s" and v is not None:
                        vals.append(shared[int(v.text)] if v.text and v.text.isdigit() and int(v.text) < len(shared) else "")
                    elif t == "inlineStr":
                        vals.append("".join(x.text or "" for x in c.iter(f"{{{NS['s']}}}t")))
                    else:
                        vals.append(v.text if v is not None and v.text else "")
                if any(x.strip() for x in vals):
                    out.append("\t".join(vals).rstrip())
                    n += 1
                    if n >= max_rows:
                        out.append(f"（此工作表超過 {max_rows} 列，以下省略）")
                        break
    return "\n".join(out)


def _pdf(p: Path) -> str:
    from pypdf import PdfReader
    r = PdfReader(str(p))
    out = []
    for i, page in enumerate(r.pages, 1):
        t = (page.extract_text() or "").strip()
        if t:
            out.append(f"【第 {i} 頁】\n{t}")
    return "\n".join(out)


def extract(p: Path) -> tuple:
    """→ (文字, 說明)。讀不出文字時文字為空、說明寫原因。"""
    p = Path(p)
    ext = p.suffix.lower()
    if not p.exists():
        return "", "找不到檔案（可能已被移動或改名）"
    if ext in OLD_EXT:
        return "", f"舊版格式讀不出文字，請用 Office 另存成 .{OLD_EXT[ext]}"
    if ext in IMG_EXT:
        return "", "圖片，讀不出文字"
    try:
        if ext in TEXT_EXT:
            t = _read_text_file(p)
        elif ext == ".docx":
            t = _docx(p)
        elif ext == ".pptx":
            t = _pptx(p)
        elif ext == ".xlsx":
            t = _xlsx(p)
        elif ext == ".pdf":
            t = _pdf(p)
            if not re.sub(r"【第 \d+ 頁】|\s", "", t):
                return "", "PDF 沒有文字層（可能是掃描檔），讀不出文字"
        else:
            return "", f"不支援的格式（{ext or '無副檔名'}）"
    except zipfile.BadZipFile:
        return "", "檔案損毀或不是有效的 Office 檔"
    except Exception as e:
        msg = str(e)
        if "encrypt" in msg.lower() or "password" in msg.lower():
            return "", "檔案有密碼保護，讀不出文字"
        return "", f"讀取失敗：{msg[:120]}"
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return (t, "") if t else ("", "沒有讀到文字")


# ── 快取 ─────────────────────────────────────────────────────────────
def _cache_file(workdir: Path, p: Path) -> Path:
    return workdir / "會議資料快取" / (hashlib.sha1(str(Path(p).resolve()).encode("utf-8")).hexdigest()[:16] + ".json")


def read(workdir: Path, p: Path) -> dict:
    """→ {path, name, text, note, chars}；原檔大小或修改時間沒變就用快取。"""
    p = Path(p)
    st = p.stat() if p.exists() else None
    key = [st.st_size, int(st.st_mtime)] if st else None
    cf = _cache_file(workdir, p)
    if key:
        try:
            c = json.loads(cf.read_text(encoding="utf-8"))
            if c.get("key") == key:
                return dict(path=str(p), name=p.name, text=c["text"], note=c["note"], chars=len(c["text"]))
        except Exception:
            pass
    text, note = extract(p)
    if key:
        try:
            cf.parent.mkdir(parents=True, exist_ok=True)
            cf.write_text(json.dumps(dict(key=key, text=text, note=note), ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return dict(path=str(p), name=p.name, text=text, note=note, chars=len(text))


# ── 組成送給 AI 的段落（份量控制）─────────────────────────────────────
def assemble(items: list, limit: int = DEFAULT_LIMIT) -> tuple:
    """items：[{name, text, send}]（依使用者排的順序）。→ (資料本文, 說明清單)。
    合計超過 limit 時，依順序截斷：超出的那份只送前段，之後的不送。"""
    out, notes, used = [], [], 0
    for i, it in enumerate(items, 1):
        if not it.get("send", True) or not it.get("text"):
            continue
        t = it["text"]
        room = limit - used
        if room <= 200:
            notes.append(f"「{it['name']}」超過上限，沒有送出")
            continue
        if len(t) > room:
            t = t[:room] + f"\n（以下截斷：原文共 {len(it['text']):,} 字，只送前 {room:,} 字）"
            notes.append(f"「{it['name']}」超過上限，只送前 {room:,} 字")
        out.append(f"【會議資料：{it['name']}】\n{t}")
        used += len(t)
    return "\n\n".join(out), notes


def prompt_block(rules: str, items: list, limit: int = DEFAULT_LIMIT) -> str:
    """給提示詞 {會議資料} 欄位的內容：使用規則＋資料本文；沒有要送的資料時回空字串（提示與沒有此功能時相同）。"""
    body, _notes = assemble(items, limit)
    if not body:
        return ""
    return f"{rules.strip()}\n\n{body}\n\n"
