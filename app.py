import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime, timedelta  
from zoneinfo import ZoneInfo  
import json 
import re
import requests
from streamlit_autorefresh import st_autorefresh  

# 1. 페이지 기본 설정 및 디자인
st.set_page_config(page_title="급식 예약 시스템", page_icon="🍴", layout="centered")

# 2. Firebase 최초 1회 초기화 (Secrets 금고 모드)
if not firebase_admin._apps:
    try:
        key_dict = json.loads(st.secrets["firebase_key"])
        cred = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://hackathon-jeongwon-default-rtdb.asia-southeast1.firebasedatabase.app/' 
        })
    except Exception as e:
        st.error(f"Firebase 초기화 실패: {e}")
        st.stop()

# Firebase 데이터베이스 참조
try:
    root_ref = db.reference('/')
    ref = root_ref.child('급식예약')
except Exception as e:
    st.error(f"데이터베이스 연결 실패: {e}")
    st.stop()

# 자정 자동 리셋 시스템
try:
    kst_now = datetime.now(ZoneInfo("Asia/Seoul"))
    today_str = kst_now.strftime("%Y-%m-%d")
    last_reset = root_ref.child('설정/마지막리셋날짜').get()
    
    if last_reset != today_str:
        ref.delete()  
        root_ref.child('설정/마지막리셋날짜').set(today_str)  
except Exception as e:
    pass 

# 3. 상수 정의 및 핵심 함수
MAX_PERSON = 100
ALL_TIMES = ["12:50", "12:55", "13:00", "13:05", "13:10", "13:15", "13:20", "13:25"]

# ✨ [수정] '오늘/내일' 텍스트를 빼고 깔끔하게 날짜만 반환
@st.cache_data(ttl=3600)
def get_lunch_menu():
    kst_now = datetime.now(ZoneInfo("Asia/Seoul"))
    
    # 오후 2시(14시) 이후에는 내일 급식을 조회하고, 그 전에는 오늘 급식을 조회
    if kst_now.hour >= 14:
        target_date = kst_now + timedelta(days=1)
    else:
        target_date = kst_now
        
    target_date_str = target_date.strftime("%Y%m%d")
    date_display = target_date.strftime("%m월 %d일") # 예: "07월 10일"
    
    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "Type": "json",
        "ATPT_OFCDC_SC_CODE": "J10", # 경기도교육청
        "SD_SCHUL_CODE": "J100000822", # 태성고등학교
        "MLSV_YMD": target_date_str
    }
    
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        if "mealServiceDietInfo" in data:
            row = data["mealServiceDietInfo"][1]["row"][0]
            menu_str = row["DDISH_NM"]
            
            menu_str = menu_str.replace("<br/>", ", ")
            menu_str = re.sub(r'\([0-9\.]+\)', '', menu_str)
            return menu_str.replace("*", "").strip(), date_display
        else:
            return "급식 정보가 없거나 주말/휴일입니다.", date_display
    except Exception as e:
        return "급식 정보를 불러오지 못했습니다.", date_display

def get_grade(student_id):
    if len(student_id) != 5 or not student_id.isdigit():
        return None
    return int(student_id[0])

def can_reserve(grade):
    return True 

def congestion(count):
    if count <= 30: return "🟢 여유"
    elif count <= 70: return "🟡 보통"
    else: return "🔴 혼잡"

def mask_name(name):
    length = len(name)
    if length <= 1: return name
    elif length == 2: return name[0] + "*"
