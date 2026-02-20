from typing import Type, List, Dict, Any
from pydantic import BaseModel, Field
from langchain.tools import BaseTool

from law_api import law_api

class LawSearchInput(BaseModel):
    query: str = Field(description="검색할 법령, 규칙, 자치법규 또는 서식에 대한 핵심 키워드 (예: 동물용 의약품, 품목허가)")
    search_scope: int = Field(
        default=0, 
        description="0: 법령조문, 1: 법령별표/서식, 2: 행정규칙조문, 3: 행정규칙별표/서식, 4: 자치법규조문, 5: 자치법규별표/서식"
    )

class LawSearchTool(BaseTool):
    name: str = "national_law_search"
    description: str = "국가법령정보센터에서 법령, 행정규칙, 자치법규 본문 및 별표/서식(필요 서류 정보)을 검색합니다."
    args_schema: Type[BaseModel] = LawSearchInput

    def _run(self, query: str, search_scope: int = 0) -> str:
        raise NotImplementedError("Use _arun for async execution")

    async def _arun(self, query: str, search_scope: int = 0) -> str:
        try:
            results = await law_api.ai_search(query=query, search_scope=search_scope)
            if not results:
                scope_str = {0:"법령", 1:"법령별표/서식", 2:"행정규칙", 3:"행정규칙별표/서식", 4:"자치법규", 5:"자치법규별표/서식"}.get(search_scope, "")
                return f"[{scope_str}] '{query}'에 대한 검색 결과가 없습니다. 다른 키워드나 Scope를 시도해보세요."
            
            formatted = []
            for idx, r in enumerate(results[:5]): # 상위 5개만 반환
                title = r.get('article_title', '')
                content = r.get('content', '')[:1000] # 길이 제한
                link = r.get('link', 'http://www.law.go.kr')
                formatted.append(f"[{idx+1}] {r['law_name']} {title}\n링크: {link}\n내용: {content}")
            
            return "\n\n".join(formatted)
        except Exception as e:
            return f"검색 중 오류 발생: {str(e)}"


class PrecSearchInput(BaseModel):
    query: str = Field(description="검색할 판례 키워드 (예: 동물용 의약품 부작용 판례)")

class PrecSearchTool(BaseTool):
    name: str = "precedent_search"
    description: str = "국가법령정보센터에서 대법원 등 주요 판례를 검색합니다."
    args_schema: Type[BaseModel] = PrecSearchInput

    def _run(self, query: str) -> str:
        raise NotImplementedError("Use _arun for async execution")

    async def _arun(self, query: str) -> str:
        try:
            items = await law_api.search_list(target="prec", query=query, display=3)
            if not items:
                return f"'{query}'에 대한 판례 검색 결과가 없습니다."
            
            formatted = []
            for idx, item in enumerate(items):
                content, _, _ = await law_api.get_content_from_item(item)
                title = item.get('사건명', '사건명 없음')
                formatted.append(f"[{idx+1}] 사건명: {title}\n내용요약: {content[:1000]}")
                
            return "\n\n".join(formatted)
        except Exception as e:
            return f"판례 검색 중 오류 발생: {str(e)}"

# 수출 등 관련 관세법 등 전문 법령 검색 필요 시 추가 가능

def get_investigator_tools() -> List[BaseTool]:
    """Agent가 사용할 툴 목록 반환"""
    return [LawSearchTool(), PrecSearchTool()]
