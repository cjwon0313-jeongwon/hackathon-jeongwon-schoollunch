import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime
from zoneinfo import ZoneInfo  # ✨ 대한민국 시간(KST) 계산용 내장 라이브러리
import json 
from streamlit_autorefresh import st_autorefresh  # ✨ 실시간 화면 동기화 도구

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

# ✨ [추가 기능 3] 밤 12시(자정) 자동 일괄 취소 시스템
try:
    # 한국 시간(KST) 기준으로 오늘 날짜 구하기 (서버 시차 문제 완벽 해결)
    kst_now = datetime.now(ZoneInfo("Asia/Seoul"))
    today_str = kst_now.strftime("%Y-%m-%d")
    
    # 데이터베이스에 기록된 마지막 리셋 날짜 확인
    last_reset = root_ref.child('설정/마지막리셋날짜').get()
    
    # 날짜가 바뀌었다면 자정이 지난 것이므로 예약 데이터 통째로 삭제
    if last_reset != today_str:
        ref.delete()  # 기존 예약 전체 삭제
        root_ref.child('설정/마지막리셋날짜').set(today_str)  # 리셋 날짜를 오늘로 갱신
except Exception as e:
    pass # 리셋 과정에서 오류가 나더라도 로그인/예약 기능은 정상 작동하도록 예외 처리

# 3. 상수 정의 및 핵심 함수
MAX_PERSON = 100
ALL_TIMES = ["12:50", "12:55", "13:00", "13:05", "13:10", "13:15", "13:20", "13:25"]

def get_grade(student_id):
    if len(student_id) != 5 or not student_id.isdigit():
        return None
    return int(student_id[0])

def can_reserve(grade):
    return True # 상시 예약 가능 상태 유지

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

# 4. 세션 상태 관리 (화면 전환 및 팝업 메시지 제어)
if 'page' not in st.session_state: st.session_state.page = 'login'
if 'student_entry' not in st.session_state: st.session_state.student_entry = ""
if 'name_entry' not in st.session_state: st.session_state.name_entry = ""
if 'toast_msg' not in st.session_state: st.session_state.toast_msg = None

# 5. UI 및 기능 구현
# --- [첫 번째 화면: 로그인] ---
if st.session_state.page == 'login':
    st.title("🍴 급식 예약 시스템")
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

# --- [두 번째 화면: 예약 및 실시간 현황판] ---
elif st.session_state.page == 'reserve':
    # ✨ [추가 기능 2] 5초마다 화면을 백그라운드에서 새로고침하여 타인의 예약 현황을 실시간 동기화
    st_autorefresh(interval=5000, key="lunch_data_refresh")

    # ✨ [추가 기능 1] 예약/취소 성공 시 화면에 예쁜 팝업 알림 띄우기
    if st.session_state.toast_msg:
        st.toast(st.session_state.toast_msg, icon="🔔")
        st.session_state.toast_msg = None # 알림 표시 후 초기화

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

    all_data = ref.get() if ref.get() else {}
    server_reservations = {t: [] for t in ALL_TIMES}
    for s_id, info in all_data.items():
        t = info.get('시간')
        if t in server_reservations:
            server_reservations[t].append({"학번": s_id, "이름": info.get('이름', '')})

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
        selected_time = st.selectbox("원하는 예약 시간을 선택하세요.", available_times)
        
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("🚀 예약하기", use_container_width=True):
                if not can_reserve(grade):
                    st.error("아직 해당 학년의 예약 시간이 아닙니다.")
                elif student in all_data:
                    st.error("이미 예약 내역이 존재합니다.")
                elif len(server_reservations[selected_time]) >= MAX_PERSON:
                    st.error("선택하신 시간대는 이미 마감되었습니다.")
                else:
                    ref.child(student).set({"이름": name, "시간": selected_time})
                    # 예약 완료 알림 메시지를 세션에 저장 후 리런
                    st.session_state.toast_msg = f"🎉 {selected_time} 급식 예약이 완료되었습니다!"
                    st.rerun()
                    
        with btn_col2:
            if st.button("❌ 예약 취소", use_container_width=True):
                if student in all_data:
                    ref.child(student).delete()
                    # 취소 완료 알림 메시지를 세션에 저장 후 리런
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
