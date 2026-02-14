"""
Structurer Module - Legal Consultation Case Structuring
"""
import json_repair
from models import BusinessModel
from llm_client import llm_client


class Structurer:
    SYSTEM_PROMPT = """
    You are an expert 'Legal Consultation Structurer' for a comprehensive legal advisory service.
    Analyze the user's situation (business idea, contract, dispute, daily legal issue, etc.) and structure it.
    
    Determine the type of legal consultation:
    - "사업 아이디어": New business model requiring regulatory review
    - "계약/거래": Contract-related questions
    - "분쟁/소송": Disputes, lawsuits, or legal conflicts
    - "일상생활": Daily life legal questions (employment, real estate, consumer rights, etc.)
    - "기타 법률자문": General legal consultation
    
    Output MUST be a JSON object following this schema:
    {
        "consultation_type": "사업 아이디어 | 계약/거래 | 분쟁/소송 | 일상생활 | 기타 법률자문",
        "project_name": "상담 케이스명 (간단한 제목)",
        "case_summary": "상황 요약 (2-3문장)",
        "stakeholders": {
            "parties_involved": "관련 당사자들 (예: 사용자, 상대방, 제3자 등)",
            "roles": ["각 당사자의 역할"]
        },
        "key_elements": {
            "money_or_assets": "금전/재산 관련 사항 (있는 경우)",
            "data_or_information": ["개인정보 또는 중요 정보 관련 사항"],
            "actions_or_services": "주요 행위 또는 서비스 내용"
        },
        "regulatory_tags": ["예상되는 관련 법률 키워드 (예: 민법, 형법, 개인정보보호법, 근로기준법 등)"]
    }
    """
    
    async def execute(self, user_input: str) -> BusinessModel:
        print("\n[1] Structuring Legal Consultation Case...")
        response = await llm_client.generate(self.SYSTEM_PROMPT, user_input, model="gpt-4o-mini")
        try:
            return BusinessModel(**json_repair.loads(response))
        except Exception as e:
            print(f"Structurer Error: {e}")
            print(f"Raw: {response}")
            raise e
