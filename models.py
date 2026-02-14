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
