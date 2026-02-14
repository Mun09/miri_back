"""
Configuration and Constants for MIRI Legal Advisory System
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Maximum number of total documents to analyze in detail (Final Limit)
MAX_ANALYSIS_DOCS = 20

# Maximum number of search results per API call (Law, Prec, etc.)
MAX_SEARCH_RESULTS_PER_SOURCE = 10

# Test Mode Configuration
api_key_check = os.getenv("OPENAI_API_KEY")
IS_TEST_ENV = os.getenv("IS_TEST", "False").lower() == "true"

if not api_key_check and not IS_TEST_ENV:
    print("⚠️ Warning: OPENAI_API_KEY not found. Switching to TEST MODE automatically.")
    IS_TEST = True
else:
    IS_TEST = IS_TEST_ENV or False

# Mock result for test mode
MOCK_RESULT = {
    "business_model": {
        "consultation_type": "사업 아이디어",
        "project_name": "법률 상담 케이스 예시 (TEST MODE)",
        "case_summary": "이 케이스는 법률 자문 AI 시스템의 테스트 모드용 샘플 데이터입니다. 실제 API 토큰 없이도 시스템의 전체 흐름을 확인할 수 있도록 구성되었습니다.",
        "stakeholders": {
            "parties_involved": "당사자 A, 당사자 B, 제3자",
            "roles": ["서비스 제공자", "이용자", "중개 플랫폼"]
        },
        "key_elements": {
            "money_or_assets": "금전적 거래 또는 자산 이동 관련",
            "data_or_information": ["개인정보", "거래정보"],
            "actions_or_services": "서비스 제공 및 이용 행위"
        },
        "regulatory_tags": ["민법", "상법", "개인정보보호법", "전자상거래법"]
    },
    "scenario": {
        "name": "테스트 시나리오: 서비스 이용 과정",
        "type": "Main",
        "actions": [
            {"actor": "당사자 A", "action": "서비스를 제공하거나 계약을 체결함", "object": "서비스/계약"},
            {"actor": "당사자 B", "action": "서비스를 이용하거나 대금을 지급함", "object": "금전/서비스"}
        ]
    },
    "evidence": [
        {
            "law_name": "민법",
            "key_clause": "제390조 (채무불이행과 손해배상)",
            "status": "Conditional",
            "summary": "채무자가 채무의 내용에 좇은 이행을 하지 아니한 때에는 채권자는 손해배상을 청구할 수 있음.",
            "url": "http://www.law.go.kr"
        },
        {
            "law_name": "개인정보 보호법",
            "key_clause": "제15조 (개인정보의 수집·이용)",
            "status": "Conditional",
            "summary": "개인정보처리자는 정보주체의 동의를 받거나 법률에 특별한 규정이 있는 경우에만 개인정보를 수집·이용할 수 있음.",
            "url": "http://www.law.go.kr"
        }
    ],
    "verdict": {
        "verdict": "Caution",
        "summary": "[TEST MODE] 이것은 테스트 모드 결과입니다. 실제 법률 자문을 원하시면 OpenAI API 키를 설정해주세요. 본 시스템은 사업 아이디어, 계약 검토, 분쟁 상담, 일상생활 법률 문제 등 다양한 법률 자문을 제공합니다.",
        "citation": "민법, 개인정보 보호법, 기타 관련 법령",
        "key_issues": [
            "테스트 모드로 실행 중 - 실제 AI 분석 없이 샘플 데이터 반환",
            "OpenAI API 키를 환경변수에 설정하면 실제 법률 분석 가능",
            "사업/계약/분쟁/일상생활 등 모든 법률 상담 지원"
        ]
    },
    "references": [
        {"title": "민법 제390조", "url": "http://www.law.go.kr"},
        {"title": "개인정보 보호법 제15조", "url": "http://www.law.go.kr"}
    ]
}
