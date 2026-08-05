import http from '@ohos.net.http';

/**
 * 与桌面端(ai_automation_hub)通信的客户端。
 * 桌面端 phone_link 服务：GET /phone/poll 拉任务，POST /phone/result 回传。
 */
export class PhoneClient {
  private ip: string = '';
  private port: number = 8781;
  private token: string = '';
  private http: http.HttpRequest;

  constructor() {
    this.http = http.createHttp();
  }

  setServer(ip: string, port: number = 8781, token: string = ''): void {
    this.ip = ip;
    this.port = port;
    this.token = token;
  }

  private base(): string {
    return `http://${this.ip}:${this.port}`;
  }

  private auth(): string {
    return this.token ? `?token=${encodeURIComponent(this.token)}` : '';
  }

  /**
   * 拉取一个待拨打的电话任务。
   * 返回：{ task_id, item_id, action, text, number } 或 null。
   */
  async pollTask(): Promise<object | null> {
    const url = `${this.base()}/phone/poll${this.auth()}`;
    const res = await this.http.request(url, {
      method: http.RequestMethod.GET,
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 10000,
      readTimeout: 10000,
    });
    if (res.responseCode !== 200) {
      return null;
    }
    const body = JSON.parse(res.result as string);
    return body && body.task_id ? body : null;
  }

  /**
   * 回传拨打结果。
   * @param taskId 任务ID
   * @param ok     是否确认成功
   * @param confirmed 对方确认的信息（录音转文字结果）
   */
  async submitResult(taskId: string, ok: boolean, confirmed: string): Promise<boolean> {
    const url = `${this.base()}/phone/result${this.auth()}`;
    const res = await this.http.request(url, {
      method: http.RequestMethod.POST,
      header: { 'Content-Type': 'application/json' },
      extraData: JSON.stringify({ task_id: taskId, ok, confirmed }),
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 10000,
      readTimeout: 10000,
    });
    return res.responseCode === 200;
  }

  /** 拉取待办任务列表（Web 端口 8780，desk_task_board 同步）。 */
  async loadTasks(): Promise<object[]> {
    const url = `http://${this.ip}:8780/api/tasks`;
    const res = await this.http.request(url, {
      method: http.RequestMethod.GET,
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 10000,
      readTimeout: 10000,
    });
    if (res.responseCode !== 200) {
      return [];
    }
    try {
      return JSON.parse(res.result as string) || [];
    } catch (e) {
      return [];
    }
  }

  /** 标记待办任务完成。 */
  async taskDone(taskId: number): Promise<boolean> {
    const url = `http://${this.ip}:8780/api/tasks/${taskId}/done`;
    const res = await this.http.request(url, {
      method: http.RequestMethod.POST,
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 10000,
      readTimeout: 10000,
    });
    return res.responseCode === 200;
  }
}
