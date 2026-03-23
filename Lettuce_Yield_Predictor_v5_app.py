import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import date, timedelta
import warnings

# 기본 설정
warnings.filterwarnings('ignore')
st.set_page_config(page_title="식물공장 수확량 예측 v5", layout="wide")

# 1. 구글 시트 연결 설정
# 시트 주소: https://docs.google.com/spreadsheets/d/1FMxN2iS0srEZD2bQ5dlQp2-JaZaXvd24W-glJpqReuo/edit?usp=sharing
SHEET_URL = "https://docs.google.com/spreadsheets/d/1FMxN2iS0srEZD2bQ5dlQp2-JaZaXvd24W-glJpqReuo/edit?usp=sharing"

conn = st.connection("gsheets", type=GSheetsConnection)

# 데이터 로드 함수
def load_data():
    return conn.read(spreadsheet=SHEET_URL, ttl="0") # 실시간 반영을 위해 캐시(ttl)를 0으로 설정

# 재배대 상수
PLANTS_PER_TRAY = 16
PLANTS_PER_GUTTER = 13

# 2. 사이드바 설정
st.sidebar.header("⚙️ 예측 설정")
target_date = st.sidebar.date_input("예측 기준일", date.today())
loss_rate_pct = st.sidebar.slider("기본 로스율 (%)", 0, 100, 20)
default_weight = st.sidebar.number_input("주당 기본 무게 (g)", value=100)

# 메인 타이틀
st.title("🌿 식물공장 상추 수확량 예측 시스템 v5")
st.info("데이터는 연결된 구글 시트와 실시간으로 동기화됩니다.")

# 3. 데이터 처리 및 계산
try:
    df = load_data()
    
    if not df.empty:
        # 날짜 형식 변환
        for col in ['sow_date', 'harvest_date']:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col]).dt.date

        # 예측 계산 함수
        def _calc(r):
            tg = pd.to_numeric(r['tray_or_gutter'], errors='coerce')
            if pd.isna(tg): return pd.Series([0, 0.0])
            ppu = PLANTS_PER_TRAY if r['bed_type'] == 'fixed' else PLANTS_PER_GUTTER
            loss = r['loss_rate'] if pd.notna(r['loss_rate']) else (loss_rate_pct / 100)
            p = round(float(tg) * ppu * (1 - loss))
            w = r['weight_per_plant_g'] if pd.notna(r['weight_per_plant_g']) else default_weight
            k = round(p * float(w) / 1000, 2)
            return pd.Series([p, k])

        df[['predicted_plants', 'predicted_kg']] = df.apply(_calc, axis=1)

        # 탭 구성
        tab1, tab2 = st.tabs(["📊 대시보드", "📝 데이터 관리"])

        with tab1:
            d3 = target_date + timedelta(days=3)
            d4 = target_date + timedelta(days=4)
            view_df = df[df['harvest_date'].isin([d3, d4])]
            
            c1, c2, c3 = st.columns(3)
            c1.metric(f"D+3 ({d3})", f"{view_df[view_df['harvest_date']==d3]['predicted_kg'].sum():.1f} kg")
            c2.metric(f"D+4 ({d4})", f"{view_df[view_df['harvest_date']==d4]['predicted_kg'].sum():.1f} kg")
            c3.metric("이번 주 합계", f"{view_df['predicted_kg'].sum():.1f} kg")
            
            st.write("### 상세 예측 목록")
            st.dataframe(view_df, use_container_width=True)

        with tab2:
            st.subheader("구글 시트 데이터 확인")
            st.write("데이터 수정은 연결된 [구글 시트]에서 직접 하시면 앱에 바로 반영됩니다.")
            st.dataframe(df)
            
    else:
        st.warning("구글 시트에 데이터가 없습니다. 시트에 첫 줄(컬럼명)과 샘플 데이터를 입력해 주세요.")

except Exception as e:
    st.error(f"구글 시트 연결 중 오류가 발생했습니다: {e}")
    st.info("시트의 공유 설정이 '링크가 있는 모든 사용자 - 뷰어(또는 편집자)'로 되어 있는지 확인하세요.")
