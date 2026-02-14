"""
National Law API Client for MIRI Legal Advisory System
한국 법제처 API 클라이언트
"""
import re
import asyncio
import aiohttp
import xmltodict
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
from typing import Any, List, Dict, Tuple
from config import MAX_SEARCH_RESULTS_PER_SOURCE


class NationalLawAPI:
    def __init__(self, api_id="jaeyeongm34", base_url="http://www.law.go.kr"):
        self.base_url = base_url
        self.api_id = api_id
        self.is_mock = not bool(self.api_id)
        self._cache = {}
        self.semaphore = asyncio.Semaphore(5)  # 동시 요청 제한

    def _force_list(self, data: Any) -> List[Any]:
        if not data: return []
        if isinstance(data, list): return data
        return [data]

    async def _fetch(self, url: str) -> Dict[str, Any]:
        if url in self._cache:
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
            "display": kwargs.get('display', MAX_SEARCH_RESULTS_PER_SOURCE),
            "nw": 3  # 기본값: 현행 법령만 검색
        }
        params.update(kwargs)  # JO 등 추가 파라미터 병합

        # 디버깅: 실제 요청 URL 파라미터 출력
        if target == 'prec':
            jo_param = kwargs.get('JO', '')
            print(f"      📡 [API 요청] {target.upper()} 검색 | Query='{query}' | JO='{jo_param}'")
        else:
            print(f"      📡 [API 요청] {target.upper()} 검색 | Query='{query}'")

        query_string = urlencode(params, doseq=True)
        url = f"{self.base_url}/DRF/{endpoint}?{query_string}"

        data = await self._fetch(url)

        # eflaw 지원 추가
        root_map = {'law': 'LawSearch', 'eflaw': 'LawSearch', 'admrul': 'AdmRulSearch', 'prec': 'PrecSearch'}
        root_key = root_map.get(target, 'LawSearch')

        try:
            search_data = data.get(root_key, {})
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
        
        # 2. 개정 이력 제거
        text = re.sub(r'<(개정|신설|전문개정|타법개정|일부개정|폐지)\s+[\d.,\s]+>', '', text)
        
        # 3. 참고 정보 제거
        text = re.sub(r'\[(전문개정|개정|신설|타법개정|일부개정|폐지)\s+[\d.,\s]+\]', '', text)
        
        # 4. 장/절/관 헤더 제거
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
            
            title = root.get('기본정보', {}).get('법령명_한글', '')
            text_parts.append(f"== {title} ==\n")

            jo_list = self._force_list(root.get('조문', {}).get('조문단위', []))
            for jo in jo_list:
                jo_content = self._clean_html(jo.get('조문내용', ''))
                item_text = [jo_content]
                
                hang_list = self._force_list(jo.get('항', []))
                for hang in hang_list:
                    h_content = self._clean_html(hang.get('항내용', ''))
                    if h_content:
                        item_text.append(f"  {h_content}")
                    
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
            
            jo_list = self._force_list(root.get('조문', {}).get('조문단위', []))
            if jo_list:
                for jo in jo_list:
                    jo_content = self._clean_html(jo.get('조문내용', ''))
                    text_parts.append(jo_content)
                    
                    hang_list = self._force_list(jo.get('항', []))
                    for hang in hang_list:
                        h_content = self._clean_html(hang.get('항내용', ''))
                        if h_content: text_parts.append(f"  {h_content}")
            else:
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
        """XML 구조를 활용해 법령의 [조문/별표] 리스트를 추출"""
        articles = []
        
        # 1. 법령 (Law)
        if '법령' in data:
            root = data['법령']
            
            # (1) 조문 파싱
            jo_list = self._force_list(root.get('조문', {}).get('조문단위', []))
            for jo in jo_list:
                jo_type = jo.get('조문여부', '')
                if jo_type == '전문':
                    continue
                
                jo_text = self._clean_html(jo.get('조문내용', ''))
                
                if not jo_text or len(jo_text) < 5:
                    continue
                
                match = re.match(r'(제\d+조의?\d?)\(?([^)]*)\)?', jo_text)
                title_id = match.group(1) if match else jo_text[:10]
                
                parts = [jo_text]
                
                hang_list = self._force_list(jo.get('항', []))
                for hang in hang_list:
                    h_content = self._clean_html(hang.get('항내용', ''))
                    if h_content: parts.append(f"  {h_content}")
                    
                    ho_list = self._force_list(hang.get('호', []))
                    for ho in ho_list:
                        ho_content = self._clean_html(ho.get('호내용', ''))
                        if ho_content: parts.append(f"    {ho_content}")
                        
                        mok_list = self._force_list(ho.get('목', []))
                        for mok in mok_list:
                            m_content = self._clean_html(mok.get('목내용', ''))
                            if m_content: parts.append(f"      {m_content}")
                
                full_text = "\n".join(parts)
                articles.append({'id': title_id, 'content': full_text})

            # (2) 별표 파싱
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

        # 2. 행정규칙 (AdmRul)
        elif '행정규칙' in data:
            root = data['행정규칙']
            jo_list = self._force_list(root.get('조문', {}).get('조문단위', []))
            if jo_list:
                for jo in jo_list:
                    jo_content = self._clean_html(jo.get('조문내용', ''))
                    
                    match = re.match(r'(제\d+조(?:의\d+)?)\(?([^)]*)\)?', jo_content)
                    if match:
                        title_id = f"{match.group(1)}{' ' + match.group(2) if match.group(2) else ''}"
                    else:
                        match_num = re.match(r'^(\d+\.|[가-힣]\.)\s*(.*)', jo_content)
                        if match_num:
                            title_id = f"{match_num.group(1)} {match_num.group(2)[:10]}..."
                        else:
                            title_id = jo_content[:20].strip() or "조문"

                    parts = [jo_content]
                    hang_list = self._force_list(jo.get('항', []))
                    for hang in hang_list:
                        h = self._clean_html(hang.get('항내용', ''))
                        if h: parts.append(f"  {h}")
                        
                        ho_list = self._force_list(hang.get('호', []))
                        for ho in ho_list:
                            ho_content = self._clean_html(ho.get('호내용', ''))
                            if ho_content:
                                parts.append(f"    {ho_content}")
                    
                    articles.append({'id': title_id, 'content': "\n".join(parts)})
            
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

        # 3. 판례 (Prec)
        elif '판례' in data:
            root = data['판례']
            issue = self._clean_html(root.get('판시사항', ''))
            if issue:
                articles.append({'id': '판시사항', 'content': issue})
            
            summary = self._clean_html(root.get('판결요지', ''))
            if summary:
                articles.append({'id': '판결요지', 'content': summary})
            else:
                content = self._clean_html(root.get('판례내용', ''))
                if content:
                    articles.append({'id': '판례내용', 'content': content[:3000] + "...(생략)"})
        
        return articles

        return self._parse_xml_to_text(data), view_url, data

    async def ai_search(self, query: str, search_scope: int = 0) -> List[Dict[str, Any]]:
        """
        Intelligent Law Search (aiSearch) - 통합 법령/규칙 검색
        search_scope: 0=법령조문, 1=법령별표/서식, 2=행정규칙조문, 3=행정규칙별표
        Returns: List of dicts with 'law_name', 'article_title', 'content', 'link'
        """
        if self.is_mock: return []

        endpoint = "lawSearch.do"
        params = {
            "OC": self.api_id,
            "target": "aiSearch",
            "type": "XML",
            "search": search_scope,
            "query": query,
            "display": 20, 
            "page": 1
        }
        
        # print(f"      📡 [AI Search] Query='{query}' | Scope={search_scope}")
        
        query_string = urlencode(params, doseq=True)
        url = f"{self.base_url}/DRF/{endpoint}?{query_string}"
        
        data = await self._fetch(url)
        
        results = []
        try:
            root = data.get('aiSearch', {})
            # aiSearch results are usually under <법령조문> for scope 0, let's check for others dynamically
            # XML parsing (xmltodict) puts repeating elements in a list, or a single dict if only one.
            # We look for common result keys.
            
            candidates = []
            
            # Case 0: Law Articles
            if '법령조문' in root:
                candidates.extend(self._force_list(root['법령조문']))
            # Case 2: AdmRul Articles (Guessing key name, usually matches the item type)
            # If the API unifies them under '법령조문' even for scope 2, we are good. 
            # If not, checking typical AdmRul keys.
            if '행정규칙조문' in root:
                candidates.extend(self._force_list(root['행정규칙조문']))
                
            for item in candidates:
                # Extract fields
                # Common fields observed: <법령명>, <조문제목>, <조문내용>
                
                # Law Name
                law_name = item.get('법령명') or item.get('행정규칙명') 
                if isinstance(law_name, dict): law_name = law_name.get('#text', '') # CDATA handling if simple dict

                # Article Title/Num
                art_num = item.get('조문번호', '?')
                art_title = item.get('조문제목')
                if isinstance(art_title, dict): art_title = art_title.get('#text', '')
                
                # Content
                content_raw = item.get('조문내용', '')
                if isinstance(content_raw, dict): content_raw = content_raw.get('#text', '')
                content = self._clean_html(content_raw)
                
                # Link construction (Standard View Link)
                # aiSearch items have <법령일련번호>, <조문일련번호> etc.
                # Standard link: http://www.law.go.kr/DRF/lawService.do?target=law&OC={id}&ID={law_id}&type=HTML...
                # Simpler to just use what we have or generic link
                # Found <법령ID> in result.
                law_id = item.get('법령ID', '')
                link = f"http://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={item.get('법령일련번호', '')}"
                
                results.append({
                    'law_name': str(law_name),
                    'article_title': f"제{art_num}조({str(art_title)})",
                    'content': content,
                    'link': link,
                    'raw': item
                })
                
            print(f"      🤖 [AI Search] '{query}' (Scope {search_scope}) -> {len(results)}건 발견")
            return results
            
        except Exception as e:
            print(f"      ⚠️ AI Search Parse Error: {e}")
            return []


# Global instance
law_api = NationalLawAPI(api_id="jaeyeongm34")
print("✅ NationalLawAPI Initialized (with 'eflaw' support).")
