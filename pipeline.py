"""
Pipeline Module - Analysis Pipeline for MIRI Legal Advisory System using LangGraph
"""
import json
import asyncio
from typing import AsyncGenerator, Dict, Any

from config import IS_TEST, MOCK_RESULT
from modules.graph_agent import miri_graph, MiriState

async def run_analysis_stream(user_input: str, what_ifs: list = None, thread_id: str = "default_thread") -> AsyncGenerator[str, None]:
    """API Streaming Response Generator using LangGraph"""
    what_ifs = what_ifs or []
    initial_state = {
        "user_input": user_input,
        "what_if_toggles": what_ifs,
    }
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        # [TEST MODE CHECK]
        if IS_TEST:
            yield json.dumps({"type": "log", "message": "⚠️ [TEST MODE] AI 토큰을 사용하지 않고 테스트 데이터를 로드합니다."}) + "\n"
            await asyncio.sleep(1.0)
            yield json.dumps({"type": "result", "data": MOCK_RESULT}) + "\n"
            return
            
        async for event in miri_graph.astream(initial_state, config=config):
            for node_name, node_state in event.items():
                if node_name == "structurer":
                    intent = node_state.get("current_intent", "modify_roadmap")
                    if intent == "modify_roadmap":
                        yield json.dumps({"type": "log", "message": "✅ [분석] 사업 모델 수정 및 구조화 진행 중..."}) + "\n"
                    else:
                        yield json.dumps({"type": "log", "message": "💬 [질의] 단순 질문으로 파악되었습니다. 답변을 생성합니다..."}) + "\n"
                        
                elif node_name == "qa_node":
                    # Emit chat message event
                    chat_msg = node_state.get("chat_response", "이해했습니다.")
                    yield json.dumps({"type": "chat_message", "message": chat_msg}) + "\n"
                    
                elif node_name == "investigator":
                    yield json.dumps({"type": "log", "message": "🔬 [조사] 관련 법령, 부처, 증빙 서류를 새롭게 검색하고 정리합니다..."}) + "\n"
                    
                elif node_name == "auditor":
                    yield json.dumps({"type": "log", "message": "⚖️ [자문] 로드맵과 리스크 스코어를 최신 상태로 갱신했습니다."}) + "\n"
                    
                    # Construct Final Result
                    bm = node_state.get("business_model")
                    risk = node_state.get("risk_evaluation")
                    
                    result_data = {
                        "business_model": bm.model_dump() if bm else {},
                        "what_ifs": [w.model_dump() for w in node_state.get("what_ifs", [])],
                        "cross_domains": [c.model_dump() for c in node_state.get("cross_domains", [])],
                        "roadmap": [r.model_dump() for r in node_state.get("roadmap", [])],
                        "risk_evaluation": risk.model_dump() if risk else {},
                        "references": [ref.model_dump() for ref in node_state.get("references", [])]
                    }
                    
                    # We also send the chat response so the frontend knows the roadmap was updated
                    chat_msg = node_state.get("chat_response", "로드맵이 업데이트되었습니다.")
                    yield json.dumps({"type": "chat_message", "message": chat_msg}) + "\n"
                    yield json.dumps({"type": "result", "data": result_data}) + "\n"
                    
    except Exception as e:
        print(f"Graph Execution Error: {e}")
        yield json.dumps({"type": "error", "message": str(e)}) + "\n"

async def run_analysis(user_input: str, what_ifs: list = None) -> Dict[str, Any]:
    """Legacy wrapper if needed, or for testing"""
    result = None
    async for chunk in run_analysis_stream(user_input, what_ifs):
        data = json.loads(chunk)
        if data["type"] == "result":
            result = data["data"]
    return result
