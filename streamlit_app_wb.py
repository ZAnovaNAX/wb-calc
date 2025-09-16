# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="Расчёт прибыли WB (Wildberries)", layout="wide")
st.title("📦 Расчёт прибыли Wildberries (WB)")

# -------------------- Утилиты --------------------
def normalize_art(x):
    if pd.isna(x):
        return None
    s = str(x).strip()
    s = s.replace('.0', '')
    s = re.sub(r"^0+", "", s)
    s = s.replace('\u200b', '')  # zero-width
    s = re.sub(r"\s+", "", s)    # удаляем пробелы внутри
    return s if s != '' else None


def to_float_safe(x):
    try:
        if pd.isna(x):
            return 0.0
        s = str(x)
        s = re.sub(r"[^\d\-\,\.]", "", s)
        s = s.replace(',', '.')
        if s == '':
            return 0.0
        return float(s)
    except Exception:
        return 0.0


def detect_tech_price_col(df):
    candidates = [c for c in df.columns if isinstance(c, str)]
    for c in candidates:
        name = c.lower()
        if 'цена со скид' in name or ('цена' in name and 'скид' in name) or 'm' == name.strip().lower():
            return c
    if df.shape[1] > 12:
        return df.columns[12]
    best = None
    best_cnt = -1
    for c in df.columns:
        cnt = pd.to_numeric(df[c], errors='coerce').notnull().sum()
        if cnt > best_cnt:
            best_cnt = cnt
            best = c
    return best


def detect_tech_art_col(df):
    for c in df.columns:
        if isinstance(c, str) and ('артикул продав' in c.lower() or 'артикул wb' in c.lower() or c.lower().startswith('артикул')):
            return c
    best = None
    best_cnt = -1
    for c in df.columns:
        cnt = pd.to_numeric(df[c], errors='coerce').notnull().sum()
        if cnt > best_cnt:
            best_cnt = cnt
            best = c
    return best


def find_best_new_art_col(new_df, tech_seller_set):
    best_col = None
    best_matches = 0
    for c in new_df.columns:
        vals = new_df[c].dropna().astype(str).map(lambda x: normalize_art(x))
        matches = len(set(vals.dropna().unique()) & tech_seller_set)
        if matches > best_matches:
            best_matches = matches
            best_col = c
    return best_col, best_matches


# -------------------- UI: загрузка --------------------
st.markdown("Загрузите файлы: \n- `техно` (файл с колонкой 'Цена со скидкой', обычно `техно.xlsx`)\n- `Новый` (файл с вашими закупочными ценами)\n")
tech_file = st.file_uploader("📂 Загрузите файл (техно.xlsx)", type=["xlsx", "xls"]) 
new_file = st.file_uploader("📂 Загрузите файл (Новый.xlsx)", type=["xlsx", "xls"]) 

if tech_file and new_file:
    try:
        tech_df = pd.read_excel(tech_file, sheet_name=0, engine='openpyxl')
    except Exception:
        tech_df = pd.read_excel(tech_file, sheet_name=0)

    try:
        new_df = pd.read_excel(new_file, sheet_name=0, header=None, engine='openpyxl')
    except Exception:
        new_df = pd.read_excel(new_file, sheet_name=0, header=None)

    st.sidebar.markdown("### Настройки")

    # процент удержания WB
    discount_pct = st.sidebar.number_input(
        "Процент удержания WB (%)", 
        min_value=0, 
        max_value=100, 
        value=35, 
        step=1
    )
    discount_coef = (100 - discount_pct) / 100

    # автоопределение колонок
    tech_price_col = detect_tech_price_col(tech_df)
    tech_art_col = detect_tech_art_col(tech_df)

    tech_cols = list(tech_df.columns)
    tech_price_col_user = st.sidebar.selectbox("Колонка с 'Ценой со скидкой' (техно)", options=tech_cols, index=tech_cols.index(tech_price_col) if tech_price_col in tech_cols else 0)
    tech_art_col_user = st.sidebar.selectbox("Колонка с 'Артикул продавца' (техно)", options=tech_cols, index=tech_cols.index(tech_art_col) if tech_art_col in tech_cols else 0)

    tech_df['seller_art_norm'] = tech_df[tech_art_col_user].apply(normalize_art)
    tech_seller_set = set(tech_df['seller_art_norm'].dropna().astype(str))

    best_new_art_col, matches = find_best_new_art_col(new_df, tech_seller_set)
    st.sidebar.write(f"Авто: найден столбец артикулов в новом файле: {best_new_art_col} (совпадений: {matches})")

    new_cols = list(new_df.columns)
    new_art_col_user = st.sidebar.selectbox("Колонка с артикулом в 'Новый.xlsx'", options=new_cols, index=new_cols.index(best_new_art_col) if best_new_art_col in new_cols else 3)

    numeric_counts = []
    for c in new_df.columns:
        if c == new_art_col_user:
            continue
        cnt = pd.to_numeric(new_df[c], errors='coerce').notnull().sum()
        numeric_counts.append((c, cnt))
    numeric_counts.sort(key=lambda x: x[1], reverse=True)
    default_p1 = numeric_counts[0][0] if len(numeric_counts) > 0 else None
    default_p2 = numeric_counts[1][0] if len(numeric_counts) > 1 else default_p1

    col_purchase_1 = st.sidebar.selectbox("Колонка закупки (1)", options=new_cols, index=new_cols.index(default_p1) if default_p1 in new_cols else 8)
    col_purchase_2 = st.sidebar.selectbox("Колонка закупки (2)", options=new_cols, index=new_cols.index(default_p2) if default_p2 in new_cols else 10)

    # чистим и нормализуем
    tech_df = tech_df[tech_df[tech_art_col_user].notna()].copy()
    tech_df['seller_art_norm'] = tech_df[tech_art_col_user].apply(normalize_art)

    new_df = new_df[new_df[new_art_col_user].notna()].copy()
    new_df['art_norm'] = new_df[new_art_col_user].apply(normalize_art)

    new_df['purchase_1'] = new_df[col_purchase_1].apply(to_float_safe)
    new_df['purchase_2'] = new_df[col_purchase_2].apply(to_float_safe)

    # объединение
    merged = pd.merge(
        tech_df,
        new_df[['art_norm', 'purchase_1', 'purchase_2']],
        left_on='seller_art_norm',
        right_on='art_norm',
        how='inner'
    )

    if merged.empty:
        st.warning("⚠️ Совпадений не найдено. Проверьте выбор колонок.")
    else:
        st.write(f"Найдено совпадений после объединения: {len(merged)}")

        # вычисления
        price_col = tech_price_col_user
        merged['price_discount'] = merged[price_col].apply(to_float_safe)
        merged['price_after_discount'] = (merged['price_discount'] * discount_coef).round(2)

        merged['purchase_upper'] = merged[['purchase_1', 'purchase_2']].max(axis=1)
        merged['purchase_lower'] = merged[['purchase_1', 'purchase_2']].min(axis=1)

        merged['profit_upper'] = (merged['price_after_discount'] - merged['purchase_upper']).round(2)
        merged['profit_lower'] = (merged['price_after_discount'] - merged['purchase_lower']).round(2)

        # результат
        out_cols = [
            tech_art_col_user,
            'seller_art_norm',
            price_col,
            'price_discount',
            'price_after_discount',
            'purchase_upper',
            'purchase_lower',
            'profit_upper',
            'profit_lower'
        ]

        df_out = merged[out_cols].copy()
        df_out = df_out.rename(columns={
            tech_art_col_user: 'Артикул WB (ориг)',
            'seller_art_norm': 'Артикул продавца (normalized)',
            price_col: 'Цена со скидкой (исх.)',
            'price_after_discount': f'Цена после -{discount_pct}%',
        })

        def color_profit(val):
            if pd.isna(val):
                return ''
            return f"color: {'green' if val > 0 else 'red'}; font-weight: bold"

        tab1, tab2 = st.tabs(["📑 Общий расчёт", "🔍 Один артикул"]) 

        with tab1:
            st.subheader("Результат расчёта для WB")
            st.dataframe(df_out.style.applymap(color_profit, subset=['profit_upper', 'profit_lower']), use_container_width=True)

            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_out.to_excel(writer, index=False, sheet_name='WB_profit', float_format="%.2f")
            st.download_button("💾 Скачать Excel", data=buffer.getvalue(), file_name="wb_profit.xlsx", mime="application/vnd.ms-excel")

        with tab2:
            st.subheader("Поиск по одному артикулу продавца")
            art_input = st.text_input("Введите артикул продавца (или нормализованный)")
            if art_input:
                art_n = normalize_art(art_input)
                row = merged[merged['seller_art_norm'] == art_n]
                if row.empty:
                    st.error('Артикул не найден в объединённых данных')
                else:
                    for _, r in row.iterrows():
                        st.write(f"**Артикул продавца:** {r['seller_art_norm']}")
                        st.write(f"**Цена со скидкой (исх.):** {r['price_discount']:,.2f} ₽")
                        st.write(f"**Цена после -{discount_pct}%:** {r['price_after_discount']:,.2f} ₽")
                        st.write(f"**Закупка верхняя:** {r['purchase_upper']:,.2f} ₽, **нижняя:** {r['purchase_lower']:,.2f} ₽")
                        st.write(f"**Прибыль верхняя:** {r['profit_upper']:,.2f} ₽, **нижняя:** {r['profit_lower']:,.2f} ₽")

else:
    st.info('Загрузите оба файла (техно и Новый) чтобы запустить расчёт.')

# Конец скрипта
