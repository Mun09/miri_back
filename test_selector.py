#!/usr/bin/env python3
"""
Selector 함수 단독 테스트
"""
import asyncio
import sys
import os
from dotenv import load_dotenv

# 현재 디렉토리 추가
sys.path.insert(0, os.path.dirname(__file__))

load_dotenv()
from miri import llm_client, Investigator

async def test_selector():
    """Selector 함수만 테스트"""
    
    # 실제 검색 시뮬레이션 - 환전 플랫폼 키워드로 검색
    investigator = Investigator()
    
    action_text = "외국인 관광객이 달러를 앱에서 토큰으로 환전하고, 현지 상점에서 토큰으로 결제"
    
    # 실제 API 호출하여 후보 수집
    print("1️⃣ 키워드 생성 테스트")
    print(f"Action: {action_text}\n")
    
    keywords = await investigator._expand_query(
        type('AtomicAction', (), {'action': action_text, 'object': '환전 플랫폼'})()
    )
    print(f"생성된 키워드: {keywords}\n")
    
    # 법령 검색
    print("2️⃣ 법령 검색 테스트")
    from miri import law_api
    
    candidates = []
    for kw in keywords[:3]:  # 처음 3개만
        results = await law_api.search_list('eflaw', kw, display=10)
        print(f"  '{kw}' 검색 결과: {len(results)}건")
        
        for item in results[:5]:  # 각 키워드당 5개
            name = item.get('법령명한글')
            if name:
                print(f"    - {name}")
                candidates.append(item)
    
    print(f"\n총 {len(candidates)}개 후보 수집됨\n")
    
    # Selector 테스트
    print("3️⃣ Selector 테스트")
    print(f"Action: {action_text}")
    print(f"후보 수: {len(candidates)}\n")
    
    selected = await investigator._select_best_candidates(candidates, action_text)
    
    print(f"\n✅ Selector 결과: {len(selected)}개 선택됨")
    for i, item in enumerate(selected, 1):
        name = item.get('법령명한글') or item.get('행정규칙명')
        print(f"  {i}. {name}")

if __name__ == "__main__":
    asyncio.run(test_selector())
