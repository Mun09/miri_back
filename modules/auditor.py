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
    You are a 'Senior Legal Counsel' responsible for comprehensive legal advisory.
    
    [Input Data]
    1. Legal Situation: {scenario}
    2. Collected Legal Evidence: {evidence}
    3. Risk Analysis (Legal Concerns): {prosecutor_final}
    4. Rights Analysis (Legal Protections): {defense_final}

    [Judgment Guidelines]
    1. **Statute-Centric Approach**: Base your verdict PRIMARILY on Acts, Decrees, and Administrative Rules.
    2. **Precedents as Reference**: Use precedents ONLY to illustrate past applications. Do NOT treat them as absolute rules if the statute is clear.
    3. **Handling Missing Precedents**: If no specific precedent exists, DO NOT warn about "uncertainty" or "risk of bias". Instead, interpret the **Statutory Text** directly.
    4. **Specific Citation**: Always cite the specific Article/Clause of the Law (e.g., "Road Traffic Act Art. 54").

    [Task]
    Provide a comprehensive legal advisory opinion.
    - Adapt your analysis to the consultation type (Business, Contract, Dispute, Daily Life).
    - If the law is clear, give a definitive answer.

    [Output JSON (Korean)]
    {{
        "위험도": "안전 | 주의 | 위험",
        "정확도": 0 ~ 100,
        "평가내용": "종합 법률 자문 의견.\\n\\n1. 상황 분석: 핵심 쟁점 요약.\\n2. 법령 검토 (핵심): 관련 법령 및 행정규칙에 근거한 위법성/적법성 판단. (가장 중요)\\n3. 판례 경향 (참고): 관련 판례가 있다면 '참고적으로' 언급. 없으면 생략하거나 일반 원칙 서술.\\n4. 권리 및 구제: 의뢰인의 권리와 대응 방안.\\n5. 결론: 최종 의견 및 행동 지침.",
        "인용근거": ["법령명 제O조", "판례: 20xx다xxxxx (참고)", ...],
        "평가결과": "규제 샌드박스 신청 권장 | 법적 대응 필요 | 계약 해제 가능 | 손해배상청구 검토 등",
        "주요쟁점": ["쟁점1: [행위] -> [법령] 위반 여부", ...]
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
