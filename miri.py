import os
import json
import asyncio
import aiohttp
import xmltodict
import json_repair
import re
from dotenv import load_dotenv
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
from typing import Any, List, Dict, Tuple, Optional
from pydantic import BaseModel, Field

# .env 파일 로드
load_dotenv()

MAX_ANALYSIS_DOCS = 5

try:
    from openai import AsyncOpenAI
except ImportError:
    raise ImportError("Please run 'pip install openai' to use this feature.")

# 4. Define LLM Client (OpenAI - Cost Optimized)
class OpenAIClient:
    def __init__(self):
        # API Key는 환경변수에서 로드하거나 여기에 직접 입력
        self.api_key = os.getenv("OPENAI_API_KEY") 
        if not self.api_key:
            print("⚠️ Warning: OPENAI_API_KEY not found in environment variables.")
        
        self.client = AsyncOpenAI(api_key=self.api_key)
        self.semaphore = asyncio.Semaphore(5) # LLM 동시 요청 제한 (Rate Limit 방지)

    async def generate(self, system_prompt: str, user_input: str, model: str = "gpt-4o-mini", **kwargs) -> str:
        async with self.semaphore:
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_input}
                    ],
                    temperature=kwargs.get("temperature", 0.7),
                    max_tokens=kwargs.get("max_tokens", 2048)
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"LLM Error ({model}): {e}")
                return "{}" # Return empty JSON-like string on error to prevent json parsing crash

llm_client = OpenAIClient()

import asyncio
import aiohttp
import xmltodict
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
from typing import Any, List, Dict, Tuple, Optional
from pydantic import BaseModel, Field
import json_repair
import json

class NationalLawAPI:
    def __init__(self, api_id="jaeyeongm34", base_url="http://www.law.go.kr"):
        self.base_url = base_url
        self.api_id = api_id
        self.is_mock = not bool(self.api_id)
        self._cache = {}
        self.semaphore = asyncio.Semaphore(20) # 동시 요청 제한

    def _force_list(self, data: Any) -> List[Any]:
        if not data: return []
        if isinstance(data, list): return data
        return [data]

    async def _fetch(self, url: str) -> Dict[str, Any]:
        if url in self._cache:
            # print(f"      📦 Cache Hit: {url}")
            return self._cache[url]
        
        async with self.semaphore:
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(url) as response:
                        if response.status != 200:
                            print(f"    ❌ API Error: Status {response.status} for {url}")
                            return {}
                        content = await response.text()
                        parsed = xmltodict.parse(content)
                        self._cache[url] = parsed
                        return parsed
                except Exception as e:
                    print(f"    ❌ Fetch Exception: {e}")
                    return {}

    async def search_list(self, target: str, query: str, **kwargs) -> List[Dict[str, Any]]:
        if self.is_mock: return []

        endpoint = "lawSearch.do"
        params = {
            "OC": self.api_id,
            "target": target,
            "type": "XML",
            "query": query,
            "display": 5,
            "nw": 3  # 기본값: 현행 법령만 검색
        }
        params.update(kwargs) # JO 등 추가 파라미터 병합

        # 디버깅: 실제 요청 URL 파라미터 출력 (판례 검색시 중요)
        if target == 'prec':
            jo_param = kwargs.get('JO', '')
            print(f"      📡 [API 요청] {target.upper()} 검색 | Query='{query}' | JO='{jo_param}'")
        else:
            print(f"      📡 [API 요청] {target.upper()} 검색 | Query='{query}'")

        query_string = urlencode(params, doseq=True)
        url = f"{self.base_url}/DRF/{endpoint}?{query_string}"

        data = await self._fetch(url)

        # [Update] eflaw 지원 추가 (eflaw의 root는 LawSearch)
        root_map = {'law': 'LawSearch', 'eflaw': 'LawSearch', 'admrul': 'AdmRulSearch', 'prec': 'PrecSearch'}
        root_key = root_map.get(target, 'LawSearch')

        try:
            search_data = data.get(root_key, {})
            # [Fix] eflaw 검색 결과의 아이템 태그는 'law'임
            item_key = 'law' if target == 'eflaw' else target

            result = search_data.get(item_key, [])
            items = self._force_list(result)
            print(f"        -> ✅ 결과: {len(items)}건 발견")
            return items
        except AttributeError:
            print(f"        -> ⚠️ 결과 파싱 실패 또는 0건")
            return []

    def _clean_html(self, text: str) -> str:
        """HTML 태그 제거 + 불필요한 메타데이터 정리"""
        if not text: return ""
        
        # 1. HTML 태그 제거
        text = re.sub(r'<[^>]+>', '', text).strip()
        
        # 2. 개정 이력 제거 (예: <개정 2009.1.30>, <신설 2017.1.17>)
        text = re.sub(r'<(개정|신설|전문개정|타법개정|일부개정|폐지)\s+[\d.,\s]+>', '', text)
        
        # 3. 참고 정보 제거 (예: [전문개정 2009.1.30])
        text = re.sub(r'\[(전문개정|개정|신설|타법개정|일부개정|폐지)\s+[\d.,\s]+\]', '', text)
        
        # 4. 장/절/관 헤더 제거 (예: "제1장 총칙", "제2절 외국환업무")
        text = re.sub(r'제\d+장\s+[가-힣\s]+', '', text)
        text = re.sub(r'제\d+절\s+[가-힣\s]+', '', text)
        
        # 5. 다중 공백/개행 정리
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

    def _parse_xml_to_text(self, data: Dict[str, Any]) -> str:
        # 1. 법령 (Law)
        if '법령' in data:
            root = data['법령']
            text_parts = []
            
            # 기본 형식: 법령명
            title = root.get('기본정보', {}).get('법령명_한글', '')
            text_parts.append(f"== {title} ==\n")

            # 조문 (Main Body)
            jo_list = self._force_list(root.get('조문', {}).get('조문단위', []))
            for jo in jo_list:
                # 조문내용 (제X조 ...)
                jo_content = self._clean_html(jo.get('조문내용', ''))
                item_text = [jo_content]
                
                # 항 (Paragraph)
                hang_list = self._force_list(jo.get('항', []))
                for hang in hang_list:
                    h_content = self._clean_html(hang.get('항내용', ''))
                    if h_content:
                        item_text.append(f"  {h_content}")
                    
                    # 호 (Subparagraph)
                    ho_list = self._force_list(hang.get('호', []))
                    for ho in ho_list:
                        ho_content = self._clean_html(ho.get('호내용', ''))
                        if ho_content:
                            item_text.append(f"    {ho_content}")
                
                text_parts.append("\n".join(item_text))
            
            return "\n\n".join(text_parts) if len(text_parts) > 1 else str(data)

        # 2. 행정규칙 (AdmRul)
        if '행정규칙' in data:
            root = data['행정규칙']
            text_parts = []
            
            title = root.get('기본정보', {}).get('행정규칙명', '')
            text_parts.append(f"== {title} ==\n")
            
            # 조문 구조가 있는 경우
            jo_list = self._force_list(root.get('조문', {}).get('조문단위', []))
            if jo_list:
                for jo in jo_list:
                    jo_content = self._clean_html(jo.get('조문내용', ''))
                    text_parts.append(jo_content)
                    
                    # 항/호 처리 (행정규칙은 구조가 덜 엄격할 수 있음)
                    hang_list = self._force_list(jo.get('항', []))
                    for hang in hang_list:
                        h_content = self._clean_html(hang.get('항내용', ''))
                        if h_content: text_parts.append(f"  {h_content}")
            else:
                 # 조문 형식이 아닌 본문 통짜인 경우
                 text_parts.append(self._clean_html(root.get('본문', '')))

            return "\n\n".join(text_parts)

        # 3. 판례 (Prec)
        if '판례' in data:
            root = data['판례']
            issue = self._clean_html(root.get('판시사항', ''))
            summary = self._clean_html(root.get('판결요지', ''))
            content = self._clean_html(root.get('판례내용', ''))
            
            return f"[판시사항]\n{issue}\n\n[판결요지]\n{summary}\n\n[판례내용]\n{content}"

        return str(data)

    def _get_unique_id(self, data: Dict[str, Any]) -> str:
        """XML 데이터에서 고유 식별자 추출"""
        if '법령' in data:
            return str(data['법령'].get('기본정보', {}).get('법령ID', 'Unknown'))
        if '행정규칙' in data:
            return str(data['행정규칙'].get('기본정보', {}).get('행정규칙일련번호', 'Unknown'))
        if '판례' in data:
            return str(data['판례'].get('판례정보일련번호', 'Unknown'))
        return "Unknown"

    def _parse_law_structure(self, data: Dict[str, Any]) -> List[Dict[str, str]]:
        """XML 구조를 활용해 법령의 [조문/별표] 리스트를 추출 (항/호/목 계층 완벽 대응)"""
        articles = []
        
        # 1. 법령 (Law)
        if '법령' in data:
            root = data['법령']
            
            # (1) 조문 파싱
            jo_list = self._force_list(root.get('조문', {}).get('조문단위', []))
            for jo in jo_list:
                # [OPTIMIZATION] 전문(章節 헤더)은 스킵 (실제 규정 아님)
                jo_type = jo.get('조문여부', '')
                if jo_type == '전문':
                    continue
                
                # 조문 제목 (제1조(목적))
                jo_text = self._clean_html(jo.get('조문내용', ''))
                
                # 빈 조문 스킵 (삭제된 조항 등)
                if not jo_text or len(jo_text) < 5:
                    continue
                
                match = re.match(r'(제\d+조의?\d?)\(?([^)]*)\)?', jo_text)
                title_id = match.group(1) if match else jo_text[:10]
                
                parts = [jo_text]
                
                # 항 (Paragraph)
                hang_list = self._force_list(jo.get('항', []))
                for hang in hang_list:
                    h_content = self._clean_html(hang.get('항내용', ''))
                    if h_content: parts.append(f"  {h_content}")
                    
                    # 호 (Subparagraph)
                    ho_list = self._force_list(hang.get('호', []))
                    for ho in ho_list:
                        ho_content = self._clean_html(ho.get('호내용', ''))
                        if ho_content: parts.append(f"    {ho_content}")
                        
                        # 목 (Item)
                        mok_list = self._force_list(ho.get('목', []))
                        for mok in mok_list:
                             m_content = self._clean_html(mok.get('목내용', ''))
                             if m_content: parts.append(f"      {m_content}")
                
                full_text = "\n".join(parts)
                articles.append({'id': title_id, 'content': full_text})

            # (2) 별표 파싱 (중요)
            # 구조: <별표> -> <별표단위> 리스트 가능성
            byeol_root = root.get('별표', {})
            # 만약 별표가 list라면 바로 사용 (.get('별표')가 리스트인 경우)
            if isinstance(byeol_root, list):
                byeol_list = byeol_root
            else:
                # 딕셔너리라면 '별표단위' 확인
                byeol_list = self._force_list(byeol_root.get('별표단위', []))
            
            for b in byeol_list:
                b_title = self._clean_html(b.get('별표제목', '별표'))
                # 별표내용이 없으면 '파일링크'라도 확인
                b_content = self._clean_html(b.get('별표내용', ''))
                if not b_content:
                     # 내용이 비어있다면, 서식 파일 링크가 있는지 확인해서 안내
                     link = b.get('별표서식파일링크') or b.get('별표서식PDF파일링크')
                     if link: b_content = f"[서식 파일 존재] {link}"
                
                if b_content or b_title: # 제목이라도 있으면 추가
                    articles.append({'id': f"[별표] {b_title}", 'content': b_content or "내용 없음 (서식 파일 확인 필요)"})

        # 2. 행정규칙 (AdmRul)
        elif '행정규칙' in data:
            root = data['행정규칙']
            # 조문
            jo_list = self._force_list(root.get('조문', {}).get('조문단위', []))
            if jo_list:
                for jo in jo_list:
                    jo_content = self._clean_html(jo.get('조문내용', ''))
                    # 항/호가 있을 수 있음
                    parts = [jo_content]
                    hang_list = self._force_list(jo.get('항', []))
                    for hang in hang_list:
                        h = self._clean_html(hang.get('항내용', ''))
                        if h: parts.append(f"  {h}")
                    
                    articles.append({'id': jo_content[:20], 'content': "\n".join(parts)})
            
            # 별표
            byeol_root = root.get('별표', {})
            if isinstance(byeol_root, list):
                byeol_list = byeol_root
            else:
                byeol_list = self._force_list(byeol_root.get('별표단위', []))
                
            for b in byeol_list:
                b_title = self._clean_html(b.get('별표제목', '별표'))
                b_content = self._clean_html(b.get('별표내용', ''))
                if not b_content:
                     link = b.get('별표서식파일링크') or b.get('별표서식PDF파일링크')
                     if link: b_content = f"[서식 파일 존재] {link}"

                if b_content or b_title:
                    articles.append({'id': f"[별표] {b_title}", 'content': b_content or "내용 없음"})

        # 3. 판례 (Prec) - 구조 분석
        elif '판례' in data:
            root = data['판례']
            # 판시사항 (Issues)
            issue = self._clean_html(root.get('판시사항', ''))
            if issue:
                articles.append({'id': '판시사항', 'content': issue})
            
            # 판결요지 (Summary)
            summary = self._clean_html(root.get('판결요지', ''))
            if summary:
                articles.append({'id': '판결요지', 'content': summary})
            else:
                 # 요지가 없는 경우 본문 사용 (Fallback)
                 content = self._clean_html(root.get('판례내용', ''))
                 if content:
                     articles.append({'id': '판례내용', 'content': content[:3000] + "...(생략)"})
        
        return articles

    async def get_content_from_item(self, item: Dict[str, Any]) -> Tuple[str, str, Any]:
        """Returns: (Text, URL, RawDataDict)"""
        if self.is_mock: return "Mock Content", "", {}
        link = item.get('법령상세링크') or item.get('행정규칙상세링크') or item.get('판례상세링크')
        if not link: return "", "", {}

        full_url = f"{self.base_url}{link}"
        parsed = urlparse(full_url)
        query_params = parse_qs(parsed.query)
        query_params['type'] = ['XML'] # XML 강제
        new_query = urlencode(query_params, doseq=True)
        final_url = urlunparse(parsed._replace(query=new_query))

        data = await self._fetch(final_url)
        
        # [Update] XML 구조화 파싱 적용 + URL 반환 + 원본 데이터 반환 (구조 활용 위해)
        view_url = final_url.replace("type=XML", "type=HTML") 
        return self._parse_xml_to_text(data), view_url, data

law_api = NationalLawAPI(api_id="jaeyeongm34")
print("✅ NationalLawAPI Updated (with 'eflaw' support).")

# 6. Define Module Schemas

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

class AtomicAction(BaseModel):
    actor: str
    action: str
    object: str

class Scenario(BaseModel):
    name: str
    type: str
    actions: List[AtomicAction]

class LegalEvidence(BaseModel):
    relevant_laws: List[str] = Field(default_factory=list)
    summary: str

class RiskReport(BaseModel):
    verdict: str = Field(description="Status: Safe | Caution | Danger | Review Required")
    summary: str = Field(description="Detailed judgement summary")
    key_issues: List[str] = Field(default_factory=list, description="List of key legal issues")
    citation: str = Field(default="", description="Relevant laws")

class DocumentReview(BaseModel):
    law_name: str
    key_clause: str = Field(description="관련 조항 (예: 제3조 제1항). 없으면 빈칸")
    status: str = Field(description="Prohibited | Permitted | Conditional | Neutral | Ambiguous")
    summary: str = Field(description="해당 조항의 핵심 내용 요약 (한글 2문장 이내)")
    url: str = Field(description="법령/판례 원문 링크", default="")

print("Classes defined.")

class Structurer:
    SYSTEM_PROMPT = """
    You are an expert 'Business Model Structurer'.
    Analyze the user's idea and structure it into a formal business model.
    
    Output MUST be a JSON object following this schema:
    {
        "project_name": "...",
        "business_type": "...",
        "stakeholders": {
            "platform_role": "...",
            "users": ["..."]
        },
        "mechanisms": {
            "money_flow": "...",
            "data_collection": ["..."],
            "service_delivery": "..."
        },
        "regulatory_tags": ["..."]
    }
    """
    async def execute(self, user_input: str) -> BusinessModel:
        print("\n[1] Structuring Business Model...")
        # [MODEL: GPT-4o] 정확한 구조화가 가장 중요함 (Initial Input)
        response = await llm_client.generate(self.SYSTEM_PROMPT, user_input, model="gpt-4o")
        try:
            return BusinessModel(**json_repair.loads(response))
        except Exception as e:
            print(f"Structurer Error: {e}")
            print(f"Raw: {response}")
            raise e
# [수정] 1. 구체적인 디테일을 생성하도록 Simulator 강화
class Simulator:
    SYSTEM_PROMPT = """
    You are a 'Regulatory Sandbox Simulator'.
    Based on the Business Model, generate ONE representative 'Main Scenario'.

    [Important] To enable legal judgment, you MUST include 'specific figures' and 'clear actions'.

    Output MUST be a JSON list adhering to this structure:
    [
        {
            "name": "Main Scenario Summary",
            "type": "Main",
            "actions": [
                {"actor": "Traveler A", "action": "Registers remaining $2,000 on platform (90% exchange rate preference)", "object": "$2,000 USD"},
                {"actor": "Buyer B", "action": "Meets in person to exchange cash after chatting in app", "object": "Cash"}
            ]
        }
    ]
    """

    async def execute(self, model: BusinessModel) -> List[Scenario]:
        print("\n[2] Simulating Scenarios (Single Representative)...")
        prompt = f"Business Model: {model.model_dump_json()}"
        # [MODEL: GPT-4o-mini] 창의적인 시나리오 생성은 mini도 충분히 잘함 (비용 절감)
        response = await llm_client.generate(self.SYSTEM_PROMPT, prompt, model="gpt-4o-mini")
        try:
            data = json_repair.loads(response)
            if isinstance(data, dict): data = [data]
            return [Scenario(**s) for s in data][:1] # 강제로 1개만 선택
        except Exception as e:
            print(f"Simulator Error: {e}")
            return []

# [수정] 3. 엄격한 법률가 페르소나 적용
class Auditor:
    SYSTEM_PROMPT = """
    당신은 깐깐한 '금융 규제 감사관(Compliance Officer)'입니다.
    제공된 [시나리오]의 구체적 행위가 [수집된 법적 근거]에 위배되는지 엄격하게 판단하십시오.

    [판단 기준]
    1. 법적 근거에 '금지', '허가 필요', '등록 의무' 등의 단어가 있는지 확인하십시오.
    2. 금액(예: 미화 5,000달러 등)이 법적 한도를 초과하는지 확인하십시오.
    3. 구체적인 조항(제X조)이 인용되지 않았다면 'Unknown'으로 처리하지 말고, "규제 공백 가능성"으로 경고(Warning)하십시오.

    Output JSON Format:
    {
        "risk_level": "Critical | Warning | Safe",
        "verdict": "판단 이유 (반드시 수집된 법령의 조항을 인용하여 논리적으로 설명)",
        "citation": "위반되거나 검토가 필요한 구체적 법령명 및 조항 (예: 외국환거래법 제8조)"
    }
    응답은 반드시 한국어로 작성하십시오.
    """

    async def execute(self, scenario: Scenario, evidence: LegalEvidence) -> RiskReport:
        evidence_text = "\n".join(evidence.relevant_laws)
        if not evidence_text: evidence_text = "관련된 구체적 법령을 발견하지 못했습니다."

        prompt = f"""
        [시나리오]
        {scenario.model_dump_json()}

        [수집된 법적 근거]
        {evidence_text}
        """
        response = await llm_client.generate(self.SYSTEM_PROMPT, prompt)
        try:
            data = json_repair.loads(response)
            return RiskReport(**data)
        except Exception as e:
            print(f"Audit Error: {e}")
            return RiskReport(risk_level="Unknown", verdict="Audit Failed", citation="")

# 인스턴스 재생성
structurer = Structurer()
simulator = Simulator()
auditor = Auditor()

import re
from typing import List, Dict, Tuple, Optional, Callable

class SearchStrategy(BaseModel):
    rationale: str = Field(description="검색 전략 수립 이유")
    databases: List[str] = Field(description="검색할 DB 목록 (순서대로 중요)", default=["law", "admrul"])
    focus_keywords: List[str] = Field(description="전략적으로 집중할 추가 키워드", default_factory=list)

class Investigator:
    """
    Expert Investigator with Self-Correction (Critic) & Action-Based Search & Strategic Planning
    """
    
    STRATEGY_PROMPT = """
    Analyze the legal nature of the following action to decide the search strategy.

    [Action]
    {action}

    [Database Characteristics]
    - law (Acts, Decrees): For clear prohibitions, permissions, and penalties.
    - admrul (Administrative Rules): For specific monetary limits, notifications, and guidelines.

    [Instructions]
    1. If the action has clear illegal potential, prioritize 'law'.
    2. If specific figures or procedures are important, definitely include 'admrul'.
    3. List databases in order of importance.
    4. Add 'Focus Keywords' if there are additional topics to search (e.g., fintech, sharing economy).
    
    Output JSON:
    {{
        "rationale": "Reason for this strategy (English)",
        "databases": ["law", "admrul"],
        "focus_keywords": ["KoreanKeyWord1", "KoreanKeyWord2"]
    }}
    
    [Important]
    "focus_keywords" MUST be in KOREAN.
    """

    EXPANSION_PROMPT = """
    Regarding the user's action '{action}' (Target: {object}), extract 5 'single legal keywords' for searching.
    
    [Important]
    The user action is provided in English/Korean, but the **Keywords MUST be in KOREAN** for the South Korean Law Database.
    If the action is in English, translate the legal concepts to Korean first.

    [Constraints]
    1. Must be a single word, not a compound noun. (e.g., "Foreign Exchange" -> "외국환", "Personal Information" -> "개인정보")
    2. Must be a noun without particles. (No '을', '를', '의')
    3. Output strictly a JSON list of Korean strings.
    """

    SELECTOR_PROMPT = """
    User Action: "{action}"

    Below is a list of candidate laws/rules:
    {candidates}

    [Instructions]
    From the [Candidates] list above, select up to 10 items most relevant to the user's action.
    DO NOT create or add new law names that are not in the list.
    Output ONLY the exact text from the [Candidates] list as a JSON list.
    """

    KEYWORD_GEN_PROMPT = """
    User Action: "{action}"
    Infer 5 core legal issue keywords (search terms) that might be problematic for the action.
    
    [Important]
    **Keywords MUST be in KOREAN** (Hangul).
    The search engine only understands Korean legal terms.

    These should not be simple nouns (e.g., 'transaction'), but words that can find specific illegal acts or penalty provisions.
    Examples: "환치기", "무등록", "불법환전", "유사수신"
    Output as a JSON list of Korean strings.
    """

    CRITIC_PROMPT = """
    [Review Mode]
    User Action: "{action}"
    Current list of secured legal evidence:
    {evidence_summary}

    Q: Can the user's action be judged through 'legal interpretation' based solely on the evidence above?

    [PASS Criteria (Relaxed)]
    - If there are similar regulations or general principles, even without explicit provisions → PASS
    - If there are related limit concepts or reporting obligations, even without specific amounts → PASS
    - If reasonable inference is possible from laws alone, even without precedents → PASS
    - If there are prohibition/restriction clauses, even without penalty clauses → PASS

    [FAIL Criteria]
    - If no relevant laws were found at all (completely different field)
    - If too abstract to interpret in any direction

    If sufficient, output "PASS". If clearly insufficient, output "FAIL" along with suggested additional keywords.

    Output JSON Format:
    {{
        "status": "PASS" | "FAIL",
        "reason": "Reason (English)",
        "new_keywords": ["keyword1", "keyword2"]
    }}
    """

    PROMPTS = {
        "law": "[Law Analysis] Core: Find clauses (Article X) in this law that prohibit or restrict the user's action.",
        "admrul": "[Administrative Rule Analysis] Core: Find specific approval criteria, monetary limits, and reporting procedure figures.",
        "prec": "[Precedent Analysis] Core: Find the gist and applied legal principles of judgments (guilty/not guilty) for similar actions."
    }

    def __init__(self):
        # [NEW] 분석 결과 캐시 (LLM 비용 절감)
        self._analysis_cache = {}

    async def _plan_search(self, action: AtomicAction) -> SearchStrategy:
        prompt = self.STRATEGY_PROMPT.format(action=action.action)
        # [MODEL: GPT-4o] 검색 '전략' 수립은 고지능 필요
        response = await llm_client.generate(prompt, "", model="gpt-4o", max_tokens=512)
        try:
            data = json_repair.loads(response)
            return SearchStrategy(**data)
        except Exception as e:
            print(f"      ⚠️ Strategy Error: {e}, Defaulting to full search.")
            return SearchStrategy(rationale="Error in strategy planning", databases=["law", "admrul", "prec"])

    def _clean_keywords(self, keywords: List[str]) -> List[str]:
        cleaned = []
        for k in keywords:
            k = re.sub(r'\(.*?\)', '', k)
            k = re.sub(r'\s*제\d*O*조.*', '', k)
            k = re.sub(r'[a-zA-Z]', '', k)
            k = k.strip()
            if len(k) >= 2: cleaned.append(k)
        return cleaned

    async def _expand_query(self, action: AtomicAction) -> List[str]:
        # 1. 법령명 추출 (단일 키워드)
        prompt = self.EXPANSION_PROMPT.format(action=f"{action.action}", object=action.object)
        # [MODEL: GPT-4o-mini] 키워드 추출은 단순 작업
        response = await llm_client.generate(prompt, "", model="gpt-4o-mini", max_tokens=256)
        try:
            parsed = json_repair.loads(response)
            return self._clean_keywords(parsed if isinstance(parsed, list) else [str(parsed)])[:5]
        except:
            return []

    async def _generate_prec_keywords(self, action: AtomicAction) -> List[str]:
        # 2. 판례/정밀 검색용 구체적 키워드 추출
        prompt = self.KEYWORD_GEN_PROMPT.format(action=action.action)
        # [MODEL: GPT-4o-mini] 키워드 추출은 단순 작업
        response = await llm_client.generate(prompt, "", model="gpt-4o-mini", max_tokens=256)
        try:
            parsed = json_repair.loads(response)
            return self._clean_keywords(parsed if isinstance(parsed, list) else [str(parsed)])[:5]
        except:
            return []

    async def _select_best_candidates(self, candidates: List[Dict[str, Any]], action_text: str) -> List[Dict[str, Any]]:
        if not candidates: return []

        # LLM에게 후보군 전달하여 선택 요청
        candidate_names = [c.get('법령명한글') or c.get('행정규칙명') for c in candidates]
        prompt = self.SELECTOR_PROMPT.format(action=action_text, candidates=candidate_names)

        try:
            # [MODEL: GPT-4o-mini] 목록 중 선택(Selection)은 mini도 잘함
            response = await llm_client.generate(prompt, "", model="gpt-4o-mini", max_tokens=512)
            selected_names = json_repair.loads(response)
            if not isinstance(selected_names, list): selected_names = [str(selected_names)]

            print(f"      🤖 [Selector] LLM 선택: {selected_names}")

            final_items = []
            for name in selected_names:
                # 이름이 일치하는 아이템 찾기 (부분 일치 (in)는 위험할 수 있으니, 최대한 정확히 매칭 시도)
                for item in candidates:
                    item_name = item.get('법령명한글') or item.get('행정규칙명')
                    # LLM이 이름을 조금 잘라서 말할 수도 있으므로 contains 체크
                    if name in item_name or item_name in name:
                        final_items.append(item)
                        break
            return final_items if final_items else candidates[:10] # Fallback increased
        except Exception as e:
            print(f"      ⚠️ Selector Error: {e}")
            return candidates[:10]

    async def _critique(self, action_text: str, evidence: List[str]) -> Dict[str, Any]:
        summary = "\n".join(evidence) if evidence else "None"
        prompt = self.CRITIC_PROMPT.format(action=action_text, evidence_summary=summary)
        # [MODEL: GPT-4o] 충분한지 판단(Reasoning)하는 Critic은 똑똑해야 함 (환각 방지)
        response = await llm_client.generate(prompt, "", model="gpt-4o", max_tokens=512)
        try:
            val = json_repair.loads(response)
            if not isinstance(val, dict): return {"status": "PASS", "new_keywords": []}
            return val
        except:
            return {"status": "PASS", "new_keywords": []}

    async def _search_phase(self, keywords: List[str], prec_keywords: List[str], action: AtomicAction, strategy: SearchStrategy, on_log: Optional[Callable[[str], Any]] = None) -> List[Tuple[str, str, str, str, Any]]:
        collected_raw_data = []
        found_law_titles = []
        
        async def log(msg):
            if on_log: await on_log(msg)

        # Merge focus keywords from strategy
        if strategy.focus_keywords:
            keywords.extend(strategy.focus_keywords)
            prec_keywords.extend(strategy.focus_keywords)
            
        target_dbs = strategy.databases
        await log(f"      🎯 [전략] 대상 DB: {target_dbs}")

        # [Phase 1.1] 2단계 법령 검색 (후보군 선정 -> LLM 선택 -> 본문 검색)
        if 'law' in target_dbs:
            await log(f"      📡 [1단계] 현행법령 후보 검색: {keywords}")

        if not keywords: keywords = []

        # 1. eflaw로 후보군 리스트업
        search_tasks = [law_api.search_list('eflaw', kw, display=10) for kw in keywords] # [Update] display=10
        candidate_items = []

        if search_tasks:
            results = await asyncio.gather(*search_tasks)
            for res, kw in zip(results, keywords):
                if res:
                    # 키워드별 상위 30개 후보 수집 (기존 10개 -> 30개 확장)
                    candidates = res[:30]
                    # print(f"        -> '{kw}' 결과: {[c.get('법령명한글') for c in candidates]}")
                    candidate_items.extend(candidates)

        # 2. 후보군 중복 제거
        seen_ids = set()
        unique_candidates = []
        for item in candidate_items:
            # eflaw 결과는 'law' 태그였으므로 '법령명한글' 사용
            name = item.get('법령명한글')
            if name and name not in seen_ids:
                seen_ids.add(name)
                unique_candidates.append(item)
        
        await log(f"        -> {len(unique_candidates)}개 법령 후보 발견")

        # 3. LLM Selector를 통한 최종 선정
        if unique_candidates:
            target_candidates = await self._select_best_candidates(unique_candidates, action.action)
        else:
            target_candidates = []

        found_law_titles = [item.get('법령명한글') for item in target_candidates]
        await log(f"      👉 2단계 법령 본문 조회: {len(found_law_titles)}건")

        # 4. 본문 상세 조회
        fetch_tasks = [law_api.get_content_from_item(item) for item in target_candidates]
        if fetch_tasks:
            contents = await asyncio.gather(*fetch_tasks)
            for item, (content, url, raw_data) in zip(target_candidates, contents):
                title = item.get('법령명한글')
                collected_raw_data.append(('law', title, content, url, raw_data))

        # [Phase 2] AdmRul Search (2-Stage with Selector)
        # 사용자 요청: 행정규칙도 '단어(Keywords)'로 검색해야 더 넓은 범위를 포괄 가능
        if 'admrul' in target_dbs:
            await log(f"      📡 행정규칙 검색 중...")
            admrul_queries = keywords[:3]

            if admrul_queries:
                # print(f"      📡 [1단계] 행정규칙(admrul) 후보 검색: {admrul_queries}")
                
                adm_tasks = [law_api.search_list('admrul', kw, display=30, nw=1) for kw in admrul_queries]
                adm_raw_results = await asyncio.gather(*adm_tasks)
                
                adm_candidates = []
                adm_seen = set()
                
                for res in adm_raw_results:
                    for item in res:
                        name = item.get('행정규칙명')
                        if name and name not in adm_seen:
                            adm_seen.add(name)
                            adm_candidates.append(item)

            if adm_candidates:
                target_admruls = await self._select_best_candidates(adm_candidates, action.action)
            else:
                target_admruls = []
            
            await log(f"      👉 행정규칙 본문 조회: {len(target_admruls)}건")

            # 본문 상세 조회
            adm_fetch_tasks = [law_api.get_content_from_item(item) for item in target_admruls]
            if adm_fetch_tasks:
                adm_contents = await asyncio.gather(*adm_fetch_tasks)
                for item, (content, url, raw_data) in zip(target_admruls, adm_contents):
                    collected_raw_data.append(('admrul', item.get('행정규칙명'), content, url, raw_data))

        # [Phase 3] Precedent Search (Multi-Strategy)
        if 'prec' in target_dbs:
            await log(f"      📡 판례 검색 수행 중...")
            # print(f"      📡 판례 검색: 키워드={prec_keywords}, 대상법령={found_law_titles}")
            
            prec_tasks = []
            
            # Strategy 1: 법령명 + 키워드 조합 (JO 파라미터 활용)
            for title in found_law_titles[:2]: # Top 2 Law only
                for kw in prec_keywords:
                    prec_tasks.append(law_api.search_list('prec', query=kw, JO=title, display=30))

            # Strategy 2: 키워드 단독 검색 (Global)
            for kw in prec_keywords:
                prec_tasks.append(law_api.search_list('prec', query=kw, display=30))

            prec_results = []
            if prec_tasks:
                prec_results = await asyncio.gather(*prec_tasks)

            # 1. Candidate Collection (Metadata only)
            prec_candidates = []
            seen_prec_ids = set()
            
            for res in prec_results:
                for item in res: # All items from search
                    # 판례는 '판례일련번호'가 고유 ID
                    p_id = item.get('판례일련번호')
                    if p_id and p_id not in seen_prec_ids:
                        seen_prec_ids.add(p_id)
                        # Selector를 위해 '법령명한글' 필드를 사건명으로 매핑 (Selector가 법령명한글을 봄)
                        item['법령명한글'] = f"[판례] {item.get('판례내용') or item.get('사건명')}"
                        prec_candidates.append(item)
            
            # print(f"      🔎 판례 후보군: {len(prec_candidates)}건 수집됨")

            # 2. LLM Selector (Filter)
            if prec_candidates:
                # 판례는 제목만으로 판단하기 어려울 수 있으나, 사건명에 핵심이 포함됨.
                # [Optimization] Selector can handle up to MAX_ANALYSIS_DOCS
                target_precs = await self._select_best_candidates(prec_candidates[:MAX_ANALYSIS_DOCS], action.action)
            else:
                target_precs = []
            
            await log(f"      👉 판례 본문 조회: {len(target_precs)}건")

            # 4. 본문 상세 조회
            prec_fetch_tasks = [law_api.get_content_from_item(item) for item in target_precs]
            if prec_fetch_tasks:
                prec_contents = await asyncio.gather(*prec_fetch_tasks)
                for item, (content, url, raw_data) in zip(target_precs, prec_contents):
                    title = item.get('법령명한글')
                    collected_raw_data.append(('prec', title, content, url, raw_data))

        # [Limit] Max Documents to prevent token explosion
        if len(collected_raw_data) > MAX_ANALYSIS_DOCS:
            await log(f"      ✂️ 문서 과다로 상위 {MAX_ANALYSIS_DOCS}건만 분석합니다.")
            collected_raw_data = collected_raw_data[:MAX_ANALYSIS_DOCS]

        return collected_raw_data

    async def _analyze_full_text(self, text: str, action: AtomicAction, category: str, title: str, url: str, raw_data: Any) -> List[DocumentReview]:
        """
        문서 전체를 순회하며 핵심 내용 추출 (Full-Text Chunking & Structured Review)
        놓치는 조항이 없도록 전체를 다 훑어봄.
        """
        # [Cache] Unique ID 기반 캐싱 (Title 사용 중단)
        doc_id = law_api._get_unique_id(raw_data)
        # 만약 raw_data가 없거나 파싱 실패시, 임시로 title+url 해시 사용
        if doc_id == "Unknown":
            doc_id = f"{title}_{url}"
            
        cache_key = (action.action, doc_id)
        
        if cache_key in self._analysis_cache:
            # print(f"      ⚡ [Cache Hit] ID={doc_id} 사용")
            cached_reviews = self._analysis_cache[cache_key]
            for r in cached_reviews: r.url = url
            return cached_reviews

        reviews = []
        
        
        # [NEW] 구조적 분석 (Smart Index Scanning)
        # 법령(law), 행정규칙(admrul) 그리고 이제 판례(prec)도 지원
        if category in ['law', 'admrul', 'prec']:
            articles = law_api._parse_law_structure(raw_data)
            
            # Case 1: 판례 (Precedent) - 구조 분석 결과가 있다면 항상 사용 (큰 텍스트 방지)
            if category == 'prec' and articles:
                 # 판례는 [판시사항, 판결요지] 만으로 구성하여 재분석
                 # print(f"      ⚖️ [Precedent] 판례 구조 분석 (판시사항/판결요지 위주)")
                 combined_text = "\n\n".join([f"[{a['id']}]\n{a['content']}" for a in articles])
                 # 재귀 호출하여 짧은 텍스트 로직으로 처리
                 return await self._analyze_full_text(combined_text, action, category, title, url, {}) 

            # Case 2: 법령/행정규칙 - 조문이 너무 많으면 목차 스캐닝 수행
            if len(articles) > 5:
                # 조문이 너무 많으면 (예: 5개 이상) 목차 스캐닝 수행
                print(f"      📑 [Index Scan] {title} - 총 {len(articles)}개 조문 중 관련 조항 선별 중...")
                
                # 1. 목차(제목)만 추출
                toc_text = "\n".join([f"{i}. {art['id']}" for i, art in enumerate(articles)])
                
                prompt = f"""
                [Table of Contents: {title}]
                {toc_text}
                
                [User Action]
                {action.action}
                
                Select the indices (numbers) of articles that seem most relevant to the User Action.
                Select up to 5 articles. If none, return empty list.
                Output JSON: [0, 3, 12]
                """
                
                # [MODEL: GPT-4o-mini] 목차 스캐닝은 매우 가벼움
                res = await llm_client.generate(prompt, "", model="gpt-4o-mini", max_tokens=128)
                try:
                    selected_indices = json_repair.loads(res)
                    if not isinstance(selected_indices, list): selected_indices = []
                    
                    target_articles = [articles[i] for i in selected_indices if isinstance(i, int) and 0 <= i < len(articles)]
                    
                    if target_articles:
                        print(f"        -> 선별된 조항: {[a['id'] for a in target_articles]}")
                        # [NEW] 선별된 조항을 개별적으로 분석 (chunking 방지)
                        for art in target_articles:
                            art_prompt = f"""
                            [Analysis Target: {category} - {title}]
                            [{art['id']}]
                            {art['content']}

                            [User Action]
                            {action.action}

                            Extract legal grounds related to the 'User Action' from the text and respond in JSON.
                            
                            [Target Schema]
                            {{
                                "law_name": "{title}",
                                "key_clause": "{art['id']}",
                                "status": "Prohibited | Permitted | Conditional | Neutral | Ambiguous",
                                "summary": "해당 조항의 핵심 내용 요약 (한글 2문장 이내)"
                            }}
                            If there is no relevant content at all, set the status to 'Neutral'.
                            """
                            art_res = await llm_client.generate(art_prompt, "", model="gpt-4o-mini", max_tokens=512)
                            try:
                                art_data = json_repair.loads(art_res)
                                if art_data.get('status') != 'Neutral':
                                    rev = DocumentReview(**art_data)
                                    rev.url = url
                                    reviews.append(rev)
                            except:
                                pass
                        
                        # 캐시 저장 후 반환 (chunking 단계로 가지 않음)
                        self._analysis_cache[cache_key] = reviews
                        return reviews
                except Exception as e:
                    print(f"        ⚠️ Index Scan Error: {e}, Falling back to full scan.")
                    pass # 실패하면 아래 청크 로직으로 넘어감

        # 1. 텍스트가 짧으면 바로 분석
        if len(text) < 5000:
            prompt = f"""
            [Analysis Target: {category} - {title}]
            {text}

            [User Action]
            {action.action}

            Extract legal grounds related to the 'User Action' from the text and respond in JSON.
            
            [Target Schema]
            {{
                "law_name": "{title}",
                "key_clause": "관련 조항 (예: 제3조 제1항) 없으면 빈칸",
                "status": "금지 | 허용 | 조건부 | 중립 | 불명확",
                "summary": "해당 조항의 핵심 내용 요약 (한글 2문장 이내)"
            }}
            If there is no relevant content at all, set the status to '중립'.
            """
            # [MODEL: GPT-4o-mini] 읽어야 할 양이 가장 많은 부분. mini 사용 필수 (비용 절감)
            res = await llm_client.generate(prompt, "", model="gpt-4o-mini", max_tokens=512)
            try:
                data = json_repair.loads(res)
                if data.get('status') != '중립':
                    rev = DocumentReview(**data)
                    rev.url = url
                    reviews.append(rev)
            except:
                pass
            return reviews

        # 2. 텍스트가 길면 분할 처리 (Chunking) - Full Scan
        chunk_size = 4000
        overlap = 300
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size - overlap)]
        
        print(f"      🧩 [Chunking] {title} - {len(chunks)}개 조각으로 분할 분석 중...")

        tasks = []
        for i, chunk in enumerate(chunks):
            prompt = f"""
            [Analysis Target: {category} - {title} (Part {i+1}/{len(chunks)})]
            {chunk}

            [User Action]
            {action.action}

            If there are legal grounds (prohibition, permission, penalty, etc.) related to the 'User Action' in this text chunk, extract them.
            If it's difficult to judge due to broken context, set the status to 'Neutral'.
            
            [Target Schema]
            {{
                "law_name": "{title}",
                "key_clause": "조항 번호",
                "status": "Prohibited | Permitted | Conditional | Neutral",
                "summary": "요약"
            }}
            """
            # [MODEL: GPT-4o-mini] 대량의 Chunk 처리
            tasks.append(llm_client.generate(prompt, "", model="gpt-4o-mini", max_tokens=512))

        results = await asyncio.gather(*tasks)

        for res in results:
            try:
                data = json_repair.loads(res)
                if data.get('status') != 'Neutral':
                     # 중복 제거 (같은 조항이 여러 청크에 걸칠 수 있음)
                     rev = DocumentReview(**data)
                     rev.url = url
                     reviews.append(rev)
            except:
                pass
        
        # [Cache] 결과 저장
        self._analysis_cache[cache_key] = reviews
        return reviews

    async def _extract_evidence(self, raw_data: List[Tuple[str, str, str, str, Any]], action: AtomicAction) -> List[DocumentReview]:
        if not raw_data: return []
        
        doc_count = len(raw_data)
        doc_titles = [f"[{c}] {t}" for c, t, _, _, _ in raw_data[:5]]
        etc_text = f" 외 {doc_count-5}건" if doc_count > 5 else ""

        print(f"\n      📝 [정밀 분석] 총 {doc_count}건의 문건을 전수 조사합니다. (LLM Reading...)")
        print(f"         대상: {', '.join(doc_titles)}{etc_text}")
        
        tasks = []
        valid_reviews = []

        for category, title, text, url, raw_data_item in raw_data:
            if not text or len(text) < 50: continue
            # [Update] 전체 텍스트 분석 요청 (List[DocumentReview] 반환)
            tasks.append(self._analyze_full_text(text, action, category, title, url, raw_data_item))

        if tasks:
            results = await asyncio.gather(*tasks)
            for res_list in results:
                # 결과가 리스트이므로 확장
                valid_reviews.extend(res_list)

        return valid_reviews

    async def _process_action(self, action: AtomicAction) -> List[DocumentReview]:
        print(f"\\n  🎬 [Action 시작] {action.action}")

        # 1. Keyword Generation
        law_names = await self._expand_query(action)
        prec_keywords = await self._generate_prec_keywords(action)
        print(f"    1️⃣  [초기 키워드] 법령: {law_names} | 판례: {prec_keywords}")

        # 1.5 Strategy Planning
        strategy = await self._plan_search(action)
        print(f"    🧠 [전략 수립] {strategy.rationale}")
        print(f"       -> 대상 DB: {strategy.databases} | 핵심어: {strategy.focus_keywords}")

        final_evidence = []

        # 2. Loop (Initial + Retry)
        max_retries = 1
        for attempt in range(max_retries + 1):
            is_retry = attempt > 0
            prefix = "🔄 [재검색]" if is_retry else "🚀 [1차 검색]"
            print(f"    {prefix} 시작...")

            # Search
            raw_data = await self._search_phase(law_names, prec_keywords, action, strategy)

            # Extract (Structured)
            new_reviews = await self._extract_evidence(raw_data, action)
            
            # Deduplicate by law_name + key_clause
            existing_keys = set(f"{r.law_name}-{r.key_clause}" for r in final_evidence)
            for r in new_reviews:
                key = f"{r.law_name}-{r.key_clause}"
                if key not in existing_keys:
                    final_evidence.append(r)
                    existing_keys.add(key)

            # Critique (Needs string for criticism)
            evidence_summary = [f"[{r.status}] {r.law_name} {r.key_clause}: {r.summary}" for r in final_evidence]
            critic_res = await self._critique(action.action, evidence_summary)
            print(f"      🧐 [Critic 평가] {critic_res.get('status')} : {critic_res.get('reason')}")

            if critic_res.get('status') == 'PASS':
                print("      -> 충분한 근거 확보. 검색 종료.")
                break

            if is_retry:
                print("      -> 재검색했으나 여전히 부족함. 종료.")
                break

            # Prepare Retry
            new_kws = critic_res.get('new_keywords', [])
            if new_kws:
                print(f"      -> ⚠️ 부족함! Critic 제안 키워드로 재시도: {new_kws}")
                law_names = [k for k in new_kws if '법' in k or 'Act' in k]
                prec_keywords = [k for k in new_kws if '법' not in k and 'Act' not in k]
                if not law_names and not prec_keywords: break
            else:
                break

        print(f"      -> ✅ 최종 확보된 근거: {len(final_evidence)}건")
        return final_evidence

    async def execute(self, scenario: Scenario, on_log: Optional[Callable[[str], Any]] = None) -> Tuple[LegalEvidence, List[DocumentReview]]:
        async def log(msg):
            if on_log: await on_log(msg)
            
        await log(f"\n[3-1] Investigator: Analyzing '{scenario.name}'...")
        
        # 1. Action 분해 및 검색 전략 수립
        all_reviews = []
        
        for action in scenario.actions:
            await log(f"\n    🧐 Investigating Action: {action.action}")
            
            # (1) 검색 전략 수립
            strategy = await self._plan_search(action)
            await log(f"      📋 검색 전략: {strategy.rationale}")
            
            # (2) 키워드 확장
            keywords = await self._expand_query(action)
            prec_keywords = await self._generate_prec_keywords(action)
            
            # (3) 검색 및 법적 근거 추출 (Retry 로직 포함)
            raw_data = await self._search_phase(keywords, prec_keywords, action, strategy, on_log=on_log)
            
            # Count Types
            cnt_law = sum(1 for r in raw_data if r[0] == 'law')
            cnt_prec = sum(1 for r in raw_data if r[0] == 'prec')
            cnt_adm = sum(1 for r in raw_data if r[0] == 'admrul')
            await log(f"      📊 수집된 자료: 법령 {cnt_law}건, 판례 {cnt_prec}건, 행정규칙 {cnt_adm}건")

            reviews = await self._extract_evidence(raw_data, action)
            
            # (4) 검증 (Critic)
            docs_text = [r.summary for r in reviews]
            critique = await self._critique(action.action, docs_text)
            
            if critique.get("status") == "RETRY":
                await log(f"      🔄 재검색 요청: {critique.get('reason')}")
                # print(f"      🔄 재검색 요청: {critique.get('reason')}")
                new_kws = critique.get("new_keywords", [])
                # 간단히 추가 검색 수행 (Strategy 무시하고 키워드 중심)
                raw_data_retry = await self._search_phase(new_kws, new_kws, action, strategy, on_log=on_log)
                reviews_retry = await self._extract_evidence(raw_data_retry, action)
                reviews.extend(reviews_retry)

            all_reviews.extend(reviews)

        # 중복 제거
        unique_reviews = []
        seen = set()
        for r in all_reviews:
            key = (r.law_name, r.key_clause)
            if key not in seen:
                seen.add(key)
                unique_reviews.append(r)
        
        # [Limit] Hard limit to 50 (Total)
        if len(unique_reviews) > 50:
             await log(f"      ✂️ 전체 수집 자료 {len(unique_reviews)}건 중 상위 50건만 사용하여 분석합니다.")
             unique_reviews = unique_reviews[:50]

        # Format for Auditor
        summary_lines = []
        for r in unique_reviews:
            icon = "🔴" if r.status == 'Prohibited' else "🟢" if r.status == 'Permitted' else "🟡"
            link_md = f"[원문]({r.url})" if r.url else ""
            summary_lines.append(f"{icon} [{r.status}] {r.law_name} {r.key_clause} | {r.summary} {link_md}")
            
        evidence = LegalEvidence(
            relevant_laws=summary_lines,
            summary=f"발견된 법적 근거 {len(unique_reviews)}건"
        )
        await log(f"✅ [Investigator] 총 {len(unique_reviews)}건의 근거 수집 완료.\n")
        return evidence, unique_reviews

investigator = Investigator()
print("✅ Investigator Updated with Detailed Logging & Critic Loop.")

from typing import Optional

# [수정 1] RiskReport 모델에 기본값(default) 추가하여 에러 방지
class RiskReport(BaseModel):
    verdict: str = Field(default="Caution", description="Risk Level: Safe | Caution | Danger")
    summary: str = Field(default="판단 보류", description="Detailed Verdict Summary")
    citation: str = Field(default="구체적 조항 없음", description="Legal Citation")
    key_issues: List[str] = Field(default_factory=list, description="Key legal issues identified")


# [수정 2] Auditor 파싱 로직 강화
class AdversarialDebate:
    """
    Multi-Agent Debate System: Prosecutor vs. Defense -> Judge
    Includes Rebuttal & Reflexion (Self-Correction) phases.
    """

    # [Update] Risk assessment perspective (not legal judgment)
    PROSECUTOR_PROMPT = """
    You are a Risk Assessment Specialist focusing on legal compliance risks.
    Based on the scenario and evidence, identify potential legal risks and compliance issues.
    Language: English.
    
    [Scenario]
    {scenario}

    [Evidence]
    {evidence}
    """

    DEFENSE_PROMPT = """
    You are a Business Innovation Consultant.
    Based on the scenario and evidence, identify opportunities, regulatory exceptions, and mitigation strategies.
    Language: English.

    [Scenario]
    {scenario}
    
    [Evidence]
    {evidence}
    """

    REBUTTAL_PROMPT = """
    You are {role}.
    Critique the opponent's argument logically.
    Opponent Argument:
    {opponent_argument}
    
    Language: English.
    """

    REFLEXION_PROMPT = """
    You are {role}.
    Refine your final argument considering the opponent's rebuttal.
    
    My Original Argument: {my_argument}
    Opponent's Rebuttal: {rebuttal}
    
    Language: English.
    """

    JUDGE_PROMPT = """
    You are a Business Risk Assessment Expert.
    Review the risk analysis and business opportunities to provide a comprehensive risk evaluation report.
    
    [Business Scenario]
    {scenario}
    
    [Risk Assessment]
    {prosecutor_final}
    
    [Opportunity Analysis]
    {defense_final}
    
    Output JSON (MUST be in Korean):
    {{
        "위험도": "안전 | 주의 | 위험",
        "정확도": 0 ~ 100,
        "평가내용": "먼저 분석된 시나리오를 간단히 설명한 후 (1-2문장), 해당 사업 모델의 법적 리스크를 평가하세요. 구체적인 법령을 인용하여 설명하세요. (한글로 작성)",
        "인용근거": ["외국환거래법 제8조", "전자금융거래법 제3조", ...],
        "평가결과": "리스크 우세 | 기회 우세",
        "주요쟁점": ["주요 리스크 요인 1 (한글)", "주요 리스크 요인 2 (한글)"]
    }}
    
    [Important]
    - Use ONLY Korean field names as shown above
    - Start with a brief explanation of the analyzed scenario (1-2 sentences)
    - Focus on business risk assessment, not legal judgment
    - Provide actionable insights for the business
    """

    async def _opening_statements(self, context: str) -> Tuple[str, str]:
        print("    ⚔️ [Round 1] Opening Statements...")
        # [MODEL: GPT-4o-mini] 토론 내용 생성은 Text Gen 능력이면 충분. 비용 절감.
        pros_task = llm_client.generate(self.PROSECUTOR_PROMPT.format(**context), "", model="gpt-4o-mini")
        def_task = llm_client.generate(self.DEFENSE_PROMPT.format(**context), "", model="gpt-4o-mini")
        
        pros_arg, def_arg = await asyncio.gather(pros_task, def_task)
        return pros_arg.strip(), def_arg.strip()

    async def _rebuttal_round(self, pros_arg: str, def_arg: str) -> Tuple[str, str]:
        print("    ⚔️ [Round 2] Rebuttal (Cross-Examination)...")
        # [MODEL: GPT-4o-mini]
        # Prosecutor critiques Defense
        p_rebut_task = llm_client.generate(self.REBUTTAL_PROMPT.format(role="Prosecutor", opponent_argument=def_arg), "", model="gpt-4o-mini")
        # Defense critiques Prosecutor
        d_rebut_task = llm_client.generate(self.REBUTTAL_PROMPT.format(role="Defense Lawyer", opponent_argument=pros_arg), "", model="gpt-4o-mini")

        p_rebut, d_rebut = await asyncio.gather(p_rebut_task, d_rebut_task)
        return p_rebut.strip(), d_rebut.strip()

    async def _reflexion_round(self, pros_arg: str, def_arg: str, p_rebut: str, d_rebut: str) -> Tuple[str, str]:
        print("    🧠 [Round 3] Reflexion (Self-Correction)...")
        # [MODEL: GPT-4o-mini]
        # Prosecutor refines stance based on Defense's rebuttal
        p_final_task = llm_client.generate(self.REFLEXION_PROMPT.format(role="Prosecutor", my_argument=pros_arg, rebuttal=d_rebut), "", model="gpt-4o-mini")
        # Defense refines stance based on Prosecutor's rebuttal
        d_final_task = llm_client.generate(self.REFLEXION_PROMPT.format(role="Defense Lawyer", my_argument=def_arg, rebuttal=p_rebut), "", model="gpt-4o-mini")

        p_final, d_final = await asyncio.gather(p_final_task, d_final_task)
        return p_final.strip(), d_final.strip()

    async def _render_verdict(self, scenario_text: str, p_final: str, d_final: str) -> RiskReport:
        print("    ⚖️ [Judge] Rendering Final Verdict...")
        prompt = self.JUDGE_PROMPT.format(
            scenario=scenario_text,
            prosecutor_final=p_final,
            defense_final=d_final
        )

        # [MODEL: GPT-4o] 판결은 가장 똑똑한 모델이 해야 함. (Final Output)
        response = await llm_client.generate(prompt, "", model="gpt-4o", max_tokens=512)

        try:
            data = json_repair.loads(response)

            # 한국어 필드명 매핑 (LLM이 한국어로 응답)
            risk_level = data.get('위험도', data.get('risk_level', 'Caution'))
            confidence = data.get('정확도', data.get('confidence_score', 0))
            verdict_text = data.get('평가내용', data.get('verdict', '평가 내용 없음'))
            cited = data.get('인용근거', data.get('cited_evidence', []))
            winning = data.get('평가결과', data.get('winning_side', '평가 중'))
            issues = data.get('주요쟁점', data.get('key_issues', []))

            # 인용 근거 포맷팅
            citation_text = "\n".join(cited) if cited else "근거 없음"

            # 위험도 영문 매핑 (프론트엔드 호환)
            risk_map = {'안전': 'Safe', '주의': 'Caution', '위험': 'Danger'}
            risk_level_en = risk_map.get(risk_level, risk_level)

            return RiskReport(
                verdict=risk_level_en,
                summary=f"[{winning}] {verdict_text} (정확도: {confidence}%)",
                citation=citation_text,
                key_issues=issues
            )
        except Exception as e:
            print(f"Judge Error: {e}")
            return RiskReport(
                verdict="Caution", 
                summary=f"평가 생성 중 오류가 발생했습니다: {e}", 
                citation="", 
                key_issues=["시스템 오류"]
            )

    async def execute(self, scenario: Scenario, evidence: LegalEvidence) -> RiskReport:
        evidence_text = "\n".join(evidence.relevant_laws)
        if not evidence_text: evidence_text = "No specific laws found."

        context = {
            "scenario": scenario.model_dump_json(),
            "evidence": evidence_text
        }

        # 1. Opening
        p_arg, d_arg = await self._opening_statements(context)
        print(f"      🗣️ Prosecutor: {p_arg[:100]}...")
        print(f"      🛡️ Defense: {d_arg[:100]}...")

        # 2. Rebuttal
        p_rebut, d_rebut = await self._rebuttal_round(p_arg, d_arg)

        # 3. Reflexion
        p_final, d_final = await self._reflexion_round(p_arg, d_arg, p_rebut, d_rebut)
        print(f"      📝 Pros Final: {p_final[:100]}...")
        print(f"      📝 Def Final: {d_final[:100]}...")

        # 4. Verdict
        return await self._render_verdict(scenario.model_dump_json(), p_final, d_final)

# 인스턴스 업데이트
auditor = AdversarialDebate()
print("✅ Adversarial Debate System (Prosecutor vs Defense vs Judge) Initialized.")

# 8. Run the Pipeline

from typing import AsyncGenerator

async def run_analysis_stream(user_input: str) -> AsyncGenerator[str, None]:
    """API Streaming Response Generator"""
    queue = asyncio.Queue()

    async def log_callback(msg: str):
        await queue.put(json.dumps({"type": "log", "message": msg}) + "\n")

    async def worker():
        try:
            # Init Agents
            structurer = Structurer()
            simulator = Simulator()
            investigator = Investigator()
            auditor = AdversarialDebate()

            await log_callback("모듈 초기화 완료. 분석을 시작합니다...")

            # 1. Structure
            await log_callback("비즈니스 모델 구조화 (Structuring) 진행 중...")
            model = await structurer.execute(user_input)
            await log_callback(f"구조화 완료: {model.project_name}")
            
            # 2. Simulate (Main Scenario)
            await log_callback("규제 샌드박스 시나리오 시뮬레이션 (Simulation) 시작...")
            scenarios = await simulator.execute(model)
            main_scenario = scenarios[0] if scenarios else None
            
            if not main_scenario:
                await queue.put(json.dumps({"type": "error", "message": "시나리오 생성 실패"}) + "\n")
                return

            await log_callback("주요 시나리오 생성 완료.")

            # 3. Investigate (Pass Log Callback)
            await log_callback("법령 데이터베이스 검색 및 분석 (Investigation) 수행 중...")
            evidence, reviews = await investigator.execute(main_scenario, on_log=log_callback)
            await log_callback(f"검토 완료: {len(reviews)}건의 법령/판례 분석됨.")
            
            # 4. Audit
            await log_callback("AI 감사관 및 변호사 토론 (Adversarial Debate) 진행 중...")
            final_report = await auditor.execute(main_scenario, evidence)
            await log_callback("법률 검토 최종 판결 도출 완료.")
            
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
            await queue.put(None) # Sentinel

    # Start worker on background
    asyncio.create_task(worker())

    # Consume logs
    while True:
        item = await queue.get()
        if item is None:
            break
        yield item

async def run_analysis(user_input: str) -> Dict[str, Any]:
    # Legacy wrapper if needed, or for testing
    result = None
    async for chunk in run_analysis_stream(user_input):
        data = json.loads(chunk)
        if data["type"] == "result":
            result = data["data"]
    return result

async def run_demo():
    print("✅ Investigator Updated with Detailed Logging & Critic Loop.")
    print("✅ Adversarial Debate System (Prosecutor vs Defense vs Judge) Initialized.")

    user_input = "빌라나 주택 거주자가 출근한 시간 동안 자신의 빈 주차면을 외부인에게 유료로 대여해주는 IoT 주차 공유 서비스"
    print(f"User Idea: {user_input}")

    print("\n--- Streaming Output ---")
    async for chunk in run_analysis_stream(user_input):
        data = json.loads(chunk)
        if data['type'] == 'log':
            print(f"LOG: {data['message']}")
        elif data['type'] == 'result':
            result = data['data']
            print("\n" + "="*50)
            print("   📢 [FINAL VERDICT] REPORT")
            print("="*50)
            
            verdict = result["verdict"]
            print(f"\n🏆 판결: {verdict.get('verdict')}")
            print(f"📝 요약: {verdict.get('summary')}")
            print(f"\n⚖️ 주요 쟁점:")
            for issue in verdict.get('key_issues', []):
                print(f" - {issue}")
                
            print(f"\n🔗 참고 문헌:")
            for ref in result["references"]:
                print(f" - {ref['title']}: {ref['url']}")

if __name__ == '__main__':
    asyncio.run(run_demo())
