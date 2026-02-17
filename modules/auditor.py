"""
Auditor Module - Adversarial Debate System
다각도 법률 분석 및 판결 모듈 (Prosecutor vs Defense vs Judge)
"""
import asyncio
import json_repair
from typing import Tuple

from models import Scenario, LegalEvidence, RiskReport
from llm_client import llm_client


class AdversarialDebate:
    """
    Multi-Agent Debate System: Prosecutor vs. Defense -> Judge
    Includes Rebuttal & Reflexion (Self-Correction) phases.
    """

    # [Configuration]
    # Removed separate Prosecutor/Defense steps for speed.

    JUDGE_PROMPT = """
    You are a 'Friendly and Professional Legal Counsel' (친절하고 전문적인 변호사).
    Your goal is to explain complex legal issues to a non-expert client in an easy-to-understand and warm manner.
    
    [Input Data]
    1. Legal Situation: {scenario}
    2. Collected Legal Evidence (Indexed): 
    {evidence}

    [Tone & Style Guidelines]
    1. **Persona**: A trustworthy, warm, and highly competent lawyer.
    2. **Language**: Polite Korean (Honorifics, e.g., "검토해 보았습니다", "판단됩니다", "추천드립니다").
    3. **Clarity**: Avoid overly difficult legal jargon where possible, or explain it simply.
    4. **Empathy**: Acknowledge the user's situation before delivering the legal verdict.

    [Judgment Guidelines]
    1. **Statute-Centric**: Base your advice primarily on Acts, Decrees, and Rules.
    2. **Precedents**: Use precedents as supporting examples to explain *how* the law is applied.
    3. **Missing Evidence**: If no specific law is found, explain general legal principles instead of saying "I don't know."
    4. **Citations**: 
       - You MUST cite the source using the index number from the [Input Data].
       - Format: "근로기준법에 따르면[1]" or "대법원은 판시하였습니다[2]".
       - DO NOT invent URLs. Only use the [Index] reference.
    5. **Sentencing**: 
       - If the user asks about punishment (fine, jail), PROVIDE THE EXACT RANGE stated in the law.
       - Example: "If found guilty under Article X, the penalty is up to 5 years in prison or a fine not exceeding 50 million won." (Always accompany with "However, actual sentencing depends on the judge/circumstances.")

    [Task]
    Provide a comprehensive legal advisory opinion.
    
    [Output JSON (Korean)]
    {{
        "위험도": "안전 | 주의 | 위험",
        "정확도": 0 ~ 100,
        "평가내용": "MIRI의 자문의견.\\n\\n안녕하세요, MIRI 법률 자문입니다. 의뢰하신 내용을 꼼꼼히 검토해 보았습니다.\\n\\n1. **상황 분석**: (의뢰인의 상황을 공감하며 요약)\\n2. **법적 검토**: (관련 법령과 행정규칙을 근거로 위법/적법 여부를 쉽게 설명. **반드시 [1], [2] 와 같이 인덱스 인용 표기**)\\n3. **판례 경향**: (관련 판례가 있다면 '이런 경우에는 법원이 이렇게 판단하는 경향이 있습니다'라고 소개)\\n4. **예상 처벌 수위**: (관련 법령에 명시된 법정형(징역, 벌금 등)을 구체적으로 언급. 단, 실제 선고는 다를 수 있음을 명시)\\n5. **대응 방안**: (의뢰인이 취할 수 있는 구체적인 행동이나 권리 구제 방안 제안)\\n6. **종합 결론**: (최종적인 조언과 함게 마무리 인사)",
        "인용근거": ["1. 근로기준법 제23조", "2. 대법원 20xx다xxxxx (참고)", ...],
        "평가결과": "부당해고 구제 신청 가능 | 계약서 수정 권고 | 법적 리스크 낮음 등 (짧은 요약)",
        "주요쟁점": ["해고 예고 의무 위반 여부 for 500만원 벌금 가능성", "정당한 해고 사유 존재 여부", ...]
    }}
    """

    def __init__(self):
        pass

    async def _render_verdict(self, scenario_text: str, evidence_text: str) -> RiskReport:
        from llm_client import llm_client
        import json_repair
        
        prompt = self.JUDGE_PROMPT.format(
            scenario=scenario_text,
            evidence=evidence_text
        )
        
        try:
            res = await llm_client.generate(prompt, "Final Legal Verdict", model="gpt-4o-mini", max_tokens=1500, temperature=0.3)
            data = json_repair.loads(res)
            
            # 한국어 필드명 매핑 (LLM이 한국어로 응답)
            risk_level = data.get('위험도', data.get('risk_level', 'Caution'))
            confidence = data.get('정확도', data.get('confidence_score', 0))
            verdict_text = data.get('평가내용', data.get('verdict', '평가 내용 없음'))
            cited = data.get('인용근거', data.get('cited_evidence', []))
            
            # 인용 근거 포맷팅
            if isinstance(cited, list):
                citation_text = ", ".join(cited)
            else:
                citation_text = str(cited)

            # 위험도 영문 매핑 (프론트엔드 호환)
            risk_map = {'안전': 'Safe', '주의': 'Caution', '위험': 'Danger'}
            risk_level_en = risk_map.get(risk_level, risk_level)

            return RiskReport(
                verdict=risk_level_en,
                summary=verdict_text,
                citation=citation_text,
                key_issues=data.get("주요쟁점", [])
            )
        except Exception as e:
            print(f"Verdict Error: {e}")
            return RiskReport(verdict="Caution", summary=f"법적 검토 중 오류가 발생했습니다: {e}", citation="", key_issues=[])

    async def execute(self, scenario: Scenario, evidence: LegalEvidence) -> RiskReport:
        # Create indexed evidence list
        evidence_list = evidence.relevant_laws
        if not evidence_list:
            evidence_text = "No specific laws found."
        else:
            evidence_text = "\n".join([f"{i+1}. {item}" for i, item in enumerate(evidence_list)])

        # Direct Verdict without debate
        return await self._render_verdict(scenario.model_dump_json(), evidence_text)

