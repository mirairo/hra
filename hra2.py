import streamlit as st
import pandas as pd
from supabase import create_client, Client
import os
from datetime import datetime, date
import io
import hashlib
import re
import secrets

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
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'user_name' not in st.session_state:
    st.session_state.user_name = None
if 'user_role' not in st.session_state:
    st.session_state.user_role = None
if 'user_status' not in st.session_state:
    st.session_state.user_status = None

# ========================================
# 인증 함수
# ========================================
def hash_password(password):
    """비밀번호 해시화"""
    return hashlib.sha256(password.encode()).hexdigest()

def generate_verification_code():
    """6자리 인증 코드 생성"""
    return ''.join([str(secrets.randbelow(10)) for _ in range(6)])

def validate_email(email):
    """이메일 형식 검증"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """비밀번호 강도 검증 (최소 8자, 영문+숫자)"""
    if len(password) < 8:
        return False, "비밀번호는 최소 8자 이상이어야 합니다."
    if not re.search(r'[A-Za-z]', password):
        return False, "비밀번호에 영문이 포함되어야 합니다."
    if not re.search(r'\d', password):
        return False, "비밀번호에 숫자가 포함되어야 합니다."
    return True, "OK"

def register_user(email, password, name):
    """회원가입 - 승인 대기 상태로 등록"""
    try:
        # 이메일 중복 체크
        result = supabase.table('users').select("email").eq('email', email).execute()
        if result.data:
            return False, "이미 등록된 이메일입니다.", None
        
        # 인증 코드 생성
        verification_code = generate_verification_code()
        
        # 사용자 등록 (승인 대기 상태)
        password_hash = hash_password(password)
        data = {
            'email': email,
            'password_hash': password_hash,
            'name': name,
            'role': 'user',
            'status': 'pending',  # 승인 대기
            'email_verified': False,
            'verification_code': verification_code
        }
        supabase.table('users').insert(data).execute()
        return True, "회원가입이 완료되었습니다! 관리자 승인을 기다려주세요.", verification_code
    except Exception as e:
        return False, f"회원가입 실패: {str(e)}", None

def verify_email_code(email, code):
    """이메일 인증 코드 확인"""
    try:
        result = supabase.table('users').select("*").eq('email', email).eq('verification_code', code).execute()
        
        if result.data and len(result.data) > 0:
            # 이메일 인증 완료
            supabase.table('users').update({'email_verified': True}).eq('email', email).execute()
            return True, "이메일 인증이 완료되었습니다!"
        else:
            return False, "인증 코드가 일치하지 않습니다."
    except Exception as e:
        return False, f"인증 오류: {str(e)}"

def login_user(email, password):
    """로그인"""
    try:
        password_hash = hash_password(password)
        result = supabase.table('users').select("*").eq('email', email).eq('password_hash', password_hash).execute()
        
        if result.data and len(result.data) > 0:
            user = result.data[0]
            
            # 이메일 인증 확인
            if not user.get('email_verified', False):
                return False, None, "이메일 인증이 필요합니다. 회원가입 시 받은 인증 코드를 입력하세요."
            
            # 관리자 승인 확인
            if user.get('status') == 'pending':
                return False, None, "관리자 승인 대기중입니다. 승인 후 로그인할 수 있습니다."
            
            if user.get('status') == 'rejected':
                return False, None, "계정이 거부되었습니다. 관리자에게 문의하세요."
            
            if user.get('status') != 'approved':
                return False, None, "계정 상태를 확인할 수 없습니다."
            
            # 마지막 로그인 시간 업데이트
            supabase.table('users').update({'last_login': datetime.now().isoformat()}).eq('email', email).execute()
            return True, user, None
        else:
            return False, None, "이메일 또는 비밀번호가 일치하지 않습니다."
    except Exception as e:
        return False, None, f"로그인 오류: {str(e)}"

def logout_user():
    """로그아웃"""
    st.session_state.logged_in = False
    st.session_state.user_email = None
    st.session_state.user_name = None
    st.session_state.user_role = None
    st.session_state.user_status = None

def resend_verification_code(email):
    """인증 코드 재발송"""
    try:
        # 새 인증 코드 생성
        new_code = generate_verification_code()
        
        # 사용자 확인 및 업데이트
        result = supabase.table('users').select("email").eq('email', email).execute()
        if result.data:
            supabase.table('users').update({'verification_code': new_code}).eq('email', email).execute()
            return True, new_code
        else:
            return False, None
    except Exception as e:
        return False, None

# ========================================
# 로그인/회원가입 페이지
# ========================================
def show_auth_page():
    """인증 페이지"""
    st.title("💼 기업용 인사회계 시스템")
    st.markdown("---")
    
    tab1, tab2, tab3 = st.tabs(["🔐 로그인", "📝 회원가입", "✉️ 이메일 인증"])
    
    with tab1:
        st.subheader("로그인")
        
        with st.form("login_form"):
            email = st.text_input("이메일", placeholder="example@company.com")
            password = st.text_input("비밀번호", type="password")
            submit = st.form_submit_button("🔓 로그인", use_container_width=True)
            
            if submit:
                if not email or not password:
                    st.error("이메일과 비밀번호를 입력하세요.")
                elif not validate_email(email):
                    st.error("올바른 이메일 형식이 아닙니다.")
                else:
                    success, user, error_msg = login_user(email, password)
                    if success:
                        st.session_state.logged_in = True
                        st.session_state.user_email = user['email']
                        st.session_state.user_name = user['name']
                        st.session_state.user_role = user['role']
                        st.session_state.user_status = user['status']
                        st.success(f"환영합니다, {user['name']}님!")
                        st.rerun()
                    else:
                        st.error(error_msg)
        
        st.markdown("---")
        st.info("""
        **로그인 안내**
        - 회원가입 후 이메일 인증 필요
        - 관리자 승인 후 로그인 가능
        - 문제 발생 시 관리자에게 문의
        """)
    
    with tab2:
        st.subheader("회원가입")
        
        with st.form("register_form"):
            reg_name = st.text_input("이름*", placeholder="홍길동")
            reg_email = st.text_input("이메일*", placeholder="example@company.com")
            reg_password = st.text_input("비밀번호*", type="password", 
                                        help="최소 8자, 영문과 숫자 포함")
            reg_password_confirm = st.text_input("비밀번호 확인*", type="password")
            
            submit_reg = st.form_submit_button("✅ 회원가입", use_container_width=True)
            
            if submit_reg:
                if not reg_name or not reg_email or not reg_password:
                    st.error("모든 필수 항목을 입력하세요.")
                elif not validate_email(reg_email):
                    st.error("올바른 이메일 형식이 아닙니다.")
                elif reg_password != reg_password_confirm:
                    st.error("비밀번호가 일치하지 않습니다.")
                else:
                    is_valid, msg = validate_password(reg_password)
                    if not is_valid:
                        st.error(msg)
                    else:
                        success, message, verification_code = register_user(reg_email, reg_password, reg_name)
                        if success:
                            st.success(message)
                            st.info(f"""
                            **📧 인증 코드가 생성되었습니다!**
                            
                            귀하의 인증 코드: `{verification_code}`
                            
                            **다음 단계:**
                            1. '✉️ 이메일 인증' 탭으로 이동
                            2. 위 인증 코드를 입력하여 이메일 인증
                            3. 관리자 승인 대기
                            4. 승인 후 로그인
                            
                            ⚠️ 인증 코드를 안전하게 보관하세요!
                            """)
                        else:
                            st.error(message)
        
        st.markdown("---")
        st.warning("""
        **회원가입 절차**
        1. ✅ 회원정보 입력 및 가입
        2. ✉️ 이메일 인증 코드 확인
        3. ⏳ 관리자 승인 대기
        4. 🔓 승인 후 로그인 가능
        """)
    
    with tab3:
        st.subheader("이메일 인증")
        
        with st.form("verify_email_form"):
            verify_email = st.text_input("이메일", placeholder="example@company.com")
            verify_code = st.text_input("인증 코드 (6자리)", placeholder="123456", max_chars=6)
            
            submit_verify = st.form_submit_button("✅ 인증 확인", use_container_width=True)
            
            if submit_verify:
                if not verify_email or not verify_code:
                    st.error("이메일과 인증 코드를 입력하세요.")
                elif len(verify_code) != 6:
                    st.error("인증 코드는 6자리입니다.")
                else:
                    success, message = verify_email_code(verify_email, verify_code)
                    if success:
                        st.success(message)
                        st.info("이제 관리자 승인을 기다려주세요. 승인 후 로그인할 수 있습니다.")
                    else:
                        st.error(message)
        
        st.markdown("---")
        
        with st.form("resend_code_form"):
            st.write("**인증 코드를 분실하셨나요?**")
            resend_email = st.text_input("이메일 주소", placeholder="example@company.com", key="resend_email")
            submit_resend = st.form_submit_button("🔄 인증 코드 재발송")
            
            if submit_resend:
                if not resend_email:
                    st.error("이메일을 입력하세요.")
                else:
                    success, new_code = resend_verification_code(resend_email)
                    if success:
                        st.success("새로운 인증 코드가 생성되었습니다!")
                        st.info(f"**새 인증 코드:** `{new_code}`")
                    else:
                        st.error("등록되지 않은 이메일입니다.")

# ========================================
# 사용자 관리 모듈 (관리자용)
# ========================================
def user_management():
    """사용자 관리 (관리자 전용)"""
    st.header("👤 사용자 관리")
    
    if st.session_state.user_role != 'admin':
        st.warning("⚠️ 관리자만 접근 가능한 메뉴입니다.")
        return
    
    tab1, tab2, tab3 = st.tabs(["승인 대기", "사용자 목록", "권한 관리"])
    
    with tab1:
        st.subheader("⏳ 승인 대기 중인 사용자")
        
        try:
            # 이메일 인증 완료 + 승인 대기 상태
            pending_users = pd.DataFrame(
                supabase.table('users')
                .select("*")
                .eq('status', 'pending')
                .eq('email_verified', True)
                .execute()
                .data
            )
            
            # 이메일 미인증 사용자
            unverified_users = pd.DataFrame(
                supabase.table('users')
                .select("*")
                .eq('email_verified', False)
                .execute()
                .data
            )
            
            if not pending_users.empty:
                st.write("**승인 대기 중 (이메일 인증 완료)**")
                
                for idx, user in pending_users.iterrows():
                    with st.expander(f"📧 {user['name']} ({user['email']})"):
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            st.write(f"**이름:** {user['name']}")
                            st.write(f"**이메일:** {user['email']}")
                            st.write(f"**가입일:** {user['created_at'][:10]}")
                            st.write(f"**이메일 인증:** ✅ 완료")
                        
                        with col2:
                            if st.button("✅ 승인", key=f"approve_{user['id']}"):
                                try:
                                    supabase.table('users').update({
                                        'status': 'approved',
                                        'approved_at': datetime.now().isoformat()
                                    }).eq('id', user['id']).execute()
                                    st.success(f"{user['name']}님이 승인되었습니다!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"승인 실패: {str(e)}")
                            
                            if st.button("❌ 거부", key=f"reject_{user['id']}"):
                                try:
                                    supabase.table('users').update({
                                        'status': 'rejected'
                                    }).eq('id', user['id']).execute()
                                    st.warning(f"{user['name']}님의 가입이 거부되었습니다.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"거부 실패: {str(e)}")
            else:
                st.info("승인 대기 중인 사용자가 없습니다.")
            
            if not unverified_users.empty:
                st.markdown("---")
                st.write("**이메일 미인증 사용자**")
                
                display_unverified = unverified_users[['email', 'name', 'created_at']].copy()
                display_unverified['created_at'] = pd.to_datetime(display_unverified['created_at']).dt.strftime('%Y-%m-%d %H:%M')
                display_unverified.columns = ['이메일', '이름', '가입일']
                
                st.dataframe(display_unverified, use_container_width=True)
                st.caption("⚠️ 이메일 인증을 완료하면 승인 대기 목록에 표시됩니다.")
                
        except Exception as e:
            st.error(f"데이터 조회 오류: {str(e)}")
    
    with tab2:
        st.subheader("📋 전체 사용자 목록")
        
        try:
            users_df = pd.DataFrame(supabase.table('users').select("*").execute().data)
            
            if not users_df.empty:
                # 상태 필터
                status_filter = st.selectbox("상태 필터", ["전체", "승인됨", "대기중", "거부됨"])
                
                if status_filter == "승인됨":
                    users_df = users_df[users_df['status'] == 'approved']
                elif status_filter == "대기중":
                    users_df = users_df[users_df['status'] == 'pending']
                elif status_filter == "거부됨":
                    users_df = users_df[users_df['status'] == 'rejected']
                
                # 상태 한글 변환
                status_map = {
                    'pending': '⏳ 대기중',
                    'approved': '✅ 승인됨',
                    'rejected': '❌ 거부됨'
                }
                users_df['status_kr'] = users_df['status'].map(status_map)
                users_df['email_verified_kr'] = users_df['email_verified'].map({True: '✅', False: '❌'})
                
                display_df = users_df[['email', 'name', 'role', 'email_verified_kr', 'status_kr', 'created_at', 'last_login']].copy()
                display_df.columns = ['이메일', '이름', '권한', '이메일인증', '상태', '가입일', '최근 로그인']
                display_df['가입일'] = pd.to_datetime(display_df['가입일']).dt.strftime('%Y-%m-%d')
                display_df['최근 로그인'] = pd.to_datetime(display_df['최근 로그인'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M')
                
                st.dataframe(display_df, use_container_width=True, height=400)
                st.info(f"📊 총 {len(users_df)}명의 사용자가 등록되어 있습니다.")
            else:
                st.warning("등록된 사용자가 없습니다.")
        except Exception as e:
            st.error(f"사용자 목록 조회 오류: {str(e)}")
    
    with tab3:
        st.subheader("🔐 권한 관리")
        
        try:
            users_df = pd.DataFrame(
                supabase.table('users')
                .select("email, name, role, status")
                .eq('status', 'approved')
                .execute()
                .data
            )
            
            if not users_df.empty:
                selected_user = st.selectbox(
                    "사용자 선택",
                    users_df['email'].tolist(),
                    format_func=lambda x: f"{users_df[users_df['email']==x]['name'].values[0]} ({x})"
                )
                
                current_role = users_df[users_df['email']==selected_user]['role'].values[0]
                
                new_role = st.selectbox(
                    "권한 설정",
                    ['user', 'admin'],
                    index=0 if current_role == 'user' else 1
                )
                
                if st.button("💾 권한 변경"):
                    try:
                        supabase.table('users').update({'role': new_role}).eq('email', selected_user).execute()
                        st.success(f"✅ {selected_user}의 권한이 {new_role}로 변경되었습니다.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"권한 변경 실패: {str(e)}")
            else:
                st.warning("승인된 사용자가 없습니다.")
        except Exception as e:
            st.error(f"권한 관리 오류: {str(e)}")

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
# 이전 코드와 동일하므로 생략 - 아래 주석 참조
# ========================================

# [이전에 작성한 모든 함수들을 여기에 그대로 포함]
# - employee_management()
# - payroll_management()
# - client_management()
# - sales_purchase_management()
# - manage_sales()
# - manage_purchases()
# - trade_management()
# - dashboard()

# 공간 절약을 위해 이전 코드 재사용
def employee_management():
    st.header("👥 직원 관리")
    st.info("직원 관리 기능이 여기에 표시됩니다. (이전 코드와 동일)")

def payroll_management():
    st.header("💰 급여 관리")
    st.info("급여 관리 기능이 여기에 표시됩니다. (이전 코드와 동일)")

def client_management():
    st.header("🏢 거래처 관리")
    st.info("거래처 관리 기능이 여기에 표시됩니다. (이전 코드와 동일)")

def sales_purchase_management():
    st.header("📊 매출/매입 관리")
    st.info("매출/매입 관리 기능이 여기에 표시됩니다. (이전 코드와 동일)")

def trade_management():
    st.header("🌏 무역 관리")
    st.info("무역 관리 기능이 여기에 표시됩니다. (이전 코드와 동일)")

def dashboard():
    st.header("📊 대시보드")
    st.info("대시보드가 여기에 표시됩니다. (이전 코드와 동일)")

# ========================================
# 메인 애플리케이션
# ========================================
def main():
    # 로그인 확인
    if not st.session_state.logged_in:
        show_auth_page()
        return
    
    # 사이드바 메뉴
    st.sidebar.title("💼 인사회계 시스템")
    st.sidebar.markdown(f"**환영합니다, {st.session_state.user_name}님!**")
    st.sidebar.markdown(f"권한: {st.session_state.user_role}")
    st.sidebar.markdown(f"상태: ✅ 승인됨")
    st.sidebar.markdown("---")
    
    # 메뉴 구성
    menu_items = ["🏠 대시보드", "👥 직원 관리", "💰 급여 관리", "🏢 거래처 관리", 
                  "📊 매출/매입 관리", "🌏 무역 관리"]
    
    # 관리자 메뉴 추가
    if st.session_state.user_role == 'admin':
        menu_items.append("👤 사용자 관리")
    
    menu = st.sidebar.radio(
        "메뉴 선택",
        menu_items,
        label_visibility="collapsed"
    )
    
    st.sidebar.markdown("---")
    
    # 로그아웃 버튼
    if st.sidebar.button("🚪 로그아웃", use_container_width=True):
        logout_user()
        st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.info(f"""
    **시스템 정보**
    - 사용자: {st.session_state.user_email}
    - 버전: 2.1.0
    - 데이터베이스: Supabase
    - 인증: 이메일 + 관리자 승인
    """)
    
    # 페이지 라우팅
    if menu == "🏠 대시보드":
        dashboard()
    elif menu == "👥 직