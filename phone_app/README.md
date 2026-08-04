# 鸿蒙手机端 · 会议准备联动 App（骨架）

配合桌面端 `ai_automation_hub` 使用：桌面端提交"打电话"任务，手机 App 局域网内拉取 → 拨打 → TTS 播报 → 录音转文字回传确认信息。

## 工程结构
```
phone_app/
├── build-profile.json5 / oh-package.json5 / hvigorfile.ts   工程配置
├── AppScope/app.json5                    应用配置（含图标）
└── entry/
    ├── build-profile.json5 / oh-package.json5 / hvigorfile.ts 模块配置
    └── src/main/
        ├── module.json5                  模块配置 + 权限声明
        ├── ets/entryability/EntryAbility.ets 入口
        ├── ets/pages/Index.ets               主界面（拉取/拨打/播报/录音转文字/回传）
        ├── ets/common/PhoneClient.ets        与桌面端 HTTP 通信
        └── resources/                        资源（图标/颜色/字符串）
```

## 如何编译安装到手机（需 DevEco Studio）
1. 用 **DevEco Studio** 打开 `phone_app/` 工程目录；
2. 首次打开按提示 **Sync / 下载 SDK 依赖**；
3. 连接鸿蒙手机（开启开发者模式/USB 调试），真机签名；
4. 点击 **Run**，编译生成 `.hap` 并安装到手机；
5. 手机与电脑同一局域网，打开 App 输入桌面端 IP 即可联动。

## 与桌面端接口（HTTP，桌面端端口 8781）
| 接口 | 方向 | 说明 |
|------|------|------|
| `GET  /phone/poll` | 手机→桌面 | 拉取一个待拨打任务 `{task_id,item_id,action,text,number}` |
| `POST /phone/result` | 手机→桌面 | 回传 `{task_id, ok, confirmed}` |

## 运行流程
1. 手机与电脑同一局域网；
2. 桌面端启动（`python main.py`），在"手机联动号码"页为每个打电话动作配好号码；
3. 手机 App 输入桌面端 IP → 拉取任务 → 拨打 + 播报 → 录音转文字回传；
4. 桌面端收到回传 → 动作项置为"已完成"并记录确认信息。

## 待完善（需 DevEco Studio 真机联调）
- **录音转文字已实现**（`Index.ets`）：`@ohos.ai.speechRecognizer` 麦克风流式识别（API 10+），识别结果自动回传桌面端；
- 真机验证点：
  1. `speechRecognizer.createEngine` 参数与 `onResult/onComplete` 回调需按系统版本核对；
  2. 权限真机授权：`INTERNET` / `MICROPHONE` / `RECORD_AUDIO` / `CALL_DIAL`；
  3. TTS 引擎参数（`@ohos.ai.textToSpeech`）按设备微调；
  4. 图标等资源文件按工程要求补齐后即可用 DevEco Studio 打开编译；
- 拨打失败/识别不可用时界面均有状态提示，可手动编辑答复后回传。
