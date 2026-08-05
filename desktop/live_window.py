"""待办任务实况窗：置顶右侧，一任务一卡片。
未到期点击 → 暂时忽略(dismiss，到期重新弹出)；
到期点击 → 彻底完成(done)。"""

import time
import tkinter as tk
from datetime import datetime

from core.config import CONFIG
from storage import db

BG = "#0a0e1a"
PANEL = "#111827"
CYAN = "#38bdf8"
CYAN2 = "#4dd0e1"
INK = "#c9d2dd"
MUTED = "#8fa3b8"
RED = "#e25c6a"
AMBER = "#e8c96a"
LINE = "#24344d"

CARD_H = 104
PAD_X = 8


class LiveWindow:
    def __init__(self, root=None, on_dismiss=None, on_done=None):
        self.on_dismiss = on_dismiss or (lambda t: None)
        self.on_done = on_done or (lambda t: None)

        if root is None:
            self._master = tk.Tk()
            self._own_master = True
        else:
            self._master = root
            self._own_master = False

        self.win = tk.Toplevel(self._master)
        self.win.title("待办任务")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=BG)

        self.w = 340
        self.h = 560
        self.cards = []
        self._drag = None
        self._t0 = time.time()

        self._build_header()
        self._canvas = tk.Canvas(self.win, bg=BG, highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._canvas.bind("<Button-1>", self._on_click)
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)

        self._place_window()
        self.refresh()
        self._tick()

    def _build_header(self):
        bar = tk.Frame(self.win, bg=BG)
        bar.pack(side=tk.TOP, fill=tk.X)
        mark = tk.Label(bar, text="▲", bg=BG, fg=CYAN,
                        font=("Microsoft YaHei UI", 10))
        mark.pack(side=tk.LEFT, padx=(10, 0), pady=6)
        title = tk.Label(bar, text="待办任务", bg=BG, fg=INK,
                         font=("Microsoft YaHei UI", 12, "bold"))
        title.pack(side=tk.LEFT, padx=(4, 0))
        btn = tk.Label(bar, text="✕", bg=BG, fg=MUTED,
                       font=("Microsoft YaHei UI", 11), cursor="hand2")
        btn.pack(side=tk.RIGHT, padx=(0, 8))
        # ✕ 只负责隐藏；不参与拖拽（<Button-1> 与 <ButtonPress-1> 同一事件序列会互相覆盖）
        btn.bind("<Button-1>", lambda e: self.hide())

        for widget in (bar, mark, title):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)

    def _start_drag(self, event):
        self._drag = (event.x_root - self.win.winfo_x(),
                      event.y_root - self.win.winfo_y())

    def _on_press(self, event):
        self._drag = None

    def _on_drag(self, event):
        if self._drag:
            self.win.geometry(f"+{event.x_root - self._drag[0]}+{event.y_root - self._drag[1]}")

    def _place_window(self):
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"{self.w}x{self.h}+{sw - self.w - 20}+{max(40, sh - self.h - 80)}")

    def refresh(self):
        for c in self.cards:
            for it in c["items"]:
                self._canvas.delete(it)
        self.cards = []
        self._canvas.delete("emptytxt")

        today = datetime.now().date().isoformat()
        active = [t for t in db.list_tasks(status=db.TASK_ACTIVE)]
        dismissed_due = [t for t in db.list_tasks(status=db.TASK_DISMISSED)
                         if t["due_date"] and t["due_date"] <= today]
        visible = active + dismissed_due

        if not visible:
            self._canvas.create_text(self.w // 2, 90, text="暂无待办任务",
                                     fill=MUTED, tags="emptytxt",
                                     font=("Microsoft YaHei UI", 12))
            return
        for t in visible:
            due_flag = bool(t["due_date"]) and t["due_date"] <= today
            self._add_card(t, due_flag)
        self._layout()

    def _add_card(self, task, due_flag):
        c = self._canvas
        x = self.w + 40
        card_w = self.w - PAD_X * 2 - 10

        border = c.create_rectangle(x, 0, x + card_w, CARD_H, fill=PANEL,
                                    outline=RED if due_flag else LINE,
                                    width=3 if due_flag else 1)
        title = c.create_text(x + 12, 18, text=task["title"] or "任务", anchor="w",
                              fill=INK, font=("Microsoft YaHei UI", 11, "bold"),
                              width=card_w - 40)
        detail = c.create_text(x + 12, 42, text=(task["detail"] or ""), anchor="w",
                               fill=MUTED, font=("Microsoft YaHei UI", 9),
                               width=card_w - 30)
        due_text = ""
        if task["due_date"]:
            due_text = f"截止 {task['due_date']}"
        if due_flag:
            due_text = f"▲ 已到期 · {task['due_date']}"
        due = c.create_text(x + 12, 78, text=due_text, anchor="w",
                            fill=RED if due_flag else AMBER,
                            font=("Microsoft YaHei UI", 9, "bold"))
        src = c.create_text(x + card_w - 10, 94, text=f"{task['source']}",
                            anchor="e", fill="#5a5a66", font=("Microsoft YaHei UI", 8))
        accent = c.create_oval(x + card_w - 16, 10, x + card_w - 4, 22,
                               fill=CYAN2 if not due_flag else RED, outline="")
        self.cards.append({
            "task": task, "due": due_flag, "x": x, "y": 0, "card_w": card_w,
            "items": [border, title, detail, due, src, accent],
            "border": border, "due_item": due,
        })

    def _layout(self):
        y = 10
        for c in self.cards:
            c["y"] = y
            self._apply_card(c)
            y += CARD_H + 10
        self._canvas.configure(scrollregion=self._canvas.bbox("all") or (0, 0, self.w, self.h))

    def _apply_card(self, c):
        x, y, w = c["x"], c["y"], c["card_w"]
        it = c["items"]
        self._canvas.coords(it[0], x, y, x + w, y + CARD_H)
        self._canvas.coords(it[1], x + 12, y + 18)
        self._canvas.coords(it[2], x + 12, y + 42)
        self._canvas.coords(it[3], x + 12, y + 78)
        self._canvas.coords(it[4], x + w - 10, y + 94)
        self._canvas.coords(it[5], x + w - 16, y + 10, x + w - 4, y + 22)

    def _tick(self):
        now = time.time()
        dirty = False
        for c in self.cards:
            if c["x"] > PAD_X + 0.5:
                c["x"] = PAD_X + (c["x"] - PAD_X) * 0.8
                if c["x"] < PAD_X + 0.5:
                    c["x"] = PAD_X
                dirty = True
            if c["due"]:
                blink = int(now * 4) % 2 == 0
                self._canvas.itemconfig(c["border"],
                                        outline=RED if blink else AMBER)
        if dirty:
            for c in self.cards:
                self._apply_card(c)
        self.win.after(50, self._tick)

    def _on_wheel(self, event):
        self._canvas.yview_scroll(int(-event.delta / 120), "units")

    def _on_click(self, event):
        for c in reversed(self.cards):
            x, y, x2, y2 = c["x"], c["y"], c["x"] + c["card_w"], c["y"] + CARD_H
            if x <= event.x <= x2 and y <= event.y <= y2:
                self._handle(c["task"], c["due"])
                return

    def _handle(self, task, due_flag):
        tid = task["id"]
        if due_flag:
            db.update_task(tid, status=db.TASK_DONE)
            self.on_done(task)
        else:
            db.update_task(tid, status=db.TASK_DISMISSED)
            self.on_dismiss(task)
        self.refresh()

    def show(self):
        self.win.deiconify()
        self.win.lift()
        self.win.attributes("-topmost", True)
        self.refresh()

    def hide(self):
        self.win.withdraw()

    def run(self):
        if self._own_master:
            self._master.mainloop()
