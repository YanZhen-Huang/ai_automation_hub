import { PhoneClient } from '../common/PhoneClient';
import call from '@ohos.telephony.call';
import textToSpeech from '@ohos.ai.textToSpeech';
import speechRecognizer from '@ohos.ai.speechRecognizer';
import { BusinessError } from '@kit.BasicServicesKit';

/**
 * 手机联动主界面（高端深蓝 + 构成主义几何 + 光感）。
 * 两个视图：① 电话联动（拉任务/拨打/播报/录音转文字/回传）
 *          ② 待办任务（desk_task_board 同步：查看/标记完成）
 */
@Entry
@Component
struct Index {
  @State view: number = 0;
  @State serverIp: string = '192.168.1.100';
  @State serverToken: string = '';
  @State status: string = '未连接';
  @State isRecording: boolean = false;
  @State statusOn: boolean = true;
  @State taskId: string = '';
  @State taskAction: string = '';
  @State taskText: string = '';
  @State taskNumber: string = '';
  @State confirmedText: string = '';
  @State tasks: any[] = [];
  @State taskStatus: string = '尚未加载';
  private client: PhoneClient = new PhoneClient();
  private recognizer: speechRecognizer.SpeechRecognizer | null = null;

  build() {
    Column({ space: 12 }) {
      // 视图切换
      Row({ space: 10 }) {
        Text('电话联动').fontSize(15).fontWeight(FontWeight.Bold)
          .fontColor(this.view === 0 ? '#38bdf8' : '#8b8b96')
          .padding(6).onClick(() => this.switchView(0))
        Text('待办任务').fontSize(15).fontWeight(FontWeight.Bold)
          .fontColor(this.view === 1 ? '#38bdf8' : '#8b8b96')
          .padding(6).onClick(() => this.switchView(1))
      }.margin({ top: 12 })

      if (this.view === 0) {
        this.buildCallView()
      } else {
        this.buildTaskView()
      }
    }
    .width('100%')
    .height('100%')
    .padding({ top: 8 })
    .linearGradient({
      direction: GradientDirection.Bottom,
      colors: [['#0a0e1a', 0.0], ['#1c1a22', 1.0]]
    })
  }

  @Builder
  buildCallView() {
    Column({ space: 12 }) {
      // 实况胶囊状态条（光感）
      Row({ space: 8 }) {
        Circle().width(8).height(8)
          .fill(this.isRecording ? '#38bdf8' : (this.statusOn ? '#7fb58a' : '#8b8b96'))
          .animation({ duration: 300, curve: Curve.EaseOut })
        Text(this.status).fontSize(12).fontColor('#92b8e0')
      }
      .padding({ left: 14, right: 14, top: 7, bottom: 7 })
      .backgroundColor('rgba(56,189,248,0.12)')
      .borderRadius(20)
      .border({ width: 1, color: 'rgba(56,189,248,0.35)' })
      .shadow({ radius: 12, color: 'rgba(56,189,248,0.28)' })

      // 构成主义几何装饰
      Row({ space: 6 }) {
        Triangle().width(14).height(14).fill('#38bdf8')
        Circle().width(10).height(10).fill('#e25c6a')
      }

      Row({ space: 8 }) {
        Text('桌面IP:').fontColor('#8b8b96')
        TextInput({ text: this.serverIp })
          .onChange((v: string) => this.serverIp = v)
          .layoutWeight(1).fontColor('#cbd3de').placeholderColor('#5a5a64')
      }.width('90%')
      Row({ space: 8 }) {
        Text('令牌:').fontColor('#8b8b96')
        TextInput({ text: this.serverToken })
          .onChange((v: string) => this.serverToken = v)
          .layoutWeight(1).fontColor('#cbd3de').placeholderColor('#5a5a64')
      }.width('90%')

      Button('连接并拉取任务').onClick(() => this.poll())
        .width('90%').backgroundColor('#38bdf8').fontColor('#06121f')
        .fontWeight(FontWeight.Bold).shadow({ radius: 14, color: 'rgba(56,189,248,0.35)' })

      if (this.taskId) {
        Column({ space: 8 }) {
          Text(`任务：${this.taskAction}`).fontSize(17).fontWeight(FontWeight.Medium).fontColor('#cbd3de')
          Text(this.taskText).fontSize(13).fontColor('#9aa6b8')
          Text(`目标号码：${this.taskNumber}`).fontSize(14).fontColor('#38bdf8')
          Row({ space: 10 }) {
            Button('拨打并播报').onClick(() => this.makeCall())
              .backgroundColor('#1a2438').fontColor('#92b8e0')
              .border({ width: 1, color: 'rgba(56,189,248,0.5)' })
            Button(this.isRecording ? '停止并识别' : '录音转文字')
              .onClick(() => this.isRecording ? this.stopRecord() : this.recordAndSubmit())
              .backgroundColor(this.isRecording ? '#e25c6a' : '#38bdf8')
              .fontColor(this.isRecording ? '#cbd3de' : '#06121f')
          }
          TextArea({ placeholder: '对方答复（识别结果可编辑）', text: this.confirmedText })
            .onChange((v: string) => this.confirmedText = v)
            .height(80).width('100%').fontColor('#cbd3de')
            .placeholderColor('#5a5a64').backgroundColor('#1a2438').borderRadius(10)
          Button('回传确认信息').onClick(() => this.submit(true))
            .width('100%').backgroundColor('#4dd0e1').fontColor('#06121f')
            .fontWeight(FontWeight.Bold)
        }
        .padding(16).width('90%').backgroundColor('rgba(19,19,24,0.85)')
        .borderRadius(14).border({ width: 1, color: 'rgba(56,189,248,0.4)' })
        .shadow({ radius: 18, color: 'rgba(56,189,248,0.2)' })
      }
    }.width('100%').alignItems(HorizontalAlign.Center)
  }

  @Builder
  buildTaskView() {
    Column({ space: 10 }) {
      Row({ space: 8 }) {
        Text('桌面IP:').fontColor('#8b8b96')
        TextInput({ text: this.serverIp })
          .onChange((v: string) => this.serverIp = v)
          .layoutWeight(1).fontColor('#cbd3de').placeholderColor('#5a5a64')
      }.width('90%')
      Row({ space: 8 }) {
        Button('加载待办').onClick(() => this.refreshTasks())
          .backgroundColor('#38bdf8').fontColor('#06121f').fontWeight(FontWeight.Bold)
        Text(this.taskStatus).fontSize(12).fontColor('#8b8b96')
      }.width('90%')

      if (this.tasks.length === 0) {
        Text('暂无待办任务').fontColor('#8b8b96').margin({ top: 40 })
      } else {
        List({ space: 8 }) {
          ForEach(this.tasks, (t: any) => {
            ListItem() {
              Row() {
                Column({ space: 3 }) {
                  Text(t.title || '').fontSize(14).fontWeight(FontWeight.Medium).fontColor('#cbd3de')
                  Text(`截止：${t.due_date || '无'} ｜ ${t.source || ''}`).fontSize(11).fontColor('#8b8b96')
                }.layoutWeight(1).alignItems(HorizontalAlign.Start)
                if (t.status === 'done') {
                  Text('✓ 完成').fontColor('#7fb58a').fontSize(13)
                } else {
                  Button('完成').fontSize(12).backgroundColor('#38bdf8').fontColor('#06121f')
                    .onClick(() => this.taskDone2(t.id))
                }
              }.padding(12).width('100%')
            }
            .backgroundColor('rgba(19,19,24,0.85)')
            .borderRadius(10)
            .border({ width: 1, color: 'rgba(56,189,248,0.25)' })
          }, (t: any) => t.id)
        }.width('90%').layoutWeight(1)
      }
    }.width('100%').alignItems(HorizontalAlign.Center)
  }

  switchView(v: number): void {
    this.view = v;
    if (v === 1) {
      this.refreshTasks();
    }
  }

  async refreshTasks(): Promise<void> {
    this.client.setServer(this.serverIp);
    this.taskStatus = '加载中...';
    try {
      this.tasks = await this.client.loadTasks();
      this.taskStatus = this.tasks.length + ' 条待办';
    } catch (e) {
      this.taskStatus = '加载失败';
    }
  }

  async taskDone2(id: number): Promise<void> {
    await this.client.taskDone(id);
    this.refreshTasks();
  }

  poll(): void {
    this.client.setServer(this.serverIp, 8781, this.serverToken);
    this.status = '连接中...';
    this.statusOn = true;
    try {
      this.client.pollTask().then((task: object | null) => {
        if (task) {
          this.taskId = task.task_id;
          this.taskAction = task.action;
          this.taskText = task.text;
          this.taskNumber = task.number || '';
          this.status = '已拉取任务';
          this.statusOn = true;
        } else {
          this.status = '暂无任务，请稍后再试';
          this.taskId = '';
          this.statusOn = false;
        }
      }).catch(() => {
        this.status = '连接失败，请检查 IP 与桌面端服务';
        this.statusOn = false;
      });
    } catch (e) {
      this.status = '连接异常';
      this.statusOn = false;
    }
  }

  makeCall(): void {
    if (!this.taskNumber) {
      this.status = '该动作未配置号码';
      return;
    }
    try {
      call.makeCall(this.taskNumber, (err: BusinessError) => {
        if (err) {
          this.status = `拨打失败：${err.code}`;
        } else {
          this.status = '已拨打，播报中...';
          this.speak();
        }
      });
    } catch (e) {
      this.status = '拨打异常';
    }
  }

  speak(): void {
    try {
      const engine = textToSpeech.createEngine({
        language: 'zh-Hans', person: 0, online: false,
      });
      engine.speak({
        text: this.taskText, queueMode: 0,
      }, (err: BusinessError) => {
        if (err) { console.error(`TTS fail: ${err.code}`); }
      });
    } catch (e) {
      console.error('TTS error: ' + e);
    }
  }

  async recordAndSubmit(): Promise<void> {
    if (!this.taskId) { this.status = '请先拉取任务'; return; }
    try {
      const sr = speechRecognizer.createEngine({ language: 'zh-CN' });
      this.recognizer = sr;
      sr.on('onResult', (err: BusinessError, result: speechRecognizer.SpeechRecognitionResult) => {
        if (!err && result.result) { this.confirmedText = result.result; }
      });
      sr.on('onComplete', (err: BusinessError) => {
        this.isRecording = false;
        if (err) { this.status = `识别异常：${err.code}`; }
        else { this.status = '识别完成'; this.releaseRecognizer(); this.submit(true); }
      });
      const recognizerInfo: speechRecognizer.RecognizerInfo = {
        audioType: speechRecognizer.AudioInfoType.AUDIO_INFO_TYPE_PCM,
        audioSource: speechRecognizer.AudioSourceType.AUDIO_SOURCE_MIC,
        intervalMilliseconds: 1000,
      };
      sr.startListening(recognizerInfo, (err: BusinessError) => {
        if (err) { this.status = `启动录音失败：${err.code}`; this.isRecording = false; }
        else {
          this.isRecording = true;
          this.status = '录音中，请说话（10秒后自动停止）...';
          setTimeout(() => { if (this.isRecording) { this.stopRecord(); } }, 10000);
        }
      });
    } catch (e) {
      this.status = '语音识别不可用：' + e;
    }
  }

  stopRecord(): void {
    if (this.recognizer) {
      try { this.recognizer.stopListening(); } catch (e) { console.error('stop err: ' + e); }
      this.releaseRecognizer();
    }
  }

  releaseRecognizer(): void {
    if (this.recognizer) {
      try { this.recognizer.release(); } catch (e) { console.error('release err: ' + e); }
      this.recognizer = null;
    }
  }

  async submit(ok: boolean): Promise<void> {
    if (!this.taskId) { return; }
    const okRes = await this.client.submitResult(this.taskId, ok, this.confirmedText);
    this.status = okRes ? '已回传桌面端' : '回传失败';
    this.statusOn = okRes;
    this.taskId = ''; this.taskText = ''; this.confirmedText = ''; this.isRecording = false;
  }
}
