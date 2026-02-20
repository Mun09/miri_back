"""
Pydantic Models for MIRI Legal Advisory System
"""
from pydantic import BaseModel, Field
from typing import List

# Unified Consultation Model (Replaces BusinessModel)
class ConsultationStakeholders(BaseModel):
    parties_involved: str = Field(description="Parties involved")
    roles: List[str] = Field(description="Roles of parties")

class ConsultationKeyElements(BaseModel):
    money_or_assets: str = Field(default="", description="Related money or assets")
    data_or_information: List[str] = Field(default_factory=list, description="Related data/info")
    actions_or_services: str = Field(default="", description="Core actions or services")

class BusinessModel(BaseModel):
    consultation_type: str = Field(description="Type of consultation")
    project_name: str = Field(description="Case title")
    case_summary: str = Field(description="Summary of the case")
    stakeholders: ConsultationStakeholders
    key_elements: ConsultationKeyElements
    regulatory_tags: List[str] = Field(description="Legal keywords")

# Scenario Models
class AtomicAction(BaseModel):
    actor: str
    action: str
    object: str

class Scenario(BaseModel):
    name: str
    type: str
    actions: List[AtomicAction]

# Legal Evidence Models
class LegalEvidence(BaseModel):
    relevant_laws: List[str] = Field(default_factory=list)
    summary: str

class DocumentReview(BaseModel):
    law_name: str
    key_clause: str = Field(description="관련 조항 (예: 제3조 제1항). 없으면 빈칸")
    status: str = Field(description="Prohibited | Permitted | Conditional | Neutral | Ambiguous")
    summary: str = Field(description="해당 조항의 핵심 내용 요약 (한글 2문장 이내)")
    url: str = Field(description="법령/판례 원문 링크", default="")

# Risk Report Models
class RiskReport(BaseModel):
    verdict: str = Field(default="Caution", description="Risk Level: Safe | Caution | Danger")
    summary: str = Field(default="판단 보류", description="Detailed Verdict Summary")
    citation: str = Field(default="구체적 조항 없음", description="Legal Citation")
    key_issues: List[str] = Field(default_factory=list, description="Key legal issues identified")

# Strategy Models
class SearchStrategy(BaseModel):
    rationale: str = Field(description="검색 전략 수립 이유")
    databases: List[str] = Field(description="검색할 DB 목록 (순서대로 중요)", default=["law", "admrul"])
    focus_keywords: List[str] = Field(description="전략적으로 집중할 추가 키워드", default_factory=list)

# --- New Models for LangChain Refactoring ---

class ActionItem(BaseModel):
    step_name: str = Field(description="단계 이름")
    required_documents: List[str] = Field(default_factory=list, description="필요 서류 및 별지 서식")
    submission_agency: str = Field(default="관할 기관", description="서류 제출 기관")
    context: str = Field(description="부가 설명 및 팁")

class RoadmapStep(BaseModel):
    phase: int = Field(description="단계 번호")
    title: str = Field(description="단계 제목")
    estimated_time: str = Field(default="알 수 없음", description="예상 소요 기간")
    description: str = Field(description="주요 업무 요약")
    action_items: List[ActionItem] = Field(default_factory=list, description="행동 지침 및 필요 서류")

class RiskEvaluation(BaseModel):
    score: str = Field(description="Risk Level: Red (위험) | Yellow (조건부) | Green (안전)")
    rationale: str = Field(description="평가 근거 요약")
    key_hurdles: List[str] = Field(default_factory=list, description="극복해야 할 주요 법적 허들")

class WhatIfTrigger(BaseModel):
    variable_name: str = Field(description="변수명 (예: 유전자형질변경유무)")
    description: str = Field(description="가정 상황 설명")
    is_active: bool = Field(default=False, description="현재 활성화 여부")

class CrossDomainMapping(BaseModel):
    source_domain: str = Field(description="비교 대상 도메인 (예: 인체용 약)")
    target_domain: str = Field(description="진입하려는 도메인 (예: 동물용 약)")
    agency_mapping: str = Field(description="주무 부처 비교")
    law_mapping: str = Field(description="핵심 적용 법령 비교")
    key_differences: str = Field(description="규제적 차이점 요약")

class ReferenceItem(BaseModel):
    title: str = Field(description="법령명 또는 판례명 (예: 사료관리법 시행규칙)")
    url: str = Field(description="국가법령정보센터 원문 링크 URL. 없으면 빈 칸")

class StructuredAnalysisResult(BaseModel):
    risk_evaluation: RiskEvaluation
    roadmap: List[RoadmapStep]
    cross_domain_mapping: List[CrossDomainMapping] = Field(default_factory=list)
    what_if_triggers: List[WhatIfTrigger] = Field(default_factory=list)
    references: List[ReferenceItem] = Field(default_factory=list, description="본문에서 인용한 법적 근거 [1], [2] 문서 목록")
