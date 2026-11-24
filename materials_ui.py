# -*- coding: utf-8 -*-
"""「會議資料」視窗：加入議程、簡報、文件，讀出文字給 AI 核對（sdd: meeting-materials）。
清單記在工作檔 state.json（materials：[{path, send}]、materials_limit）；原檔只讀，移除只是從清單拿掉。"""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import materials as MT

FONT = "Microsoft JhengHei"


def load_items(app, c) -> list:
    """工作檔記的清單 → [{path, name, text, note, chars, send}]（依順序）。"""
    out = []
    for m in app.state(c.workdir).get("materials", []):
        it = MT.read(c.workdir, Path(m["path"]))
        it["send"] = bool(m.get("send", True))
        out.append(it)
    return out


def block(app, c) -> tuple:
    """→ (給 {會議資料} 的內容, 份數, 字數)；沒有要送的資料回 ("", 0, 0)。"""
    import prompts
    items = load_items(app, c)
    limit = int(app.state(c.workdir).get("materials_limit", MT.DEFAULT_LIMIT))
    body, _n = MT.assemble(items, limit)
    if not body:
        return "", 0, 0
    sent = [it for it in items if it["send"] and it["text"]]
    return MT.prompt_block(prompts.load("會議資料規則")[0], items, limit), len(sent), len(body)


class MaterialsWindow:
    def __init__(self, app, c):
        self.app, self.c = app, c
        w = self.win = tk.Toplevel(app.root)
        w.title(f"會議資料：{c.name}")
        w.geometry("900x560")
        ttk.Label(w, text="加入這場會議的議程、簡報、文件（txt、md、csv、Word、PowerPoint、Excel、PDF）。"
                          "讀出的文字會和逐字稿一起送給 AI，用來核對人名、文號、數字與議題；記錄內容仍以會議實際講到的為準。\n"
                          "原檔不會被移動或修改；「移除」只是從清單拿掉。資料會送給 AI 服務，請確認可以交出去。",
                  wraplength=860, foreground="#555", padding=(10, 8)).pack(anchor="w")
        f = ttk.Frame(w)
        f.pack(fill="both", expand=True, padx=10)
        self.tv = ttk.Treeview(f, columns=("send", "name", "chars", "note"), show="headings", selectmode="browse")
        for k, t, wd in (("send", "送出", 50), ("name", "檔名", 360), ("chars", "字數", 80), ("note", "狀態", 330)):
            self.tv.heading(k, text=t)
            self.tv.column(k, width=wd, anchor="center" if k in ("send", "chars") else "w")
        sb = ttk.Scrollbar(f, command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tv.bind("<Double-1>", lambda _: self.preview())
        bf = ttk.Frame(w, padding=(10, 6))
        bf.pack(fill="x")
        for text, cmd in (("加入檔案…", self.add), ("移除", self.remove), ("上移", lambda: self.move(-1)),
                          ("下移", lambda: self.move(1)), ("送出／不送", self.toggle), ("預覽讀出的文字", self.preview),
                          ("重新讀取", self.refresh)):
            ttk.Button(bf, text=text, command=cmd).pack(side="left", padx=(0, 4))
        lf = ttk.Frame(w, padding=(10, 0, 10, 8))
        lf.pack(fill="x")
        ttk.Label(lf, text="送出上限（字）").pack(side="left")
        self.v_limit = tk.IntVar(value=int(app.state(c.workdir).get("materials_limit", MT.DEFAULT_LIMIT)))
        sp = ttk.Spinbox(lf, from_=10000, to=300000, increment=10000, textvariable=self.v_limit, width=8,
                         command=self.save_limit)
        sp.pack(side="left", padx=4)
        sp.bind("<FocusOut>", lambda _: self.save_limit())
        self.v_sum = tk.StringVar()
        ttk.Label(lf, textvariable=self.v_sum, foreground="#1a5276").pack(side="left", padx=10)
        ttk.Button(lf, text="關閉", command=w.destroy).pack(side="right")
        self.refresh()

    # ── 清單 ──────────────────────────────────────────────────
    def entries(self) -> list:
        return list(self.app.state(self.c.workdir).get("materials", []))

    def store(self, entries):
        self.app.save_state(self.c.workdir, materials=entries)

    def refresh(self):
        sel = self.tv.selection()
        self.items = load_items(self.app, self.c)
        self.tv.delete(*self.tv.get_children())
        for i, it in enumerate(self.items):
            self.tv.insert("", "end", iid=str(i), values=("✓" if it["send"] else "—", it["name"],
                                                           f"{it['chars']:,}" if it["chars"] else "—", it["note"] or "可讀取"))
        if sel and self.tv.exists(sel[0]):
            self.tv.selection_set(sel[0])
        limit = self.v_limit.get()
        _body, notes = MT.assemble(self.items, limit)
        send = [it for it in self.items if it["send"] and it["text"]]
        total = sum(it["chars"] for it in send)
        self.v_sum.set(f"要送出 {len(send)} 份，合計 {total:,} 字（上限 {limit:,}）" + ("；" + "；".join(notes) if notes else ""))

    def sel_index(self):
        s = self.tv.selection()
        return int(s[0]) if s else None

    def add(self):
        ps = filedialog.askopenfilenames(parent=self.win, title="選擇會議資料",
                                         filetypes=[("可讀取的資料", MT.SUPPORTED), ("全部檔案", "*.*")])
        if not ps:
            return
        ent = self.entries()
        have = {str(Path(e["path"]).resolve()).lower() for e in ent}
        for p in ps:
            if str(Path(p).resolve()).lower() not in have:
                ent.append(dict(path=str(Path(p)), send=True))
        self.store(ent)
        self.win.configure(cursor="watch")
        self.win.update()
        try:
            self.refresh()
        finally:
            self.win.configure(cursor="")
        self.app.log(f"會議資料：加入 {len(ps)} 份（{self.c.name}）")

    def remove(self):
        i = self.sel_index()
        if i is None:
            return
        ent = self.entries()
        name = Path(ent[i]["path"]).name
        if messagebox.askyesno("移除", f"把「{name}」從清單拿掉？\n（原檔不會被刪除）", parent=self.win):
            ent.pop(i)
            self.store(ent)
            self.refresh()

    def move(self, d):
        i = self.sel_index()
        ent = self.entries()
        if i is None or not 0 <= i + d < len(ent):
            return
        ent[i], ent[i + d] = ent[i + d], ent[i]
        self.store(ent)
        self.refresh()
        self.tv.selection_set(str(i + d))

    def toggle(self):
        i = self.sel_index()
        if i is None:
            return
        ent = self.entries()
        ent[i]["send"] = not ent[i].get("send", True)
        self.store(ent)
        self.refresh()

    def save_limit(self):
        try:
            v = max(10000, int(self.v_limit.get()))
        except (tk.TclError, ValueError):
            v = MT.DEFAULT_LIMIT
        self.v_limit.set(v)
        self.app.save_state(self.c.workdir, materials_limit=v)
        self.refresh()

    def preview(self):
        i = self.sel_index()
        if i is None:
            return
        it = self.items[i]
        d = tk.Toplevel(self.win)
        d.title(f"讀出的文字：{it['name']}")
        d.geometry("820x600")
        t = tk.Text(d, wrap="word", font=(FONT, 10))
        t.insert("1.0", it["text"] or f"（{it['note']}）")
        t.configure(state="disabled")
        t.pack(fill="both", expand=True, padx=8, pady=8)
