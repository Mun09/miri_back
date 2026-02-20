import os
from typing import TypedDict, List, Dict, Any, Optional, Literal
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field

from config import IS_TEST, MOCK_RESULT
from models import BusinessModel, WhatIfTrigger, CrossDomainMapping, RoadmapStep, RiskEvaluation, ActionItem
from modules.tools import get_investigator_tools

# 1. State Definition
class MiriState(TypedDict):
    user_input: str
    chat_history: List[BaseMessage]
    what_if_toggles: List[str] # active variable names
    
    # Extractions
    business_model: Optional[BusinessModel]
    what_ifs: List[WhatIfTrigger]
    cross_domains: List[CrossDomainMapping]
    
    # Current Intent for Routing
    current_intent: str # "modify_roadmap" or "ask_question"
    chat_response: str # Quick response for Q&A
    
    # Research
    research_evidence: str
    
    # Final Output
    roadmap: List[RoadmapStep]
    risk_evaluation: Optional[RiskEvaluation]
    references: List[Any]

# 2. Nodes
async def structurer_node(state: MiriState) -> Dict[str, Any]:
    llm = ChatOpenAI(model="gpt-4o", temperature=0) # Using 4o for better reasoning on context
    
    class StructurerOutput(BaseModel):
        intent: Literal["modify_roadmap", "ask_question"] = Field(description="Is the user adding constraints/changing the business model (modify_roadmap) or just asking a question about the current situation (ask_question)?")
        business_model: BusinessModel = Field(description="The updated or newly created Business Model.")
        what_ifs: List[WhatIfTrigger]
        cross_domains: List[CrossDomainMapping]
        chat_response: str = Field(default="", description="If intent is 'ask_question', write the answer here in Korean. Otherwise leave blank.")
        
    structured_llm = llm.with_structured_output(StructurerOutput)
    
    existing_bm = state.get("business_model")
    bm_json = existing_bm.model_dump_json() if existing_bm else "None (This is the first message)"
    
    prompt = f"""
    You are an expert 'Legal Consultation Refiner & Structurer'.
    Analyze the user's latest input against the existing Business Model.
    IMPORTANT: NEVER drop existing constraints unless explicitly told. We are progressively building this model.
    ALL output string fields MUST be strictly in KOREAN (한국어).
    
    User Input: {state['user_input']}
    Active What-Ifs: {state.get('what_if_toggles', [])}
    
    Existing Business Model:
    {bm_json}
    
    Instructions:
    1. Determine INTENT:
       - If the user is adding a new feature, changing a constraint, or giving new facts -> 'modify_roadmap'.
       - If the user is just asking a question about the EXISTING roadmap or general law -> 'ask_question'.
       - NEVER perform a hard reset. Always merge new facts into the Existing Business Model.
    2. If 'modify_roadmap': Update the BusinessModel, WhatIfTriggers, and CrossDomainMappings. Leave 'chat_response' blank.
    3. If 'ask_question': Return the EXACT SAME Existing Business Model. DO NOT MODIFY IT. Write your answer to their question in 'chat_response'.
    """
    
    try:
        result = await structured_llm.ainvoke([SystemMessage(content=prompt)])
        return {
            "current_intent": result.intent,
            "business_model": result.business_model,
            "what_ifs": result.what_ifs,
            "cross_domains": result.cross_domains,
            "chat_response": result.chat_response
        }
    except Exception as e:
        print(f"Structurer Error: {e}")
        return {"current_intent": "modify_roadmap"}


def router_logic(state: MiriState) -> str:
    if state.get("current_intent") == "ask_question":
        return "qa_node"
    return "investigator"

async def qa_node(state: MiriState) -> Dict[str, Any]:
    from langgraph.prebuilt import create_react_agent
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0) # use 4o for better QA
    tools = get_investigator_tools()
    
    agent = create_react_agent(llm, tools)
    
    bm = state.get('business_model')
    context = ""
    if bm:
        context = f"Project: {bm.project_name}\nSummary: {bm.case_summary}\nTags: {bm.regulatory_tags}"
        
    # We ignore previous chat_response from structurer and do a proper search
    prompt = f"""
    You are an expert Legal QA Assistant.
    The user has a specific question regarding their business model or general regulations.
    
    Current Business Model Context: {context}
    User Question: {state.get('user_input', '')}
    
    1. Use the `national_law_search` or `precedent_search` tools to find the exact legal answer.
    2. Provide a conversational, direct, and highly accurate answer in KOREAN (한국어).
    3. If you find legal basis, mention the specific laws and articles.
    """
    
    try:
        response = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
        answer = response["messages"][-1].content
        return {"current_intent": "ask_question", "chat_response": answer}
    except Exception as e:
        print(f"QA Node Error: {e}")
        return {"current_intent": "ask_question"}


async def investigator_node(state: MiriState) -> Dict[str, Any]:
    from langgraph.prebuilt import create_react_agent
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    tools = get_investigator_tools()
    
    agent = create_react_agent(llm, tools)
    
    bm = state.get('business_model')
    context = ""
    if bm:
        context = f"Project: {bm.project_name}\\nSummary: {bm.case_summary}\\nTags: {bm.regulatory_tags}"
        
    what_ifs_active = state.get('what_if_toggles', [])
    previous_evidence = state.get('research_evidence', '')
    
    prompt = f"""
    You are an expert Legal Investigator.
    Target: Investigate the regulations, required forms (별지 서식), and precedents for the following case.
    IMPORTANT: ALWAYS think and summarize evidence in KOREAN (한국어).
    
    User's Latest Request/Question: {state.get('user_input', '')}
    Current Business Model Context: {context}
    Active What-If Conditions: {what_ifs_active}
    
    Previous Evidence Found (Build upon this, do not discard it):
    {previous_evidence[-1000:] if previous_evidence else 'None'}
    
    Use the `national_law_search` tool to find exact regulations and forms (Use search_scope 1 or 3 for forms).
    Use `precedent_search` if needed.
    Pay special attention to finding answers to any specific questions asked in the User's Latest Request (e.g., exemption data, specific forms).
    
    Provide a comprehensive summary of the regulatory requirements, specific legal forms to submit, agencies, and timelines in Korean.
    Be sure to explicitly mention which exact forms (e.g. "별지 제4호 서식") are needed and include the URL linking back to the raw law if available from the tool.
    """
    
    try:
        response = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
        evidence = response["messages"][-1].content
        # Append or replace evidence. For now, we replace because the prompt asks to summarize comprehensively.
        return {"research_evidence": evidence}
    except Exception as e:
        print(f"Investigator Error: {e}")
        return {}


async def auditor_node(state: MiriState) -> Dict[str, Any]:
    from models import ReferenceItem
    llm = ChatOpenAI(model="gpt-4o", temperature=0.1) 
    
    class AuditorOutput(BaseModel):
        roadmap: List[RoadmapStep]
        risk: RiskEvaluation
        references: List[ReferenceItem]
        chat_response: str = Field(description="A friendly, conversational answer addressing the User's Latest Input directly. Explain what changes were made to the roadmap or explicitly answer their specific questions based on the evidence.")
        
    structured_llm = llm.with_structured_output(AuditorOutput)
    
    bm = state.get('business_model')
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
    
    Research Evidence (contains answers to user questions):
    {state.get('research_evidence', '')}
    
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
            "chat_response": result.chat_response
        }
    except Exception as e:
        print(f"Auditor Error: {e}")
        return {}



# Build Graph
builder = StateGraph(MiriState)

builder.add_node("structurer", structurer_node)
builder.add_node("investigator", investigator_node)
builder.add_node("auditor", auditor_node)
builder.add_node("qa_node", qa_node)

builder.set_entry_point("structurer")
# Router logic
builder.add_conditional_edges("structurer", router_logic, {
    "investigator": "investigator",
    "qa_node": "qa_node"
})

builder.add_edge("investigator", "auditor")
builder.add_edge("auditor", END)
builder.add_edge("qa_node", END)

# Attach Checkpointer (MemorySaver)
memory = MemorySaver()
miri_graph = builder.compile(checkpointer=memory)

