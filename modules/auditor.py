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

    PROSECUTOR_PROMPT = """
    You are a Legal Risk Assessment Specialist.
    Based on the scenario and evidence, identify ALL potential legal risks, liabilities, and violations.
    
    [Hierarchy of Evidence]
    1. **Primary Authority**: Statutes (Acts, Decrees) and Administrative Rules.
    2. **Secondary Reference**: Precedents (Case Law). Use these only to support statutory interpretation.
    
    [Scenario]
    {scenario}

    [Evidence]
    {evidence}
    
    Focus on:
    - Specific violations of Statutes/Rules
    - Civil/Criminal liabilities based on these laws
    - Administrative sanctions (fines, license revocation)
    - If precedents are scarce, rely on the **text of the law** and **legal principles**.
    - DO NOT overemphasize the lack of precedents as a risk itself.
    """

    DEFENSE_PROMPT = """
    You are a Legal Rights Advocate.
    Based on the scenario and evidence, identify legal protections and rights.

    [Hierarchy of Evidence]
    1. **Primary Authority**: Statutes (Acts, Decrees) and Administrative Rules.
    2. **Secondary Reference**: Precedents (Case Law).
    
    [Scenario]
    {scenario}
    
    [Evidence]
    {evidence}
    
    Focus on:
    - Exceptions or protections defined in Statutes/Rules
    - Rights guaranteed by law
    - Interpretation of legal text in favor of the client
    - If precedents are scarce, argue based on **statutory intent** and **fairness**.
    """

    REBUTTAL_PROMPT = """
    You are {role}.
    Critique the opponent's argument logically.
    Opponent Argument:
    {opponent_argument}
    
    Language: English.
    """

    REFLEXION_PROMPT = """
    You are {role}.
    Refine your final argument.
    My Original Argument: {my_argument}
    Opponent's Rebuttal: {rebuttal}
    
    Language: English.
    """

    JUDGE_PROMPT = """
    You are a 'Friendly and Professional Legal Counsel' (친절하고 전문적인 변호사).
    Your goal is to explain complex legal issues to a non-expert client in an easy-to-understand and warm manner.
    
    [Input Data]
    1. Legal Situation: {scenario}
    2. Collected Legal Evidence: {evidence}
    3. Risk Analysis (Legal Concerns): {prosecutor_final}
    4. Rights Analysis (Legal Protections): {defense_final}

    [Tone & Style Guidelines]
    1. **Persona**: A trustworthy, warm, and highly competent lawyer.
    2. **Language**: Polite Korean (Honorifics, e.g., "검토해 보았습니다", "판단됩니다", "추천드립니다").
    3. **Clarity**: Avoid overly difficult legal jargon where possible, or explain it simply.
    4. **Empathy**: Acknowledge the user's situation before delivering the legal verdict.

    [Judgment Guidelines]
    1. **Statute-Centric**: Base your advice primarily on Acts, Decrees, and Rules.
    2. **Precedents**: Use precedents as supporting examples to explain *how* the law is applied.
    3. **Missing Evidence**: If no specific law is found, explain general legal principles instead of saying "I don't know."

    [Task]
    Provide a comprehensive legal advisory opinion.
    
    [Output JSON (Korean)]
    {{
        "위험도": "안전 | 주의 | 위험",
        "정확도": 0 ~ 100,
        "평가내용": "친절한 변호사 말투로 작성된 종합 자문 의견.\\n\\n안녕하세요, MIRI 법률 자문입니다. 의뢰하신 내용을 꼼꼼히 검토해 보았습니다.\\n\\n1. **상황 분석**: (의뢰인의 상황을 공감하며 요약)\\n2. **법적 검토**: (관련 법령과 행정규칙을 근거로 위법/적법 여부를 쉽게 설명)\\n3. **판례 경향**: (관련 판례가 있다면 '이런 경우에는 법원이 이렇게 판단하는 경향이 있습니다'라고 소개)\\n4. **대응 방안**: (의뢰인이 취할 수 있는 구체적인 행동이나 권리 구제 방안 제안)\\n5. **종합 결론**: (최종적인 조언과 함게 마무리 인사)",
        "인용근거": ["근로기준법 제23조", "대법원 20xx다xxxxx (참고)", ...],
        "평가결과": "부당해고 구제 신청 가능 | 계약서 수정 권고 | 법적 리스크 낮음 등 (짧은 요약)",
        "주요쟁점": ["해고 예고 의무 위반 여부", "정당한 해고 사유 존재 여부", ...]
    }}
    """

    async def _opening_statements(self, context: dict) -> Tuple[str, str]:
        print("    ⚔️ [Round 1] Opening Statements...")
        pros_task = llm_client.generate("", self.PROSECUTOR_PROMPT.format(**context), model="gpt-4o-mini")
        def_task = llm_client.generate("", self.DEFENSE_PROMPT.format(**context), model="gpt-4o-mini")
        
        pros_arg, def_arg = await asyncio.gather(pros_task, def_task)
        return pros_arg.strip(), def_arg.strip()

    async def _rebuttal_round(self, pros_arg: str, def_arg: str) -> Tuple[str, str]:
        print("    ⚔️ [Round 2] Rebuttal (Cross-Examination)...")
        p_rebut_task = llm_client.generate(self.REBUTTAL_PROMPT.format(role="Prosecutor", opponent_argument=def_arg), "", model="gpt-4o-mini")
        d_rebut_task = llm_client.generate(self.REBUTTAL_PROMPT.format(role="Defense Lawyer", opponent_argument=pros_arg), "", model="gpt-4o-mini")

        p_rebut, d_rebut = await asyncio.gather(p_rebut_task, d_rebut_task)
        return p_rebut.strip(), d_rebut.strip()

    async def _reflexion_round(self, pros_arg: str, def_arg: str, p_rebut: str, d_rebut: str) -> Tuple[str, str]:
        print("    🧠 [Round 3] Reflexion (Self-Correction)...")
        p_final_task = llm_client.generate(self.REFLEXION_PROMPT.format(role="Prosecutor", my_argument=pros_arg, rebuttal=d_rebut), "", model="gpt-4o-mini")
        d_final_task = llm_client.generate(self.REFLEXION_PROMPT.format(role="Defense Lawyer", my_argument=def_arg, rebuttal=p_rebut), "", model="gpt-4o-mini")

        p_final, d_final = await asyncio.gather(p_final_task, d_final_task)
        return p_final.strip(), d_final.strip()

    async def _render_verdict(self, scenario_text: str, p_final: str, d_final: str, evidence_text: str) -> RiskReport:
        print("    ⚖️ [Judge] Rendering Final Verdict...")
        prompt = self.JUDGE_PROMPT.format(
            scenario=scenario_text,
            prosecutor_final=p_final,
            defense_final=d_final,
            evidence=evidence_text
        )

        response = await llm_client.generate("", prompt, model="gpt-4o-mini", max_tokens=2048)

        try:
            data = json_repair.loads(response)

            # 한국어 필드명 매핑 (LLM이 한국어로 응답)
            risk_level = data.get('위험도', data.get('risk_level', 'Caution'))
            confidence = data.get('정확도', data.get('confidence_score', 0))
            verdict_text = data.get('평가내용', data.get('verdict', '평가 내용 없음'))
            cited = data.get('인용근거', data.get('cited_evidence', []))
            winning = data.get('평가결과', data.get('winning_side', '평가 중'))
            issues = data.get('주요쟁점', data.get('key_issues', []))

            # 인용 근거 포맷팅
            if isinstance(cited, list):
                citation_text = "\n".join(cited)
            else:
                citation_text = str(cited)

            # 위험도 영문 매핑 (프론트엔드 호환)
            risk_map = {'안전': 'Safe', '주의': 'Caution', '위험': 'Danger'}
            risk_level_en = risk_map.get(risk_level, risk_level)

            return RiskReport(
                verdict=risk_level_en,
                summary=f"[{winning}] {verdict_text} (정확도: {confidence}%)",
                citation=citation_text,
                key_issues=issues
            )
        except Exception as e:
            print(f"Judge Error: {e}")
            return RiskReport(
                verdict="Caution", 
                summary=f"평가 생성 중 오류가 발생했습니다: {e}", 
                citation="", 
                key_issues=["시스템 오류"]
            )

    async def execute(self, scenario: Scenario, evidence: LegalEvidence) -> RiskReport:
        evidence_text = "\n".join(evidence.relevant_laws)
        if not evidence_text: evidence_text = "No specific laws found."

        context = {
            "scenario": scenario.model_dump_json(),
            "evidence": evidence_text
        }

        # 1. Opening
        p_arg, d_arg = await self._opening_statements(context)
        print(f"      🗣️ Prosecutor: {p_arg[:100]}...")
        print(f"      🛡️ Defense: {d_arg[:100]}...")

        # 2. Rebuttal
        p_rebut, d_rebut = await self._rebuttal_round(p_arg, d_arg)

        # 3. Reflexion
        p_final, d_final = await self._reflexion_round(p_arg, d_arg, p_rebut, d_rebut)
        print(f"      📝 Pros Final: {p_final[:100]}...")
        print(f"      📝 Def Final: {d_final[:100]}...")

        # 4. Verdict
        return await self._render_verdict(scenario.model_dump_json(), p_final, d_final, evidence_text)
