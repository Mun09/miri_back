"""
Pipeline Module - Analysis Pipeline for MIRI Legal Advisory System
분석 파이프라인 모듈
"""
import json
import asyncio
from typing import AsyncGenerator, Dict, Any

from config import IS_TEST, MOCK_RESULT
from modules import Structurer, Investigator, AdversarialDebate


async def run_analysis_stream(user_input: str) -> AsyncGenerator[str, None]:
    """API Streaming Response Generator"""
    queue = asyncio.Queue()

    async def log_callback(msg: str):
        await queue.put(json.dumps({"type": "log", "message": msg}) + "\n")

    async def worker():
        try:
            # [TEST MODE CHECK]
            if IS_TEST:
                await log_callback("⚠️ [TEST MODE] AI 토큰을 사용하지 않고 테스트 데이터를 로드합니다.")
                await asyncio.sleep(1.0)
                
                await log_callback("비즈니스 모델 구조화 (Mocking)...")
                await asyncio.sleep(1.0)
                await log_callback(f"시나리오: {MOCK_RESULT['scenario']['name']}")
                await asyncio.sleep(1.0)
                
                await log_callback("법령 데이터베이스 검색 (Skipped for Test)...")
                await asyncio.sleep(1.0)
                
                await log_callback("✅ 테스트 분석 완료!")
                await queue.put(json.dumps({"type": "result", "data": MOCK_RESULT}) + "\n")
                return

            # Init Agents
            structurer = Structurer()
            investigator = Investigator()
            auditor = AdversarialDebate()

            await log_callback("분석 모듈 초기화 완료.")

            # 1. Structure
            await log_callback("법률 상담 케이스 구조화 및 분석 중...")
            model = await structurer.execute(user_input)
            await log_callback(f"케이스 분석 완료: {model.project_name}")
            
            # 2. Extract Scenario (Direct from User Input)
            await log_callback("사용자 질의 핵심 법률 행위 추출 중...")
            
            # [Optimization] Simulator 제거 -> Direct Extraction
            # 사용자의 의도를 왜곡하지 않기 위해 Simulator를 거치지 않고 바로 Action을 추출합니다.
            scenario_prompt = f"""
            Extract the core legal actions from the user's query.
            Do NOT add fictional details or assumptions. Strive for factual accuracy based ONLY on the input.
            
            User Input: "{user_input}"
            
            Output JSON Schema:
            {{
                "name": "Scenario Name (Short)",
                "type": "General | Business | Criminal | Civil",
                "actions": [
                    {{
                        "actor": "Primary Subject (e.g., User, Employer, Driver)",
                        "action": "Legal Action (e.g., firing without notice, hit-and-run)",
                        "object": "Target Object (e.g., Employee, Pedestrian)"
                    }}
                ]
            }}
            """
            from llm_client import llm_client # Lazy import
            import json_repair
            from models import Scenario
            
            try:
                sc_res = await llm_client.generate(scenario_prompt, "Extract legal actions.", model="gpt-4o-mini", max_tokens=256)
                sc_data = json_repair.loads(sc_res)
                main_scenario = Scenario(**sc_data)
            except Exception as e:
                print(f"Scenario Extraction Error: {e}")
                # Fallback
                main_scenario = Scenario(
                    name="Direct Query", 
                    type="General", 
                    actions=[{"actor": "User", "action": user_input, "object": "Legal Issue"}]
                )

            await log_callback(f"시나리오 추출 완료: {main_scenario.name}")

            # 3. Investigate (Pass Log Callback)
            await log_callback("법령 데이터베이스 검색 및 심층 분석 수행 중...")
            evidence, reviews = await investigator.execute(main_scenario, on_log=log_callback)
            await log_callback(f"법적 검토 완료: {len(reviews)}건의 법령 및 판례 분석")
            
            # 4. Audit
            await log_callback("법률 전문가 다각도 분석 및 종합 검토 중...")
            final_report = await auditor.execute(main_scenario, evidence)
            await log_callback("최종 법률 자문 보고서 생성 완료.")
            
            # 5. Extract Unique References
            references = []
            seen_urls = set()
            for r in reviews:
                if r.url and r.url not in seen_urls:
                    references.append({"title": f"{r.law_name} {r.key_clause}", "url": r.url})
                    seen_urls.add(r.url)

            result_data = {
                "business_model": json.loads(model.model_dump_json()),
                "scenario": json.loads(main_scenario.model_dump_json()),
                "evidence": [json.loads(r.model_dump_json()) for r in reviews],
                "verdict": json.loads(final_report.model_dump_json()),
                "references": references
            }
            
            await queue.put(json.dumps({"type": "result", "data": result_data}) + "\n")

        except Exception as e:
            print(f"Worker Error: {e}")
            await queue.put(json.dumps({"type": "error", "message": str(e)}) + "\n")
        finally:
            await queue.put(None)  # Sentinel

    # Start worker on background
    asyncio.create_task(worker())

    # Consume logs
    while True:
        item = await queue.get()
        if item is None:
            break
        yield item


async def run_analysis(user_input: str) -> Dict[str, Any]:
    """Legacy wrapper if needed, or for testing"""
    result = None
    async for chunk in run_analysis_stream(user_input):
        data = json.loads(chunk)
        if data["type"] == "result":
            result = data["data"]
    return result
