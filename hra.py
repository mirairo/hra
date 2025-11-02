import streamlit as st
import pandas as pd
from supabase import create_client, Client
import os
from datetime import datetime, date
import io

# ========================================
# 페이지 설정
# ========================================
st.set_page_config(
    page_title="기업용 인사회계 시스템",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========================================
# Supabase 연결 설정
# ========================================
@st.cache_resource
def init_supabase():
    """Supabase 클라이언트 초기화"""
    url = os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY", "")
    
    if not url or not key:
        st.error("⚠️ Supabase 연결 정보가 없습니다. .streamlit/secrets.toml 파일을 확인하세요.")
        st.stop()
    
    try:
        supabase: Client = create_client(url, key)
        return supabase
    except Exception as e:
        st.error(f"❌ 데이터베이스 연결 실패: {str(e)}")
        st.stop()

supabase = init_supabase()

# ========================================
# 세션 상태 초기화
# ========================================
if 'user' not in st.session_state:
    st.session_state.user = None
if 'profile' not in st.session_state:
    st.session_state.profile = None

# ========================================
# 인증 함수
# ========================================
def sign_up(email, password, name):
    """회원가입"""
    try:
        # Supabase Auth로 사용자 생성
        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
        })
        
        if response.user:
            # user_profiles 테이블에 메타데이터 추가
            supabase.table('user_profiles').insert({
                'id': response.user.id,
                'email': email,
                'name': name,
                'role': 'user',
                'status': 'pending'
            }).execute()
            
            return True, "회원가입이 완료되었습니다! 이메일을 확인하여 인증을 완료하세요."
        else:
            return False, "회원가입 실패"
            
    except Exception as e:
        error_msg = str(e)
        if "already registered" in error_msg.lower():
            return False, "이미 등록된 이메일입니다."
        return False, f"회원가입 오류: {error_msg}"

def sign_in(email, password):
    """로그인"""
    try:
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if response.user:
            # 사용자 프로필 조회
            profile = supabase.table('user_profiles').select("*").eq('id', response.user.id).single().execute()
            
            if profile.data:
                # 승인 상태 확인
                if profile.data['status'] != 'approved':
                    supabase.auth.sign_out()
                    return False, None, "관리자 승인 대기중입니다. 승인 후 로그인할 수 있습니다."
                
                return True, {'user': response.user, 'profile': profile.data}, None
            else:
                supabase.auth.sign_out()
                return False, None, "사용자 프로필을 찾을 수 없습니다."
        
        return False, None, "로그인 실패"
        
    except Exception as e:
        error_msg = str(e)
        if "Invalid login credentials" in error_msg:
            return False, None, "이메일 또는 비밀번호가 일치하지 않습니다."
        elif "Email not confirmed" in error_msg:
            return False, None, "이메일 인증이 필요합니다. 받은편지함을 확인하세요."
        return False, None, f"로그인 오류: {error_msg}"

def sign_out():
    """로그아웃"""
    try:
        supabase.auth.sign_out()
        st.session_state.user = None
        st.session_state.profile = None
    except:
        pass

def check_session():
    """세션 확인"""
    try:
        user = supabase.auth.get_user()
        if user:
            profile = supabase.table('user_profiles').select("*").eq('id', user.id).single().execute()
            if profile.data and profile.data['status'] == 'approved':
                return {'user': user, 'profile': profile.data}
        return None
    except:
        return None

# ========================================
# 인증 페이지
# ========================================
def show_auth_page():
    """로그인/회원가입 페이지"""
    st.title("💼 기업용 인사회계 시스템")
    st.markdown("---")
    
    tab1, tab2 = st.tabs(["🔐 로그인", "📝 회원가입"])
    
    with tab1:
        st.subheader("로그인")
        
        with st.form("login_form"):
            email = st.text_input("이메일", placeholder="example@company.com")
            password = st.text_input("비밀번호", type="password")
            submit = st.form_submit_button("🔓 로그인", use_container_width=True)
            
            if submit:
                if not email or not password:
                    st.error("이메일과 비밀번호를 입력하세요.")
                else:
                    with st.spinner("로그인 중..."):
                        success, data, error = sign_in(email, password)
                        if success:
                            st.session_state.user = data['user']
                            st.session_state.profile = data['profile']
                            st.success(f"환영합니다, {data['profile']['name']}님!")
                            st.rerun()
                        else:
                            st.error(error)
        
        st.markdown("---")
        st.info("""
        **로그인 안내**
        - 회원가입 후 이메일 인증 필요
        - 관리자 승인 후 로그인 가능
        """)
    
    with tab2:
        st.subheader("회원가입")
        
        with st.form("signup_form"):
            name = st.text_input("이름*", placeholder="홍길동")
            email = st.text_input("이메일*", placeholder="example@company.com")
            password = st.text_input("비밀번호*", type="password", help="최소 6자 이상")
            password_confirm = st.text_input("비밀번호 확인*", type="password")
            
            submit = st.form_submit_button("✅ 회원가입", use_container_width=True)
            
            if submit:
                if not name or not email or not password:
                    st.error("모든 필수 항목을 입력하세요.")
                elif password != password_confirm:
                    st.error("비밀번호가 일치하지 않습니다.")
                elif len(password) < 6:
                    st.error("비밀번호는 최소 6자 이상이어야 합니다.")
                else:
                    with st.spinner("회원가입 중..."):
                        success, message = sign_up(email, password, name)
                        if success:
                            st.success(message)
                            st.info("""
                            **다음 단계:**
                            1. ✉️ 이메일 확인
                            2. ✅ 이메일 인증 링크 클릭
                            3. ⏳ 관리자 승인 대기
                            4. 🔓 승인 후 로그인
                            """)
                        else:
                            st.error(message)
        
        st.markdown("---")
        st.warning("""
        **회원가입 절차**
        1. ✅ 회원정보 입력 및 가입
        2. ✉️ 이메일 인증 (받은편지함 확인)
        3. ⏳ 관리자 승인 대기
        4. 🔓 승인 후 로그인 가능
        """)

# ========================================
# 사용자 관리 (관리자 전용)
# ========================================
def user_management():
    """사용자 관리"""
    st.header("👤 사용자 관리")
    
    if st.session_state.profile['role'] != 'admin':
        st.warning("⚠️ 관리자만 접근 가능한 메뉴입니다.")
        return
    
    tab1, tab2 = st.tabs(["승인 대기", "사용자 목록"])
    
    with tab1:
        st.subheader("⏳ 승인 대기 중인 사용자")
        
        try:
            pending = supabase.table('user_profiles').select("*").eq('status', 'pending').execute()
            
            if pending.data:
                for user in pending.data:
                    # 이메일 인증 상태 확인
                    auth_user = supabase.auth.admin.get_user_by_id(user['id'])
                    email_confirmed = auth_user.user.email_confirmed_at is not None if auth_user.user else False
                    
                    with st.expander(f"📧 {user['name']} ({user['email']})"):
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            st.write(f"**이름:** {user['name']}")
                            st.write(f"**이메일:** {user['email']}")
                            st.write(f"**가입일:** {user['created_at'][:10]}")
                            st.write(f"**이메일 인증:** {'✅ 완료' if email_confirmed else '❌ 미인증'}")
                        
                        with col2:
                            if email_confirmed:
                                if st.button("✅ 승인", key=f"approve_{user['id']}"):
                                    supabase.table('user_profiles').update({
                                        'status': 'approved',
                                        'approved_at': datetime.now().isoformat(),
                                        'approved_by': st.session_state.user.id
                                    }).eq('id', user['id']).execute()
                                    st.success(f"{user['name']}님이 승인되었습니다!")
                                    st.rerun()
                                
                                if st.button("❌ 거부", key=f"reject_{user['id']}"):
                                    supabase.table('user_profiles').update({
                                        'status': 'rejected'
                                    }).eq('id', user['id']).execute()
                                    st.warning(f"{user['name']}님의 가입이 거부되었습니다.")
                                    st.rerun()
                            else:
                                st.caption("⏳ 이메일 인증 대기중")
            else:
                st.info("승인 대기 중인 사용자가 없습니다.")
                
        except Exception as e:
            st.error(f"데이터 조회 오류: {str(e)}")
    
    with tab2:
        st.subheader("📋 전체 사용자 목록")
        
        try:
            users = supabase.table('user_profiles').select("*").execute()
            
            if users.data:
                df = pd.DataFrame(users.data)
                
                status_map = {
                    'pending': '⏳ 대기중',
                    'approved': '✅ 승인됨',
                    'rejected': '❌ 거부됨'
                }
                df['status_kr'] = df['status'].map(status_map)
                
                display_df = df[['email', 'name', 'role', 'status_kr', 'created_at']].copy()
                display_df.columns = ['이메일', '이름', '권한', '상태', '가입일']
                display_df['가입일'] = pd.to_datetime(display_df['가입일']).dt.strftime('%Y-%m-%d')
                
                st.dataframe(display_df, use_container_width=True, height=400)
                st.info(f"📊 총 {len(df)}명의 사용자가 등록되어 있습니다.")
            else:
                st.warning("등록된 사용자가 없습니다.")
                
        except Exception as e:
            st.error(f"사용자 목록 조회 오류: {str(e)}")

# ========================================
# 유틸리티 함수
# ========================================
def format_number(num):
    """숫자를 천단위 콤마로 포맷팅"""
    if pd.isna(num):
        return "0"
    return f"{int(num):,}"

def format_currency(num):
    """통화 형식으로 포맷팅"""
    if pd.isna(num):
        return "₩0"
    return f"₩{int(num):,}"

def execute_query(table_name, operation="select", data=None, filters=None):
    """Supabase 쿼리 실행"""
    try:
        if operation == "select":
            query = supabase.table(table_name).select("*")
            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)
            response = query.execute()
            return pd.DataFrame(response.data) if response.data else pd.DataFrame()
        
        elif operation == "insert":
            response = supabase.table(table_name).insert(data).execute()
            return response.data
        
        elif operation == "update":
            if not filters:
                raise ValueError("Update operation requires filters")
            query = supabase.table(table_name).update(data)
            for key, value in filters.items():
                query = query.eq(key, value)
            response = query.execute()
            return response.data
        
        elif operation == "delete":
            if not filters:
                raise ValueError("Delete operation requires filters")
            query = supabase.table(table_name).delete()
            for key, value in filters.items():
                query = query.eq(key, value)
            response = query.execute()
            return response.data
            
    except Exception as e:
        st.error(f"데이터베이스 오류: {str(e)}")
        return None

def upload_excel_data(uploaded_file, table_name, column_mapping):
    """엑셀 파일을 읽어서 데이터베이스에 업로드"""
    try:
        df = pd.read_excel(uploaded_file)
        df = df.rename(columns=column_mapping)
        
        for col in df.columns:
            if 'date' in col.lower():
                df[col] = pd.to_datetime(df[col]).dt.strftime('%Y-%m-%d')
        
        df = df.fillna('')
        records = df.to_dict('records')
        success_count = 0
        
        for record in records:
            result = execute_query(table_name, "insert", record)
            if result:
                success_count += 1
        
        return success_count, len(records)
    
    except Exception as e:
        st.error(f"엑셀 업로드 오류: {str(e)}")
        return 0, 0

# ========================================
# 기존 모듈들 (직원/급여/거래처/매출매입/무역/대시보드)
# hra.py의 기존 코드와 동일
# ========================================

# 직원 관리
def employee_management():
    st.header("👥 직원 관리")
    st.info("직원 관리 기능 (기존 hra.py 코드 사용)")

# 급여 관리
def payroll_management():
    st.header("💰 급여 관리")
    st.info("급여 관리 기능 (기존 hra.py 코드 사용)")

# 거래처 관리
def client_management():
    st.header("🏢 거래처 관리")
    st.info("거래처 관리 기능 (기존 hra.py 코드 사용)")

# 매출/매입 관리
def sales_purchase_management():
    st.header("📊 매출/매입 관리")
    st.info("매출/매입 관리 기능 (기존 hra.py 코드 사용)")

# 무역 관리
def trade_management():
    st.header("🌏 무역 관리")
    st.info("무역 관리 기능 (기존 hra.py 코드 사용)")

# 대시보드
def dashboard():
    st.header("📊 대시보드")
    st.info("대시보드 (기존 hra.py 코드 사용)")

# ========================================
# 메인 애플리케이션
# ========================================
def main():
    # 세션 확인
    if not st.session_state.user:
        session = check_session()
        if session:
            st.session_state.user = session['user']
            st.session_state.profile = session['profile']
    
    # 로그인 확인
    if not st.session_state.user or not st.session_state.profile:
        show_auth_page()
        return
    
    # 승인 상태 확인
    if st.session_state.profile['status'] != 'approved':
        st.warning("⏳ 관리자 승인 대기중입니다.")
        if st.button("🚪 로그아웃"):
            sign_out()
            st.rerun()
        return
    
    # 사이드바 메뉴
    st.sidebar.title("💼 인사회계 시스템")
    st.sidebar.markdown(f"**환영합니다, {st.session_state.profile['name']}님!**")
    st.sidebar.markdown(f"권한: {st.session_state.profile['role']}")
    st.sidebar.markdown("---")
    
    # 메뉴 구성
    menu_items = ["🏠 대시보드", "👥 직원 관리", "💰 급여 관리", "🏢 거래처 관리", 
                  "📊 매출/매입 관리", "🌏 무역 관리"]
    
    # 관리자 메뉴 추가
    if st.session_state.profile['role'] == 'admin':
        menu_items.append("👤 사용자 관리")
    
    menu = st.sidebar.radio("메뉴 선택", menu_items, label_visibility="collapsed")
    
    st.sidebar.markdown("---")
    
    # 로그아웃 버튼
    if st.sidebar.button("🚪 로그아웃", use_container_width=True):
        sign_out()
        st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.info(f"""
    **시스템 정보**
    - 사용자: {st.session_state.profile['email']}
    - 버전: 2.0.0 (Auth)
    - 인증: Supabase Auth
    """)
    
    # 페이지 라우팅
    if menu == "🏠 대시보드":
        dashboard()
    elif menu == "👥 직원 관리":
        employee_management()
    elif menu == "💰 급여 관리":
        payroll_management()
    elif menu == "🏢 거래처 관리":
        client_management()
    elif menu == "📊 매출/매입 관리":
        sales_purchase_management()
    elif menu == "🌏 무역 관리":
        trade_management()
    elif menu == "👤 사용자 관리":
        user_management()

if __name__ == "__main__":
    main()
