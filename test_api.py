#!/usr/bin/env python3
"""
MIRI 백엔드 API 테스트 스크립트
"""
import requests
import json
import time

API_URL = "http://localhost:8000/analyze"

TEST_CASES = [
    {
        "name": "환전 플랫폼 (문제 케이스)",
        "idea": "외국인 관광객이 달러를 현지 상점에서 사용할 수 있도록, 달러를 앱에서 토큰으로 환전하고(90% 환율 적용), 현지 상점에서 토큰으로 결제할 수 있는 플랫폼"
    },
    {
        "name": "부동산 중개 플랫폼",
        "idea": "개인이 자신의 부동산을 플랫폼에 등록하고, 임대인과 직거래할 수 있는 P2P 부동산 중개 플랫폼"
    }
]

def test_analysis(test_case):
    """단일 테스트 케이스 실행"""
    print(f"\n{'='*80}")
    print(f"🧪 테스트: {test_case['name']}")
    print(f"{'='*80}")
    print(f"📝 아이디어: {test_case['idea']}")
    print(f"\n⏳ 분석 시작...")
    
    start_time = time.time()
    
    try:
        response = requests.post(
            API_URL,
            json={"idea": test_case['idea']},
            stream=True,
            timeout=300
        )
        
        if response.status_code != 200:
            print(f"❌ 오류: HTTP {response.status_code}")
            print(response.text)
            return False
        
        logs = []
        result = None
        
        # 스트리밍 응답 처리
        for line in response.iter_lines():
            if line:
                try:
                    data = json.loads(line.decode('utf-8'))
                    
                    if data.get('type') == 'log':
                        log_msg = data.get('message', '')
                        logs.append(log_msg)
                        
                        # 중요 로그만 출력
                        if any(keyword in log_msg for keyword in ['[Selector]', '선택:', '발견', 'Chunking', 'Index Scan']):
                            print(f"  📊 {log_msg}")
                    
                    elif data.get('type') == 'result':
                        result = data.get('data')
                        
                except json.JSONDecodeError:
                    continue
        
        elapsed = time.time() - start_time
        
        print(f"\n{'='*80}")
        print(f"✅ 분석 완료 ({elapsed:.1f}초)")
        print(f"{'='*80}")
        
        if result:
            print(f"\n🎯 결과 요약:")
            print(f"  - 위험도: {result.get('verdict', 'N/A')}")
            print(f"  - 요약: {result.get('summary', 'N/A')[:100]}...")
            
            evidence = result.get('evidence', [])
            print(f"  - 발견된 증거: {len(evidence)}건")
            
            if evidence:
                print(f"\n📋 주요 법령:")
                for i, ev in enumerate(evidence[:5], 1):
                    print(f"    {i}. {ev.get('law_name', 'N/A')}")
                    print(f"       조항: {ev.get('key_clause', 'N/A')}")
                    print(f"       상태: {ev.get('status', 'N/A')}")
            else:
                print(f"  ⚠️ 관련 법령을 찾지 못했습니다!")
        else:
            print(f"❌ 결과 없음")
            
        # 검색 통계
        selector_logs = [log for log in logs if 'Selector' in log]
        chunking_logs = [log for log in logs if 'Chunking' in log]
        
        print(f"\n📈 통계:")
        print(f"  - Selector 호출: {len(selector_logs)}회")
        print(f"  - Chunking 발생: {len(chunking_logs)}회")
        
        return True
        
    except requests.exceptions.Timeout:
        print(f"❌ 타임아웃 (300초 초과)")
        return False
    except Exception as e:
        print(f"❌ 오류: {e}")
        return False

def main():
    print(f"\n{'#'*80}")
    print(f"# MIRI 백엔드 API 자동 테스트")
    print(f"# API: {API_URL}")
    print(f"# 테스트 케이스: {len(TEST_CASES)}개")
    print(f"{'#'*80}")
    
    # 서버 상태 확인
    try:
        health = requests.get("http://localhost:8000/health", timeout=5)
        if health.status_code == 200:
            print(f"✅ 서버 연결 성공")
        else:
            print(f"⚠️ 서버 응답 이상: {health.status_code}")
    except:
        print(f"❌ 서버에 연결할 수 없습니다. uvicorn이 실행 중인지 확인하세요.")
        return
    
    # 테스트 실행
    results = []
    for test_case in TEST_CASES:
        success = test_analysis(test_case)
        results.append((test_case['name'], success))
        
        # 다음 테스트 전 대기
        if test_case != TEST_CASES[-1]:
            print(f"\n⏸️  5초 대기 후 다음 테스트...")
            time.sleep(5)
    
    # 최종 리포트
    print(f"\n{'#'*80}")
    print(f"# 테스트 결과 요약")
    print(f"{'#'*80}")
    
    for name, success in results:
        status = "✅ 성공" if success else "❌ 실패"
        print(f"{status} - {name}")
    
    success_count = sum(1 for _, s in results if s)
    print(f"\n총 {len(results)}개 중 {success_count}개 성공")

if __name__ == "__main__":
    main()
