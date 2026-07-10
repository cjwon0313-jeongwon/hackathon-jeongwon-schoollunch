import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime, timedelta  
from zoneinfo import ZoneInfo  
import json 
import re
import requests
from streamlit_autorefresh import st_autorefresh  

st.set_page_config(page_title="급식 예약 시스템", page_icon="🍴", layout="centered")

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

try:
    root_ref = db.reference('/')
    ref = root_ref.child('급식예약')
except Exception as e:
    st.error(f"데이터베이스 연결 실패: {e}")
    st.stop()

try:
    kst_now = datetime.now(ZoneInfo("Asia/Seoul"))
    today_str = kst_now.strftime("%Y-%m-%d")
    last_reset = root_ref.child('설정/마지막리셋날짜').get()
    
    if last_reset != today_str:
        ref.delete()  
        root_ref.child('설정/마지막리셋날짜').set(today_str)  
except Exception as e:
    pass 

MAX_PERSON = 100
ALL_TIMES = ["12:50", "12:55", "13:00", "13:05", "13:10", "13:15", "13:20", "13:25"]

@st.cache_data(ttl=3600)
def get_lunch_menu():
    kst_now = datetime.now(ZoneInfo("Asia/Seoul"))
    
    if kst_now.hour >= 14:
        target_date = kst_now + timedelta(days=1)
    else:
        target_date = kst_now
        
    target_date_str = target_date.strftime("%Y%m%d")
    date_display = target_date.strftime("%m월 %d일")
    
    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "Type": "json",
        "ATPT_OFCDC_SC_CODE": "J10", 
        "SD_SCHUL_CODE": "J100000822", 
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
    else:
        mid = length // 2
        return name[:mid] + "*" + name[mid+1:]

if 'page' not in st.session_state: st.session_state.page = 'login'
if 'student_entry' not in st.session_state: st.session_state.student_entry = ""
if 'name_entry' not in st.session_state: st.session_state.name_entry = ""
if 'toast_msg' not in st.session_state: st.session_state.toast_msg = None

if st.session_state.page == 'login':
    st.title("🍴 태성고 급식 예약 시스템")
    st.subheader("학번과 이름을 입력하여 입장해 주세요.")
    
    student_input = st.text_input("학번 (5자리 예: 10623)", value=st.session_state.student_entry, max_chars=5)
    name_input = st.text_input("이름 (예: 최정원)", value=st.session_state.name_entry)
    
    if st.button("입장하기", use_container_width=True):
        grade = get_grade(student_input)
        if not student_input or not name_input:
            st.error("학번과 이름을 모두 입력해주세요.")
        elif grade not in [1, 2, 3]:
            st.error("올바른 학번(5자리, 1~3학년)을 입력하세요.")
        else:
            st.session_state.student_entry = student_input
            st.session_state.name_entry = name_input
            st.session_state.page = 'reserve'
            st.rerun()

elif st.session_state.page == 'reserve':
    st_autorefresh(interval=5000, key="lunch_data_refresh")

    if st.session_state.toast_msg:
        st.toast(st.session_state.toast_msg, icon="🔔")
        st.session_state.toast_msg = None 

    student = st.session_state.student_entry
    name = st.session_state.name_entry
    grade = get_grade(student)
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("◀ 뒤로가기"):
            all_data = ref.get() if ref.get() else {}
            if student in all_data:
                st.warning("예약이 존재합니다. 먼저 예약을 취소한 후 뒤로가기를 해주세요.")
            else:
                st.session_state.page = 'login'
                st.rerun()
    with col2:
        st.write(f"접속자: **{student} {name} ({grade}학년)**")
        
    st.markdown("---")
    st.title("📅 예약 시간 선택 및 현황")

    lunch_menu, date_display = get_lunch_menu()
    st.info(f"🍱 **{date_display} 점심 메뉴:**\n\n{lunch_menu}")

    all_data = ref.get() if ref.get() else {}
    server_reservations = {t: [] for t in ALL_TIMES}
    
    for s_id, info in all_data.items():
        t = info.get('시간')
        if t in server_reservations:
            server_reservations[t].append({
                "학번": s_id, 
                "이름": info.get('이름', ''),
                "timestamp": info.get('timestamp', 0)
            })

    for t in ALL_TIMES:
        server_reservations[t].sort(key=lambda x: x['timestamp'])

    available_times = []
    for t in ALL_TIMES:
        hour, minute = map(int, t.split(':'))
        time_mins = hour * 60 + minute
        if grade == 1 and time_mins >= 13 * 60 + 10: available_times.append(t)
        elif grade == 2 and time_mins >= 13 * 60: available_times.append(t)
        elif grade == 3 and time_mins >= 12 * 60 + 50: available_times.append(t)

    if not available_times:
        st.error("선택 가능한 예약 시간이 없습니다.")
    else:
        is_reserved = student in all_data
        if is_reserved:
            my_time = all_data[student].get('시간')
            st.success(f"✅ **{name}**님은 현재 **{my_time}** 시간대에 예약되어 있습니다.")

        selected_time = st.selectbox("원하는 예약 시간을 선택하세요.", available_times)
        
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("🚀 예약하기", use_container_width=True):
                if not can_reserve(grade):
                    st.error("아직 해당 학년의 예약 시간이 아닙니다.")
                elif is_reserved:
                    st.error("이미 예약 내역이 존재합니다. 변경을 원하시면 취소 후 다시 예약해주세요.")
                elif len(server_reservations[selected_time]) >= MAX_PERSON:
                    st.error("선택하신 시간대는 이미 마감되었습니다.")
                else:
                    ref.child(student).set({
                        "이름": name, 
                        "시간": selected_time,
                        "timestamp": datetime.now(ZoneInfo("Asia/Seoul")).timestamp()
                    })
                    st.session_state.toast_msg = f"🎉 {selected_time} 급식 예약이 완료되었습니다!"
                    st.rerun()
                    
        with btn_col2:
            if st.button("❌ 예약 취소", use_container_width=True):
                if is_reserved:
                    ref.child(student).delete()
                    st.session_state.toast_msg = "🛑 급식 예약이 정상적으로 취소되었습니다."
                    st.rerun()
                else:
                    st.error("예약된 내역이 없습니다.")

    st.markdown("### 📊 실시간 예약 현황판")
    st.caption("※ 5초마다 자동으로 새로고침되어 다른 사람의 예약 현황이 실시간 반영됩니다.")

    for t in ALL_TIMES:
        hour, minute = map(int, t.split(':'))
        time_mins = hour * 60 + minute
        if grade == 1 and time_mins < 13 * 60 + 10: continue
        if grade == 2 and time_mins < 13 * 60: continue
        if grade == 3 wins = hour * 60 + minute
        if grade == 3 and time_mins < 12 * 60 + 50: continue

        people_list = server_reservations[t]
        people_count = len(people_list)
        status = congestion(people_count)
        
        label = f"⏰ {t}  |  인원: {people_count:3d}/{MAX_PERSON}명  |  상태: {status}"
        with st.expander(label):
            if not people_list:
                st.write("└ 📪 예약자가 없습니다.")
            else:
                for idx, person in enumerate(people_list, 1):
                    masked = mask_name(person['이름'])
                    st.write(f"└ **{idx}.** {person['학번']}   {masked}")
