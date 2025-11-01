import streamlit as st
import pandas as pd
from supabase import create_client, Client
import os
from datetime import datetime, date
import io
import hashlib
import re

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

# ========================================
# 인증 함수
# ========================================
def hash_password(password):
    """비밀번호 해시화"""
    return hashlib.sha256(password.encode()).hexdigest()

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

def create_users_table():
    """사용자 테이블 생성 (최초 1회)"""
    try:
        # 테이블 존재 확인을 위한 쿼리
        supabase.table('users').select("id").limit(1).execute()
    except:
        # 테이블이 없으면 SQL로 생성 필요
        st.warning("⚠️ users 테이블이 없습니다. Supabase SQL Editor에서 다음을 실행하세요:")
        st.code("""
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP
);

ALTER TABLE users DISABLE ROW LEVEL SECURITY;
        """, language="sql")

def register_user(email, password, name):
    """회원가입"""
    try:
        # 이메일 중복 체크
        result = supabase.table('users').select("email").eq('email', email).execute()
        if result.data:
            return False, "이미 등록된 이메일입니다."
        
        # 사용자 등록
        password_hash = hash_password(password)
        data = {
            'email': email,
            'password_hash': password_hash,
            'name': name,
            'role': 'user'
        }
        supabase.table('users').insert(data).execute()
        return True, "회원가입이 완료되었습니다!"
    except Exception as e:
        return False, f"회원가입 실패: {str(e)}"

def login_user(email, password):
    """로그인"""
    try:
        password_hash = hash_password(password)
        result = supabase.table('users').select("*").eq('email', email).eq('password_hash', password_hash).execute()
        
        if result.data and len(result.data) > 0:
            user = result.data[0]
            # 마지막 로그인 시간 업데이트
            supabase.table('users').update({'last_login': datetime.now().isoformat()}).eq('email', email).execute()
            return True, user
        else:
            return False, None
    except Exception as e:
        st.error(f"로그인 오류: {str(e)}")
        return False, None

def logout_user():
    """로그아웃"""
    st.session_state.logged_in = False
    st.session_state.user_email = None
    st.session_state.user_name = None
    st.session_state.user_role = None

# ========================================
# 로그인/회원가입 페이지
# ========================================
def show_auth_page():
    """인증 페이지"""
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
                elif not validate_email(email):
                    st.error("올바른 이메일 형식이 아닙니다.")
                else:
                    success, user = login_user(email, password)
                    if success:
                        st.session_state.logged_in = True
                        st.session_state.user_email = user['email']
                        st.session_state.user_name = user['name']
                        st.session_state.user_role = user['role']
                        st.success(f"환영합니다, {user['name']}님!")
                        st.rerun()
                    else:
                        st.error("이메일 또는 비밀번호가 일치하지 않습니다.")
    
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
                        success, message = register_user(reg_email, reg_password, reg_name)
                        if success:
                            st.success(message)
                            st.info("로그인 탭에서 로그인하세요.")
                        else:
                            st.error(message)
        
        st.markdown("---")
        st.info("""
        **회원가입 안내**
        - 이메일과 비밀번호로 간편하게 가입
        - 비밀번호는 안전하게 암호화되어 저장
        - 가입 후 즉시 시스템 사용 가능
        """)

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
# 사용자 관리 모듈 (관리자용)
# ========================================
def user_management():
    """사용자 관리 (관리자 전용)"""
    st.header("👤 사용자 관리")
    
    if st.session_state.user_role != 'admin':
        st.warning("⚠️ 관리자만 접근 가능한 메뉴입니다.")
        return
    
    tab1, tab2 = st.tabs(["사용자 목록", "권한 관리"])
    
    with tab1:
        st.subheader("📋 등록된 사용자")
        
        try:
            users_df = pd.DataFrame(supabase.table('users').select("*").execute().data)
            
            if not users_df.empty:
                display_df = users_df[['email', 'name', 'role', 'created_at', 'last_login']].copy()
                display_df.columns = ['이메일', '이름', '권한', '가입일', '최근 로그인']
                display_df['가입일'] = pd.to_datetime(display_df['가입일']).dt.strftime('%Y-%m-%d %H:%M')
                display_df['최근 로그인'] = pd.to_datetime(display_df['최근 로그인']).dt.strftime('%Y-%m-%d %H:%M')
                
                st.dataframe(display_df, use_container_width=True, height=400)
                st.info(f"📊 총 {len(users_df)}명의 사용자가 등록되어 있습니다.")
            else:
                st.warning("등록된 사용자가 없습니다.")
        except Exception as e:
            st.error(f"사용자 목록 조회 오류: {str(e)}")
    
    with tab2:
        st.subheader("🔐 권한 관리")
        
        try:
            users_df = pd.DataFrame(supabase.table('users').select("email, name, role").execute().data)
            
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
                st.warning("관리할 사용자가 없습니다.")
        except Exception as e:
            st.error(f"권한 관리 오류: {str(e)}")

# ========================================
# 1. 직원 관리 모듈
# ========================================
def employee_management():
    st.header("👥 직원 관리")
    
    tab1, tab2, tab3 = st.tabs(["직원 목록", "직원 등록", "엑셀 업로드"])
    
    with tab1:
        st.subheader("📋 직원 목록")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            search_name = st.text_input("이름 검색", key="emp_search_name")
        with col2:
            search_dept = st.text_input("부서 검색", key="emp_search_dept")
        with col3:
            search_status = st.selectbox("재직 상태", ["전체", "재직중", "퇴사"], key="emp_search_status")
        
        df = execute_query("employees")
        
        if not df.empty:
            if search_name:
                df = df[df['name'].str.contains(search_name, na=False)]
            if search_dept:
                df = df[df['department'].str.contains(search_dept, na=False)]
            if search_status != "전체":
                df = df[df['status'] == search_status]
            
            df['salary_formatted'] = df['salary'].apply(format_currency)
            
            display_df = df[['employee_code', 'name', 'department', 'position', 
                            'hire_date', 'salary_formatted', 'phone', 'status']].copy()
            display_df.columns = ['사번', '이름', '부서', '직급', '입사일', '급여', '연락처', '상태']
            
            st.dataframe(display_df, use_container_width=True, height=400)
            st.info(f"📊 총 {len(df)}명의 직원이 검색되었습니다.")
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='직원목록')
            
            st.download_button(
                label="📥 엑셀 다운로드",
                data=output.getvalue(),
                file_name=f"직원목록_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("등록된 직원이 없습니다.")
    
    with tab2:
        st.subheader("➕ 직원 등록")
        
        with st.form("employee_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                employee_code = st.text_input("사번*", placeholder="예: EMP001")
                name = st.text_input("이름*", placeholder="예: 홍길동")
                department = st.text_input("부서", placeholder="예: 영업부")
                position = st.text_input("직급", placeholder="예: 부장")
            
            with col2:
                hire_date = st.date_input("입사일", value=date.today())
                salary = st.number_input("급여", min_value=0, value=3000000, step=100000)
                phone = st.text_input("연락처", placeholder="예: 010-1234-5678")
                email = st.text_input("이메일", placeholder="예: hong@company.com")
            
            status = st.selectbox("재직 상태", ["재직중", "퇴사"])
            
            submitted = st.form_submit_button("✅ 등록", use_container_width=True)
            
            if submitted:
                if not employee_code or not name:
                    st.error("사번과 이름은 필수 입력 항목입니다.")
                else:
                    data = {
                        "employee_code": employee_code,
                        "name": name,
                        "department": department,
                        "position": position,
                        "hire_date": str(hire_date),
                        "salary": float(salary),
                        "phone": phone,
                        "email": email,
                        "status": status
                    }
                    
                    result = execute_query("employees", "insert", data)
                    if result:
                        st.success("✅ 직원이 성공적으로 등록되었습니다!")
                        st.rerun()
    
    with tab3:
        st.subheader("📤 엑셀 일괄 등록")
        
        st.info("""
        **엑셀 파일 형식 안내**
        - 첫 번째 행은 헤더(컬럼명)이어야 합니다
        - 필수 컬럼: 사번, 이름
        - 권장 컬럼: 부서, 직급, 입사일, 급여, 연락처, 이메일
        """)
        
        sample_data = {
            '사번': ['EMP001', 'EMP002'],
            '이름': ['홍길동', '김철수'],
            '부서': ['영업부', '회계부'],
            '직급': ['부장', '과장'],
            '입사일': ['2020-01-15', '2021-03-20'],
            '급여': [5000000, 4000000],
            '연락처': ['010-1234-5678', '010-9876-5432'],
            '이메일': ['hong@company.com', 'kim@company.com']
        }
        sample_df = pd.DataFrame(sample_data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            sample_df.to_excel(writer, index=False, sheet_name='직원등록샘플')
        
        st.download_button(
            label="📄 샘플 템플릿 다운로드",
            data=output.getvalue(),
            file_name="직원등록_템플릿.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        uploaded_file = st.file_uploader("엑셀 파일 선택", type=['xlsx', 'xls'], key="emp_upload")
        
        if uploaded_file:
            column_mapping = {
                '사번': 'employee_code',
                '이름': 'name',
                '부서': 'department',
                '직급': 'position',
                '입사일': 'hire_date',
                '급여': 'salary',
                '연락처': 'phone',
                '이메일': 'email'
            }
            
            if st.button("📤 업로드 시작", key="emp_upload_btn"):
                with st.spinner("업로드 중..."):
                    success, total = upload_excel_data(uploaded_file, "employees", column_mapping)
                    st.success(f"✅ {success}/{total}건 업로드 완료!")
                    if success > 0:
                        st.rerun()

# ========================================
# 2. 급여 관리 모듈
# ========================================
def payroll_management():
    st.header("💰 급여 관리")
    
    tab1, tab2 = st.tabs(["급여 목록", "급여 지급"])
    
    with tab1:
        st.subheader("📋 급여 지급 내역")
        
        col1, col2 = st.columns(2)
        with col1:
            search_date = st.date_input("지급일 검색", value=date.today())
        with col2:
            search_emp = st.text_input("사번 검색", key="payroll_search")
        
        df = execute_query("payroll")
        
        if not df.empty:
            if search_emp:
                df = df[df['employee_code'].str.contains(search_emp, na=False)]
            
            for col in ['base_salary', 'bonus', 'deduction', 'net_salary']:
                df[f'{col}_formatted'] = df[col].apply(format_currency)
            
            display_df = df[['employee_code', 'payment_date', 'base_salary_formatted', 
                            'bonus_formatted', 'deduction_formatted', 'net_salary_formatted']].copy()
            display_df.columns = ['사번', '지급일', '기본급', '상여금', '공제액', '실지급액']
            
            st.dataframe(display_df, use_container_width=True, height=400)
        else:
            st.warning("급여 지급 내역이 없습니다.")
    
    with tab2:
        st.subheader("➕ 급여 지급 등록")
        
        with st.form("payroll_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                employee_code = st.text_input("사번*")
                payment_date = st.date_input("지급일", value=date.today())
                base_salary = st.number_input("기본급", min_value=0, value=3000000, step=100000)
            
            with col2:
                bonus = st.number_input("상여금", min_value=0, value=0, step=100000)
                deduction = st.number_input("공제액", min_value=0, value=0, step=10000)
                net_salary = base_salary + bonus - deduction
                st.metric("실지급액", format_currency(net_salary))
            
            remarks = st.text_area("비고")
            
            submitted = st.form_submit_button("✅ 지급 등록")
            
            if submitted:
                if not employee_code:
                    st.error("사번은 필수 입력 항목입니다.")
                else:
                    data = {
                        "employee_code": employee_code,
                        "payment_date": str(payment_date),
                        "base_salary": float(base_salary),
                        "bonus": float(bonus),
                        "deduction": float(deduction),
                        "net_salary": float(net_salary),
                        "remarks": remarks
                    }
                    
                    result = execute_query("payroll", "insert", data)
                    if result:
                        st.success("✅ 급여가 성공적으로 등록되었습니다!")
                        st.rerun()

# ========================================
# 3. 거래처 관리 모듈
# ========================================
def client_management():
    st.header("🏢 거래처 관리")
    
    tab1, tab2, tab3 = st.tabs(["거래처 목록", "거래처 등록", "엑셀 업로드"])
    
    with tab1:
        st.subheader("📋 거래처 목록")
        
        col1, col2 = st.columns(2)
        with col1:
            search_name = st.text_input("거래처명 검색", key="client_search_name")
        with col2:
            search_country = st.text_input("국가 검색", key="client_search_country")
        
        df = execute_query("clients")
        
        if not df.empty:
            if search_name:
                df = df[df['client_name'].str.contains(search_name, na=False)]
            if search_country:
                df = df[df['country'].str.contains(search_country, na=False)]
            
            display_df = df[['client_code', 'client_name', 'business_type', 'country', 
                            'contact_person', 'phone', 'email']].copy()
            display_df.columns = ['거래처코드', '거래처명', '업종', '국가', '담당자', '전화', '이메일']
            
            st.dataframe(display_df, use_container_width=True, height=400)
            st.info(f"📊 총 {len(df)}개 거래처가 검색되었습니다.")
        else:
            st.warning("등록된 거래처가 없습니다.")
    
    with tab2:
        st.subheader("➕ 거래처 등록")
        
        with st.form("client_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                client_code = st.text_input("거래처코드*", placeholder="예: CLI001")
                client_name = st.text_input("거래처명*", placeholder="예: ABC Trading")
                business_type = st.text_input("업종", placeholder="예: 수출입")
                country = st.text_input("국가", placeholder="예: USA")
            
            with col2:
                contact_person = st.text_input("담당자", placeholder="예: John Smith")
                phone = st.text_input("전화번호", placeholder="예: +1-555-1234")
                email = st.text_input("이메일", placeholder="예: john@abc.com")
            
            address = st.text_area("주소")
            
            submitted = st.form_submit_button("✅ 등록")
            
            if submitted:
                if not client_code or not client_name:
                    st.error("거래처코드와 거래처명은 필수 입력 항목입니다.")
                else:
                    data = {
                        "client_code": client_code,
                        "client_name": client_name,
                        "business_type": business_type,
                        "country": country,
                        "contact_person": contact_person,
                        "phone": phone,
                        "email": email,
                        "address": address
                    }
                    
                    result = execute_query("clients", "insert", data)
                    if result:
                        st.success("✅ 거래처가 성공적으로 등록되었습니다!")
                        st.rerun()
    
    with tab3:
        st.subheader("📤 엑셀 일괄 등록")
        
        sample_data = {
            '거래처코드': ['CLI001', 'CLI002'],
            '거래처명': ['ABC Trading', '대한상사'],
            '업종': ['수출', '도매'],
            '국가': ['USA', 'Korea'],
            '담당자': ['John Smith', '김철수'],
            '전화': ['+1-555-1234', '02-1234-5678'],
            '이메일': ['john@abc.com', 'kim@daehan.com']
        }
        sample_df = pd.DataFrame(sample_data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            sample_df.to_excel(writer, index=False, sheet_name='거래처샘플')
        
        st.download_button(
            label="📄 샘플 템플릿 다운로드",
            data=output.getvalue(),
            file_name="거래처등록_템플릿.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        uploaded_file = st.file_uploader("엑셀 파일 선택", type=['xlsx', 'xls'], key="client_upload")
        
        if uploaded_file:
            column_mapping = {
                '거래처코드': 'client_code',
                '거래처명': 'client_name',
                '업종': 'business_type',
                '국가': 'country',
                '담당자': 'contact_person',
                '전화': 'phone',
                '이메일': 'email',
                '주소': 'address'
            }
            
            if st.button("📤 업로드 시작", key="client_upload_btn"):
                with st.spinner("업로드 중..."):
                    success, total = upload_excel_data(uploaded_file, "clients", column_mapping)
                    st.success(f"✅ {success}/{total}건 업로드 완료!")
                    if success > 0:
                        st.rerun()

# ========================================
# 4. 매출/매입 관리 모듈
# ========================================
def sales_purchase_management():
    st.header("📊 매출/매입 관리")
    
    menu = st.selectbox("관리 항목 선택", ["매출 관리", "매입 관리"])
    
    if menu == "매출 관리":
        manage_sales()
    else:
        manage_purchases()

def manage_sales():
    tab1, tab2 = st.tabs(["매출 목록", "매출 등록"])
    
    with tab1:
        st.subheader("📋 매출 내역")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            search_date_from = st.date_input("시작일", key="sales_date_from")
        with col2:
            search_date_to = st.date_input("종료일", value=date.today(), key="sales_date_to")
        with col3:
            search_client = st.text_input("거래처 검색", key="sales_client")
        
        df = execute_query("sales")
        
        if not df.empty:
            if search_client:
                df = df[df['client_code'].str.contains(search_client, na=False)]
            
            for col in ['quantity', 'unit_price', 'amount']:
                df[f'{col}_formatted'] = df[col].apply(format_number)
            
            display_df = df[['sales_no', 'sales_date', 'client_code', 'product_name',
                            'quantity_formatted', 'unit_price_formatted', 'amount_formatted',
                            'currency', 'payment_status']].copy()
            display_df.columns = ['매출번호', '매출일', '거래처코드', '품목명', '수량', '단가', '금액', '통화', '입금상태']
            
            st.dataframe(display_df, use_container_width=True, height=400)
            
            total_amount = df['amount'].sum()
            st.metric("💰 총 매출액", format_currency(total_amount))
        else:
            st.warning("매출 내역이 없습니다.")
    
    with tab2:
        st.subheader("➕ 매출 등록")
        
        with st.form("sales_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                sales_no = st.text_input("매출번호*", placeholder="예: S2024001")
                sales_date = st.date_input("매출일", value=date.today())
                client_code = st.text_input("거래처코드*", placeholder="예: CLI001")
                product_name = st.text_input("품목명*", placeholder="예: 전자제품")
            
            with col2:
                quantity = st.number_input("수량", min_value=0.0, value=1.0, step=1.0)
                unit_price = st.number_input("단가", min_value=0, value=100000, step=10000)
                amount = quantity * unit_price
                st.metric("금액", format_number(amount))
                currency = st.selectbox("통화", ["KRW", "USD", "EUR", "JPY", "CNY"])
            
            payment_status = st.selectbox("입금상태", ["미수금", "입금완료", "부분입금"])
            remarks = st.text_area("비고")
            
            submitted = st.form_submit_button("✅ 등록")
            
            if submitted:
                if not sales_no or not client_code or not product_name:
                    st.error("매출번호, 거래처코드, 품목명은 필수 입력 항목입니다.")
                else:
                    data = {
                        "sales_no": sales_no,
                        "sales_date": str(sales_date),
                        "client_code": client_code,
                        "product_name": product_name,
                        "quantity": float(quantity),
                        "unit_price": float(unit_price),
                        "amount": float(amount),
                        "currency": currency,
                        "payment_status": payment_status,
                        "remarks": remarks
                    }
                    
                    result = execute_query("sales", "insert", data)
                    if result:
                        st.success("✅ 매출이 성공적으로 등록되었습니다!")
                        st.rerun()

def manage_purchases():
    tab1, tab2 = st.tabs(["매입 목록", "매입 등록"])
    
    with tab1:
        st.subheader("📋 매입 내역")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            search_date_from = st.date_input("시작일", key="purchase_date_from")
        with col2:
            search_date_to = st.date_input("종료일", value=date.today(), key="purchase_date_to")
        with col3:
            search_supplier = st.text_input("공급업체 검색", key="purchase_supplier")
        
        df = execute_query("purchases")
        
        if not df.empty:
            if search_supplier:
                df = df[df['supplier_code'].str.contains(search_supplier, na=False)]
            
            for col in ['quantity', 'unit_price', 'amount']:
                df[f'{col}_formatted'] = df[col].apply(format_number)
            
            display_df = df[['purchase_no', 'purchase_date', 'supplier_code', 'product_name',
                            'quantity_formatted', 'unit_price_formatted', 'amount_formatted',
                            'currency', 'payment_status']].copy()
            display_df.columns = ['매입번호', '매입일', '공급업체코드', '품목명', '수량', '단가', '금액', '통화', '지급상태']
            
            st.dataframe(display_df, use_container_width=True, height=400)
            
            total_amount = df['amount'].sum()
            st.metric("💰 총 매입액", format_currency(total_amount))
        else:
            st.warning("매입 내역이 없습니다.")
    
    with tab2:
        st.subheader("➕ 매입 등록")
        
        with st.form("purchase_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                purchase_no = st.text_input("매입번호*", placeholder="예: P2024001")
                purchase_date = st.date_input("매입일", value=date.today())
                supplier_code = st.text_input("공급업체코드*", placeholder="예: CLI001")
                product_name = st.text_input("품목명*", placeholder="예: 원자재")
            
            with col2:
                quantity = st.number_input("수량", min_value=0.0, value=1.0, step=1.0, key="pur_qty")
                unit_price = st.number_input("단가", min_value=0, value=100000, step=10000, key="pur_price")
                amount = quantity * unit_price
                st.metric("금액", format_number(amount))
                currency = st.selectbox("통화", ["KRW", "USD", "EUR", "JPY", "CNY"], key="pur_cur")
            
            payment_status = st.selectbox("지급상태", ["미지급", "지급완료", "부분지급"])
            remarks = st.text_area("비고", key="pur_remarks")
            
            submitted = st.form_submit_button("✅ 등록")
            
            if submitted:
                if not purchase_no or not supplier_code or not product_name:
                    st.error("매입번호, 공급업체코드, 품목명은 필수 입력 항목입니다.")
                else:
                    data = {
                        "purchase_no": purchase_no,
                        "purchase_date": str(purchase_date),
                        "supplier_code": supplier_code,
                        "product_name": product_name,
                        "quantity": float(quantity),
                        "unit_price": float(unit_price),
                        "amount": float(amount),
                        "currency": currency,
                        "payment_status": payment_status,
                        "remarks": remarks
                    }
                    
                    result = execute_query("purchases", "insert", data)
                    if result:
                        st.success("✅ 매입이 성공적으로 등록되었습니다!")
                        st.rerun()

# ========================================
# 5. 무역 관리 모듈
# ========================================
def trade_management():
    st.header("🌏 무역 관리")
    
    tab1, tab2 = st.tabs(["무역 거래 목록", "무역 거래 등록"])
    
    with tab1:
        st.subheader("📋 무역 거래 내역")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            search_type = st.selectbox("거래 구분", ["전체", "수출", "수입"], key="trade_type")
        with col2:
            search_date_from = st.date_input("시작일", key="trade_date_from")
        with col3:
            search_date_to = st.date_input("종료일", value=date.today(), key="trade_date_to")
        
        df = execute_query("trade_transactions")
        
        if not df.empty:
            if search_type != "전체":
                df = df[df['transaction_type'] == search_type]
            
            for col in ['quantity', 'unit_price', 'amount', 'exchange_rate', 'krw_amount']:
                if col in df.columns:
                    df[f'{col}_formatted'] = df[col].apply(format_number)
            
            display_df = df[['transaction_no', 'transaction_type', 'transaction_date', 
                            'client_code', 'product_name', 'quantity_formatted', 
                            'unit_price_formatted', 'amount_formatted', 'currency',
                            'exchange_rate_formatted', 'krw_amount_formatted', 'customs_status']].copy()
            display_df.columns = ['거래번호', '구분', '거래일', '거래처', '품목', '수량', 
                                 '단가', '금액', '통화', '환율', '원화금액', '통관상태']
            
            st.dataframe(display_df, use_container_width=True, height=400)
            
            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                total_export = df[df['transaction_type'] == '수출']['krw_amount'].sum()
                st.metric("📤 총 수출액", format_currency(total_export))
            with col_s2:
                total_import = df[df['transaction_type'] == '수입']['krw_amount'].sum()
                st.metric("📥 총 수입액", format_currency(total_import))
            with col_s3:
                net_trade = total_export - total_import
                st.metric("💹 무역수지", format_currency(net_trade))
        else:
            st.warning("무역 거래 내역이 없습니다.")
    
    with tab2:
        st.subheader("➕ 무역 거래 등록")
        
        with st.form("trade_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                transaction_no = st.text_input("거래번호*", placeholder="예: T2024001")
                transaction_type = st.selectbox("거래 구분*", ["수출", "수입"])
                transaction_date = st.date_input("거래일", value=date.today())
                client_code = st.text_input("거래처코드*", placeholder="예: CLI001")
                product_name = st.text_input("품목명*", placeholder="예: 전자부품")
            
            with col2:
                quantity = st.number_input("수량", min_value=0.0, value=1.0, step=1.0, key="trade_qty")
                unit_price = st.number_input("단가", min_value=0.0, value=1000.0, step=100.0, key="trade_price")
                amount = quantity * unit_price
                st.metric("금액", format_number(amount))
                currency = st.selectbox("통화", ["USD", "EUR", "JPY", "CNY", "KRW"], key="trade_cur")
                exchange_rate = st.number_input("환율", min_value=0.0, value=1300.0, step=1.0, key="trade_rate")
            
            krw_amount = amount * exchange_rate
            st.info(f"💱 원화 환산액: {format_currency(krw_amount)}")
            
            customs_status = st.selectbox("통관상태", ["신고중", "통관완료", "보류", "검사중"])
            bl_no = st.text_input("BL번호", placeholder="예: BL2024001")
            remarks = st.text_area("비고", key="trade_remarks")
            
            submitted = st.form_submit_button("✅ 등록")
            
            if submitted:
                if not transaction_no or not client_code or not product_name:
                    st.error("거래번호, 거래처코드, 품목명은 필수 입력 항목입니다.")
                else:
                    data = {
                        "transaction_no": transaction_no,
                        "transaction_type": transaction_type,
                        "transaction_date": str(transaction_date),
                        "client_code": client_code,
                        "product_name": product_name,
                        "quantity": float(quantity),
                        "unit_price": float(unit_price),
                        "amount": float(amount),
                        "currency": currency,
                        "exchange_rate": float(exchange_rate),
                        "krw_amount": float(krw_amount),
                        "customs_status": customs_status,
                        "bl_no": bl_no,
                        "remarks": remarks
                    }
                    
                    result = execute_query("trade_transactions", "insert", data)
                    if result:
                        st.success("✅ 무역 거래가 성공적으로 등록되었습니다!")
                        st.rerun()

# ========================================
# 6. 대시보드 모듈
# ========================================
def dashboard():
    st.header("📊 대시보드")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        emp_df = execute_query("employees")
        total_employees = len(emp_df) if not emp_df.empty else 0
        st.metric("👥 총 직원 수", f"{total_employees}명")
    
    with col2:
        client_df = execute_query("clients")
        total_clients = len(client_df) if not client_df.empty else 0
        st.metric("🏢 총 거래처", f"{total_clients}개")
    
    with col3:
        sales_df = execute_query("sales")
        total_sales = sales_df['amount'].sum() if not sales_df.empty else 0
        st.metric("📈 총 매출", format_currency(total_sales))
    
    with col4:
        purchase_df = execute_query("purchases")
        total_purchase = purchase_df['amount'].sum() if not purchase_df.empty else 0
        st.metric("📉 총 매입", format_currency(total_purchase))
    
    st.divider()
    
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("📊 부서별 직원 현황")
        if not emp_df.empty:
            dept_count = emp_df['department'].value_counts().reset_index()
            dept_count.columns = ['부서', '인원']
            st.bar_chart(dept_count.set_index('부서'))
        else:
            st.info("직원 데이터가 없습니다.")
    
    with col_chart2:
        st.subheader("💰 월별 매출 추이")
        if not sales_df.empty:
            sales_df['sales_date'] = pd.to_datetime(sales_df['sales_date'])
            monthly_sales = sales_df.groupby(sales_df['sales_date'].dt.to_period('M'))['amount'].sum().reset_index()
            monthly_sales['sales_date'] = monthly_sales['sales_date'].astype(str)
            monthly_sales.columns = ['월', '매출액']
            st.line_chart(monthly_sales.set_index('월'))
        else:
            st.info("매출 데이터가 없습니다.")
    
    st.divider()
    
    st.subheader("📋 최근 거래 내역")
    
    tab1, tab2, tab3 = st.tabs(["최근 매출", "최근 매입", "최근 무역거래"])
    
    with tab1:
        if not sales_df.empty:
            recent_sales = sales_df.sort_values('created_at', ascending=False).head(5)
            display_sales = recent_sales[['sales_no', 'sales_date', 'client_code', 'product_name', 'amount']].copy()
            display_sales['amount'] = display_sales['amount'].apply(format_currency)
            display_sales.columns = ['매출번호', '매출일', '거래처', '품목', '금액']
            st.dataframe(display_sales, use_container_width=True)
        else:
            st.info("매출 데이터가 없습니다.")
    
    with tab2:
        if not purchase_df.empty:
            recent_purchase = purchase_df.sort_values('created_at', ascending=False).head(5)
            display_purchase = recent_purchase[['purchase_no', 'purchase_date', 'supplier_code', 'product_name', 'amount']].copy()
            display_purchase['amount'] = display_purchase['amount'].apply(format_currency)
            display_purchase.columns = ['매입번호', '매입일', '공급업체', '품목', '금액']
            st.dataframe(display_purchase, use_container_width=True)
        else:
            st.info("매입 데이터가 없습니다.")
    
    with tab3:
        trade_df = execute_query("trade_transactions")
        if not trade_df.empty:
            recent_trade = trade_df.sort_values('created_at', ascending=False).head(5)
            display_trade = recent_trade[['transaction_no', 'transaction_type', 'transaction_date', 
                                         'client_code', 'product_name', 'krw_amount']].copy()
            display_trade['krw_amount'] = display_trade['krw_amount'].apply(format_currency)
            display_trade.columns = ['거래번호', '구분', '거래일', '거래처', '품목', '원화금액']
            st.dataframe(display_trade, use_container_width=True)
        else:
            st.info("무역 거래 데이터가 없습니다.")

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
    - 버전: 2.0.0
    - 데이터베이스: Supabase
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