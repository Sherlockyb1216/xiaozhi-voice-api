# 小智语音助手 API（服务化封装层）

把开源语音助手 [xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server) 的能力抽出来，做成业务系统能直接调用的 HTTP 服务：一次 `POST /ask`，返回文本回复 + base64 编码的 MP3。

> **关于代码归属（重要）**
> 本仓库是**服务化封装层**，不是语音系统的完整实现。
> `app.py`（FastAPI 入口、接口定义、异步调用、TTS 封装与降级）由我编写；
> ASR / LLM / TTS / 意图识别等 provider 来自上游 xiaozhi-esp32-server，本仓库未包含其源码，运行前需自行拉取。
> 这样划界是为了让 review 时能一眼看出「哪部分是封装、哪部分是复用」。

---

## 架构

```
客户端
  │  POST /ask  { "text": "...", "phone_number": "..." }
  ▼
FastAPI (app.py)
  │  httpx.AsyncClient.stream()  ──►  AI CRM 服务 (POST /chat)
  │                                    · 意图识别
  │                                    · 知识库检索
  │                                    · 按手机号维护多轮上下文
  ▼
EdgeTTS 合成 ──► MP3 ──► base64
  ▼
{ "response_text": "...", "response_audio": "<base64 mp3>" }
```

设计上把「业务对话」和「语音合成」分开：对话交给 CRM，本服务只负责协议转换、音频合成和降级。

---

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 健康检查 |
| POST | `/ask` | 文本进，文本 + base64 MP3 出 |

请求：

```json
{ "text": "现在几点了？", "phone_number": "13800001111" }
```

响应：

```json
{ "response_text": "...", "response_audio": "SUQzBAAAAAA..." }
```

- `text` 为空 → 400
- TTS 失败 → `response_audio` 为 `null`，文本照常返回（主链路不因音频失败而中断）
- 启动后访问 `/docs` 可见 Swagger 文档

---

## 快速开始

```bash
# 1. 拉取上游 provider 代码
git clone https://github.com/xinnan-tech/xiaozhi-esp32-server.git
# 将上游的 core/ 目录拷贝到本仓库根目录

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置
cp .env.example .env    # 填入 LLM 的 API Key / Base URL / 模型名

# 4. 启动 CRM 服务（另起一个进程，端口 5000）
# 5. 启动本服务
uvicorn app:app --host 0.0.0.0 --port 8000

# 6. 访问文档
# http://localhost:8000/docs
```

---

## 测试记录

见 [`docs/测试记录.md`](docs/测试记录.md)，7 条用例覆盖：

- 普通闲聊 / 时间查询 / 笑话
- 空文本 400 边界
- 知识库检索（退换货政策）
- 跨轮记忆（"我叫什么名字"）

---

## 踩坑

**FunASR 的 sentencepiece 模型只认英文路径。** 中文目录下加载直接失败，通过动态切换工作目录规避。这个坑只在中文 Windows 环境出现，上游 issue 里有同类反馈。

---

## 已知限制

- 意图识别、RAG、多轮记忆都在 CRM 侧，本仓库只做透传，因此**本仓库不包含 RAG 的实现**。
- 没有并发压测，延迟数据只有单次请求的耗时打印，没有 P95。
- 上游 `core/` 未随仓库分发，克隆后不能开箱即跑。
