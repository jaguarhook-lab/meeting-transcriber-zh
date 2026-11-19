# -*- coding: utf-8 -*-
"""寫字動畫進度元件（取代主畫面進度條；使用者 2026-11-19 選定「小手寫出逐字稿」）。

上行：握筆小手（✍）往右移動，把剛辨識出的句子一個字一個字寫出來，寫滿一行就淡出換行。
下行：細進度條。知道比例時顯示完成比例；不知道時（轉檔、載模型、AI 撰寫…）跑馬燈，小手反覆寫出目前階段說明。

API：stage(說明) 不確定進度；progress(0～1)；add_text(句子)；done(說明)；stop()（取消，變灰）；reset()。
"""
import math
import tkinter as tk
from tkinter import font as tkfont

INK, GRAY, BAR, TRACK = "#1f3864", "#9a9a9a", "#2e75b6", "#e3e8ef"
TICK_MS = 45


class HandWriter(tk.Canvas):
    def __init__(self, master, height=68, font_family="Microsoft JhengHei", **kw):
        super().__init__(master, height=height, highlightthickness=0, bg=kw.pop("bg", "white"), **kw)
        self.f_text = tkfont.Font(family=font_family, size=12)
        self.f_hand = tkfont.Font(family="Segoe UI Emoji", size=22)   # 握筆的手 ✍（Segoe UI Emoji 最清楚）
        self.h = height
        self.base_y = 34                                  # 文字基準列
        self.bar_y = height - 9
        self.reset()
        self.after(TICK_MS, self._tick)

    # ── 對外 API ─────────────────────────────────────────────
    def reset(self):
        self.delete("all")
        self.mode = "idle"                                # idle／stage／text／done／stopped
        self.frac = None                                  # None＝不確定進度（跑馬燈）
        self.pending = []                                 # 等著寫的句子
        self.cur, self.pos = "", 0                        # 正在寫的句子與已寫字數
        self.line_ids, self.x = [], 8
        self.hold = 0                                     # 寫完停頓的 tick 數
        self.fade = 0                                     # 淡出中的 tick 數
        self.loop_text = ""
        self.t = 0
        self.hand = self.create_text(8, self.base_y, text="", font=self.f_hand, fill=INK, anchor="sw")
        self.track = self.create_rectangle(0, 0, 0, 0, fill=TRACK, width=0)
        self.bar = self.create_rectangle(0, 0, 0, 0, fill=BAR, width=0)
        self.pct = self.create_text(0, 0, text="", font=("Segoe UI", 8), fill="#555", anchor="e")

    def stage(self, text):
        """不確定進度的階段：小手反覆寫出說明，進度條跑馬燈。"""
        if self.mode == "stage" and self.loop_text == text:
            return
        self.mode, self.frac, self.loop_text = "stage", None, text
        self.pending = []
        self._new_line(text)

    def progress(self, frac):
        self.frac = max(0.0, min(1.0, float(frac)))

    def add_text(self, sentence):
        sentence = str(sentence).strip()
        if not sentence:
            return
        if self.mode != "text":
            self.mode, self.pending = "text", []
            self._new_line("")
        self.pending.append(sentence)
        if len(self.pending) > 2:                         # 辨識比寫字快：跳到最新的句子，不越寫越落後
            self.pending = self.pending[-1:]

    def done(self, text="完成"):
        self.mode, self.frac, self.pending = "done", 1.0, []
        self._new_line(text)

    def stop(self):
        """取消：動畫停住並變灰。"""
        self.mode = "stopped"
        for i in self.line_ids + [self.hand, self.bar]:
            self.itemconfigure(i, fill=GRAY)

    # ── 內部 ─────────────────────────────────────────────────
    def _new_line(self, text):
        for i in self.line_ids:
            self.delete(i)
        self.line_ids, self.x = [], 8
        self.cur, self.pos, self.hold, self.fade = text, 0, 0, 0
        for i in (self.hand, self.bar):
            self.itemconfigure(i, fill=INK if i == self.hand else BAR)

    def _write_char(self, ch):
        w = self.winfo_width() or 600
        cw = self.f_text.measure(ch)
        if self.x + cw > w - 40:                          # 寫滿一行：淡出後從頭寫
            self.fade = 6
            return False
        self.line_ids.append(self.create_text(self.x, self.base_y + 4, text=ch, font=self.f_text, fill=INK, anchor="sw"))
        self.x += cw
        return True

    def _tick(self):
        try:
            self._step()
            self._draw_bar()
        except tk.TclError:
            return                                        # 視窗已關閉
        self.after(TICK_MS, self._tick)

    def _step(self):
        self.t += 1
        if self.mode in ("idle", "stopped"):
            if self.mode == "idle":
                self.itemconfigure(self.hand, text="")
            return
        if self.fade:                                     # 淡出整行
            self.fade -= 1
            shade = ["#c8cdd6", "#b0b8c6", "#97a3b6", "#7d8ea6", "#5f7393", "#425a80"][min(self.fade, 5)]
            for i in self.line_ids:
                self.itemconfigure(i, fill=shade)
            if not self.fade:
                rest = self.cur[self.pos:]
                self._new_line(rest)
            return
        if self.pos < len(self.cur):
            n = 2 if len(self.pending) else 1             # 還有句子在等：寫快一點
            for _ in range(n):
                if self.pos < len(self.cur) and self._write_char(self.cur[self.pos]):
                    self.pos += 1
                else:
                    break
        elif self.mode == "text" and self.pending:
            nxt = self.pending.pop(0)
            if self.x > 8:
                nxt = "　" + nxt                          # 句子之間空一格
            self.cur, self.pos = self.cur + nxt, len(self.cur)
        elif self.mode == "stage":                         # 寫完停一下再重寫
            self.hold += 1
            if self.hold > 18:
                self._new_line(self.loop_text)
        # 小手：在筆尖位置，寫字時上下微動
        writing = self.pos < len(self.cur) and not self.fade
        bob = math.sin(self.t * 1.3) * 2.2 if writing else 0
        self.itemconfigure(self.hand, text="✍")
        self.coords(self.hand, self.x + 1, self.base_y + 12 + bob)

    def _draw_bar(self):
        w = self.winfo_width() or 600
        x0, x1, y0, y1 = 8, w - 44, self.bar_y, self.bar_y + 5
        self.coords(self.track, x0, y0, x1, y1)
        if self.mode in ("idle",):
            self.coords(self.bar, 0, 0, 0, 0)
            self.itemconfigure(self.pct, text="")
            return
        if self.frac is None:                             # 跑馬燈
            span = (x1 - x0) * 0.18
            pos = (math.sin(self.t * 0.06) + 1) / 2 * (x1 - x0 - span)
            self.coords(self.bar, x0 + pos, y0, x0 + pos + span, y1)
            self.itemconfigure(self.pct, text="")
        else:
            self.coords(self.bar, x0, y0, x0 + (x1 - x0) * self.frac, y1)
            self.itemconfigure(self.pct, text=f"{self.frac:.0%}")
        self.coords(self.pct, w - 6, y0 + 3)
