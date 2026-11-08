import sys
import os
import asyncio
import json
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

# ---------- 导入核心模块 ----------
from core.utils.dialogue import Dialogue
from core.providers.intent.intent_llm.intent_llm import IntentProvider
from core.providers.llm.openai.openai import LLMProvider
from core.providers.tts.edge import TTSProvider

app = FastAPI(title="小智语音助手 API", version="1.0")

# ---------- 请求/响应模型 ----------
class AskRequest(BaseModel):
    text: str
    phone_number: str | None = "anonymous"

class AskResponse(BaseModel):
    response_text: str
    response_audio: str | None = None

# ---------- 初始化核心组件 ----------
# 1. LLM 实例（根据 .env 配置初始化）
llm_config = {
    "api_key": os.getenv("OPENAI_API_KEY"),
    "base_url": os.getenv("OPENAI_API_BASE"),
    "model_name": os.getenv("LLM_MODEL"),
}
print("当前LLM配置：",llm_config)
llm = LLMProvider(llm_config)

# 2. 意图识别实例
intent_config = {}
intent_provider = IntentProvider(intent_config)
intent_provider.llm = llm  # 将LLM注入意图识别

# 3. TTS 实例
tts_config = {
    "output_dir":"tmp/",
    "voice":"zh-CN-XiaoyiNeural"
}
tts = TTSProvider(tts_config,delete_audio_file=False)

import httpx

async def call_ai_crm(phone_number: str, query: str) -> str:
    """调用 ai_crm 的 /chat 接口，处理流式响应"""
    async with httpx.AsyncClient() as client:
        try:
            async with client.stream(
                "POST",
                "http://127.0.0.1:5000/chat",
                json={"phone_number": phone_number, "query": query},
                timeout=30.0
            ) as resp:
                reply_chunks = []
                async for chunk in resp.aiter_text():
                    reply_chunks.append(chunk)
                reply_text = "".join(reply_chunks).strip()
                if not reply_text:
                    return "抱歉，CRM 服务返回为空。"
                return reply_text
        except Exception as e:
            print(f"调用 AI CRM 失败: {e}")
            return "抱歉，CRM 服务暂时不可用。"

# ---------- 核心处理函数 ----------
import base64
import os

async def process_text(text: str, phone: str = "anonymous", history: list = None) -> dict:
    # 使用 AI CRM 获取智能回复（意图识别、RAG、多轮对话全由它处理）
    reply_text = await call_ai_crm(phone, text)

    # TTS 合成语音
    audio_base64 = None
    try:
        output_file = tts.generate_filename()
        await tts.text_to_speak(reply_text, output_file)
        if os.path.exists(output_file):
            with open(output_file, "rb") as f:
                audio_bytes = f.read()
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    except Exception as e:
        print(f"TTS 调用失败: {e}")

    return {"response_text": reply_text, "response_audio": audio_base64}
# ---------- 接口 ----------
@app.post("/ask", response_model=AskResponse)
async def ask_endpoint(request: AskRequest):
    user_text = request.text.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="文本内容不能为空")
    phone = request.phone_number or "anonymous"
    result = await process_text(user_text, phone=phone)
    return AskResponse(**result)
@app.get("/")
async def root():
    return {"message": "小智语音助手 API 已启动"}