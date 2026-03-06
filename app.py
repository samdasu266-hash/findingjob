import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time

st.set_page_config(page_title="공공기관 채용 모아보기", layout="wide")
st.title("🎯 핵심 공공기관 채용 공고 모니터링")
st.write("의료기관평가인증원, 국민건강보험공단, 건강보험심사평가원, 한국보건의료연구원(NECA)")

# 가상 크롬 브라우저 세팅
@st.cache_resource
def get_driver():
    options = Options()
    options.add_argument('--headless') # 화면에 크롬 창을 띄우지 않고 백그라운드에서 실행
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    # 크롬 드라이버 자동 설치 및 적용
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def scrape_ats_site(url, agency_name):
    try:
        driver = get_driver()
        driver.get(url)
        # 핵심! 자바스크립트로 데이터가 채워질 때까지 3초간 여유롭게 기다려줌
        time.sleep(3) 
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        jobs = []
        # 채용 대행사마다 구조가 달라서, 링크(a 태그) 안의 텍스트를 광범위하게 탐색
        links = soup.find_all('a')
        
        for link in links:
            text = link.get_text(strip=True)
            # 텍스트에 채용 관련 키워드가 포함되어 있으면 수집
            if len(text) > 4 and any(keyword in text for keyword in ['채용', '공고', '모집', '안내', '직원']):
                href = link.get('href', '')
                # 상대 경로인 경우 절대 경로로 변환
                if href.startswith('/'):
                    domain = url.split('/')[0] + "//" + url.split('/')[2]
                    href = domain + href
                elif href == '#' or 'javascript' in href:
                    href = url # 자바스크립트 클릭 버튼이면 그냥 메인 주소 연결
                    
                jobs.append({'기관': agency_name, '공고명': text, '바로가기': href if href.startswith('http') else url})
        
        if not jobs:
            return [{'기관': agency_name, '공고명': '진행중인 공고가 없거나 홈페이지 접속 확인 필요', '바로가기': url}]
            
        # 중복 제거 로직
        unique_jobs = list({job['공고명']: job for job in jobs}.values())
        return unique_jobs[:5] # 기관별 최신 5개만 
        
    except Exception as e:
        return [{'기관': agency_name, '공고명': '보안 차단 (수동 확인 필요)', '바로가기': url}]

# 실행 버튼
if st.button("🔄 4개 기관 최신 공고 불러오기"):
    with st.spinner("가상 브라우저로 대행사 보안을 뚫고 수집 중이야... (약 10~15초 소요)"):
        all_jobs = []
        all_jobs.extend(scrape_ats_site("https://hira.recruitlab.co.kr/app/recruitment-announcement/list", "건강보험심사평가원"))
        all_jobs.extend(scrape_ats_site("https://koiha.recruiter.co.kr/career/job", "의료기관평가인증원"))
        all_jobs.extend(scrape_ats_site("https://nhis.kpcice.kr/Include/", "국민건강보험공단"))
        all_jobs.extend(scrape_ats_site("https://neca.applyin.co.kr/jobs/", "한국보건의료연구원(NECA)"))
        
        df = pd.DataFrame(all_jobs)
        
        st.dataframe(
            df,
            column_config={"바로가기": st.column_config.LinkColumn("링크")},
            hide_index=True,
            use_container_width=True
        )
else:
    st.info("위 버튼을 눌러 최신 공고를 한 번에 긁어와 봐!")
