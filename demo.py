"""
MIRI Demo - LangChain 기반 법률 자문 AI 데모 실행
"""
import asyncio
import json
from pipeline import run_analysis_stream

async def run_demo():
    print("✅ LangGraph 기반 다중 에이전트 시스템 (Structurer -> Investigator -> Auditor) 초기화.")
    print("✅ 의사결정 트리(Roadmap), What-If 기능 탑재 완료")

    user_input = "동물용 신약(건강기능식품)을 개발해서 판매하고 싶습니다. 기존 인체용과 무엇이 다른가요?"
    what_ifs = ["유전자 변형 원료(GMO) 포함 여부"]
    
    print(f"\n법률 상담 예시: {user_input}")
    print(f"가정(What-If) 변수: {what_ifs}")

    print("\n--- Streaming Output ---")
    async for chunk in run_analysis_stream(user_input, what_ifs):
        data = json.loads(chunk)
        if data['type'] == 'log':
            print(f"{data['message']}")
        elif data['type'] == 'result':
            result = data['data']
            print("\n" + "="*50)
            print("   📢 [FINAL VERDICT & ROADMAP] REPORT")
            print("="*50)
            
            risk = result.get("risk_evaluation", {})
            print(f"\n🚦 리스크 스코어: {risk.get('score', 'N/A')}")
            print(f"📝 평가 근거: {risk.get('rationale', 'N/A')}")
            
            print(f"\n🗺️ 규제 통과 로드맵 (Decision Tree):")
            for step in result.get("roadmap", []):
                print(f"  [단계 {step['phase']}] {step['title']} (예상 소요: {step['estimated_time']})")
                for action in step.get('action_items', []):
                    print(f"    - 제출처: {action['submission_agency']}")
                    print(f"    - 필요 서류: {', '.join(action['required_documents'])}")
            
            print(f"\n🔄 추천 What-If 시나리오 변수:")
            for w in result.get("what_ifs", []):
                print(f"  - {w['variable_name']}: {w['description']}")
                
            print(f"\n⚖️ 도메인 교차 비교 (Cross-Domain):")
            for c in result.get("cross_domains", []):
                print(f"  - {c['source_domain']} vs {c['target_domain']}")
                print(f"    > 주무 부처: {c['agency_mapping']}")
                print(f"    > 차이점: {c['key_differences']}")

if __name__ == '__main__':
    asyncio.run(run_demo())
