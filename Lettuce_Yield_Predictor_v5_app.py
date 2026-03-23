import streamlit as st
import pandas as pd
import numpy as np
import os
import warnings
from datetime import date, timedelta

# 기본 설정
warnings.filterwarnings('ignore')
st.set_page_config(page_title="상추 수확량 예측 시스템", layout="wide")

# 파일 저장 경로 (GitHub 환경에서는 현재 폴더에 저장됩니다)
DB_PATH = 'DB_배치데이터.csv'
DB_COLS = [
    'batch_id', 'sow_date', 'transplant_date', 'plant_date', 'harvest_date', 
    'grow_days', 'bed_type', 'bed_id', 'tray_or_gutter', 'weight_per_plant_g', 
    'loss_rate', 'actual_yield', 'actual_weight_kg', 'note'
]

# 상수 설정
PLANTS_PER_TRAY = 16
PLANTS_PER_GUTTER = 13

# 데이터 로드 함수
def load_data():
    if os.path.exists(DB_PATH):
        df = pd.read_csv(DB_PATH, encoding='utf-8-sig')
        # 날짜 형식 변환
        for col in ['sow_date', 'harvest_date', 'plant_date']:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col]).dt.date
        return df
    return pd.DataFrame(columns=DB_COLS)

# 앱 인터페이스
st.title("🌿 식물공장 상추 수확량 예측 시스템 v5")

# 사이드바 설정
st.sidebar.header("⚙️ 기본 설정")
target_date = st.sidebar.date_input("예측 기준일", date.today())
loss_rate_pct = st.sidebar.slider("기본 로스율 (%)", 0, 100, 20)
default_weight = st.sidebar.number_input("주당 기본 무게 (g)", value=100)

db = load_data()

# 데이터 계산 및 처리 로직 (생략된 기존 계산식 포함)
def process_predictions(df):
    if df.empty: return df
    # 로직: 판 수 * 주수 * (1-로스율)
    def _row_calc(r):
        tg = r['tray_or_gutter'] if pd.notna(r['tray_or_gutter']) else 0
        ppu = PLANTS_PER_TRAY if r['bed_type'] == 'fixed' else PLANTS_PER_GUTTER
        loss = r['loss_rate'] if pd.notna(r['loss_rate']) else (loss_rate_pct/100)
        p = round(float(tg) * ppu * (1 - loss))
        w = r['weight_per_plant_g'] if pd.notna(r['weight_per_plant_g']) else default_weight
        k = round(p * float(w) / 1000, 2)
        return pd.Series([p, k])
    
    df[['predicted_plants', 'predicted_kg']] = df.apply(_row_calc, axis=1)
    return df

db = process_predictions(db)

# 탭 구성
tab1, tab2 = st.tabs(["📊 대시보드", "➕ 배치 추가/관리"])

with tab1:
    st.subheader(f"📅 {target_date} 기준 예측 현황")
    if not db.empty:
        # D+3, D+4 필터링
        d3, d4 = target_date + timedelta(days=3), target_date + timedelta(days=4)
        view_df = db[db['harvest_date'].isin([d3, d4])]
        
        col1, col2 = st.columns(2)
        col1.metric("총 예측 주수", f"{view_df['predicted_plants'].sum():,.0f}주")
        col2.metric("총 예측 무게", f"{view_df['predicted_kg'].sum():.1f} kg")
        
        st.dataframe(view_df, use_container_width=True)
    else:
        st.info("데이터가 없습니다. '배치 추가' 탭에서 데이터를 입력해 주세요.")

with tab2:
    st.subheader("새로운 배치 등록")
    with st.form("new_batch_form"):
        c1, c2, c3 = st.columns(3)
        new_id = c1.text_input("배치 ID (예: BATCH-01)")
        new_type = c2.selectbox("재배 방식", ["fixed", "mgs"])
        new_bed = c3.text_input("재배대 번호")
        
        d1, d2, d3 = st.columns(3)
        s_date = d1.date_input("파종일")
        h_date = d2.date_input("수확예정일")
        tg_val = d3.number_input("판/거터 수", min_value=1)
        
        if st.form_submit_button("DB에 저장"):
            new_row = pd.DataFrame([{
                'batch_id': new_id, 'bed_type': new_type, 'bed_id': new_bed,
                'sow_date': s_date, 'harvest_date': h_date, 'tray_or_gutter': tg_val
            }])
            updated_db = pd.concat([db, new_row], ignore_index=True)
            updated_db.to_csv(DB_PATH, index=False, encoding='utf-8-sig')
            st.success("저장 완료! 페이지를 새로고침 하세요.")
            st.rerun()