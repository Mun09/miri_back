"""
MIRI Demo - 법률 자문 AI 데모 실행
"""
import asyncio
import json
from pipeline import run_analysis_stream


async def run_demo():
    print("✅ Investigator Updated with Detailed Logging & Critic Loop.")
    print("✅ Adversarial Debate System (Prosecutor vs Defense vs Judge) Initialized.")
    print("✅ 법률 자문 AI 시스템 '미리(MIRI)' - 모든 법률 상담에 대응 가능")

    user_input = "회사에서 갑자기 해고 통보를 받았는데, 해고 예고 기간도 없고 해고 사유도 명확하지 않습니다. 부당해고인지 알고 싶습니다."
    print(f"\n법률 상담 예시: {user_input}")
    print("(다른 예시: 사업 아이디어, 계약 분쟁, 임대차 문제, 소비자 피해, 교통사고 등)")

    print("\n--- Streaming Output ---")
    async for chunk in run_analysis_stream(user_input):
        data = json.loads(chunk)
        if data['type'] == 'log':
            print(f"LOG: {data['message']}")
        elif data['type'] == 'result':
            result = data['data']
            print("\n" + "="*50)
            print("   📢 [FINAL VERDICT] REPORT")
            print("="*50)
            
            verdict = result["verdict"]
            print(f"\n🏆 판결: {verdict.get('verdict')}")
            print(f"📝 요약: {verdict.get('summary')}")
            print(f"\n⚖️ 주요 쟁점:")
            for issue in verdict.get('key_issues', []):
                print(f" - {issue}")
                
            print(f"\n🔗 참고 문헌:")
            for ref in result["references"]:
                print(f" - {ref['title']}: {ref['url']}")


if __name__ == '__main__':
    asyncio.run(run_demo())
