import os
import json
import asyncio
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.async_api import async_playwright

# 1. Firebase 인증 (GitHub Secrets에서 가져온 정보를 사용합니다)
firebase_json = os.environ.get('FIREBASE_CONFIG_JSON')
if not firebase_json:
    print("오류: FIREBASE_CONFIG_JSON 환경 변수가 설정되지 않았습니다.")
    exit(1)

# 서비스 계정 키로 Firebase 초기화
cred = credentials.Certificate(json.loads(firebase_json))
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()

# 웹사이트(index.html)와 약속된 데이터 저장 경로 ID
APP_ID = "recruitment-portal-v3"

async def scrape_site(browser, inst_id, url):
    """
    각 기관의 웹사이트에 접속하여 채용 정보를 수집하는 함수입니다.
    """
    # 한국 브라우저처럼 위장하여 해외 IP 차단을 최소화합니다.
    page = await browser.new_page(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        locale="ko-KR"
    )
    
    try:
        print(f"[{inst_id}] 접속 중: {url}")
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(5)  # 자바스크립트로 로딩되는 공고를 기다립니다.
        
        found_jobs = []
        
        # --- 기관별 수집 로직 ---
        # 1. 건강보험심사평가원 (HIRA)
        if inst_id == 'hira':
            # 공고 목록 아이템을 찾습니다 (실제 사이트 구조에 맞춰 튜닝)
            items = await page.query_selector_all(".recruitment-item, tr, .job-list-item")
            for item in items[:10]:
                title_el = await item.query_selector("a, .title")
                if title_el:
                    title = (await title_el.inner_text()).strip()
                    # 특정 제목(사전예고)에 대한 링크 처리
                    link = "https://www.hira.or.kr/re/recruit/recruitAdList.do?pgmid=HIRAA040078000000" if "사전예고" in title else url
                    
                    found_jobs.append({
                        "instId": inst_id,
                        "title": title,
                        "postedDate": datetime.now().strftime("%Y-%m-%d"),
                        "endDate": "2026-12-31", # 실제 날짜 추출 로직 추가 가능
                        "type": "사전공고" if "사전예고" in title else "공고",
                        "link": link
                    })

        # 2. 국민건강보험공단 (NHIS)
        elif inst_id == 'nhis':
            # 국민건강보험공단 수집 로직 예시
            items = await page.query_selector_all("tr, .list-item")
            for item in items[:5]:
                title_el = await item.query_selector("td.subject, a, .tit")
                if title_el:
                    title = (await title_el.inner_text()).strip()
                    found_jobs.append({
                        "instId": inst_id,
                        "title": title,
                        "postedDate": datetime.now().strftime("%Y-%m-%d"),
                        "endDate": "2026-04-30",
                        "type": "정규직",
                        "link": url
                    })

        return found_jobs
    except Exception as e:
        print(f"[{inst_id}] 수집 중 오류 발생: {e}")
        return []
    finally:
        await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        # 수집할 기관 리스트
        targets = [
            {"id": "hira", "url": "https://hira.recruitlab.co.kr/app/recruitment-announcement/list"},
            {"id": "nhis", "url": "https://nhis.kpcice.kr/Include/PackageAppo.html?rRound=1"},
            {"id": "neca", "url": "https://neca.applyin.co.kr/jobs/"}
        ]
        
        all_collected_jobs = []
        for target in targets:
            jobs = await scrape_site(browser, target['id'], target['url'])
            all_collected_jobs.extend(jobs)
        
        # 2. Firestore에 데이터 쓰기 (규칙 준수)
        if all_collected_jobs:
            # 기존 데이터를 초기화하거나 업데이트하기 위해 배치 작업 사용
            batch = db.batch()
            
            # 공고 저장 경로: artifacts/{APP_ID}/public/data/jobs/
            jobs_path = db.collection('artifacts').document(APP_ID).collection('public').document('data').collection('jobs')
            
            # 기존에 있던 임시 공고들을 지우고 새로 쓰거나, 문서 ID를 지정해서 덮어씁니다.
            for i, job in enumerate(all_collected_jobs):
                doc_ref = jobs_path.document(f"job_{i}")
                batch.set(doc_ref, job)
            
            # 마지막 수집 시간 저장 (index.html에서 이 시간을 보여줍니다)
            meta_ref = db.collection('artifacts').document(APP_ID).collection('public').document('data').collection('metadata').document('sync')
            batch.set(meta_ref, {"lastSync": datetime.now().isoformat()})
            
            batch.commit()
            print(f"총 {len(all_collected_jobs)}개의 공고가 성공적으로 업데이트되었습니다.")
        else:
            print("수집된 공고가 없습니다.")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
