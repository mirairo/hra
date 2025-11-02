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
# RLS 정책 비활성화 안내
# ========================================
def show_rls_warning():
    """RLS 정책 수정 안내"""
    st.error("""
    ### ⚠️ Supabase RLS 정책 오류 감지
    
    `user_profiles` 테이블의 RLS 정책에서 무한 재귀가 발생하고 있습니다.
    
    **해결 방법:**
    
    1. Supabase Dashboard 접속
    2. Table Editor → user_profiles 테이블 선택
    3. RLS (Row Level Security) 탭으로 이동
    4. 모든 정책 삭제 또는 아래 정책으로 교체
    
    **추천 정책 (SQL Editor에서 실행):**
    
    ```sql
    -- 기존 정책 모두 삭제
    DROP POLICY IF EXISTS "Users can view own profile" ON user_profiles;
    DROP POLICY IF EXISTS "Users can update own profile" ON user_profiles;
    DROP POLICY IF EXISTS "Enable insert for authenticated users" ON user_profiles;
    
    -- RLS 활성화
    ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
    
    -- 새 정책 생성 (무한 재귀 방지)
    CREATE POLICY "Allow authenticated insert"
    ON user_profiles FOR INSERT
    TO authenticated
    WITH CHECK (auth.uid() = id);
    
    CREATE POLICY "Allow users to read own profile"
    ON user_profiles FOR SELECT
    TO authenticated
    USING (auth.uid() = id);
    
    CREATE POLICY "Allow users to update own profile"
    ON user_profiles FOR UPDATE
    TO authenticated
    USING (auth.uid() = id);
    
    -- 관리자는 모든 프로필 조회 가능
    CREATE POLICY "Allow admins to read all profiles"
    ON user_profiles FOR SELECT
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM user_profiles
            WHERE id = auth.uid() AND role = 'admin'
        )
    );
    ```
    
    **또는 임시로 RLS 비활성화 (개발 중에만):**
    
    ```sql
    ALTER TABLE user_profiles DISABLE ROW LEVEL SECURITY;
    ```
    
    설정 후 페이지를 새로고침하세요.
    """)

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
            try:
                supabase.table('user_profiles').insert({
                    'id': response.user.id,
                    'email': email,
                    'name': name,
                    'role': 'user',
                    'status': 'pending'
                }).execute()
            except Exception as profile_error:
                error_msg = str(profile_error)
                # RLS 정책 오류 감지
                if 'infinite recursion' in error_msg or '42P17' in error_msg:
                    show_rls_warning()
                    return False, "RLS 정책 오류가 감지되었습니다. 위의 안내를 참고하여 수정해주세요."
                else:
                    st.error(f"프로필 생성 오류: {error_msg}")
                    return False, f"회원가입 오류: 프로필을 생성할 수 없습니다."
            
            return True, "회원가입이 완료되었습니다! 이메일을 확인하여 인증을 완료하세요."
        else:
            return False, "회원가입 실패"
            
    except Exception as e:
        error_msg = str(e)
        if "already registered" in error_msg.lower() or "already been registered" in error_msg.lower():
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
            try:
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
            except Exception as profile_error:
                error_msg = str(profile_error)
                if 'infinite recursion' in error_msg or '42P17' in error_msg:
                    show_rls_warning()
                    return False, None, "RLS 정책 오류가 감지되었습니다."
                raise
        
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
        if user and user.user:
            profile = supabase.table('user_profiles').select("*").eq('id', user.user.id).single().execute()
            if profile.data and profile.data['status'] == 'approved':
                return {'user': user.user, 'profile': profile.data}
        return None
    except Exception as e:
        error_msg = str(e)
        if 'infinite recursion' in error_msg or '42P17' in error_msg:
            show_rls_warning()
        return None

# ========================================
# 인증 페이지
# ========================================
def show_auth_page():
    """로그인/회원가입 페이지"""
    st.title("💼 기업용 인사회계 시스템")
    st.markdown("---")
    
    tab1, tab2 = st.tabs(["🔓 로그인", "📝 회원가입"])
    
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
                            if error:
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
                    with st.expander(f"📧 {user['name']} ({user['email']})"):
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            st.write(f"**이름:** {user['name']}")
                            st.write(f"**이메일:** {user['email']}")
                            st.write(f"**가입일:** {user['created_at'][:10] if user.get('created_at') else 'N/A'}")
                        
                        with col2:
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
                st.info("승인 대기 중인 사용자가 없습니다.")
                
        except Exception as e:
            error_msg = str(e)
            if 'infinite recursion' in error_msg or '42P17' in error_msg:
                show_rls_warning()
            else:
                st.error(f"데이터 조회 오류: {error_msg}")
    
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
                if '가입일' in display_df.columns:
                    display_df['가입일'] = pd.to_datetime(display_df['가입일'], errors='coerce').dt.strftime('%Y-%m-%d')
                
                st.dataframe(display_df, use_container_width=True, height=400)
                st.info(f"📊 총 {len(df)}명의 사용자가 등록되어 있습니다.")
            else:
                st.warning("등록된 사용자가 없습니다.")
                
        except Exception as e:
            error_msg = str(e)
            if 'infinite recursion' in error_msg or '42P17' in error_msg:
                show_rls_warning()
            else:
                st.error(f"사용자 목록 조회 오류: {error_msg}")

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

# ========================================
# 기존 모듈들 (직원/급여/거래처/매출매입/무역/대시보드)
# ========================================

def employee_management():
    st.header("👥 직원 관리")
    st.info("직원 관리 기능 (기존 hra.py 코드 사용)")

def payroll_management():
    st.header("💰 급여 관리")
    st.info("급여 관리 기능 (기존 hra.py 코드 사용)")

def client_management():
    st.header("🏢 거래처 관리")
    st.info("거래처 관리 기능 (기존 hra.py 코드 사용)")

def sales_purchase_management():
    st.header("📊 매출/매입 관리")
    st.info("매출/매입 관리 기능 (기존 hra.py 코드 사용)")

def trade_management():
    st.header("🌍 무역 관리")
    st.info("무역 관리 기능 (기존 hra.py 코드 사용)")

def dashboard():
    st.header("📊 대시보드")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("총 직원 수", "0명", "")
    with col2:
        st.metric("이번 달 급여", "₩0", "")
    with col3:
        st.metric("활성 거래처", "0개", "")
    
    st.info("대시보드 기능이 구현될 예정입니다.")

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
                  "📊 매출/매입 관리", "🌍 무역 관리"]
    
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
    - 버전: 2.0.2 (RLS Warning)
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
    elif menu == "🌍 무역 관리":
        trade_management()
    elif menu == "👤 사용자 관리":
        user_management()

if __name__ == "__main__":
    main()
