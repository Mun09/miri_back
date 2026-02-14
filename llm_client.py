"""
OpenAI LLM Client for MIRI Legal Advisory System
"""
import os
import asyncio
from config import IS_TEST

try:
    from openai import AsyncOpenAI
except ImportError:
    raise ImportError("Please run 'pip install openai' to use this feature.")


class OpenAIClient:
    def __init__(self):
        # API Key는 환경변수에서 로드하거나 여기에 직접 입력
        self.api_key = os.getenv("OPENAI_API_KEY") 
        if not self.api_key:
            if IS_TEST:
                self.api_key = "sk-dummy-key-for-test-mode"
                print("⚠️ [TEST MODE] Using dummy API Key due to missing env var.")
            else:
                print("⚠️ Warning: OPENAI_API_KEY not found in environment variables.")
        
        self.client = AsyncOpenAI(api_key=self.api_key)
        self.semaphore = asyncio.Semaphore(3)  # LLM 동시 요청 제한 (Rate Limit 방지)

    async def generate(self, system_prompt: str, user_input: str, model: str = "gpt-4o-mini", **kwargs) -> str:
        max_retries = 3
        base_delay = 1.0  # 1초
        
        async with self.semaphore:
            for attempt in range(max_retries):
                try:
                    response = await self.client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_input}
                        ],
                        temperature=kwargs.get("temperature", 0.7),
                        max_tokens=kwargs.get("max_tokens", 2048)
                    )
                    return response.choices[0].message.content.strip()
                except Exception as e:
                    error_str = str(e)
                    
                    # Rate Limit 에러 처리
                    if "rate_limit" in error_str.lower() or "429" in error_str:
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)  # Exponential backoff
                            print(f"⏳ Rate Limit 도달. {delay}초 후 재시도... ({attempt + 1}/{max_retries})")
                            await asyncio.sleep(delay)
                            continue
                    
                    print(f"LLM Error ({model}): {e}")
                    return "{}"  # Return empty JSON-like string on error to prevent json parsing crash
            
            return "{}"  # 모든 재시도 실패


# Global instance
llm_client = OpenAIClient()
