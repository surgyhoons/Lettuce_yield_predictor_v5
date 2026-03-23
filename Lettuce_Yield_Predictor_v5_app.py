import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import numpy as np
import os, warnings
from datetime import date, timedelta

# 기본 설정 및 에러 무시
warnings.filterwarnings('ignore')
st.set_page_config(page_title="식물공장 상추 수확량 예측 v5", layout="wide")

# ============================================================
# 1. 구글 시트 연결 설정 (Secrets 연동)
# ============================================================
# 시트 주소: https://docs.google.com/spreadsheets/d/1FMxN2iS0srEZD2bQ5dlQp2-JaZaXvd24W-glJpqReuo/edit?usp=sharing
conn = st.connection("gsheets", type=GSheetsConnection)

def load_db():
    try:
        # 캐시 없이 실시간 데이터를 읽어옵니다.
        df = conn.read(ttl="0")
        return df
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return pd.DataFrame()

# ============================================================
# 2. 고정 설정값 (노트북 소스 그대로 유지)
# ============================================================
FIXED_BED_CONFIG = {
    1:40,  2:40,  3:40,  4:40,  5:40,  6:40,  7:40,
    8:32,  9:32,  10:32, 11:32, 12:32, 13:32, 14:32,
    15:32, 16:32, 17:32, 18:32,
    19:40, 20:40
}
PLANTS_PER_TRAY   = 16
PLANTS_PER_GUTTER = 13

# ============================================================
# 3. 사이드바 - 사용자 설정 (노트북 '셀 3' 역할)
# ============================================================
st.sidebar.header("⚙️ 예측 설정값")
PREDICTION_DATE = st.sidebar.date_input("예측 기준일 (D+0)", date.today())
LOSS_RATE_PCT = st.sidebar.slider("기본 로스율 (%)", 0, 100, 20)
DEFAULT_WEIGHT_G = st.sidebar.number_input("주당 기본 무게 (g)", value=100)
MGS_TOTAL_GUTTERS_VAL = st.sidebar.number_input("MGS 거터 수 (미확정 시 0)", value=0)
MGS_TOTAL_GUTTERS = None if MGS_TOTAL_GUTTERS_VAL == 0 else MGS_TOTAL_GUTTERS_VAL

# 내부 계산용 변수
LOSS_RATE = LOSS_RATE_PCT / 100
YIELD_RATE = 1 - LOSS_RATE
DASH_DATES = [PREDICTION_DATE, PREDICTION_DATE + timedelta(days=3), PREDICTION_DATE + timedelta(days=4)]
TARGET_DATES = DASH_DATES[1:]

# ============================================================
# 4. 데이터 처리 엔진
# ============================================================
def process_data(d):
    if d.empty: return d
    # 날짜 파싱
    for col in ['sow_date','transplant_date','plant_date','harvest_date']:
        d[col] = pd.to_datetime(d[col], errors='coerce')
    
    # 숫자형 변환 및 결측치 처리
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
        if pd.isna(tg): return pd.Series({'predicted_plants': np.nan, 'predicted_kg': np.nan})
        ppu = PLANTS_PER_TRAY if r['bed_type'] == 'fixed' else PLANTS_PER_GUTTER
        p = round(float(tg) * ppu * (1 - r['loss_rate']))
        k = round(p * float(r['weight_per_plant_g']) / 1000, 2)
        return pd.Series({'predicted_plants': p, 'predicted_kg': k})
    
    d[['predicted_plants','predicted_kg']] = d.apply(_row, axis=1)
    # 총 재배일수 계산
    d['total_days'] = (d['harvest_date'] - d['sow_date']).dt.days
    return d

# --- 메인 화면 렌더링 ---
st.title("🌿 식물공장 상추 수확량 예측 시스템 v5")

db_raw = load_db()
if db_raw.empty:
    st.warning("연결된 구글 시트에서 데이터를 가져올 수 없거나 시트가 비어 있습니다.")
else:
    db_all = process_data(db_raw)
    target = db_all[db_all['harvest_date'].dt.date.isin(TARGET_DATES)].copy()

    # ============================================================
    # 5. 📊 3일 대시보드 UI (노트북 '셀 5' 완벽 복원)
    # ============================================================
    def day_sum(d, t_date):
        sub = d[d['harvest_date'].dt.date == t_date]
        pp = sub['predicted_plants'].sum(skipna=True)
        pk = sub['predicted_kg'].sum(skipna=True)
        ap = sub['actual_yield'].sum(skipna=True)
        ak = sub['actual_weight_kg'].sum(skipna=True)
        has_actual = sub['actual_weight_kg'].notna().any()
        return (pp, pk, ap if ap else None, ak if ak and has_actual else None, has_actual)

    d0_pp, d0_pk, d0_ap, d0_ak, d0_ha = day_sum(db_all, DASH_DATES[0])
    d3_pp, d3_pk, d3_ap, d3_ak, d3_ha = day_sum(db_all, DASH_DATES[1])
    d4_pp, d4_pk, d4_ap, d4_ak, d4_ha = day_sum(db_all, DASH_DATES[2])

    def get_day_card_html(label, color, dt, pp, pk, ap, ak, has_actual):
        WEEKDAYS_KR = ['월','화','수','목','금','토','일']
        date_s = f'{dt.month}월 {dt.day}일 ({WEEKDAYS_KR[dt.weekday()]})'
        border = f'border:2px solid {color}' if color != '#888' else 'border:0.5px solid #ccc'
        
        diff_html = ""
        if pd.notna(pk) and pd.notna(ak):
            d_val = round(ak - pk, 1)
            sign, clr = ('+', '#27500A') if d_val >= 0 else ('', '#A32D2D')
            diff_html = f'<div style="text-align:right;font-size:12px;font-weight:500;color:{clr}">오차 {sign}{d_val} kg</div>'
            
        actual_block = f'''
            <div style="border-top:0.5px solid #e0e0e0;margin-top:10px;padding-top:10px">
                <div style="font-size:10px;font-weight:600;color:#888;margin-bottom:6px">실적</div>
                <div style="display:flex;justify-content:space-between;margin-bottom:4px"><span style="font-size:11px;color:#888">실제 주수</span><span style="font-size:15px;font-weight:500">{f"{int(ap):,}" if ap else "—"}</span></div>
                <div style="display:flex;justify-content:space-between;margin-bottom:4px"><span style="font-size:11px;color:#888">실제 무게</span><span style="font-size:15px;font-weight:500;color:#185FA5">{f"{ak:.1f}" if ak else "—"} kg</span></div>
                {diff_html}
            </div>''' if has_actual else ""

        return f'''
        <div style="background:#fff;{border};border-radius:12px;padding:14px 16px;height:240px">
          <div style="font-size:10px;font-weight:600;color:{color};margin-bottom:6px">{label}</div>
          <div style="font-size:14px;font-weight:500;margin-bottom:12px">{date_s}</div>
          <div style="font-size:10px;font-weight:600;color:#888;margin-bottom:6px">예측</div>
          <div style="display:flex;justify-content:space-between;margin-bottom:4px"><span style="font-size:11px;color:#888">주수</span><span style="font-size:17px;font-weight:500">{f"{int(pp):,}" if pd.notna(pp) else "0"}주</span></div>
          <div style="display:flex;justify-content:space-between;margin-bottom:4px"><span style="font-size:11px;color:#888">무게</span><span style="font-size:17px;font-weight:500;color:{color}">{f"{pk:.1f}" if pd.notna(pk) else "0.0"} kg</span></div>
          {actual_block}
        </div>'''

    col1, col2, col3 = st.columns(3)
    col1.markdown(get_day_card_html('D+0 · 오늘', '#888', DASH_DATES[0], d0_pp, d0_pk, d0_ap, d0_ak, d0_ha), unsafe_allow_html=True)
    col2.markdown(get_day_card_html('D+3 · 수확 예정', '#3B6D11', DASH_DATES[1], d3_pp, d3_pk, d3_ap, d3_ak, d3_ha), unsafe_allow_html=True)
    col3.markdown(get_day_card_html('D+4 · 수확 예정', '#185FA5', DASH_DATES[2], d4_pp, d4_pk, d4_ap, d4_ak, d4_ha), unsafe_allow_html=True)

    total_pp, total_pk = (d3_pp if pd.notna(d3_pp) else 0) + (d4_pp if pd.notna(d4_pp) else 0), round((d3_pk if pd.notna(d3_pk) else 0) + (d4_pk if pd.notna(d4_pk) else 0), 1)
    st.markdown(f'''
    <div style="background:#27500A;border-radius:12px;padding:14px 20px;display:flex;justify-content:space-around;margin-top:20px;margin-bottom:20px">
        <div style="text-align:center"><div style="font-size:10px;color:#C0DD97">이번 주 예측 주수 (D+3~4)</div><div style="font-size:20px;font-weight:500;color:#EAF3DE">{int(total_pp):,}주</div></div>
        <div style="text-align:center"><div style="font-size:10px;color:#C0DD97">이번 주 예측 무게 (D+3~4)</div><div style="font-size:20px;font-weight:500;color:#EAF3DE">{total_pk:.1f} kg</div></div>
        <div style="text-align:center"><div style="font-size:10px;color:#C0DD97">수확률</div><div style="font-size:20px;font-weight:500;color:#EAF3DE">{100-LOSS_RATE_PCT}%</div></div>
    </div>
    ''', unsafe_allow_html=True)

    # ============================================================
    # 6. 📋 상세 테이블 UI (노트북 디자인 그대로)
    # ============================================================
    st.write("### 📋 배치별 상세 (D+3~4)")
    detail_rows = ""
    for _, row in target.sort_values('harvest_date').iterrows():
        bt_bg, bt_fg = ('#EAF3DE','#27500A') if row['bed_type']=='fixed' else ('#E6F1FB','#0C447C')
        
        # 실제 주당 무게 계산
        awpg = None
        if pd.notna(row['actual_yield']) and row['actual_yield'] > 0 and pd.notna(row['actual_weight_kg']):
            awpg = round(float(row['actual_weight_kg']) * 1000 / float(row['actual_yield']), 1)
        
        # 실적 오차 계산
        diff_html = ""
        if pd.notna(row['actual_weight_kg']) and pd.notna(row['predicted_kg']):
            diff = round(row['actual_weight_kg'] - row['predicted_kg'], 1)
            sign, clr = ('+', '#27500A') if diff >= 0 else ('', '#A32D2D')
            diff_html = f'<br><span style="font-size:10px;color:{clr}">{sign}{diff} kg</span>'

        # 행 데이터 생성
        h_date_s = row['harvest_date'].strftime('%m-%d') if pd.notna(row['harvest_date']) else "—"
        s_date_s = row['sow_date'].strftime('%m-%d') if pd.notna(row['sow_date']) else "—"
        t_days_s = f"{int(row['total_days'])}일" if pd.notna(row['total_days']) else "—"
        p_plants_s = f"{int(row['predicted_plants']):,}" if pd.notna(row['predicted_plants']) else "0"
        p_kg_s = f"{row['predicted_kg']:.1f}" if pd.notna(row['predicted_kg']) else "0.0"

        detail_rows += f'''
        <tr style="border-bottom:0.5px solid #eee; font-size:12px">
          <td style="padding:8px;font-family:monospace">{row['batch_id']}</td>
          <td><span style="background:{bt_bg};color:{bt_fg};padding:2px 7px;border-radius:10px;font-weight:600">{'고정' if row['bed_type']=='fixed' else 'MGS'}</span></td>
          <td style="text-align:center">{row['bed_id']}</td>
          <td style="text-align:center">{s_date_s}</td>
          <td style="text-align:center">{h_date_s}</td>
          <td style="text-align:center">{t_days_s}</td>
          <td style="text-align:center">{row['tray_or_gutter'] if pd.notna(row['tray_or_gutter']) else "—"}</td>
          <td style="text-align:right">{p_plants_s}주</td>
          <td style="text-align:right;font-weight:600;color:#27500A">{p_kg_s} kg{diff_html}</td>
          <td style="text-align:right;color:#185FA5">{f"{int(row['actual_yield']):,}주" if pd.notna(row['actual_yield']) else ""}</td>
          <td style="text-align:right;color:#185FA5">{f"{row['actual_weight_kg']:.1f}kg" if pd.notna(row['actual_weight_kg']) else ""}</td>
          <td style="text-align:right">{f"{awpg}g" if awpg else "—"}</td>
        </tr>'''

    st.markdown(f'''
    <div style="overflow-x:auto">
    <table style="width:100%; border-collapse:collapse">
        <thead style="background:#f7f7f7; font-size:11px">
            <tr style="border-bottom:1.5px solid #ddd">
                <th style="padding:10px;text-align:left">배치 ID</th><th style="text-align:left">방식</th><th>재배대</th><th>파종일</th><th>수확일</th><th>재배일</th><th>판/거터</th><th style="text-align:right">예측주수</th><th style="text-align:right">예측무게</th><th style="text-align:right">실제주수</th><th style="text-align:right">실제무게</th><th style="text-align:right">주당무게</th>
            </tr>
        </thead>
        <tbody>{detail_rows}</tbody>
    </table>
    </div>
    ''', unsafe_allow_html=True)

    # ============================================================
    # 7. 📝 노션 마크다운 출력 (에러 방지 적용)
    # ============================================================
    with st.expander("📋 노션 마크다운 복사하기"):
        md = [
            f'## 수확량 예측 — {PREDICTION_DATE} 기준', 
            '', 
            '| 수확예정일 | 방식 | 재배대 | 예측주수 | 예측무게(kg) | 실적(kg) |', 
            '|---|---|---|---|---|---|'
        ]
        for _, r in target.iterrows():
            h_date = r['harvest_date'].date() if pd.notna(r['harvest_date']) else "—"
            p_plants = f"{int(r['predicted_plants']):,}주" if pd.notna(r['predicted_plants']) else "N/A"
            p_kg = f"{r['predicted_kg']:.1f}" if pd.notna(r['predicted_kg']) else "N/A"
            a_kg = f"{r['actual_weight_kg']:.1f}" if pd.notna(r['actual_weight_kg']) else "—"
            md.append(f"| {h_date} | {r['bed_type']} | {r['bed_id']} | {p_plants} | {p_kg} | {a_kg} |")
        st.code('\n'.join(md))

st.sidebar.markdown("---")
st.sidebar.info("💡 데이터 수정/삭제는 연결된 구글 시트에서 직접 수행해 주세요.")
