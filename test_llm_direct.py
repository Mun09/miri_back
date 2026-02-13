#!/usr/bin/env python3
"""
LLM 직접 호출 테스트
"""
import asyncio
from openai import AsyncOpenAI
import os
from dotenv import load_dotenv

load_dotenv()

async def test_llm_directly():
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    prompt = """
Below is a list of 4 laws/rules.

Business Action:
외국인 관광객이 달러를 앱에서 토큰으로 환전하고, 현지 상점에서 토큰으로 결제

Available Laws:
1. 외국환거래법
2. 외국환거래법 시행령
3. 전자금융거래법
4. 전자금융거래법 시행령

Task: Select ALL laws that are relevant to this business action. Return their exact names as a JSON array.

Output format:
["법령명1", "법령명2", "법령명3"]

If NONE are relevant, return: []
"""
    
    print("Prompt:")
    print(prompt)
    print("\n" + "="*80 + "\n")
    
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content":  ""},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=1024
    )
    
    result = response.choices[0].message.content.strip()
    
    print("LLM Response:")
    print(result)
    print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    asyncio.run(test_llm_directly())
