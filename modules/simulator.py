"""
Simulator Module - Legal Scenario Generation
"""
import json_repair
from typing import List
from models import BusinessModel, Scenario
from llm_client import llm_client


class Simulator:
    SYSTEM_PROMPT = """
    당신은 '법률 상황 시나리오 시뮬레이터'입니다.
    사용자의 법률 상담 케이스를 바탕으로 대표적인 '핵심 시나리오' 1개를 생성하십시오.
    
    [중요] 법적 판단이 가능하도록 반드시 다음을 포함하십시오:
    - 구체적인 수치 (금액, 기간, 인원 등)
    - 명확한 행위 (누가, 무엇을, 어떻게)
    - 시간적 순서 (언제, 어떤 순서로)

    상담 유형별 시나리오 예시:
    - 사업 아이디어: 서비스 이용 과정의 핵심 거래 흐름
    - 계약/거래: 계약 체결부터 이행, 분쟁 발생까지의 과정
    - 분쟁/소송: 분쟁의 발단부터 현재 상황까지
    - 일상생활: 문제 상황의 구체적 전개 과정

    출력은 반드시 아래 구조의 JSON 리스트여야 하며, 모든 내용은 '한국어'로 작성하십시오.
    [
        {
            "name": "시나리오 요약 (한 줄로 핵심 상황 설명)",
            "type": "Main",
            "actions": [
                {"actor": "당사자 A", "action": "구체적 행위 (금액, 날짜, 방식 포함)", "object": "대상/객체"},
                {"actor": "당사자 B", "action": "구체적 반응/행위", "object": "대상/객체"}
            ]
        }
    ]
    """

    async def execute(self, model: BusinessModel) -> List[Scenario]:
        print("\n[2] Simulating Legal Scenarios...")
        prompt = f"상담 케이스: {model.model_dump_json()}"
        response = await llm_client.generate(self.SYSTEM_PROMPT, prompt, model="gpt-4o-mini")
        try:
            data = json_repair.loads(response)
            if isinstance(data, dict): data = [data]
            return [Scenario(**s) for s in data][:1]  # 강제로 1개만 선택
        except Exception as e:
            print(f"Simulator Error: {e}")
            return []
