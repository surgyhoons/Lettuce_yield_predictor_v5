import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import numpy as np
import os, warnings
from datetime import date, timedelta

# 기본 설정
warnings.filterwarnings('ignore')
st.set_page_config(page_title="식물공장 상추 수확량 예측 v5", layout="wide")

# 1. 구글 시트 연결 (Secrets 설정 필요)
# 시트 주소: https://docs.google.com/spreadsheets/d/1FMxN2iS0srEZD2bQ5dlQp2-JaZaXvd24W-glJpqReuo/edit?usp=sharing
SHEET_URL = "https://docs.google.com/spreadsheets/d/1FMxN2iS0srEZD2bQ5dlQp2-JaZaXvd24W-glJpqReuo/edit?usp=sharing"

conn = st.connection("gsheets", type=GSheetsConnection)

# 데이터 로드 함수
def load_data():
    return conn.read(spreadsheet=SHEET_URL, ttl="0") # 실시간 반영을 위해 캐시(ttl)를 0으로 설정

# 2. 고정 설정값 (노트북 소스 그대로 유지)
FIXED_BED_CONFIG = {
    1:40,  2:40,  3:40,  4:40,  5:40,  6:40,  7:40,
    8:32,  9:32,  10:32, 11:32, 12:32, 13:32, 14:32,
    15:32, 16:32, 17:32, 18:32,
    19:40, 20:40
}
PLANTS_PER_TRAY   = 16
PLANTS_PER_GUTTER = 13

# 3. 사이드바 - 사용자 설정 (노트북 '셀 3' 역할)
st.sidebar.header("⚙️ 예측 설정값")
PREDICTION_DATE = st.sidebar.date_input("예측 기준일 (D+0)", date.today())
LOSS_RATE_PCT = st.sidebar.slider("기본 로스율 (%)", 0, 100, 20)
DEFAULT_WEIGHT_G = st.sidebar.number_input("주당 기본 무게 (g)", value=100)
MGS_TOTAL_GUTTERS = st.sidebar.number_input("MGS 거터 수 (미확정 시 0)", value=0)
MGS_TOTAL_GUTTERS = None if MGS_TOTAL_GUTTERS == 0 else MGS_TOTAL_GUTTERS

# 내부 계산용 변수
LOSS_RATE = LOSS_RATE_PCT / 100
YIELD_RATE = 1 - LOSS_RATE
DASH_DATES = [PREDICTION_DATE, PREDICTION_DATE + timedelta(days=3), PREDICTION_DATE + timedelta(days=4)]
TARGET_DATES = DASH_DATES[1:]

# 4. 계산 엔진 (노트북 로직 100% 이식)
def process_data(d):
    if d.empty: return d
    # 날짜 파싱
    for col in ['sow_date','transplant_date','plant_date','harvest_date']:
        d[col] = pd.to_datetime(d[col], errors='coerce')
    
    # 기본값 채우기
    d['loss_rate'] = pd.to_numeric(d['loss_rate'], errors='coerce').fillna(LOSS_RATE)
    d['tray_or_gutter'] = pd.to_numeric(d['tray_or_gutter'], errors='coerce')
    d['weight_per_plant_g'] = pd.to_numeric(d['weight_per_plant_g'], errors='coerce').fillna(DEFAULT_WEIGHT_G)
    d['actual_yield'] = pd.to_numeric(d['actual_yield'], errors='coerce')
    d['actual_weight_kg'] = pd.to_numeric(d['actual_weight_kg'], errors='coerce')
    
    if MGS_TOTAL_GUTTERS is not None:
        d.loc[d['bed_type'] == 'mgs', 'tray_or_gutter'] = MGS_TOTAL_GUTTERS
        
    # 예측값 계산
    def _row(r):
        tg = r['tray_or_gutter']
        if pd.isna(tg): return pd.Series({'predicted_plants': None, 'predicted_kg': None})
        ppu = PLANTS_PER_TRAY if r['bed_type'] == 'fixed' else PLANTS_PER_GUTTER
        p = round(float(tg) * ppu * (1 - r['loss_rate']))
        k = round(p * float(r['weight_per_plant_g']) / 1000, 2)
        return pd.Series({'predicted_plants': p, 'predicted_kg': k})
    
    d[['predicted_plants','predicted_kg']] = d.apply(_row, axis=1)
    d['total_days'] = (d['harvest_date'] - d['sow_date']).dt.days
    return d

# --- UI 렌더링 시작 ---
st.title("🌿 식물공장 상추 수확량 예측 시스템 v5")

db_raw = load_db()
if db_raw.empty:
    st.warning("연결된 구글 시트에 데이터가 없습니다.")
else:
    db_all = process_data(db_raw)
    target = db_all[db_all['harvest_date'].dt.date.isin(TARGET_DATES)].copy()

    # 5. 대시보드 (노트북 '셀 5' UI 100% 복원)
    def day_sum(d, t_date):
        sub = d[d['harvest_date'].dt.date == t_date]
        pp, pk = sub['predicted_plants'].sum(), sub['predicted_kg'].sum()
        ap, ak = sub['actual_yield'].sum(), sub['actual_weight_kg'].sum()
        has_actual = sub['actual_weight_kg'].notna().any()
        return (int(pp), round(float(pk),1), int(ap) if ap else None, round(float(ak),1) if ak and has_actual else None, has_actual)

    d0_pp, d0_pk, d0_ap, d0_ak, d0_ha = day_sum(db_all, DASH_DATES[0])
    d3_pp, d3_pk, d3_ap, d3_ak, d3_ha = day_sum(db_all, DASH_DATES[1])
    d4_pp, d4_pk, d4_ap, d4_ak, d4_ha = day_sum(db_all, DASH_DATES[2])

    # 노트북의 day_card HTML 함수
    def get_day_card_html(label, color, dt, pp, pk, ap, ak, has_actual):
        WEEKDAYS_KR = ['월','화','수','목','금','토','일']
        date_s = f'{dt.month}월 {dt.day}일 ({WEEKDAYS_KR[dt.weekday()]})'
        border = f'border:2px solid {color}' if color != '#888' else 'border:0.5px solid #ccc'
        
        diff_html = ""
        if pk and ak is not None:
            d_val = round(ak - pk, 1)
            sign, clr = ('+', '#27500A') if d_val >= 0 else ('', '#A32D2D')
            diff_html = f'<div style="text-align:right;font-size:12px;font-weight:500;color:{clr}">오차 {sign}{d_val} kg</div>'
            
        actual_block = f'''
            <div style="border-top:0.5px solid #e0e0e0;margin-top:10px;padding-top:10px">
                <div style="font-size:10px;font-weight:600;color:#888;margin-bottom:6px">실적</div>
                <div style="display:flex;justify-content:space-between;margin-bottom:4px"><span style="font-size:11px;color:#888">실제 주수</span><span style="font-size:15px;font-weight:500">{ap if ap else "—"}</span></div>
                <div style="display:flex;justify-content:space-between;margin-bottom:4px"><span style="font-size:11px;color:#888">실제 무게</span><span style="font-size:15px;font-weight:500;color:#185FA5">{ak if ak else "—"} kg</span></div>
                {diff_html}
            </div>''' if has_actual else ""

        return f'''
        <div style="background:#fff;{border};border-radius:12px;padding:14px 16px;height:100%">
          <div style="font-size:10px;font-weight:600;color:{color};margin-bottom:6px">{label}</div>
          <div style="font-size:14px;font-weight:500;margin-bottom:12px">{date_s}</div>
          <div style="font-size:10px;font-weight:600;color:#888;margin-bottom:6px">예측</div>
          <div style="display:flex;justify-content:space-between;margin-bottom:4px"><span style="font-size:11px;color:#888">주수</span><span style="font-size:17px;font-weight:500">{pp:,}주</span></div>
          <div style="display:flex;justify-content:space-between;margin-bottom:4px"><span style="font-size:11px;color:#888">무게</span><span style="font-size:17px;font-weight:500;color:{color}">{pk:.1f} kg</span></div>
          {actual_block}
        </div>'''

    # 상단 3개 카드 배치
    col1, col2, col3 = st.columns(3)
    col1.markdown(get_day_card_html('D+0 · 오늘', '#888', DASH_DATES[0], d0_pp, d0_pk, d0_ap, d0_ak, d0_ha), unsafe_allow_html=True)
    col2.markdown(get_day_card_html('D+3 · 수확 예정', '#3B6D11', DASH_DATES[1], d3_pp, d3_pk, d3_ap, d3_ak, d3_ha), unsafe_allow_html=True)
    col3.markdown(get_day_card_html('D+4 · 수확 예정', '#185FA5', DASH_DATES[2], d4_pp, d4_pk, d4_ap, d4_ak, d4_ha), unsafe_allow_html=True)

    # 중간 요약 바 (HTML)
    total_pp, total_pk = d3_pp + d4_pp, round(d3_pk + d4_pk, 1)
    st.markdown(f'''
    <div style="background:#27500A;border-radius:12px;padding:14px 20px;display:flex;justify-content:space-around;margin-top:20px;margin-bottom:20px">
        <div style="text-align:center"><div style="font-size:10px;color:#C0DD97">이번 주 예측 주수 (D+3~4)</div><div style="font-size:20px;font-weight:500;color:#EAF3DE">{total_pp:,}주</div></div>
        <div style="text-align:center"><div style="font-size:10px;color:#C0DD97">이번 주 예측 무게 (D+3~4)</div><div style="font-size:20px;font-weight:500;color:#EAF3DE">{total_pk:.1f} kg</div></div>
        <div style="text-align:center"><div style="font-size:10px;color:#C0DD97">수확률</div><div style="font-size:20px;font-weight:500;color:#EAF3DE">{100-LOSS_RATE_PCT}%</div></div>
    </div>
    ''', unsafe_allow_html=True)

    # 6. 상세 배치 테이블 (HTML 방식 유지)
    st.write("### 📋 배치별 상세 (D+3~4)")
    detail_rows = ""
    for _, row in target.sort_values('harvest_date').iterrows():
        bt_bg, bt_fg = ('#EAF3DE','#27500A') if row['bed_type']=='fixed' else ('#E6F1FB','#0C447C')
        awpg = round(float(row['actual_weight_kg']) * 1000 / float(row['actual_yield']), 1) if (pd.notna(row['actual_yield']) and row['actual_yield'] > 0 and pd.notna(row['actual_weight_kg'])) else None
        
        diff_html = ""
        if pd.notna(row['actual_weight_kg']):
            diff = round(row['actual_weight_kg'] - row['predicted_kg'], 1)
            sign, clr = ('+', '#27500A') if diff >= 0 else ('', '#A32D2D')
            diff_html = f'<br><span style="font-size:10px;color:{clr}">{sign}{diff} kg</span>'

        detail_rows += f'''
        <tr style="border-bottom:0.5px solid #eee; font-size:12px">
          <td style="padding:8px;font-family:monospace">{row['batch_id']}</td>
          <td><span style="background:{bt_bg};color:{bt_fg};padding:2px 7px;border-radius:10px;font-weight:600">{'고정' if row['bed_type']=='fixed' else 'MGS'}</span></td>
          <td style="text-align:center">{row['bed_id']}</td>
          <td style="text-align:center">{row['sow_date'].strftime('%m-%d')}</td>
          <td style="text-align:center">{row['harvest_date'].strftime('%m-%d')}</td>
          <td style="text-align:center">{int(row['total_days'])}일</td>
          <td style="text-align:center">{row['tray_or_gutter']}</td>
          <td style="text-align:right">{row['predicted_plants']:,}주</td>
          <td style="text-align:right;font-weight:600;color:#27500A">{row['predicted_kg']:.1f} kg{diff_html}</td>
          <td style="text-align:right;color:#185FA5">{f"{int(row['actual_yield']):,}주" if pd.notna(row['actual_yield']) else ""}</td>
          <td style="text-align:right;color:#185FA5">{f"{row['actual_weight_kg']:.1f}kg" if pd.notna(row['actual_weight_kg']) else ""}</td>
          <td style="text-align:right">{f"{awpg}g" if awpg else "—"}</td>
        </tr>'''

    st.markdown(f'''
    <table style="width:100%; border-collapse:collapse">
        <thead style="background:#f7f7f7; font-size:11px">
            <tr><th>배치 ID</th><th>방식</th><th>재배대</th><th>파종일</th><th>수확일</th><th>재배일</th><th>판/거터</th><th>예측주수</th><th>예측무게</th><th>실제주수</th><th>실제무게</th><th>주당무게</th></tr>
        </thead>
        <tbody>{detail_rows}</tbody>
    </table>
    ''', unsafe_allow_html=True)

    # 7. 노션 출력 (텍스트 영역으로 제공)
    with st.expander("📋 노션 마크다운 복사하기"):
        md = [f'## 수확량 예측 — {PREDICTION_DATE} 기준', '', '| 수확예정일 | 방식 | 재배대 | 예측주수 | 예측무게(kg) | 실적(kg) |', '|---|---|---|---|---|---|']
        for _, r in target.iterrows():
            md.append(f"| {r['harvest_date'].date()} | {r['bed_type']} | {r['bed_id']} | {int(r['predicted_plants']):,}주 | {r['predicted_kg']:.1f} | {r['actual_weight_kg'] if pd.notna(r['actual_weight_kg']) else '—'} |")
        st.code('\n'.join(md))

st.sidebar.markdown("---")
st.sidebar.write("💡 데이터 수정은 구글 시트에서 직접 하세요.")
