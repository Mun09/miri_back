import asyncio
import json
from miri import NationalLawAPI, Investigator, AtomicAction

async def test_search_logic():
    print("🚀 [TEST] Starting Search & Parsing Logic Test...\n")

    # 1. Initialize API & Investigator
    law_api = NationalLawAPI(api_id="jaeyeongm34") # Use your ID
    investigator = Investigator()
    
    # 2. Define a Test Action (Skip Scenario Generation)
    test_action = AtomicAction(
        actor="Self",
        action="주거지 전용 주차장 공유 (유료 대여)",
        object="주차장법"
    )

    print(f"🧪 Test Action: {test_action.action}\n")

    # 3. Test Direct Search (Law - Enforcement Rule often has tables)
    keywords = ["주차장법 시행규칙"]
    print(f"📡 Searching Law (Targeting Tables): {keywords}")
    
    # Simulate _search_phase logic manually
    law_candidate_tasks = [law_api.search_list('law', kw, display=2) for kw in keywords]
    results = await asyncio.gather(*law_candidate_tasks)
    
    candidates = []
    for res in results:
        candidates.extend(res)
    
    print(f"   -> Found {len(candidates)} candidates.")
    
    if not candidates:
        print("❌ No candidates found. Check API Key or Network.")
        return

    target_item = candidates[0]
    title = target_item.get('법령명한글')
    print(f"   -> Top Candidate: {title}")

    # 4. Test Content Fetch & Parsing
    print(f"\n📥 Fetching Content & Parsing Structure...")
    content, url, raw_data = await law_api.get_content_from_item(target_item)
    
    # 5. Verify Structure (Articles & Attached Tables)
    print(f"\n🔍 [DEBUG] Raw XML Keys: {raw_data.get('법령', {}).keys()}")
    articles = law_api._parse_law_structure(raw_data)
    print(f"   -> Parsed {len(articles)} articles/tables.")
    
    print("\n🔍 [Sample Parsed Data]")
    for i, art in enumerate(articles[:3]):
        print(f"   [{i+1}] ID: {art['id']}")
        print(f"       Content Snippet: {art['content'][:50].replace('\n', ' ')}...")
    
    # Check for '별표' (Attached Table)
    byeol_tables = [a for a in articles if "[별표]" in a['id']]
    if byeol_tables:
        print(f"\n🌟 Found {len(byeol_tables)} Attached Tables (별표)!")
        print(f"   -> Example: {byeol_tables[0]['id']}")
    else:
        print("\n⚠️ No Attached Tables found (Available fields depend on XML).")

    # 6. Test Cache Logic (Simulated)
    print("\n⚡ Testing Cache Logic...")
    
    # First Analysis
    print("   [1] First Analysis Call...")
    reviews1 = await investigator._analyze_full_text(content, test_action, 'law', title, url, raw_data)
    print(f"       -> Generated {len(reviews1)} reviews.")

    # Second Analysis (Should hit cache)
    print("   [2] Second Analysis Call (Same Action)...")
    # We need to access the private cache to verify, or rely on print logs if enabled
    # But since we are calling the method, we can measure time or check object identity if returned from cache
    
    import time
    start = time.time()
    reviews2 = await investigator._analyze_full_text(content, test_action, 'law', title, url, raw_data)
    end = time.time()
    
    print(f"       -> Generated {len(reviews2)} reviews.")
    print(f"       -> Time taken: {end - start:.4f}s (Should be near 0)")

    if reviews1 and reviews2 and reviews1[0] is reviews2[0]:
         print("   ✅ Cache Verified (Same Object Returned)")
    elif (end - start) < 0.1:
         print("   ✅ Cache Query Fast (Likely Hit)")
    else:
         print("   ⚠️ Cache Miss or Slow")

if __name__ == "__main__":
    asyncio.run(test_search_logic())
