import operator
from typing import TypedDict, List, Dict, Any, Optional, Literal, Annotated
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field

from config import IS_TEST, MOCK_RESULT
from models import (
    BusinessModel, WhatIfTrigger, CrossDomainMapping,
    RoadmapStep, RiskEvaluation, ActionItem,
    EvidenceItem, ResearchEvidence, ReferenceItem,
)
from modules.tools import get_investigator_tools


# ─────────────────────────────────────────────
# 1. State Definition
# ─────────────────────────────────────────────
class MiriState(TypedDict):
    user_input: str
    chat_history: Annotated[list[BaseMessage], add_messages]
    what_if_toggles: List[str]

    # Extractions
    business_model: Optional[BusinessModel]
    what_ifs: List[WhatIfTrigger]
    cross_domains: List[CrossDomainMapping]

    # Routing
    current_intent: str  # "modify_roadmap" or "ask_question"
    chat_response: str

    # Research (structured)
    research_evidence: Optional[ResearchEvidence]

    # Final Output
    roadmap: List[RoadmapStep]
    risk_evaluation: Optional[RiskEvaluation]
    references: List[Any]

    # Error tracking & retry
    errors: Annotated[List[str], operator.add]
    retry_count: int


# ─────────────────────────────────────────────
# 2. Helper: format recent chat history
# ─────────────────────────────────────────────
def _format_chat_history(state: MiriState, n: int = 6) -> str:
    history = state.get("chat_history", [])
    recent = history[-n:] if len(history) > n else history
    if not recent:
        return "None"
    lines = []
    for msg in recent:
        role = "User" if msg.type == "human" else "Assistant"
        lines.append(f"{role}: {msg.content[:300]}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# 3. Nodes
# ─────────────────────────────────────────────

# ── 3-1. Intent Classifier (lightweight, gpt-4o-mini) ──
async def intent_classifier_node(state: MiriState) -> Dict[str, Any]:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    class IntentOutput(BaseModel):
        intent: Literal["modify_roadmap", "ask_question"] = Field(
            description="Is the user modifying the business model/roadmap or just asking a question?"
        )

    structured_llm = llm.with_structured_output(IntentOutput)

    existing_bm = state.get("business_model")
    bm_summary = ""
    if existing_bm:
        bm_summary = f"Project: {existing_bm.project_name}, Tags: {existing_bm.regulatory_tags}"

    history_text = _format_chat_history(state, n=4)

    prompt = f"""
    Classify the user's intent. This is a legal advisory system for Korean entrepreneurs.

    Recent conversation:
    {history_text}

    Current business model: {bm_summary if bm_summary else 'None yet'}
    User input: {state['user_input']}

    Rules:
    - 'modify_roadmap': User is adding facts, features, constraints, or changing the business model. Also use this if no business model exists yet.
    - 'ask_question': User is asking about existing roadmap, general law, or a clarification question.
    - If this is the FIRST message (no business model exists), ALWAYS classify as 'modify_roadmap'.
    """

    try:
        result = await structured_llm.ainvoke([SystemMessage(content=prompt)])
        return {"current_intent": result.intent}
    except Exception as e:
        print(f"Intent Classifier Error: {e}")
        return {
            "current_intent": "modify_roadmap",
            "errors": [f"[의도 분류 오류] {type(e).__name__}: {str(e)[:200]}"],
        }


# ── 3-2. Structurer (full extraction, gpt-4o-mini) ──
async def structurer_node(state: MiriState) -> Dict[str, Any]:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    class StructurerOutput(BaseModel):
        business_model: BusinessModel = Field(description="The updated or newly created Business Model.")
        what_ifs: List[WhatIfTrigger]
        cross_domains: List[CrossDomainMapping]

    structured_llm = llm.with_structured_output(StructurerOutput)

    existing_bm = state.get("business_model")
    bm_json = existing_bm.model_dump_json() if existing_bm else "None (This is the first message)"
    history_text = _format_chat_history(state, n=6)

    prompt = f"""
    You are an expert 'Legal Consultation Refiner & Structurer'.
    Update the Business Model based on the user's latest input.
    IMPORTANT: NEVER drop existing constraints unless explicitly told. We are progressively building this model.
    ALL output string fields MUST be strictly in KOREAN (한국어).

    Recent Conversation History:
    {history_text}

    User Input: {state['user_input']}
    Active What-Ifs: {state.get('what_if_toggles', [])}

    Existing Business Model:
    {bm_json}

    Instructions:
    - Always merge new facts into the Existing Business Model. NEVER perform a hard reset.
    - Consider the conversation history to understand if the user is refining a previous request.
    - Update BusinessModel, WhatIfTriggers, and CrossDomainMappings accordingly.
    """

    try:
        result = await structured_llm.ainvoke([SystemMessage(content=prompt)])
        return {
            "business_model": result.business_model,
            "what_ifs": result.what_ifs,
            "cross_domains": result.cross_domains,
            "chat_history": [AIMessage(content="[사업 모델 업데이트 완료]")],
        }
    except Exception as e:
        print(f"Structurer Error: {e}")
        return {
            "errors": [f"[구조화 단계 오류] {type(e).__name__}: {str(e)[:200]}"],
        }


# ── 3-3. Router ──
def router_logic(state: MiriState) -> str:
    if state.get("current_intent") == "ask_question":
        return "qa_node"
    return "structurer"


# ── 3-4. QA Node (gpt-4o-mini + ReAct) ──
async def qa_node(state: MiriState) -> Dict[str, Any]:
    from langgraph.prebuilt import create_react_agent

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    tools = get_investigator_tools()
    agent = create_react_agent(llm, tools)

    bm = state.get("business_model")
    context = ""
    if bm:
        context = f"Project: {bm.project_name}\nSummary: {bm.case_summary}\nTags: {bm.regulatory_tags}"

    history_text = _format_chat_history(state, n=6)

    prompt = f"""
    You are an expert Legal QA Assistant.

    Recent Conversation History:
    {history_text}

    Current Business Model Context: {context}
    User Question: {state.get('user_input', '')}

    1. Use the `national_law_search` or `precedent_search` tools to find the exact legal answer.
    2. Provide a conversational, direct, and highly accurate answer in KOREAN (한국어).
    3. If you find legal basis, mention the specific laws and articles.
    4. Consider the conversation history to provide contextually appropriate answers.
    """

    try:
        response = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
        answer = response["messages"][-1].content
        return {
            "current_intent": "ask_question",
            "chat_response": answer,
            "chat_history": [AIMessage(content=answer)],
        }
    except Exception as e:
        print(f"QA Node Error: {e}")
        return {
            "current_intent": "ask_question",
            "chat_response": "죄송합니다, 질문 처리 중 오류가 발생했습니다. 다시 시도해 주세요.",
            "errors": [f"[QA 단계 오류] {type(e).__name__}: {str(e)[:200]}"],
        }


# ── 3-5. Investigator (gpt-4o-mini + ReAct → structured post-processing) ──
async def investigator_node(state: MiriState) -> Dict[str, Any]:
    from langgraph.prebuilt import create_react_agent

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    tools = get_investigator_tools()
    agent = create_react_agent(llm, tools)

    bm = state.get("business_model")
    context = ""
    if bm:
        context = f"Project: {bm.project_name}\nSummary: {bm.case_summary}\nTags: {bm.regulatory_tags}"

    what_ifs_active = state.get("what_if_toggles", [])

    # Build previous evidence context (preserved, not truncated)
    previous_evidence = state.get("research_evidence")
    prev_evidence_text = ""
    if previous_evidence and previous_evidence.items:
        prev_items = [
            f"- {item.law_name} {item.article}: {item.content}"
            for item in previous_evidence.items[-10:]
        ]
        prev_evidence_text = "\n".join(prev_items)

    prompt = f"""
    You are an expert Legal Investigator.
    Target: Investigate the regulations, required forms (별지 서식), and precedents for the following case.
    IMPORTANT: ALWAYS think and summarize evidence in KOREAN (한국어).

    User's Latest Request/Question: {state.get('user_input', '')}
    Current Business Model Context: {context}
    Active What-If Conditions: {what_ifs_active}

    Previous Evidence Found (Build upon this, do not discard it):
    {prev_evidence_text if prev_evidence_text else 'None'}

    Use the `national_law_search` tool to find exact regulations and forms (Use search_scope 1 or 3 for forms).
    Use `precedent_search` if needed.

    For EACH piece of evidence found, clearly state:
    1. The law/precedent name (법령명)
    2. The specific article number (조문 번호)
    3. The key content (핵심 내용)
    4. The URL if available

    Provide a comprehensive summary of the regulatory requirements, specific legal forms to submit, agencies, and timelines in Korean.
    """

    try:
        response = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
        evidence_text = response["messages"][-1].content

        # Post-process: structure the free-text evidence into EvidenceItems
        structurer_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        structured_llm = structurer_llm.with_structured_output(ResearchEvidence)

        struct_prompt = f"""
        Parse the following legal research results into structured evidence items.
        Extract each distinct piece of legal evidence as a separate item.
        ALL fields MUST be in KOREAN (한국어).

        Research Results:
        {evidence_text}
        """

        structured_evidence = await structured_llm.ainvoke(
            [SystemMessage(content=struct_prompt)]
        )

        # Preserve previous evidence items by appending (deduplicate by law_name + article)
        if previous_evidence and previous_evidence.items:
            existing_keys = {
                (item.law_name, item.article) for item in previous_evidence.items
            }
            new_items = [
                item
                for item in structured_evidence.items
                if (item.law_name, item.article) not in existing_keys
            ]
            all_items = previous_evidence.items + new_items
            structured_evidence = ResearchEvidence(
                items=all_items, summary=structured_evidence.summary
            )

        return {"research_evidence": structured_evidence}
    except Exception as e:
        print(f"Investigator Error: {e}")
        return {
            "research_evidence": ResearchEvidence(items=[], summary=""),
            "errors": [f"[조사 단계 오류] {type(e).__name__}: {str(e)[:200]}"],
        }


# ── 3-6. Auditor (gpt-4o-mini, structured output) ──
async def auditor_node(state: MiriState) -> Dict[str, Any]:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)

    class AuditorOutput(BaseModel):
        roadmap: List[RoadmapStep]
        risk: RiskEvaluation
        references: List[ReferenceItem]
        chat_response: str = Field(
            description="A friendly, conversational answer addressing the User's Latest Input directly."
        )

    structured_llm = llm.with_structured_output(AuditorOutput)

    bm = state.get("business_model")

    # Format structured evidence
    evidence = state.get("research_evidence")
    evidence_text = ""
    if evidence and evidence.items:
        for idx, item in enumerate(evidence.items, 1):
            evidence_text += f"[{idx}] {item.law_name} {item.article}\n"
            evidence_text += f"    내용: {item.content}\n"
            evidence_text += f"    URL: {item.url}\n"
            evidence_text += f"    관련성: {item.relevance}\n\n"

    prompt = f"""
    You are an Expert Legal Auditor.
    Based on the structured business model and the research evidence, build a regulatory Decision Tree Roadmap and evaluate Risk.

    CRITICAL LANGUAGE INSTRUCTION: EVERYTHING MUST BE WRITTEN IN PERFECT KOREAN (한국어). Do not output English sentences.

    CRITICAL CITATION INSTRUCTION:
    Whenever you make a legal claim, state a rule, or define a requirement in `roadmap.description`, `roadmap.action_items.context`, or `risk.rationale`, YOU MUST INCLUDE AN INLINE CITATION like [1], [2], etc.
    These numbers must perfectly correspond to the `references` list which will contain the Title and URL of the law/evidence. NEVER MAKE A CLAIM WITHOUT A CITATION INDEX.

    User's Latest Input / Question: {state.get('user_input', '')}
    Business Model: {bm.model_dump_json() if bm else ''}
    Active What-Ifs: {state.get('what_if_toggles', [])}

    Research Evidence (structured, indexed):
    {evidence_text if evidence_text else 'No evidence collected'}

    Evidence Summary: {evidence.summary if evidence else 'N/A'}

    Rules for Roadmap (Decision Tree):
    - Must be a chronological sequence of steps to pass regulations.
    - Extract specific ActionItems (Exact forms like '별지 제x호', specific attachments, target agencies) from the evidence.

    Rules for RiskEvaluation:
    - Score must be precisely 'Red', 'Yellow', or 'Green'.
    - Provide a clear rationale based on the evidence, heavily referencing [1], [2], etc.

    Rules for chat_response:
    - You MUST explicitly answer the User's Latest Input. If they asked about specific exemptions or data items, summarize the answer briefly here based on the Research Evidence.
    """

    try:
        result = await structured_llm.ainvoke([SystemMessage(content=prompt)])
        return {
            "roadmap": result.roadmap,
            "risk_evaluation": result.risk,
            "references": result.references,
            "chat_response": result.chat_response,
        }
    except Exception as e:
        print(f"Auditor Error: {e}")
        return {
            "errors": [f"[자문 단계 오류] {type(e).__name__}: {str(e)[:200]}"],
        }


# ── 3-7. Validator (no LLM call, checks completeness) ──
async def validator_node(state: MiriState) -> Dict[str, Any]:
    roadmap = state.get("roadmap", [])
    references = state.get("references", [])
    evidence = state.get("research_evidence")
    retry_count = state.get("retry_count", 0)

    has_evidence = bool(evidence and evidence.items and len(evidence.items) > 0)
    has_references = bool(references and len(references) > 0)
    has_roadmap = bool(roadmap and len(roadmap) > 0)

    validation_passed = has_evidence and has_references and has_roadmap

    if not validation_passed and retry_count < 1:
        missing = []
        if not has_evidence:
            missing.append("법적 근거 자료 없음")
        if not has_references:
            missing.append("인용 참고문헌 없음")
        if not has_roadmap:
            missing.append("로드맵 미생성")

        return {
            "retry_count": retry_count + 1,
            "errors": [
                f"[검증 실패] {', '.join(missing)} - 조사 단계 재시도 ({retry_count + 1}/1)"
            ],
        }

    return {"retry_count": retry_count}


def validator_router(state: MiriState) -> str:
    retry_count = state.get("retry_count", 0)
    evidence = state.get("research_evidence")
    references = state.get("references", [])
    roadmap = state.get("roadmap", [])

    has_evidence = bool(evidence and evidence.items and len(evidence.items) > 0)
    has_references = bool(references and len(references) > 0)
    has_roadmap = bool(roadmap and len(roadmap) > 0)

    validation_passed = has_evidence and has_references and has_roadmap

    if not validation_passed and retry_count <= 1:
        return "investigator"
    return "end"


# ─────────────────────────────────────────────
# 4. Build Graph
# ─────────────────────────────────────────────
builder = StateGraph(MiriState)

builder.add_node("intent_classifier", intent_classifier_node)
builder.add_node("structurer", structurer_node)
builder.add_node("investigator", investigator_node)
builder.add_node("auditor", auditor_node)
builder.add_node("validator", validator_node)
builder.add_node("qa_node", qa_node)

builder.set_entry_point("intent_classifier")

builder.add_conditional_edges(
    "intent_classifier",
    router_logic,
    {"structurer": "structurer", "qa_node": "qa_node"},
)

builder.add_edge("structurer", "investigator")
builder.add_edge("investigator", "auditor")
builder.add_edge("auditor", "validator")

builder.add_conditional_edges(
    "validator",
    validator_router,
    {"investigator": "investigator", "end": END},
)

builder.add_edge("qa_node", END)

# ─────────────────────────────────────────────
# 5. Persistent Checkpointer (SqliteSaver with MemorySaver fallback)
# ─────────────────────────────────────────────
checkpointer = MemorySaver()
miri_graph = builder.compile(checkpointer=checkpointer)


async def setup_persistent_checkpointer():
    """Upgrade to AsyncSqliteSaver once an event loop is available (call from FastAPI startup)."""
    global miri_graph
    try:
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from config import CHECKPOINT_DB_PATH

        conn = await aiosqlite.connect(CHECKPOINT_DB_PATH)
        persistent = AsyncSqliteSaver(conn=conn)
        miri_graph = builder.compile(checkpointer=persistent)
        print(f"✅ Persistent checkpointer ready (SQLite: {CHECKPOINT_DB_PATH})")
    except Exception as e:
        print(f"⚠️ Persistent checkpointer failed ({e}), keeping MemorySaver")
