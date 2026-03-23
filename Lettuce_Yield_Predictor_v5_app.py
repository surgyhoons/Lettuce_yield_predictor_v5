# 7. 노션 출력 (에러 방지용 안전 로직 추가)
    with st.expander("📋 노션 마크다운 복사하기"):
        md = [
            f'## 수확량 예측 — {PREDICTION_DATE} 기준', 
            '', 
            '| 수확예정일 | 방식 | 재배대 | 예측주수 | 예측무게(kg) | 실적(kg) |', 
            '|---|---|---|---|---|---|'
        ]
        
        for _, r in target.iterrows():
            # 값이 비어있을 경우를 대비한 안전한 변환
            h_date = r['harvest_date'].date() if pd.notna(r['harvest_date']) else "—"
            
            # 주수: 값이 있으면 정수+콤마(,), 없으면 N/A
            p_plants = f"{int(r['predicted_plants']):,}주" if pd.notna(r['predicted_plants']) else "N/A"
            
            # 무게: 값이 있으면 소수점 1자리, 없으면 N/A
            p_kg = f"{r['predicted_kg']:.1f}" if pd.notna(r['predicted_kg']) else "N/A"
            
            # 실적: 값이 있으면 소수점 1자리, 없으면 —
            a_kg = f"{r['actual_weight_kg']:.1f}" if pd.notna(r['actual_weight_kg']) else "—"
            
            md.append(f"| {h_date} | {r['bed_type']} | {r['bed_id']} | {p_plants} | {p_kg} | {a_kg} |")
            
        st.code('\n'.join(md))
