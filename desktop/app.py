import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from ai.extract import extract_attendees
from automation import phrases, workflows
from collectors import submit_manual
from core import settings as settings_center
from core.events import bus
from storage import db

STATUS_TEXT = {"pending": "待执行", "running": "执行中", "waiting": "待人工",
               "done": "已完成"}

# 深蓝科技风配色（无纯白）
BG = "#0a0e1a"
PANEL = "#111827"
CYAN = "#38bdf8"
CYAN2 = "#4dd0e1"
CYAN3 = "#92b8e0"
INK = "#c9d2dd"
MUTED = "#8fa3b8"
RED = "#e25c6a"
LINE = "#24344d"


class DesktopApp:
    def __init__(self, root):
        self.root = root
        self.root.title("会议准备自动化工作台")
        self.root.geometry("960x640")
        self.current_id = None
        self._uiq = queue.Queue()
        self._approval_notice_at = 0
        self._build_ui()
        self._subscribe()
        self._drain_ui()
        self.refresh_meetings()

    def _build_ui(self):
        self._style()
        self._build_banner()
        nb = ttk.Notebook(self.root)
        nb.pack(fill=tk.BOTH, expand=True)

        self._build_meeting_page(nb)
        self._build_tasks_page(nb)
        self._build_info_page(nb)
        self._build_phone_page(nb)
        self._build_settings_page(nb)
        self._build_status_page(nb)
        self._build_log_page(nb)

    def _style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=INK, borderwidth=0)
        style.configure("TFrame", background=BG)
        style.configure("TPanedwindow", background=BG)
        style.configure("TLabel", background=BG, foreground=INK)
        style.configure("TEntry", fieldbackground=PANEL, foreground=INK,
                        insertcolor=INK)
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL,
                        foreground=INK, arrowcolor=CYAN3)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)])
        style.configure("TCheckbutton", background=BG, foreground=INK)
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED,
                        padding=(18, 8), font=("Microsoft YaHei UI", 10, "bold"),
                        borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", "#1a2438")],
                  foreground=[("selected", CYAN3)])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=INK, rowheight=26, borderwidth=0)
        style.map("Treeview", background=[("selected", "#1e2b44")],
                  foreground=[("selected", INK)])
        style.configure("Treeview.Heading", background="#1a2438",
                        foreground=CYAN3, font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Cyan.TButton", background=CYAN2, foreground="#06121f",
                        font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Cyan.TButton", background=[("active", CYAN)])

    def _build_banner(self):
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill=tk.X)
        tk.Label(bar, text="▲", bg=BG, fg=CYAN,
                 font=("Microsoft YaHei UI", 11)).pack(side=tk.LEFT, padx=(12, 2), pady=10)
        tk.Label(bar, text="●", bg=BG, fg=RED,
                 font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(bar, text="会议准备自动化工作台", bg=BG, fg=INK,
                 font=("Microsoft YaHei UI", 13, "bold")).pack(side=tk.LEFT)
        tk.Label(bar, text="CYBER · CONSTRUCTIVISM", bg=BG, fg=CYAN2,
                 font=("Consolas", 8)).pack(side=tk.RIGHT, padx=12)
        line = tk.Frame(self.root, bg=CYAN2, height=2)
        line.pack(fill=tk.X)

    def _build_meeting_page(self, nb):
        page = ttk.Frame(nb)
        nb.add(page, text="会议准备")
        toolbar = ttk.Frame(page)
        toolbar.pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(toolbar, text="新建会议", command=self._new_meeting).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="刷新", command=self.refresh_meetings).pack(
            side=tk.LEFT, padx=2)

        paned = ttk.PanedWindow(page, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        left = ttk.Frame(paned)
        self.meeting_tree = ttk.Treeview(left, columns=("title", "time", "status"),
                                         show="headings", height=12)
        for col, w, hd in (("title", 180, "会议"), ("time", 140, "时间"),
                           ("status", 80, "状态")):
            self.meeting_tree.heading(col, text=hd)
            self.meeting_tree.column(col, width=w, anchor="w")
        self.meeting_tree.pack(fill=tk.BOTH, expand=True)
        self.meeting_tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        paned.add(left, weight=1)

        self.detail = ttk.Frame(paned)
        paned.add(self.detail, weight=2)
        self._build_detail_widgets()

    def _build_detail_widgets(self):
        self.detail_title = ttk.Label(self.detail, text="",
                                      font=("Microsoft YaHei UI", 12, "bold"))
        self.detail_title.pack(anchor="w", padx=6, pady=(6, 2))
        self.detail_items = tk.Frame(self.detail, bg=PANEL)
        self.detail_items.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

    def _build_tasks_page(self, nb):
        page = ttk.Frame(nb)
        nb.add(page, text="待办任务")
        toolbar = ttk.Frame(page)
        toolbar.pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(toolbar, text="刷新", command=self.refresh_tasks).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="完成", command=self._task_done).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="忽略", command=self._task_dismiss).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="恢复", command=self._task_reactivate).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="删除", command=self._task_remove).pack(side=tk.LEFT, padx=2)
        ttk.Label(toolbar, text="双击 = 完成", foreground=MUTED).pack(side=tk.LEFT, padx=8)
        self.task_tree = ttk.Treeview(page, columns=("title", "due", "status", "source"),
                                      show="headings", height=10)
        for col, w, hd in (("title", 220, "任务"), ("due", 110, "截止"),
                           ("status", 70, "状态"), ("source", 90, "来源")):
            self.task_tree.heading(col, text=hd)
            self.task_tree.column(col, width=w, anchor="w")
        self.task_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self.task_tree.bind("<Double-1>", self._task_double)
        self.refresh_tasks()

    def refresh_tasks(self):
        self.task_tree.delete(*self.task_tree.get_children())
        for t in db.list_tasks(limit=100):
            self.task_tree.insert("", "end", iid=str(t["id"]),
                                  values=(t["title"], t["due_date"] or "",
                                          t["status"], t["source"]))

    def _task_selected(self):
        sel = self.task_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中一个任务")
            return None
        return int(sel[0])

    def _task_done(self):
        tid = self._task_selected()
        if tid:
            db.update_task(tid, status=db.TASK_DONE)
            self.refresh_tasks()

    def _task_dismiss(self):
        tid = self._task_selected()
        if tid:
            db.update_task(tid, status=db.TASK_DISMISSED)
            self.refresh_tasks()

    def _task_reactivate(self):
        tid = self._task_selected()
        if tid:
            db.update_task(tid, status=db.TASK_ACTIVE)
            self.refresh_tasks()

    def _task_remove(self):
        tid = self._task_selected()
        if tid and messagebox.askyesno("确认", "删除该任务？"):
            db.remove_task(tid)
            self.refresh_tasks()

    def _task_double(self, event):
        tid = self._task_selected()
        if tid:
            db.update_task(tid, status=db.TASK_DONE)
            self.refresh_tasks()

    def _build_info_page(self, nb):
        page = ttk.Frame(nb)
        nb.add(page, text="信息采集")
        top = ttk.Frame(page)
        top.pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(top, text="手动输入信息（交给 AI 提炼）：").pack(side=tk.LEFT)
        self.info_text = tk.Text(page, height=4, bg=PANEL, fg=INK,
                                 insertbackground=INK, relief="flat",
                                 highlightthickness=1, highlightbackground=LINE)
        self.info_text.pack(fill=tk.X, padx=6)
        ttk.Button(page, text="提交", command=self._submit_info).pack(
            anchor="w", padx=6, pady=4)
        self.info_list = tk.Listbox(page, bg=PANEL, fg=INK, relief="flat",
                                    highlightthickness=1, highlightbackground=LINE)
        self.info_list.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

    def _build_phone_page(self, nb):
        page = ttk.Frame(nb)
        nb.add(page, text="手机联动号码")
        hint = ttk.Label(page, text="为每个「打电话」动作配置目标号码（手机端将拨打该号码并语音播报）")
        hint.grid(row=0, column=0, columnspan=2, padx=6, pady=6, sticky="w")
        self.phone_entries = {}
        codes = [("call_room", "会议室"), ("call_tea", "茶水"),
                 ("call_service", "服务"), ("call_facilities", "音响/投影设施"),
                 ("call_table_card", "桌牌"), ("call_print", "印刷")]
        row = 1
        for code, name in codes:
            ttk.Label(page, text=name).grid(row=row, column=0, padx=6, pady=3, sticky="w")
            var = tk.StringVar(value=db.get_number(code))
            self.phone_entries[code] = var
            ttk.Entry(page, textvariable=var, width=24).grid(row=row, column=1, padx=6)
            row += 1
        ttk.Button(page, text="保存", command=self._save_numbers).grid(
            row=row, column=0, columnspan=2, padx=6, pady=8)

    def _save_numbers(self):
        for code, var in self.phone_entries.items():
            db.set_number(code, var.get())
        messagebox.showinfo("提示", "号码已保存")

    def _build_settings_page(self, nb):
        page = ttk.Frame(nb)
        nb.add(page, text="设置")
        hint = ttk.Label(page, text="关键配置在此修改，保存后立即生效（部分需重启）")
        hint.pack(anchor="w", padx=6, pady=6)
        self.settings_vars = {}
        values = settings_center.get_settings()
        wrap = ttk.Frame(page)
        wrap.pack(fill=tk.BOTH, expand=True, padx=6)
        canvas = tk.Canvas(wrap, highlightthickness=0, bg=PANEL)
        self.settings_canvas = canvas
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=PANEL)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        def _wheel(e):
            canvas.yview_scroll(int(-e.delta / 120), "units")

        canvas.bind("<MouseWheel>", _wheel)
        inner.bind("<MouseWheel>", _wheel)

        row = 0
        for it in settings_center.items():
            key = it["key"]
            desc = it.get("description", "")
            lbl = tk.Label(inner, text=it["label"], bg=PANEL, fg=INK,
                           font=("Microsoft YaHei UI", 9, "bold"), anchor="w",
                           justify="left")
            lbl.grid(row=row, column=0, padx=6, pady=(3, 0), sticky="w")
            lbl.bind("<MouseWheel>", _wheel)
            if desc:
                dl = tk.Label(inner, text=desc, bg=PANEL, fg=MUTED, anchor="w",
                              justify="left", wraplength=300,
                              font=("Microsoft YaHei UI", 8))
                dl.grid(row=row, column=0, padx=6, sticky="w", pady=(0, 3))
                dl.bind("<MouseWheel>", _wheel)
            if it["type"] == "bool":
                var = tk.BooleanVar(value=bool(values.get(key)))
                cb = ttk.Checkbutton(inner, variable=var)
                cb.grid(row=row, column=1, padx=6)
                cb.bind("<MouseWheel>", _wheel)
            else:
                var = tk.StringVar(value="" if values.get(key) is None
                                   else str(values.get(key)))
                ent = ttk.Entry(inner, textvariable=var, width=40)
                ent.grid(row=row, column=1, padx=6)
                ent.bind("<MouseWheel>", _wheel)
                if it["type"] == "password":
                    ent.configure(show="*")
            self.settings_vars[key] = (var, it["type"])
            row += 1

        row += 1
        tk.Label(inner, text="会议室库（人工维护可用会议室）", bg=PANEL, fg=CYAN3,
                 font=("Microsoft YaHei UI", 9, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=6, pady=(10, 2))
        row += 1
        self.rooms_lb = tk.Listbox(inner, bg=PANEL, fg=INK, relief="flat",
                                   height=5, highlightthickness=1,
                                   highlightbackground=LINE)
        self.rooms_lb.grid(row=row, column=0, columnspan=2, sticky="ew", padx=6)
        self._reload_rooms()
        row += 1
        self.room_new = tk.StringVar()
        ttk.Entry(inner, textvariable=self.room_new, width=28).grid(
            row=row, column=0, padx=6, pady=3, sticky="w")
        ttk.Button(inner, text="添加", command=self._add_room).grid(
            row=row, column=1, padx=6)
        row += 1
        ttk.Button(inner, text="删除所选", command=self._del_room).grid(
            row=row, column=0, padx=6, pady=3, sticky="w")

        row += 1
        tk.Label(inner, text="话术模板（变量：{room} {time} {attendees} {count} "
                             "{location} {title} {file}）",
                 bg=PANEL, fg=CYAN3, font=("Microsoft YaHei UI", 9, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=6, pady=(10, 2))
        row += 1
        self.tpl_code = tk.StringVar(value="call_room")
        ttk.Combobox(inner, textvariable=self.tpl_code, state="readonly",
                     values=[c for c, _ in phrases.TEMPLATE_CODES],
                     width=14).grid(row=row, column=0, padx=6, sticky="w")
        ttk.Button(inner, text="加载", command=self._load_tpl).grid(
            row=row, column=1, padx=6)
        row += 1
        self.tpl_text = tk.Text(inner, height=3, bg=PANEL, fg=INK, relief="flat",
                                insertbackground=INK, highlightthickness=1,
                                highlightbackground=LINE)
        self.tpl_text.grid(row=row, column=0, columnspan=2, sticky="ew", padx=6)
        row += 1
        self.tpl_ai = tk.BooleanVar()
        ttk.Checkbutton(inner, text="AI 润色话术", variable=self.tpl_ai).grid(
            row=row, column=0, padx=6, pady=3, sticky="w")
        ttk.Button(inner, text="保存模板", command=self._save_tpl).grid(
            row=row, column=1, padx=6)
        row += 1
        ttk.Button(page, text="保存设置", command=self._save_settings).pack(
            anchor="w", padx=6, pady=8)

    def _reload_rooms(self):
        self.rooms_lb.delete(0, "end")
        for r in db.list_rooms():
            self.rooms_lb.insert("end", r["name"])

    def _add_room(self):
        name = self.room_new.get().strip()
        if name:
            db.add_room(name)
            self.room_new.set("")
            self._reload_rooms()

    def _del_room(self):
        sel = self.rooms_lb.curselection()
        if not sel:
            return
        rooms = db.list_rooms()
        if sel[0] < len(rooms):
            db.remove_room(rooms[sel[0]]["id"])
            self._reload_rooms()

    def _load_tpl(self):
        code = self.tpl_code.get()
        t = db.get_template(code) or {}
        self.tpl_text.delete("1.0", "end")
        self.tpl_text.insert(
            "1.0", t.get("template", phrases.DEFAULT_TEMPLATES.get(code, "")))
        self.tpl_ai.set(bool(t.get("use_ai", 0)))

    def _save_tpl(self):
        code = self.tpl_code.get()
        db.set_template(code, self.tpl_text.get("1.0", "end").strip(),
                        self.tpl_ai.get())
        messagebox.showinfo("提示", "话术模板已保存")

    def _save_settings(self):
        mapping = {}
        for key, (var, vtype) in self.settings_vars.items():
            if vtype == "bool":
                mapping[key] = var.get()
            elif vtype == "int":
                try:
                    mapping[key] = int(var.get())
                except ValueError:
                    mapping[key] = var.get()
            else:
                mapping[key] = var.get().strip()
        settings_center.update_settings(mapping)
        messagebox.showinfo("提示", "设置已保存")

    def _build_status_page(self, nb):
        page = ttk.Frame(nb)
        nb.add(page, text="运行状态")
        ttk.Button(page, text="刷新", command=self.refresh_status).pack(
            anchor="w", padx=6, pady=6)
        self.status_tree = ttk.Treeview(page, columns=("name", "state", "detail"),
                                        show="headings", height=8)
        for col, w, hd in (("name", 120, "服务"), ("state", 90, "状态"),
                           ("detail", 320, "详情")):
            self.status_tree.heading(col, text=hd)
            self.status_tree.column(col, width=w, anchor="w")
        self.status_tree.pack(fill=tk.X, padx=6)

        ttk.Label(page, text="数据统计", font=("Microsoft YaHei UI", 10, "bold"),
                  foreground=CYAN).pack(anchor="w", padx=6, pady=(10, 2))
        self.count_tree = ttk.Treeview(page, columns=("item", "n"),
                                       show="headings", height=4)
        for col, w, hd in (("item", 140, "项目"), ("n", 80, "数量")):
            self.count_tree.heading(col, text=hd)
            self.count_tree.column(col, width=w, anchor="w")
        self.count_tree.pack(fill=tk.X, padx=6)

        ttk.Label(page, text="最近日志", font=("Microsoft YaHei UI", 10, "bold"),
                  foreground=CYAN).pack(anchor="w", padx=6, pady=(10, 2))
        self.status_log = tk.Listbox(page, bg=PANEL, fg=INK, relief="flat",
                                     highlightthickness=1, highlightbackground=LINE)
        self.status_log.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.refresh_status()

    def refresh_status(self):
        from core import status as st
        try:
            s = st.service_status()
        except Exception:
            return
        self.status_tree.delete(*self.status_tree.get_children())
        for sv in s["services"]:
            name = sv["name"]
            running = sv.get("running", False)
            state = "运行中" if running else "未启动"
            detail = []
            if "port" in sv:
                detail.append(f"端口 {sv['port']}")
                if "url" in sv:
                    detail.append(sv["url"])
            if "interval" in sv:
                detail.append(f"间隔 {sv['interval']}s")
            if sv.get("enabled") is False:
                state = "已关闭"
            if sv.get("available") is False:
                state = "未配置"
            self.status_tree.insert("", "end", values=(
                name, state, " ".join(detail)))
        self.count_tree.delete(*self.count_tree.get_children())
        for k, v in s["counts"].items():
            label = {"info_items": "信息条目", "meetings": "会议",
                     "prep_items": "动作项", "rooms": "会议室",
                     "action_logs": "动作日志"}.get(k, k)
            self.count_tree.insert("", "end", values=(label, v))
        self.status_log.delete(0, "end")
        for ln in st.recent_logs(15):
            self.status_log.insert("end", ln)

    def _build_log_page(self, nb):
        page = ttk.Frame(nb)
        nb.add(page, text="动作日志")
        self.log_list = tk.Listbox(page, bg=PANEL, fg=INK, relief="flat",
                                   highlightthickness=1, highlightbackground=LINE)
        self.log_list.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    def _subscribe(self):
        for topic in ("prep.updated", "info.new", "action.logged"):
            bus().subscribe(topic, lambda p: self._post(self._on_event))
        bus().subscribe("approval.requested",
                        lambda p: self._post(self._ask_approval, p))
        bus().subscribe("room.select.requested",
                        lambda p: self._post(self._ask_room, p))
        bus().subscribe("attendees.requested",
                        lambda p: self._post(self._ask_attendees, p))

    def _post(self, fn, *args):
        self._uiq.put((fn, args))

    def _drain_ui(self):
        while True:
            try:
                fn, args = self._uiq.get_nowait()
                fn(*args)
            except queue.Empty:
                break
        self.root.after(100, self._drain_ui)

    def _ask_room(self, payload):
        mid = payload.get("meeting_id")
        item_id = payload.get("item_id")
        name = payload.get("name") or "预订会议室"
        dlg = tk.Toplevel(self.root)
        dlg.title(f"选择会议室 · {name}")
        dlg.configure(bg=BG)
        dlg.grab_set()
        tk.Label(dlg, text="可用会议室（AI 正在排除不可用项…）", bg=BG, fg=INK,
                 font=("Microsoft YaHei UI", 9, "bold")).pack(padx=8, pady=6, anchor="w")
        lb = tk.Listbox(dlg, bg=PANEL, fg=INK, relief="flat", height=8,
                        highlightthickness=1, highlightbackground=LINE)
        lb.pack(fill=tk.BOTH, expand=True, padx=8)

        def ok():
            sel = lb.curselection()
            if not sel:
                messagebox.showwarning("提示", "请选择一个会议室")
                return
            room = lb.get(sel[0])
            workflows.set_room(mid, room)
            dlg.destroy()
            self.refresh_meetings()

        tk.Button(dlg, text="选定并预订", command=ok, bg=CYAN2, fg="#06121f",
                  font=("Microsoft YaHei UI", 9, "bold"), relief="flat").pack(
            pady=8, side=tk.LEFT, padx=(8, 4))
        tk.Button(dlg, text="取消", command=dlg.destroy, bg=PANEL, fg=INK,
                  relief="flat").pack(pady=8, side=tk.LEFT)

        threading.Thread(target=self._load_rooms_async, args=(lb, mid),
                         daemon=True).start()

    def _load_rooms_async(self, lb, mid):
        try:
            cands = workflows.candidates_for_room(mid)
        except Exception:
            cands = []
        self._post(self._fill_rooms, lb, cands)

    def _fill_rooms(self, lb, cands):
        lb.delete(0, "end")
        for r in cands:
            lb.insert("end", r)
        if not cands:
            lb.insert("end", "（无可用会议室，请先维护会议室库）")

    def _ask_attendees(self, payload):
        mid = payload.get("meeting_id")
        item_id = payload.get("item_id")
        name = payload.get("name") or "桌牌制作"
        dlg = tk.Toplevel(self.root)
        dlg.title(f"确定与会人员 · {name}")
        dlg.configure(bg=BG)
        dlg.grab_set()
        tk.Label(dlg, text="与会人员名单（逗号分隔）：", bg=BG, fg=INK,
                 font=("Microsoft YaHei UI", 9, "bold")).pack(padx=8, pady=6, anchor="w")
        var = tk.StringVar()
        ent = tk.Entry(dlg, textvariable=var, width=40, bg=PANEL, fg=INK,
                       insertbackground=INK, relief="flat")
        ent.pack(padx=8, fill=tk.X)

        def ai_fill():
            infos = db.list_info_items(mid)
            texts = [i["content"] for i in infos]
            btn_ai.config(text="AI 提炼中…", state="disabled")

            def work():
                try:
                    names = extract_attendees(texts)
                except Exception:
                    names = []
                self._post(ai_done, names)

            def ai_done(names):
                if names:
                    var.set(",".join(names))
                    messagebox.showinfo("AI 提炼", "已从信息中提炼人员，可编辑后确认")
                else:
                    messagebox.showinfo("AI 提炼", "未提炼到人员，请手动录入")
                btn_ai.config(text="AI 提炼", state="normal")

            threading.Thread(target=work, daemon=True).start()

        def ok():
            names = var.get().strip()
            if not names:
                messagebox.showwarning("提示", "请填写与会人员")
                return
            workflows.set_attendees(mid, names, "manual")
            dlg.destroy()
            self.refresh_meetings()

        btn_ai = tk.Button(dlg, text="AI 提炼", command=ai_fill, bg=CYAN2,
                           fg="#06121f", font=("Microsoft YaHei UI", 9, "bold"),
                           relief="flat")
        btn_ai.pack(pady=8, side=tk.LEFT, padx=(8, 4))
        tk.Button(dlg, text="确认名单", command=ok, bg=CYAN2, fg="#06121f",
                  font=("Microsoft YaHei UI", 9, "bold"), relief="flat").pack(
            pady=8, side=tk.LEFT, padx=4)
        tk.Button(dlg, text="取消", command=dlg.destroy, bg=PANEL, fg=INK,
                  relief="flat").pack(pady=8, side=tk.LEFT)

    def _ask_approval(self, payload):
        item_id = payload.get("item_id")
        name = payload.get("name") or ""
        item = db.get_prep_item(item_id)
        if item:
            meeting = db.get_meeting(item["meeting_id"]) or {}
            if item["code"] == "call_room" and not (meeting.get("room") or "").strip():
                self._ask_room({"meeting_id": item["meeting_id"],
                                "item_id": item_id, "name": name})
                return
            if item["code"] == "call_table_card" and not (meeting.get("attendees") or "").strip():
                self._ask_attendees({"meeting_id": item["meeting_id"],
                                     "item_id": item_id, "name": name})
                return
        now = time.time()
        if now - self._approval_notice_at > 5:
            self._approval_notice_at = now
            messagebox.showinfo(
                "待审批",
                "有自动化动作待审批，请在「会议准备」页选中会议后，"
                "点击详情中对应动作的「确认/执行」按钮处理。")

    def _on_event(self):
        try:
            self.refresh_meetings()
            self.refresh_tasks()
            self.refresh_infos()
            self.refresh_logs()
        except Exception:
            pass

    # ---------- 会议 ----------

    def refresh_meetings(self):
        self.meeting_tree.delete(*self.meeting_tree.get_children())
        for m in db.list_meetings():
            self.meeting_tree.insert("", "end", iid=str(m["id"]),
                                     values=(m["title"], m["start_time"] or "",
                                             m["status"]))
        if self.current_id and db.get_meeting(self.current_id):
            self._render_detail()
        else:
            self.current_id = None
            self.detail_title.config(text="请选择会议")

    def _on_select(self):
        sel = self.meeting_tree.selection()
        if not sel:
            return
        self.current_id = int(sel[0])
        self._render_detail()

    def _render_detail(self):
        meeting = db.get_meeting(self.current_id)
        if not meeting:
            return
        self.detail_title.config(text=f"{meeting['title']}  "
                                      f"({meeting['start_time'] or '时间未定'})")
        for w in self.detail_items.winfo_children():
            w.destroy()
        plan = []
        for phase, label in ((1, "一阶段（并行）"), (2, "二阶段（串行）")):
            plan.append(("label", label))
            for it in db.list_prep_items(self.current_id):
                if it["phase"] == phase:
                    plan.append(("row", it))
        for i, (kind, data) in enumerate(plan):
            self.detail_items.after(i * 45,
                                    lambda k=kind, d=data: self._add_detail(k, d))

    def _add_detail(self, kind, data):
        if kind == "label":
            ttk.Label(self.detail_items, text=data,
                      font=("Microsoft YaHei UI", 10, "bold"),
                      foreground=CYAN).pack(anchor="w", pady=(6, 2))
            return
        row = ttk.Frame(self.detail_items)
        row.pack(fill=tk.X, pady=1)
        ttk.Label(row, text=data["name"], width=28).pack(side=tk.LEFT)
        ttk.Label(row, text=STATUS_TEXT.get(data["status"], data["status"]),
                  width=8).pack(side=tk.LEFT)
        if data["result"]:
            ttk.Label(row, text=f"← {data['result']}",
                      foreground=MUTED).pack(side=tk.LEFT)
        if data["status"] == "waiting":
            btn = ttk.Button(row, text="确认",
                             command=lambda iid=data["id"]: self._confirm_item(iid))
            btn.pack(side=tk.RIGHT)
            btn.bind("<Enter>", lambda e: btn.configure(style="Cyan.TButton"))
            btn.bind("<Leave>", lambda e: btn.configure(style=""))

    def _new_meeting(self):
        import datetime as _dt
        dlg = tk.Toplevel(self.root)
        dlg.title("新建会议")
        dlg.configure(bg=BG)
        dlg.grab_set()
        ttk.Label(dlg, text="会议主题：", background=BG, foreground=INK).grid(
            row=0, column=0, padx=6, pady=6, sticky="w")
        title_v = tk.StringVar()
        ttk.Entry(dlg, textvariable=title_v, width=32).grid(row=0, column=1, padx=6)
        ttk.Label(dlg, text="会议时间：", background=BG, foreground=INK).grid(
            row=1, column=0, padx=6, pady=6, sticky="w")
        time_v = tk.StringVar()
        ttk.Entry(dlg, textvariable=time_v, width=32).grid(row=1, column=1, padx=6)
        tk.Label(dlg, text="格式：2026-08-06 14:00 或 2026-08-06（可留空）",
                 bg=BG, fg=MUTED, font=("Microsoft YaHei UI", 8)).grid(
            row=2, column=1, padx=6, sticky="w")
        ttk.Label(dlg, text="送达地点：", background=BG, foreground=INK).grid(
            row=3, column=0, padx=6, pady=6, sticky="w")
        loc_v = tk.StringVar()
        ttk.Entry(dlg, textvariable=loc_v, width=32).grid(row=3, column=1, padx=6)
        tk.Label(dlg, text="印刷/材料送达地点，如：总部一楼前台",
                 bg=BG, fg=MUTED, font=("Microsoft YaHei UI", 8)).grid(
            row=4, column=1, padx=6, sticky="w")

        def ok():
            title = title_v.get().strip()
            if not title:
                messagebox.showwarning("提示", "请填写会议主题")
                return
            raw = time_v.get().strip()
            t = raw or None
            if raw:
                valid = False
                for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
                    try:
                        _dt.datetime.strptime(raw, fmt)
                        valid = True
                        break
                    except ValueError:
                        continue
                if not valid:
                    messagebox.showwarning("格式错误",
                                           "时间格式不正确，示例：2026-08-06 14:00")
                    return
            mid = workflows.setup_meeting(title, t)
            loc = loc_v.get().strip()
            if loc:
                db.update_meeting(mid, location=loc)
            workflows.run_phase1(mid)
            dlg.destroy()
            self.refresh_meetings()

        ttk.Button(dlg, text="创建并开始准备", command=ok).grid(
            row=5, column=0, columnspan=2, pady=8)

    def _confirm_item(self, item_id):
        item = db.get_prep_item(item_id)
        if not item:
            return
        meeting = db.get_meeting(item["meeting_id"]) or {}
        if item["code"] == "call_room" and not (meeting.get("room") or "").strip():
            self._ask_room({"meeting_id": item["meeting_id"], "item_id": item_id,
                            "name": item["name"]})
            return
        if item["code"] == "call_table_card" and not (meeting.get("attendees") or "").strip():
            self._ask_attendees({"meeting_id": item["meeting_id"], "item_id": item_id,
                                 "name": item["name"]})
            return
        if item["code"] in workflows.HUMAN_CODES:
            r = messagebox.askyesno("人工确认", "确认该项已完成？")
            if r:
                workflows.mark_done(item_id, "人工已确认")
        else:
            r = messagebox.askyesno("操作审批", f"是否执行「{item['name']}」？")
            if r:
                workflows.approve(item_id)
        self.refresh_meetings()

    # ---------- 信息 ----------

    def _submit_info(self):
        text = self.info_text.get("1.0", "end").strip()
        if not text:
            return
        submit_manual(text, meeting_id=self.current_id)
        self.info_text.delete("1.0", "end")
        self.refresh_infos()

    def refresh_infos(self):
        self.info_list.delete(0, "end")
        for i in db.list_info_items(limit=100):
            self.info_list.insert("end", f"[{i['source']}] {i['content'][:60]}")

    def refresh_logs(self):
        self.log_list.delete(0, "end")
        for l in db.list_action_logs(limit=100):
            self.log_list.insert("end",
                                 f"{l['created_at']} {l['action']} [{l['status']}] {l['message'][:50]}")

    def run(self):
        self.root.mainloop()
