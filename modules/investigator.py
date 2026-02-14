"""
Investigator Module - Legal Research and Evidence Collection
법률 조사 및 증거 수집 모듈
"""
import re
import asyncio
import json_repair
from typing import List, Dict, Tuple, Optional, Callable, Any

from models import SearchStrategy, AtomicAction, Scenario, LegalEvidence, DocumentReview
from llm_client import llm_client
from law_api import law_api
from config import MAX_ANALYSIS_DOCS


class Investigator:
    """
    Expert Investigator with Self-Correction (Critic) & Action-Based Search & Strategic Planning
    """
    
    STRATEGY_PROMPT = """
    Analyze the legal nature of the following action/situation to decide the optimal search strategy.

    [Action/Situation]
    {action}

    [Database Characteristics]
    - law (Acts, Decrees): For legal prohibitions, permissions, obligations, civil/criminal liabilities, and penalties.
    - admrul (Administrative Rules): For specific criteria, monetary limits, procedures, and detailed guidelines.
    - prec (Precedents): For case law interpretations, similar dispute resolutions, and judicial standards.

    [Instructions]
    1. Determine if this is: business regulation, contract law, criminal law, civil dispute, labor law, or general legal matter
    2. If criminal/civil liability is involved, prioritize 'law' and 'prec'
    3. If specific procedures or quantitative standards matter, include 'admrul'
    4. For disputes or interpretation issues, include 'prec'
    5. List databases in order of importance
    6. Add 'Focus Keywords' for comprehensive search coverage
    
    Output JSON:
    {{
        "rationale": "Reason for this strategy (English)",
        "databases": ["law", "admrul", "prec"],
        "focus_keywords": ["KoreanKeyWord1", "KoreanKeyWord2"]
    }}
    
    [Important]
    "focus_keywords" MUST be in KOREAN.
    """

    EXPANSION_PROMPT = """
    User situation/action: '{action}' (Target: {object})
    
    Extract 3-5 SPECIFIC LEGAL KEYWORDS for finding relevant Korean laws.
    
    [Strategy]
    Analyze the legal domain:
    1. What laws GOVERN or REGULATE this action/situation?
    2. What LEGAL RIGHTS, OBLIGATIONS, or LIABILITIES are involved?
    3. What SPECIFIC LEGAL TERMS are used in Korean law for this matter?
    4. Consider: civil law, criminal law, special laws, labor law, commercial law, etc.
    
    [Examples - Be SPECIFIC and DOMAIN-APPROPRIATE]
    ✓ Good (Specific Legal Terms):
      * "Unfair dismissal" → ["부당해고", "근로기준", "해고예고"]
      * "Breach of contract" → ["계약위반", "손해배상", "채무불이행"]
      * "Personal injury accident" → ["불법행위", "과실", "손해배상"]
      * "Consumer fraud" → ["소비자보호", "기만행위", "약관규제"]
      * "Currency exchange platform" → ["외국환", "전자금융", "환전"]
      * "Privacy violation" → ["개인정보", "정보통신", "명예훼손"]
      * "Real estate dispute" → ["부동산", "임대차", "소유권"]
    
    ✗ Bad (Too generic or non-legal):
      * "Contract issue" → ["계약", "문제"] ← TOO VAGUE
      * "Money problem" → ["돈", "금전"] ← NOT LEGAL TERMS
    
    [Important]
    - Keywords MUST be in KOREAN
    - Focus on LEGAL TERMS that appear in statutes, not everyday language
    - Think about civil/criminal liability, rights, obligations, prohibitions
    - Single nouns without particles (No '을', '를', '의')
    - Return JSON array of 3-5 strings
    
    Output format: ["법률용어1", "법률용어2", "법률용어3"]
    """

    SELECTOR_PROMPT = """
    You are an expert 'Legal Researcher' responsible for selecting relevant laws and precedents.
    
    [Task]
    Review the provided list of law/precedent titles and select ALL items that are RELEVANT to the user's situation.
    
    [Selection Criteria]
    1. Direct Relevance: The title explicitly mentions the issue (e.g., "unfair dismissal", "hit-and-run").
    2. Broader Relevance: The law governs the domain (e.g., "Labor Standards Act" for firing).
    3. Be Generous: If in doubt, INCLUDE it. It's better to analyze more than to miss critical evidence.
    
    [Input Format]
    User will provide:
    - User Action/Scenario
    - List of Candidates (numbered)

    [Output Format]
    Return ONLY a JSON array of the exact strings (names) selected from the list.
    Example: ["Title 1", "Title 3"]
    
    If NONE are relevant, return: []
    """

    KEYWORD_GEN_PROMPT = """
    User Situation/Action: "{action}"
    Infer 5 core legal keywords for comprehensive case law and precedent search.
    
    [Important]
    **Keywords MUST be in KOREAN** (Hangul).
    The search engine only understands Korean legal terms.

    Focus on:
    1. Specific illegal acts or violations (e.g., "무단사용", "무등록영업", "사기")
    2. Legal concepts for disputes (e.g., "손해배상", "계약해제", "부당이득")
    3. Rights and obligations (e.g., "퇴직금", "보증금반환", "위자료")
    4. Procedural terms if relevant (e.g., "가처분", "중재", "조정")
    
    Examples by type:
    - Business: "무등록", "불법영업", "인허가위반"
    - Contract: "채무불이행", "계약해제", "손해배상"
    - Labor: "부당해고", "임금체불", "근로기준위반"
    - Real Estate: "명도", "임대차보호", "보증금"
    - Criminal: "사기", "횡령", "배임"
    
    Output as a JSON list of Korean strings: ["키워드1", "키워드2", ...]
    """

    AI_QUERY_PROMPT = """
    [Task] Generate effective search queries for the 'Intelligent Bureau of Legislation Search System' (AI Search).
    
    [User Action/Scenario]
    {action}
    
    [Instructions]
    - The AI Search system handles natural language but performs best with "KEY PHRASES" that describe the legal violation or topic.
    - Generate 2-3 queries.
    - Queries MUST be in KOREAN.
    - Example: "뺑소니 처벌", "음주운전 면허취소 기준", "개인정보 유출 과태료"
    
    Output JSON: ["query1", "query2"]
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
        # [MODEL: GPT-4o-mini] 검색 전략 수립 (비용 절감)
        response = await llm_client.generate("", prompt, model="gpt-4o-mini", max_tokens=512)
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

    async def _generate_ai_queries(self, action: AtomicAction) -> List[str]:
        # Generate natural language queries for AI Search
        prompt = self.AI_QUERY_PROMPT.format(action=action.action)
        response = await llm_client.generate("", prompt, model="gpt-4o-mini", max_tokens=256)
        try:
            return json_repair.loads(response)[:3]
        except:
            return [action.action]

    async def _expand_query(self, action: AtomicAction) -> List[str]:
        # Legacy Keyword Extraction (still useful for Precedents)
        prompt = self.EXPANSION_PROMPT.format(action=f"{action.action}", object=action.object)
        response = await llm_client.generate("", prompt, model="gpt-4o-mini", max_tokens=256)
        try:
            parsed = json_repair.loads(response)
            return self._clean_keywords(parsed if isinstance(parsed, list) else [str(parsed)])[:5]
        except:
            return []

    async def _generate_prec_keywords(self, action: AtomicAction) -> List[str]:
        # 2. 판례/정밀 검색용 구체적 키워드 추출
        prompt = self.KEYWORD_GEN_PROMPT.format(action=action.action)
        response = await llm_client.generate(prompt, "", model="gpt-4o-mini", max_tokens=256)
        try:
            parsed = json_repair.loads(response)
            return self._clean_keywords(parsed if isinstance(parsed, list) else [str(parsed)])[:5]
        except:
            return []

    async def _select_best_candidates(self, candidates: List[Dict[str, Any]], action_text: str) -> List[Dict[str, Any]]:
        if not candidates: return []
        
        # [OPTIMIZATION] LLM에게 너무 많은 후보를 주면 처리 못함. 상위 30개로 제한
        if len(candidates) > 30:
            print(f"      ⚠️ [Selector] 후보 {len(candidates)}개 → 30개로 제한")
            candidates = candidates[:30]

        # LLM에게 후보군 전달하여 선택 요청
        candidate_names = [c.get('법령명한글') or c.get('행정규칙명') for c in candidates]
        
        print(f"      📋 [Selector] {len(candidates)}개 후보에서 선택 중...")
        print(f"      📜 [후보 목록]:")
        for i, name in enumerate(candidate_names[:10], 1):  # 처음 10개만 출력
            print(f"         {i}. {name}")
        if len(candidate_names) > 10:
            print(f"         ... 외 {len(candidate_names) - 10}개")
        
        system_prompt = self.SELECTOR_PROMPT
        user_input_prompt = f"""
Candidate Count: {len(candidate_names)}

[User Action/Scenario]
{action_text}

[List of Candidates]
{chr(10).join([f"{i+1}. {name}" for i, name in enumerate(candidate_names)])}
"""
        
        # print(f"      📋 [DEBUG] Selector Prompt:\n{user_input_prompt[:500]}...\n")  # 프롬프트 일부 출력 (Verbose)
        
        try:
            # [MODEL: GPT-4o-mini] 목록 중 선택(Selection)은 mini도 잘함
            response = await llm_client.generate(system_prompt, user_input_prompt, model="gpt-4o-mini", max_tokens=1024)
            
            print(f"      🔍 [Selector] LLM 전체 응답:\n{response}\n")  # 전체 응답 출력
            
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
            
            if not final_items:
                print(f"      ⚠️ [Selector] 매칭 실패. 상위 10개 사용 (Fallback)")
                return candidates[:10]
            
            return final_items
        except Exception as e:
            print(f"      ⚠️ Selector Error: {e}")
            return candidates[:10]

    async def _critique(self, action_text: str, evidence: List[str]) -> Dict[str, Any]:
        summary = "\n".join(evidence) if evidence else "None"
        prompt = self.CRITIC_PROMPT.format(action=action_text, evidence_summary=summary)
        # [MODEL: GPT-4o-mini] Critic 평가 (비용 절감)
        response = await llm_client.generate(prompt, "", model="gpt-4o-mini", max_tokens=512)
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

        # [Phase 1] AI Search (Law & AdmRul)
        if 'law' in target_dbs or 'admrul' in target_dbs:
            # 1. Generate Intelligent Queries
            # If keywords are provided (e.g., from critic retry), use them, otherwise generate new AI queries.
            ai_queries = keywords if keywords else await self._generate_ai_queries(action)
            await log(f"      📡 [AI 검색] 질의어: {ai_queries}")
            
            if not ai_queries: ai_queries = [action.action]
            
            search_tasks = []
            for q in ai_queries:
                if 'law' in target_dbs:
                    search_tasks.append(law_api.ai_search(q, 0)) # Scope 0: Law
                if 'admrul' in target_dbs:
                    search_tasks.append(law_api.ai_search(q, 2)) # Scope 2: AdmRul

            if search_tasks:
                results_list = await asyncio.gather(*search_tasks)
                
                cnt_total = 0
                for results in results_list:
                    for item in results:
                        # item keys: law_name, article_title, content, link, raw
                        # Use 'ai_result' category to skip complex structure parsing
                        collected_raw_data.append(('ai_result', f"{item['law_name']} {item['article_title']}", item['content'], item['link'], item['raw']))
                        found_law_titles.append(item['law_name'])
                        cnt_total += 1
                
                await log(f"        -> AI 법령/규칙 검색 완료: {cnt_total}개 조항 확보")

        # [Phase 2] Precedent Search (Legacy)
        # AI Search API (search=0,1,2,3) generally covers Statutes/Rules. Precedents ('prec') often require separate handling.
        if 'prec' in target_dbs:
            await log(f"      📡 판례 검색 수행 중...")
            
            prec_tasks = []
            
            # Use found law titles as filter (JO) if available, plus global search
            unique_law_titles = list(set(found_law_titles))
            
            # Strategy 1: Law + Keyword
            for title in unique_law_titles[:2]: 
                for kw in prec_keywords:
                    prec_tasks.append(law_api.search_list('prec', query=kw, JO=title, display=30))

            # Strategy 2: Global Keyword
            for kw in prec_keywords:
                prec_tasks.append(law_api.search_list('prec', query=kw, display=30))

            prec_results = []
            if prec_tasks:
                prec_results = await asyncio.gather(*prec_tasks)

            prec_candidates = []
            seen_prec_ids = set()
            
            for res in prec_results:
                for item in res: 
                    p_id = item.get('판례일련번호')
                    if p_id and p_id not in seen_prec_ids:
                        seen_prec_ids.add(p_id)
                        item['법령명한글'] = f"[판례] {item.get('판례내용') or item.get('사건명')}"
                        prec_candidates.append(item)
            
            # Selector for Precedents
            if prec_candidates:
                target_precs = await self._select_best_candidates(prec_candidates[:30], action.action)
            else:
                target_precs = []
            
            await log(f"      👉 판례 본문 조회: {len(target_precs)}건")

            prec_fetch_tasks = [law_api.get_content_from_item(item) for item in target_precs]
            if prec_fetch_tasks:
                prec_contents = await asyncio.gather(*prec_fetch_tasks)
                for item, (content, url, raw_data) in zip(target_precs, prec_contents):
                    title = item.get('법령명한글')
                    collected_raw_data.append(('prec', title, content, url, raw_data))

        # [Limit] Max Documents
        if len(collected_raw_data) > MAX_ANALYSIS_DOCS:
            await log(f"자료 최적화: 수집된 {len(collected_raw_data)}건 중 상위 {MAX_ANALYSIS_DOCS}건 분석 진행")
            collected_raw_data = collected_raw_data[:MAX_ANALYSIS_DOCS]

        return collected_raw_data

    async def _analyze_full_text(self, text: str, action: AtomicAction, category: str, title: str, url: str, raw_data: Any) -> List[DocumentReview]:
        """
        문서 전체를 순회하며 핵심 내용 추출
        category='ai_result' 인 경우 이미 조항 단위이므로 바로 분석.
        """
        # [Cache]
        if category == 'ai_result':
             # Use article title + law name hash or link
             # raw_data is the item dict from ai_search
             doc_id = f"AI_{title}_{url}"
        else:
             doc_id = law_api._get_unique_id(raw_data)
             if doc_id == "Unknown": doc_id = f"{title}_{url}"
            
        cache_key = (action.action, doc_id)
        
        if cache_key in self._analysis_cache:
            cached_reviews = self._analysis_cache[cache_key]
            for r in cached_reviews: r.url = url
            return cached_reviews

        reviews = []
        full_action_context = f"[{action.actor}] {action.action} (대상: {action.object})"
        
        # [Optimization] If ai_result, skip structure parsing/index scanning
        if category == 'ai_result':
            # Direct Analysis
            prompt = f"""
            [Analysis Target: {title}]
            {text}

            [User Action Context]
            {full_action_context}

            Extract legal grounds related to the 'User Action Context' from this specific article.
            
            [Target Schema]
            {{
                "law_name": "{title.split(' ')[0]}", 
                "key_clause": "{title.split(' ')[1] if ' ' in title else '조항'}",
                "status": "Prohibited | Permitted | Conditional | Neutral | Ambiguous",
                "summary": "해당 조항의 핵심 내용 요약 (한글 2문장 이내)"
            }}
            If irrelevant, set status to 'Neutral'.
            """
            res = await llm_client.generate(prompt, "Analyze this article.", model="gpt-4o-mini", max_tokens=512)
            try:
                data = json_repair.loads(res)
                if data.get('status') != 'Neutral':
                    rev = DocumentReview(**data)
                    rev.url = url
                    reviews.append(rev)
            except:
                pass
            
            self._analysis_cache[cache_key] = reviews
            return reviews

        # Existing Logic for Legacy (Full Text / Precedents)
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
                
                print(f"        -> 분석 대상 행위: {action.action[:100]}...")  # 디버깅용
                
                prompt = f"""
You are analyzing a legal document to find relevant articles for a specific business action.

[Document: {title}]
[Table of Contents]
{toc_text}

[Business Action to Analyze]
{full_action_context}

Task:
1. Review the table of contents above
2. Identify which articles are MOST relevant to the business action
3. Select up to 5 article indices (numbers only)
4. If NO articles seem relevant, return an empty list: []

Output Format (JSON array of numbers):
[0, 5, 12]

Important:
- Only select articles that are DIRECTLY related to the business action
- If unsure or no clear match, return []
- Be strict in selection to avoid irrelevant articles
"""
                
                # [MODEL: GPT-4o-mini] 목차 스캐닝
                # System Prompt에 지침을 넣고, User Input은 간단하게 "분석 시작" 정도로 처리
                res = await llm_client.generate(prompt, "Analyze the specific business action against the table of contents.", model="gpt-4o-mini", max_tokens=256)
                try:
                    selected_indices = json_repair.loads(res)
                    if not isinstance(selected_indices, list): selected_indices = []
                    
                    print(f"        -> LLM 선별 결과: {selected_indices}")
                    
                    target_articles = [articles[i] for i in selected_indices if isinstance(i, int) and 0 <= i < len(articles)]
                    
                    if target_articles:
                        print(f"        -> 선별된 조항: {[a['id'] for a in target_articles]}")
                        # [NEW] 선별된 조항을 개별적으로 분석 (chunking 방지)
                        for art in target_articles:
                            art_prompt = f"""
                            [Analysis Target: {category} - {title}]
                            [{art['id']}]
                            {art['content']}

                            [User Action Context]
                            {full_action_context}

                            Extract legal grounds related to the 'User Action Context' from the text and respond in JSON.
                            
                            [Target Schema]
                            {{
                                "law_name": "{title}",
                                "key_clause": "{art['id']}",
                                "status": "Prohibited | Permitted | Conditional | Neutral | Ambiguous",
                                "summary": "해당 조항의 핵심 내용 요약 (한글 2문장 이내)"
                            }}
                            If there is no relevant content at all, set the status to 'Neutral'.
                            """
                            art_res = await llm_client.generate(art_prompt, "Analyze this article.", model="gpt-4o-mini", max_tokens=512)
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
                    else:
                        # [Critical Fix] 인덱스 스캔 결과 "관련 없음"이면 과감하게 Skip (무작정 청킹 방지)
                        print(f"        🚫 [Index Scan] '{title}'에서 관련 조항 발견되지 않음 -> 분석 종료.")
                        self._analysis_cache[cache_key] = []
                        return []
                except Exception as e:
                    print(f"        ⚠️ Index Scan Error: {e}, Falling back to chunking.")
                    pass # 실패하면 아래 청크 로직으로 넘어감

        # 1. 텍스트가 짧으면 바로 분석
        if len(text) < 5000:
            prompt = f"""
            [Analysis Target: {category} - {title}]
            {text}

            [User Action Context]
            {full_action_context}

            Extract legal grounds related to the 'User Action Context' from the text and respond in JSON.
            
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
            res = await llm_client.generate(prompt, "Analyze this text for legal risks.", model="gpt-4o-mini", max_tokens=512)
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

            [User Action Context]
            {full_action_context}

            If there are legal grounds (prohibition, permission, penalty, etc.) related to the 'User Action Context' in this text chunk, extract them.
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
            tasks.append(llm_client.generate(prompt, "Analyze this chunk for legal relevance.", model="gpt-4o-mini", max_tokens=512))

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
        print(f"\n  🎬 [Action 시작] {action.action}")

        # 1. Keyword Generation
        # law_names = await self._expand_query(action) # Legacy unused
        
        # New AI Queries used inside _search_phase
        prec_keywords = await self._generate_prec_keywords(action)
        print(f"    1️⃣  [판례 키워드]: {prec_keywords}")

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
            # Pass new_kws from critic as 'keywords' argument to _search_phase for AI search override
            current_ai_keywords = critic_res.get('new_keywords', []) if is_retry else []
            raw_data = await self._search_phase(current_ai_keywords, prec_keywords, action, strategy)

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
                # The `current_ai_keywords` will be set in the next loop iteration.
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
            await log(f"\n    🔍 법률 쟁점 분석 중: {action.action}")
            
            # (1) 검색 전략 수립
            strategy = await self._plan_search(action)
            await log(f"검색 전략 수립 완료: {strategy.rationale}")
            
            # (2) 키워드 확장 (AI Search 활용을 위해 초기 키워드는 비워둠 -> _search_phase에서 생성)
            keywords = []
            prec_keywords = await self._generate_prec_keywords(action)
            
            # (3) 검색 및 법적 근거 추출 (Retry 로직 포함)
            raw_data = await self._search_phase(keywords, prec_keywords, action, strategy, on_log=on_log)
            
            # Count Types (ai_result integrated)
            cnt_ai = sum(1 for r in raw_data if r[0] == 'ai_result')
            cnt_prec = sum(1 for r in raw_data if r[0] == 'prec')
            
            await log(f"법령 자료 수집: AI검색 {cnt_ai}건 (법령/규칙), 판례 {cnt_prec}건")

            reviews = await self._extract_evidence(raw_data, action)
            
            # (4) 검증 (Critic)
            docs_text = [r.summary for r in reviews]
            critique = await self._critique(action.action, docs_text)
            
            if critique.get("status") == "RETRY":
                await log(f"추가 검색 필요: {critique.get('reason')}")
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
            unique_reviews = unique_reviews[:50]
            
        evidence_summary = [f"- {r.law_name} {r.key_clause}: {r.summary}" for r in unique_reviews]
        return LegalEvidence(relevant_laws=evidence_summary, summary=""), unique_reviews
