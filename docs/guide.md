# 会议准备自动化工作台 · 完整使用手册

> 版本：0.1.0 ｜ 最后更新：2026-08-05

---

## 目录

1. [项目概述](#一项目概述)
2. [系统架构](#二系统架构)
3. [核心技术说明](#三核心技术说明)
4. [业务流程](#四业务流程)
5. [桌面端使用](#五桌面端使用)
6. [Web 端使用](#六web-端使用)
7. [鸿蒙手机端使用](#七鸿蒙手机端使用)
8. [设置项说明](#八设置项说明)
9. [配置文件结构](#九配置文件结构)
10. [部署与打包](#十部署与打包)
11. [目录结构](#十一目录结构)
12. [常见问题](#十二常见问题)

---

## 一、项目概述

**会议准备自动化工作台**是一个「多源信息收集 → AI 提炼 → 固定工作流自动执行 → 双端可视化」的会议筹备自动化系统。

系统自动从**微信、手动输入、录音、OCR** 等渠道收集会议相关信息，AI 提炼要点，并按固定工作流推进会议筹备动作：订会议室、安排茶水/服务/音响设施、准备汇报材料并转 PPT、安排印刷、微信下通知、确定签字表、排桌牌、提醒接待等。其中"打电话"类动作通过**鸿蒙手机端 App** 以「普通电话 + 语音播报 + 录音转文字」方式自动完成，并将对方的确认信息回传。

### 技术栈

| 端 | 技术 |
|----|------|
| 桌面端 | Python 3.13 + tkinter + pystray（托盘） |
| Web 端 | FastAPI + Vue3(CDN) 单页 |
| 存储 | SQLite（单文件双库） |
| AI | DeepSeek（OpenAI 兼容接口），无 Key 时关键词规则降级 |
| 采集 | uiautomation（微信 UIA）、RapidOCR（屏幕识别）、faster-whisper（录音，可选） |
| 动作 | python-pptx（生成 PPT）、webbrowser / subprocess / Windows 通知 |
| 手机端 | 鸿蒙 ArkTS（@ohos.telephony.call / @ohos.ai.textToSpeech / @ohos.ai.speechRecognizer） |
| 通信 | 桌面端局域网 HTTP（Web 8780 / 手机联动 8781） |

---

## 二、系统架构

```
          ┌────────────────────────────────────────────┐
          │    desktop/ (tkinter+托盘)                  │  桌面主窗口
          │    server/  (FastAPI + Vue)                 │  Web 界面
          └──────────────────────┬─────────────────────┘
                                 │ 事件订阅/刷新
             ┌───────────────────▼──────────────────┐
             │           core/ 事件总线 + 调度器       │  模块解耦、定时触发
             └───────────────────┬──────────────────┘
   ┌──────────────┬──────────────┴──────────┬────────────────┐
   ▼              ▼                         ▼                ▼
collectors/     ai/                     automation/       storage/
 采集多源信息    LLM提炼/降级规则          固定工作流+动作库   SQLite 双库
                                          │
                                          ▼
                                   phone_link (8781) ──→ 鸿蒙手机端 App
```

**数据流（固定工作流）**：
```
信息采集 → 入库 → AI 提炼 → 创建会议 → 一阶段并行动作 → 二阶段串行动作
                                 （打电话/材料/通知/人工确认）    （桌牌/审查/接待）
```

---

## 三、核心技术说明

### 3.1 core/ 底座
| 模块 | 说明 |
|------|------|
| `events.py` | 线程安全事件总线（发布/订阅），模块间解耦；主题如 `info.new` / `prep.updated` / `phone.result` / `notification` / `action.logged` |
| `scheduler.py` | 调度器：周期任务（采集轮询、OCR 轮询）+ 定点任务（每日 HH:MM） |
| `config.py` | 配置中心：`config.json` + 环境变量，深合并，`BASE_DIR` 适配打包运行 |
| `settings.py` | 设置中心：把 15 个关键配置项以表单暴露给桌面/Web 修改，`config.json` 落盘 |
| `logger.py` | 日志：滚动文件（`data/app.log`）+ 控制台 |

### 3.2 storage/ SQLite 双库
数据文件：`data/meeting_prep.db`，5 张表：

| 表 | 用途 | 关键字段 |
|----|------|----------|
| `info_items` | **信息库**：采集的原始信息 | source, content, meeting_id(可关联会议), meta |
| `meetings` | **会议库**：会议准备 | title, start_time, status(preparing/prepared/cancelled) |
| `prep_items` | 会议准备动作项（工作流实例） | meeting_id, phase(1/2), code, name, status(pending/running/waiting/done), result, order_index |
| `action_logs` | 动作执行日志 | item_id, action, status, message |
| `phone_numbers` | 打电话动作目标号码 | code, number |

### 3.3 collectors/ 采集
| 来源 | 实现 | 开关 |
|------|------|------|
| 微信 | `im/wechat.py`：uiautomation 只读扫描会话列表 | 设置「启用微信采集」 |
| 手动输入 | `manual.py`：文本入信息库并发 `info.new` 事件 | 随时可用 |
| 录音 | `speech.py`：faster-whisper 本地转写（未装则关闭） | 设置「Whisper 模型」 |
| OCR | `ocr.py`：Pillow `ImageGrab` 截指定屏幕区域 + RapidOCR 识别（独立调度） | 设置「启用OCR识别」+「识别区域」 |

所有来源经 `ingest()` **内容去重**后入库。

### 3.4 ai/ 智能
| 模块 | 说明 |
|------|------|
| `llm.py` | OpenAI 兼容客户端（DeepSeek），可配置 api_key/base_url/model |
| `extract.py` | 信息提炼：输入文本 → `{is_meeting_related, summary, points, prep_reminders}`；无 Key 时关键词规则降级 |

### 3.5 automation/ 执行
| 模块 | 说明 |
|------|------|
| `workflows.py` | **固定工作流**定义与执行（见「四、业务流程」） |
| `actions.py` | 动作库：通知、导出文件、生成 PPT、打开网页/程序、运行命令、微信自动发送、打电话联动 |
| `phone_link.py` | 桌面端 HTTP 服务（8781），管理"打电话"任务队列，接收手机回传 |

### 3.6 desktop/ 桌面端
tkinter 主窗口（Notebook 五个页签：会议准备 / 信息采集 / 手机联动号码 / 设置 / 动作日志）+ 系统托盘（隐藏到托盘、显示、退出）。事件触发自动刷新。

### 3.7 server/ Web 端
FastAPI + Vue3(CDN) 单页，5 秒自动刷新实时显示工作流执行。前端资源随打包发布。

### 3.8 phone_app/ 鸿蒙手机端
ArkTS 工程（需 DevEco Studio 编译为 `.hap`）：拉取任务 → 拨打 → TTS 播报 → 录音转文字 → 回传桌面端。

---

## 四、业务流程

### 4.1 信息采集流程
```
微信(UIA) / 手动输入 / 录音(Whisper) / OCR(屏幕区域)
        ↓  内容去重
     info_items 入库 → AI 提炼（会议相关则桌面/Web 通知）
```
- 主轮询间隔：设置「采集轮询间隔」（默认 300 秒）
- OCR 独立轮询：设置「OCR识别间隔」（默认 120 秒）

### 4.2 会议准备一阶段（并行，除特殊要求外）
创建会议即自动触发以下 8 项**并行**执行：

| # | 动作项 | code | 执行方式 |
|---|--------|------|----------|
| 1 | 打电话要会议室 | call_room | 手机端拨打+播报，回传确认 |
| 2 | 打电话要茶水 | call_tea | 同上 |
| 3 | 打电话要服务 | call_service | 同上 |
| 4 | 打电话要音响/投影等配套设施 | call_facilities | 同上 |
| 5 | 准备汇报材料并转PPT后安排印刷 | prep_materials | 自动：AI提炼→生成PPT+文档→手机端电话安排印刷 |
| 6 | 确定会议时间（人工） | confirm_time | 人工确认 |
| 7 | 微信下通知 | notify_wechat | 自动发送（可设置开关）或生成通知文本 |
| 8 | 确定签字表 | confirm_sign_list | 人工确认 |

### 4.3 会议准备二阶段（串行）
前一动作完成后自动推进下一项：

| # | 动作项 | code | 执行方式 |
|---|--------|------|----------|
| 1 | 确定与会人员 | confirm_attendees | 人工确认 |
| 2 | 打电话安排桌牌 | call_table_card | 手机端拨打+播报，回传确认 |
| 3 | 人工审查确认 | manual_review | 人工确认 |
| 4 | 提醒人工接待 | remind_reception | 自动通知 |

### 4.4 手机联动拨打流程
```
桌面端动作项(running)
   → 提交打电话任务(含动作话术+目标号码) 到任务队列
   → 手机 App GET /phone/poll 拉取任务
   → 拨打目标号码 → TTS 播报请求内容
   → 录音转文字（对方答复）
   → POST /phone/result 回传 {task_id, ok, confirmed}
   → 桌面端动作项 → done，记录确认信息
   → 二阶段串行则自动推进下一项
```

### 4.5 动作状态机
`pending`(待执行) → `running`(已提交执行/等手机回传) → `done`(完成)
人工确认类动作：`pending` → `waiting`(待人工) → 点击确认 → `done`

---

## 五、桌面端使用

### 5.1 启动
- 绿色版：解压 `meeting_prep_绿色版.zip` → 双击 `meeting_prep.exe`
- 安装版：运行 `meeting_prep_setup.exe` → 自动安装到 `%LOCALAPPDATA%\Programs\meeting_prep\` 并创建桌面快捷方式「会议准备工作台」
- 源码：`python main.py`

启动后屏幕出现主窗口，右下角托盘出现红色三角图标。**关闭主窗口 = 最小化到托盘**（不退出）。

### 5.2 界面（五个页签）
| 页签 | 功能 |
|------|------|
| **会议准备** | 左侧会议列表，右侧所选会议的一/二阶段动作项；「新建会议」输入主题+时间即自动开始一阶段并行准备；`waiting` 动作项有「确认」按钮 |
| **信息采集** | 手动粘贴/输入文本提交入库；下方信息库列表 |
| **手机联动号码** | 为 6 个打电话动作配置目标号码，保存后生效 |
| **设置** | 15 项关键配置（见「八、设置项说明」） |
| **动作日志** | 所有动作执行记录（成功/失败/消息） |

### 5.3 常用操作
1. **新建会议**：会议准备页 → 新建会议 → 填主题/时间 → 创建并开始准备 → 一阶段自动并行启动
2. **人工确认**：对 `waiting` 项点「确认」→ 标记完成，二阶段自动推进
3. **配号码**：手机联动号码页 → 填号码 → 保存
4. **录信息**：信息采集页 → 粘贴文本 → 提交（交 AI 提炼）
5. **改配置**：设置页 → 修改 → 保存设置

---

## 六、Web 端使用

启动桌面端后，浏览器访问：**http://127.0.0.1:8780**

功能与桌面端对应，5 秒自动刷新（工作流执行实时可见）：
- **新建会议**：填主题/时间 → 创建并开始准备
- **会议详情**：一阶段/二阶段动作项状态，`waiting` 项「人工确认」
- **手动录入信息**、**信息库**、**动作日志**
- **设置**：与桌面端设置页一致

---

## 七、鸿蒙手机端使用

### 7.1 编译安装
1. DevEco Studio 打开 `phone_app/` 工程 → Sync 下载 SDK
2. 连接鸿蒙手机（USB 调试）→ 真机签名 → Run 生成 `.hap` 安装
3. 真机授权：网络 / 麦克风 / 录音 / 拨号

### 7.2 使用
1. 电脑运行桌面端（`meeting_prep.exe`），并已在「手机联动号码」页配好号码
2. 手机与电脑**同一局域网**，App 输入桌面端 IP
3. 「连接并拉取任务」→ 显示当前待拨打任务（动作/话术/号码）
4. 「拨打并播报」：拨打号码 + TTS 语音播报请求内容
5. 「录音转文字」：对方答复自动识别（可手动编辑）
6. 「回传确认信息」：确认信息回传桌面端，动作项置为完成

---

## 八、设置项说明

可在桌面端「设置」页或 Web「设置」卡片修改，保存到 `config.json`：

| 设置项 | 类型 | 默认 | 说明 |
|--------|------|------|------|
| LLM API Key | 密码 | 空 | DeepSeek Key，填了启用 AI 提炼 |
| LLM Base URL | 文本 | https://api.deepseek.com | 模型服务地址 |
| LLM 模型 | 文本 | deepseek-chat | 模型名 |
| Web 端口 | 整数 | 8780 | Web 服务端口（重启生效） |
| 手机联动端口 | 整数 | 8781 | 手机端对接端口（重启生效） |
| 采集轮询间隔(秒) | 整数 | 300 | 微信等来源扫描频率 |
| 启用微信采集 | 布尔 | 开 | 是否用 UIA 扫微信会话 |
| 启用OCR识别 | 布尔 | 关 | 是否后台识别屏幕区域 |
| OCR 识别间隔(秒) | 整数 | 120 | OCR 轮询频率 |
| OCR 识别区域 | 文本 | 0,0,800,600 | left,top,width,height |
| OCR 引擎 | 文本 | rapidocr | rapidocr（默认）/ tesseract |
| 启用微信自动发送 | 布尔 | 关 | 微信通知是否自动发送 |
| 微信通知目标 | 文本 | 空 | 目标群/联系人名称 |
| 微信发送延迟(秒) | 整数 | 3 | 搜索目标后等待时间 |
| Whisper 模型 | 文本 | small | 录音转文字模型档位 |

---

## 九、配置文件结构

`data/config.json`（首次启动自动生成）：
```json
{
  "app": { "name": "会议准备自动化工作台", "version": "0.1.0" },
  "llm": { "api_key": "", "base_url": "https://api.deepseek.com", "model": "deepseek-chat" },
  "server": { "host": "127.0.0.1", "port": 8780 },
  "collect": { "interval_seconds": 300, "wechat_enabled": true,
               "manual_enabled": true, "speech_enabled": true, "ocr_enabled": false },
  "ocr": { "interval_seconds": 120, "region": "0,0,800,600", "engine": "rapidocr" },
  "wechat": { "send_enabled": false, "notify_target": "", "send_delay": 3 },
  "speech": { "whisper_model": "small", "device": "auto" },
  "phone": { "enabled": true, "host": "0.0.0.0", "port": 8781 },
  "desktop": { "live_enabled": true }
}
```
环境变量覆盖：`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`COLLECT_INTERVAL`。

电话号码单独存于数据库 `phone_numbers` 表（桌面端「手机联动号码」页维护）。

---

## 十、部署与打包

### 10.1 源码运行
```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt   # 建议加 -i 清华源
.venv\Scripts\python main.py
```

### 10.2 打包（venv 内）
```powershell
# 桌面端 onedir 绿色版
.venv\Scripts\python -m PyInstaller --noconfirm --onedir --windowed --name meeting_prep ^
  --add-data "server/frontend;server/frontend" ^
  --collect-all rapidocr_onnxruntime --collect-all uvicorn ^
  --exclude-module pandas --exclude-module matplotlib --exclude-module scipy main.py

# 安装版（先打 zip 再打包安装器）
Compress-Archive dist\meeting_prep\* build\meeting_prep_pkg.zip
.venv\Scripts\python -m PyInstaller --noconfirm --onefile --windowed ^
  --name meeting_prep_setup --add-data "build/meeting_prep_pkg.zip;." build/installer_setup.py
```

### 10.3 产物
| 产物 | 位置 | 说明 |
|------|------|------|
| 安装版 | `dist\meeting_prep_setup.exe` | 一键安装 + 桌面快捷方式 |
| 绿色版 | `dist\meeting_prep_绿色版.zip` | 解压即用 |
| onedir | `dist\meeting_prep\` | 文件夹版 |
| 手机端 | `phone_app\` | 鸿蒙源码工程（DevEco 编译） |

---

## 十一、目录结构

```
ai_automation_hub/
├── main.py                    # 双端启动入口
├── requirements.txt
├── .venv/                     # 虚拟环境
├── core/                      # 底座：events/config/settings/logger/scheduler
├── storage/db.py              # SQLite 双库
├── collectors/                # 采集：im/wechat, manual, speech, ocr
├── ai/                        # 智能：llm, extract
├── automation/                # 执行：workflows, actions, phone_link
├── desktop/app.py             # 桌面端
├── server/                    # Web：app.py, api/routes.py, frontend/
├── phone_app/                 # 鸿蒙手机端工程
├── docs/                      # 文档
├── build/                     # 打包中间产物
├── dist/                      # 发布产物
└── data/                      # 运行时：db / config.json / app.log / out/
```

---

## 十二、常见问题

**Q1：Web 端打不开？**
确认桌面端在运行；浏览器访问 `http://127.0.0.1:8780`。端口被占可到设置改「Web 端口」（需重启）。

**Q2：手机 App 连不上桌面端？**
1. 手机与电脑同一局域网；2. 设置里确认「手机联动端口」(8781) 未被占用；3. Windows 防火墙放行 8781；4. 检查桌面端 IP（`ipconfig`）。

**Q3：为什么没采集到消息？**
检查「启用微信采集」开关、微信是否登录打开、轮询间隔。

**Q4：OCR 识别不到内容？**
设置「OCR 识别区域」为包含目标文字的区域；确认「启用OCR识别」打开；RapidOCR 首次运行需加载模型。

**Q5：微信通知没有自动发？**
「启用微信自动发送」需打开，且「微信通知目标」填群/联系人名；微信需登录并保持主窗口打开；发送失败会降级为生成通知文本。

**Q6：打电话动作一直"执行中"？**
等待手机 App 拉取并回传；确认已为该动作配号码；可到 Web/桌面「动作日志」查看回传情况。

**Q7：无 DeepSeek Key 能用吗？**
能。AI 提炼降级为关键词规则；材料 PPT 仍可生成（基于规则要点）。

**Q8：数据存在哪？**
`data/` 目录：任务/信息/日志在 `meeting_prep.db`，配置在 `config.json`。升级覆盖安装不影响。

**Q9：关闭主窗口程序退出了吗？**
没有，会最小化到托盘；托盘图标右键「退出」才是完全退出。

**Q10：如何卸载？**
安装版删除 `%LOCALAPPDATA%\Programs\meeting_prep\` 与桌面快捷方式即可（数据在 `data\`，如需保留先备份）。
