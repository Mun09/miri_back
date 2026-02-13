import asyncio
import xml.dom.minidom
from miri import NationalLawAPI

async def inspect_raw_xml():
    print("🚀 Fetching Raw XML for '주차장법 시행규칙'...\n")
    api = NationalLawAPI(api_id="jaeyeongm34")
    
    # 1. Search List
    items = await api.search_list('law', '주차장법 시행규칙', display=1)
    if not items:
        print("❌ Law not found.")
        return

    target = items[0]
    link = target.get('법령상세링크')
    print(f"🔗 Link: {link}")

    # 2. Fetch Detail XML (Manual Fetch to see raw text)
    full_url = f"{api.base_url}{link}".replace('type=HTML', 'type=XML')
    print(f"📡 Requesting: {full_url}")
    
    # We use the internal fetch but return raw text for inspection
    # Assuming _fetch returns a dictionary (parsed XML), we might need to verify what _fetch actually returns.
    # In miri.py, _fetch uses xmltodict.parse, so it returns a Dict.
    # To see the structure, we can just print the Dict keys or reconvert to XML.
    
    data_dict = await api._fetch(full_url)
    
    # 3. Print Structure (Keys)
    print("\n🔍 [Root Keys]:", data_dict.keys())
    
    if '법령' in data_dict:
        law_root = data_dict['법령']
        print("🔍 [법령 Keys]:", law_root.keys())
        
        # Check '조문' structure
        if '조문' in law_root:
            jo = law_root['조문']
            print(f"🔍 [조문 Keys]: {jo.keys()}")
            # Print first article structure
            if '조문단위' in jo:
                first_jo = jo['조문단위'][0] if isinstance(jo['조문단위'], list) else jo['조문단위']
                print(f"   📄 [제1조 구조]: {first_jo.keys()}")

        # Check '별표' structure
        if '별표' in law_root:
            byeol = law_root['별표']
            print(f"🔍 [별표 Type]: {type(byeol)}")
            if isinstance(byeol, list):
                print(f"   🌟 [별표 List Size]: {len(byeol)}")
                print(f"   🌟 [First Item Keys]: {byeol[0].keys()}")
                print(f"   🌟 [First Item Title]: {byeol[0].get('별표제목')}")
            else:
                print(f"   🌟 [별표 Keys]: {byeol.keys()}")

    else:
        print("⚠️ '법령' tag not found in root.")

if __name__ == "__main__":
    asyncio.run(inspect_raw_xml())
