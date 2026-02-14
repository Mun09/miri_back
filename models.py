"""
Pydantic Models for MIRI Legal Advisory System
"""
from pydantic import BaseModel, Field
from typing import List

# Business Model / Consultation Case Models
class Stakeholders(BaseModel):
    platform_role: str = Field(description="Role of the platform")
    users: List[str] = Field(description="List of user types")

class Mechanisms(BaseModel):
    money_flow: str = Field(description="How money moves")
    data_collection: List[str] = Field(description="What data is collected")
    service_delivery: str = Field(description="How service is delivered")

class BusinessModel(BaseModel):
    project_name: str = Field(description="Name of the project")
    business_type: str = Field(description="Type of business")
    stakeholders: Stakeholders
    mechanisms: Mechanisms
    regulatory_tags: List[str] = Field(description="List of regulatory keywords")

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
