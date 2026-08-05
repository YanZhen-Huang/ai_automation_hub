# 会议准备自动化工作台 · 完整技术解析（可复现）

> 目标：本文档完整描述项目的技术实现，**仅凭本文即可从零重建本系统**。
> 适用读者：AI 代理 / 开发者复刻。
> 版本：0.1.0 ｜ 最后更新：2026-08-05

---

## 1. 项目定位

一个「多源信息收集 → AI 提炼 → 固定工作流自动执行 → 桌面/Web 双端可视化 + 鸿蒙手机联动」的**会议前准备自动化系统**。

用户创建会议后，系统按固定流程推进：订会议室（AI 排除不可用项→人工点选）、安排茶水/服务/音响设施、AI 生成汇报材料转 PPT 并自动微信发文件给印刷方（电话确认+送达地点）、微信下通知、定签字表；二阶段串行：定与会人员→排桌牌→人工审查→提醒接待。所有**打电话动作通过鸿蒙手机端 App**（局域网 HTTP + token 鉴权）以「普通电话 + TTS 播报 + 录音转文字」完成，确认信息回传。

## 2. 技术栈

| 端 | 技术 |
|----|------|
| 桌面端 | Python 3.13 + tkinter/ttk + pystray(托盘) |
| Web 端 | FastAPI + Vue3(本地 vue.global.prod.js，离线可用) + uvicorn |
| 存储 | SQLite（WAL 模式，单文件双库，`data/meeting_prep.db`） |
| AI | DeepSeek（OpenAI 兼容，超时 60s）；无 Key 时关键词规则降级 |
| 采集 | uiautomation(微信 UIA)、RapidOCR(屏幕识别，onnxruntime)、faster-whisper(录音，可选) |
| 动作 | python-pptx(生成 PPT)、webbrowser/subprocess/Windows 通知、微信 UIA 发文本/文件 |
| 手机端 | 鸿蒙 ArkTS（@ohos.telephony.call / @ohos.ai.textToSpeech / @ohos.ai.speechRecognizer） |

## 3. 目录结构（每个文件职责）

```
ai_automation_hub/
├── main.py                       # 启动入口：启动手机联动+Web+调度器+桌面窗口+托盘
├── requirements.txt              # 依赖清单
├── core/
│   ├── config.py                 # 配置中心：DEFAULTS + config.json 深合并 + phone token 自动生成
│   ├── settings.py               # 设置中心：16 个可编辑设置项(白名单) + 取值/保存
│   ├── events.py                 # 线程安全事件总线(发布/订阅)
│   ├── scheduler.py              # 调度器：周期任务(单线程)
│   ├── logger.py                 # 日志：文件 app.log + 控制台(windowed 下跳过 stdout)
│   └── status.py                 # 运行状态采集：服务/进程/统计/最近日志
├── storage/db.py                 # SQLite 访问层（7 张表 + CRUD）
├── collectors/
│   ├── base.py                   # Collector 基类 + 注册表 + collect_all()
│   ├── manual.py                 # 手动输入：submit_manual(text) 入库+发事件
│   ├── speech.py                 # 录音转文字：faster-whisper 懒加载+转写+入库
│   ├── uia_common.py             # 公共 UIA 层（窗口匹配 + 控件树遍历）
│   ├── ocr.py                    # OCR：ImageGrab 截屏 + RapidOCR 识别指定区域
│   └── im/                       # wechat/dingtalk/feishu/onenote UIA 会话采集
├── ai/
│   ├── llm.py                    # LLM 客户端(OpenAI 兼容/DeepSeek)，timeout=60
│   └── extract.py                # 提炼：extract/extract_rooms/extract_attendees/generate_materials
├── automation/
│   ├── workflows.py              # 固定工作流定义与执行（状态机核心）
│   ├── actions.py                # 动作库 + 微信 UIA 发文本/文件 + 文件名清洗
│   ├── phrases.py                # 话术中心：模板+变量填充+AI 润色
│   └── phone_link.py             # 桌面端手机联动 HTTP 服务（任务队列+token+超时重投递）
├── desktop/app.py                # tkinter 主窗口（7 页签 + 事件队列线程安全）
├── desktop/live_window.py        # 待办任务实况窗（右侧置顶卡片，整合自 desk）
├── server/
│   ├── app.py                    # FastAPI app + 静态前端挂载(frozen 路径适配)
│   ├── api/routes.py             # 全部 REST API
│   └── frontend/                 # Vue 单页(index.html + vue.global.prod.js 本地)
├── phone_app/                    # 鸿蒙工程(需 DevEco 编译)
└── docs/                         # 文档
```

## 4. 数据模型（SQLite，WAL）

连接：`sqlite3.connect(DB, timeout=15)` + `PRAGMA journal_mode=WAL` + `busy_timeout=8000`。每次操作独立连接。

**info_items（信息库·原始采集）**
| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | 自增 |
| source | TEXT | wechat/manual/speech/ocr |
| content | TEXT | 原始文本（ocr 带 `[OCR]` 前缀） |
| meeting_id | INTEGER | 关联会议（可空） |
| meta | TEXT | JSON 附加信息 |
| created_at | TEXT | ISO 时间 |

**meetings（会议库）**
id PK, title, start_time, status(preparing/prepared/cancelled), room(选定会议室), location(送达地点), attendees(与会人员，逗号分隔), attendee_source(ai/manual), created_at。
> 旧库迁移：`_ensure_columns` 自动为缺列 ADD COLUMN。

**rooms（会议室库）**：id PK, name, status(active), note, created_at。

**phrase_templates（话术模板）**：code PK, template, use_ai(0/1), updated_at。

**prep_items（工作流动作项）**
| 列 | 说明 |
|----|------|
| id / meeting_id / phase(1/2) / code / name | 基本属性 |
| status | pending/waiting/running/done |
| detail / result / order_index / created_at / updated_at | 状态与结果 |

**action_logs**：id, item_id, action, status, message, created_at。

**phone_numbers**：code PK, number, updated_at（6 个打电话动作的目标号码）。

**tasks（待办任务，整合自 desk_task_board）**：id PK, title, detail, due_date, source(ai/manual), status(active/dismissed/done), info_id(关联信息), created_at, updated_at。

## 5. 配置系统

`data/config.json`，默认值见 `core/config.py` DEFAULTS。关键配置：

```json
{
  "llm": {"api_key":"","base_url":"https://api.deepseek.com","model":"deepseek-chat"},
  "server": {"host":"127.0.0.1","port":8780},
  "collect": {"interval_seconds":300,"wechat_enabled":true,"manual_enabled":true,"speech_enabled":true,"ocr_enabled":true},
  "ocr": {"interval_seconds":120,"region":"0,0,800,600","engine":"rapidocr"},
  "wechat": {"send_enabled":false,"notify_target":"","print_target":"","send_delay":3},
  "speech": {"whisper_model":"small","device":"auto"},
  "phone": {"enabled":true,"host":"0.0.0.0","port":8781,"token":"<首次启动自动生成>"}
}
```

- 环境变量覆盖：`DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL`/`DEEPSEEK_MODEL`/`COLLECT_INTERVAL`。
- 深合并跳过 `null` 值（防覆盖崩溃）。
- `phone.token` 首次启动生成（uuid hex16），写入 config.json，用于手机联动鉴权。

**设置中心**（`core/settings.py`）：16 个白名单设置项，`get_settings()` 读值、`update_settings()` 白名单过滤后写回并 `save_config()`。桌面「设置」页与 Web「设置」卡片共用同一份定义（label + type + description）。

## 6. 事件总线与线程模型

**事件总线**（`core/events.py`）：`bus().subscribe(topic, handler)` / `bus().publish(topic, payload)`，线程安全（RLock）。主题：

| 主题 | 触发时机 |
|------|----------|
| `info.new` | 新信息入库 |
| `prep.updated` | 动作项状态变化 |
| `action.logged` | 动作日志写入 |
| `notification` | 需要用户知晓的通知 |
| `approval.requested` | 动作进入待审批 |
| `room.select.requested` | 需选会议室 |
| `attendees.requested` | 需确定与会人员 |
| `phone.result` | 手机回传拨打结果 |
| `phone.timeout` | 手机任务超时 |

**线程安全关键设计**：
- 后台线程（调度器/uvicorn/手机 HTTP）发布事件 → **桌面端用 `queue.Queue` 中转**（`_post` + `root.after(100)` 轮询 `_drain_ui`），绝不跨线程直接调 tkinter。
- 托盘回调 → `events.put()` → 主线程 `drain_events` 处理。
- 调度器 15s 轮询 + `_throttle` 按配置间隔节流（改设置实时生效）。

## 7. 固定工作流（核心）

### 动作项定义

**一阶段（并行，8 项）**：
| code | name | 执行方式 |
|------|------|----------|
| call_room | 打电话要会议室 | 需先人工选会议室 → 手机拨打 |
| call_tea / call_service / call_facilities | 茶水/服务/音响设施 | 手机拨打 |
| prep_materials | 备材料转PPT+印刷 | 自动生成材料→微信发文件→电话安排印刷 |
| confirm_time / confirm_sign_list | 定时间/签字表（人工） | 人工确认 |
| notify_wechat | 微信下通知 | UIA 自动发送或降级文本 |

**二阶段（串行，4 项）**：confirm_attendees(人工) → call_table_card(需先定人员→手机拨打) → manual_review(人工) → remind_reception(自动通知)。

### 状态机

```
pending →(request_approval)→ waiting →(approve)→ running →(phone.result ok)→ done
                        ↑                    └─ 失败/超时 → waiting(可重试)
```
- `HUMAN_CODES`（confirm_* / manual_review）：approve 直接 `_mark_done("已确认")`。
- `CALL_CODES`：approve → `execute_item` → 置 running + 提交手机任务。
- `call_room` approve 时若 meeting.room 空 → 发 `room.select.requested`（不执行）。
- `call_table_card` approve 时若 meeting.attendees 空 → 发 `attendees.requested`。

### 关键函数
- `setup_meeting(title, start_time)`：建会议 + 挂 12 个动作项。
- `run_phase1(mid)`：所有 phase1 pending → request_approval；再 `_advance_phase2` 激活二阶段首项。
- `approve(item_id)`：按 code 分流（room/attendees 前置检查 → HUMAN 直接完成 → 否则 execute）。
- `set_room(mid, room)` / `set_attendees(mid, names, source)`：更新会议字段 → `_resume_waiting` 续跑对应动作。
- `candidates_for_room(mid)`：会议室库 − AI 提炼的不可用项（去重）。
- `_advance_phase2(mid)`：找第一个未完成 phase2 项，若前一项 done → request_approval（串行）。
- `on_phone_result`：ok→done(记录确认)；失败→waiting(可重试)。
- `on_phone_timeout`：手机超时→waiting。

### 材料生成链路（prep_materials）
1. 取本会议 info（**不回退全库**，防串会）前 50 条
2. `generate_materials(title, texts)` → `{summary, chapters:[{heading, points}]}`（LLM；无 Key 降级单章）
3. `_make_ppt`：python-pptx 封面+每章+总结（文件名 `sanitize_filename`）
4. `_make_doc`：markdown 文档
5. `send_wechat_file(ppt, print_target)` 自动微信发文件（可配置开关）
6. `phrases.fill("call_print", meeting, {file,count})` → 手机电话话术（含送达地点）

## 8. AI 能力（`ai/extract.py`）

| 函数 | 逻辑 |
|------|------|
| `extract(texts)` | 判断会议相关 + 提炼要点。有 Key 走 LLM JSON；无 Key 关键词规则 |
| `extract_rooms(texts)` | 提炼**不可用**会议室。LLM 或规则：`ROOM_RE` 匹配房间名（如 `3F-301`/`2号楼201`/`XXX会议室`），**只向后 18 字符窗口**查 `UNAVAIL_WORDS`（维修/不可用/被占/没空/停用/装修/关闭/取消），按行扫描防跨行污染 |
| `extract_attendees(texts)` | 提炼与会人员（LLM；无 Key 返回空走人工） |
| `generate_materials(title, texts)` | LLM 生成结构化材料 JSON；降级用 extract 要点组单章 |

## 9. 话术中心（`automation/phrases.py`）

默认模板（存 db 可覆盖，桌面/Web 可编辑）：
```
call_room:        您好，请帮我预订{room}会议室（会议时间 {time}）。请确认，谢谢。
call_tea:         您好，请安排会场茶水服务（会议时间 {time}）。请确认，谢谢。
call_service:     您好，请安排会场服务（会议时间 {time}）。请确认，谢谢。
call_facilities:  您好，请准备音响、投影仪等配套设施（会议时间 {time}）。请确认，谢谢。
call_table_card:  您好，请安排会议桌牌制作，共{count}人：{attendees}。请确认，谢谢。
call_print:       您好，{title}的汇报材料已通过微信发送给您，共{count}份，请安排印刷并送到{location}。请确认，谢谢。
```
- 变量：`{title} {time} {room} {location} {attendees} {count} {file}`。
- `fill(code, meeting, extra)`：查 db 模板（无则默认）→ 变量替换（None→空串）→ 若 use_ai 调 `polish()`（LLM 润色口语）。
- 名单计数按 `[，,、\s]+` 切分。

## 10. 动作库（`automation/actions.py`）

- `notify(title, msg)`：发 `notification` 事件 + 日志。
- `export_text / generate_ppt / open_url / run_command`：通用动作（文件名用 `sanitize_filename` 清洗 `\/:*?"<>|`）。
- `send_wechat_text(text, target)`：UIA 找微信窗口→搜索框输 target→点会话→输入框输文本→回车。失败返回 False（上层降级为生成文本）。
- `send_wechat_file(path, target)`：UIA 打开会话→点附件入口→在 #32770 打开对话框输入路径→发送。失败降级。
- `call_phone(item_id, name, text, number)`：调 PhoneLink.submit_call 入队。
- `execute(action, item_id, **kwargs)`：统一入口，带日志。

## 11. 手机联动（`automation/phone_link.py`）

- 桌面端 `ThreadingHTTPServer` 监听 `0.0.0.0:8781`。
- **鉴权**：GET/POST 需带 `?token=<config phone.token>`，否则 401（body 限 64KB）。
- **协议**：
  - `GET /phone/poll?token=` → 取一个任务 `{task_id,item_id,action,text,number}`（空则 `{}`）
  - `POST /phone/result?token=` → body `{task_id, ok, confirmed}` → 发 `phone.result` 事件
- **超时重投递**：任务 `created_at` + `TASK_TTL=600s`，超时未回传重新入队（`retries`≤3），超限丢弃并发 `phone.timeout`。
- 手机端：拉任务→`makeCall(number)`→TTS 播报 `text`→录音转文字→回传。

## 12. REST API（`server/api/routes.py`，前缀 /api）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /meetings | 会议列表 |
| POST | /meetings | 建会议{title,start_time}，校验标题/时间格式(YYYY-MM-DD[ HH:MM])，自动 run_phase1 |
| GET | /meetings/{id} | 会议详情 + phase1/phase2 分组动作项 |
| POST | /meetings/{id}/prep/{iid}/done | 人工确认完成{result} |
| POST | /meetings/{id}/prep/{iid}/approve | 审批执行（含会议室/人员前置检查） |
| POST | /meetings/{id}/run-phase1 | 重跑一阶段 |
| GET | /info | 信息列表(?meeting_id/?source) |
| POST | /info | 手动录入{text,meeting_id} |
| GET | /logs | 动作日志 |
| GET/PUT | /phone-numbers, /phone-numbers/{code} | 号码配置 |
| GET/PUT | /settings | 设置项(items+values) / 更新(白名单) |
| GET | /status | 服务状态 + 数据统计 + 最近日志 |
| GET/POST/DELETE | /rooms | 会议室库 CRUD（空名 400） |
| GET/PUT | /templates, /templates/{code} | 话术模板 |
| PUT | /meetings/{id} | 更新会议字段（None 跳过，允许空串清空） |
| POST | /meetings/{id}/set-room | 选会议室{name} → set_room |
| POST | /meetings/{id}/set-attendees | 定人员{attendees,source} |
| GET | /meetings/{id}/room-candidates | AI 候选会议室 |

## 13. 桌面端（`desktop/app.py`）

tkinter + ttk(clam 主题)，6 个 Notebook 页签：会议准备 / 信息采集 / 手机联动号码 / 设置 / 运行状态 / 动作日志。深蓝科技配色（`#0a0e1a` 底 + 青 `#38bdf8`）。事件全部经 `queue.Queue` 转主线程。动作项详情逐条 `after(i*45)` 滑入。审批：call_room 弹会议室选择框（占位用独立标签不入选）、call_table_card 弹人员框（AI 提炼/手动）、其他限频提示去详情处理。

## 14. Web 前端

Vue3（**本地** `vue.global.prod.js`，离线可用）。5s 轮询自动刷新（会议详情/信息/日志/状态）。深蓝科技 UI + 粒子背景 Canvas + 弹性入场/波纹/流光动画。设置/会议室库/号码/话术模板/运行状态均可操作。

## 15. 鸿蒙端（`phone_app/`）

ArkTS 工程（DevEco 编译 .hap）。页面：桌面 IP + token 输入 → 拉任务 → 拨打+播报 → 录音转文字(可编辑) → 回传。权限：INTERNET/MICROPHONE/RECORD_AUDIO/CALL_DIAL。真机联调需调整 API 版本参数。

## 16. 打包与分发

```powershell
# venv
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 桌面 onedir 绿色版
.venv\Scripts\python -m PyInstaller --noconfirm --onedir --windowed --name meeting_prep ^
  --add-data "server/frontend;server/frontend" ^
  --collect-all rapidocr_onnxruntime --collect-all uvicorn ^
  --exclude-module pandas --exclude-module matplotlib --exclude-module scipy main.py

# 打 zip（排除 data）→ 安装器
Compress-Archive dist\meeting_prep\* build\meeting_prep_pkg.zip
.venv\Scripts\python -m PyInstaller --noconfirm --onefile --windowed ^
  --name meeting_prep_setup --add-data "build/meeting_prep_pkg.zip;." build/installer_setup.py
```
打包要点：uvicorn 需 `log_config=None`（windowed 下 stdout 为 None）；前端资源 frozen 路径适配（`_MEIPASS`/exe 旁）；rapidocr 需 `--collect-all` 带模型；安装器安装完成后**自动启动主程序**。

## 17. 从零重建步骤

1. 按 §3 建目录，按 §16 建 venv 装依赖
2. 实现 core/（config/settings/events/scheduler/logger/status）
3. 实现 storage/db.py（§4 全部表 + CRUD）
4. 实现 collectors/（§8 用到：base/uia_common/manual/speech/ocr/im.*）
5. 实现 ai/（llm + extract，§8）
6. 实现 automation/（actions/phrases/workflows/phone_link，§7-11）
7. 实现 server/（app + routes，§12；frontend §14）
8. 实现 desktop/（§13，含 live_window 实况窗）
9. 实现 main.py（§6 启动编排，含实况窗启动）
10. 测试：`main.py` 启动 → 桌面窗口 + 实况窗 + Web 8780 + 手机 8781；创建会议 → 12 动作项待审批 → 选会议室/定人员 → 手机回传 → 串行推进
11. 打包分发（§16）
12. 鸿蒙端（§15）真机联调

## 18. 待办任务模块（整合自 desk_task_board）

- **tasks 表**：title/detail/due_date/source/status(active/dismissed/done)/info_id。
- **提炼**：`ai/extract.extract_tasks(texts)`（AI 或规则）→ 标题/截止/详情；`_find_date` 从句中提取"今天/明天/周X/X月X日"等解析。
- **信息库互享**：采集管线对新信息同时做 `extract`（会议要点）与 `extract_tasks`（待办任务）双产物。
- **去重**：`db.add_task_unique(title, due_date)`（未完成同标题+截止跳过）。
- **实况窗**：`desktop/live_window.py` 右侧置顶卡片；active + dismissed到期显示；未到期点击=dismiss，到期点击=done；`task.new`/`info.new` 事件经 queue 驱动刷新。
- **桌面页签**：主窗口「待办任务」（完成/忽略/恢复/删除/双击完成）。
- **Web**：`/api/tasks` 列表/新增，`/api/tasks/{id}/done|dismiss|reactivate`。
- **鸿蒙**：App「待办任务」视图（`loadTasks`/`taskDone`，Web 端口 8780）。

## 19. 关键设计决策与坑

- 端口避开 Windows Hyper-V 保留段（8568-8667），Web 用 8780、手机 8781。
- 会议室不可用提炼**只向后窗口查**，避免行内前词污染。
- 材料生成**只取本会议信息**，防止跨会议内容串用。
- 电话任务**超时重投递**，避免手机不在线导致工作流卡死。
- 所有失败回 `waiting` 可重试，不永久卡 `running`。
- 设置项**白名单**，防 Web 端写入任意配置键。
- 手机接口 **token 鉴权**，防局域网窃取任务。
- 任务提炼规则：**强任务词单命中即可**（汇报/提交/记得/截止…），日期解析先**提取句中日期片段**再解析。
