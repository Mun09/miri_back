"""
Pipeline Module - Analysis Pipeline for MIRI Legal Advisory System using LangGraph
"""
import json
import asyncio
from typing import AsyncGenerator, Dict, Any

from langchain_core.messages import HumanMessage

from config import IS_TEST, MOCK_RESULT
from modules.graph_agent import miri_graph, MiriState, auditor_node


def _build_result_data(accumulated: Dict[str, Any]) -> Dict[str, Any]:
    """Build the final result_data dict from accumulated state."""
    bm = accumulated.get("business_model")
    risk = accumulated.get("risk_evaluation")
    return {
        "business_model": bm.model_dump() if bm else {},
        "what_ifs": [w.model_dump() for w in accumulated.get("what_ifs", [])],
        "cross_domains": [c.model_dump() for c in accumulated.get("cross_domains", [])],
        "roadmap": [r.model_dump() for r in accumulated.get("roadmap", [])],
        "risk_evaluation": risk.model_dump() if risk else {},
        "references": [ref.model_dump() for ref in accumulated.get("references", [])],
    }


async def run_analysis_stream(
    user_input: str,
    what_ifs: list = None,
    thread_id: str = "default_thread",
    is_whatif_only: bool = False,
) -> AsyncGenerator[str, None]:
    """API Streaming Response Generator using LangGraph"""
    what_ifs = what_ifs or []
    config = {"configurable": {"thread_id": thread_id}}

    try:
        # ── TEST MODE ──
        if IS_TEST:
            yield json.dumps({"type": "log", "message": "⚠️ [TEST MODE] AI 토큰을 사용하지 않고 테스트 데이터를 로드합니다."}) + "\n"
            await asyncio.sleep(1.0)
            yield json.dumps({"type": "result", "data": MOCK_RESULT}) + "\n"
            return

        # ── WHAT-IF SHORTCUT: bypass full pipeline, re-run auditor only ──
        if is_whatif_only:
            yield json.dumps({"type": "log", "message": "🔄 [What-If] 시나리오 변수만 업데이트합니다..."}) + "\n"

            try:
                current_state = await miri_graph.aget_state(config)

                if current_state and current_state.values:
                    saved_state = dict(current_state.values)
                    saved_state["what_if_toggles"] = what_ifs
                    saved_state["user_input"] = user_input or saved_state.get("user_input", "")

                    auditor_result = await auditor_node(saved_state)
                    saved_state.update(auditor_result)

                    result_data = _build_result_data(saved_state)

                    chat_msg = auditor_result.get("chat_response", "What-If 시나리오가 반영되어 로드맵이 갱신되었습니다.")
                    yield json.dumps({"type": "log", "message": "⚖️ [자문] What-If 기반 로드맵 재생성 완료."}) + "\n"
                    yield json.dumps({"type": "chat_message", "message": chat_msg}) + "\n"
                    yield json.dumps({"type": "result", "data": result_data}) + "\n"
                else:
                    yield json.dumps({"type": "error", "message": "기존 분석 결과가 없습니다. 먼저 전체 분석을 실행해 주세요."}) + "\n"
            except Exception as e:
                print(f"What-If Shortcut Error: {e}")
                yield json.dumps({"type": "error", "message": f"What-If 업데이트 오류: {str(e)}"}) + "\n"
            return

        # ── FULL PIPELINE ──
        initial_state = {
            "user_input": user_input,
            "what_if_toggles": what_ifs,
            "chat_history": [HumanMessage(content=user_input)],
        }

        # Accumulate state across node events (fixes bug where auditor event
        # doesn't contain business_model/what_ifs/cross_domains from structurer)
        accumulated_state: Dict[str, Any] = {}

        async for event in miri_graph.astream(initial_state, config=config):
            for node_name, node_state in event.items():
                # Merge this node's output into accumulated state
                accumulated_state.update(node_state)

                # Emit any errors from this node
                for err in node_state.get("errors", []):
                    yield json.dumps({"type": "error_log", "message": err}) + "\n"

                if node_name == "intent_classifier":
                    intent = node_state.get("current_intent", "modify_roadmap")
                    if intent == "modify_roadmap":
                        yield json.dumps({"type": "log", "message": "✅ [분석] 사업 모델 수정 요청으로 파악됨. 구조화 진행 중..."}) + "\n"
                    else:
                        yield json.dumps({"type": "log", "message": "💬 [질의] 단순 질문으로 파악됨. 답변을 생성합니다..."}) + "\n"

                elif node_name == "structurer":
                    yield json.dumps({"type": "log", "message": "📐 [구조화] 사업 모델을 업데이트합니다..."}) + "\n"

                elif node_name == "qa_node":
                    chat_msg = node_state.get("chat_response", "이해했습니다.")
                    yield json.dumps({"type": "chat_message", "message": chat_msg}) + "\n"

                elif node_name == "investigator":
                    yield json.dumps({"type": "log", "message": "🔬 [조사] 관련 법령, 부처, 증빙 서류를 검색하고 정리합니다..."}) + "\n"

                elif node_name == "auditor":
                    yield json.dumps({"type": "log", "message": "⚖️ [자문] 로드맵과 리스크 스코어를 갱신했습니다."}) + "\n"

                elif node_name == "validator":
                    # Check if validator routed to END or back to investigator
                    evidence = accumulated_state.get("research_evidence")
                    has_evidence = bool(evidence and getattr(evidence, "items", None) and len(evidence.items) > 0)
                    references = accumulated_state.get("references", [])
                    roadmap = accumulated_state.get("roadmap", [])
                    retry_count = node_state.get("retry_count", 0)

                    validation_passed = has_evidence and bool(references) and bool(roadmap)

                    if validation_passed or retry_count > 1:
                        yield json.dumps({"type": "log", "message": "✅ [검증] 결과가 충분합니다. 최종 결과를 전달합니다."}) + "\n"

                        result_data = _build_result_data(accumulated_state)
                        chat_msg = accumulated_state.get("chat_response", "로드맵이 업데이트되었습니다.")
                        yield json.dumps({"type": "chat_message", "message": chat_msg}) + "\n"
                        yield json.dumps({"type": "result", "data": result_data}) + "\n"
                    else:
                        yield json.dumps({"type": "log", "message": "🔄 [검증] 결과가 불충분합니다. 조사를 재시도합니다..."}) + "\n"

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
