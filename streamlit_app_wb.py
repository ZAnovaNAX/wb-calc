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
    s = s.replace('\u200b', '')  # zero-width if any
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
    # Try to find obvious column by name
    candidates = [c for c in df.columns if isinstance(c, str)]
    for c in candidates:
        name = c.lower()
        if 'цена со скид' in name or ('цена' in name and 'скид' in name) or 'm' == name.strip().lower():
            return c
    # fallback to column index 12 (M) if exists
    if df.shape[1] > 12:
        return df.columns[12]
    # else choose numeric column with most non-nulls
    best = None
    best_cnt = -1
    for c in df.columns:
        cnt = pd.to_numeric(df[c], errors='coerce').notnull().sum()
        if cnt > best_cnt:
            best_cnt = cnt
            best = c
    return best


def detect_tech_art_col(df):
    # prefer explicit names
    for c in df.columns:
        if isinstance(c, str) and ('артикул продав' in c.lower() or 'артикул wb' in c.lower() or c.lower().startswith('артикул')):
            return c
    # fallback to any column with many numeric values
    best = None
    best_cnt = -1
    for c in df.columns:
        cnt = pd.to_numeric(df[c], errors='coerce').notnull().sum()
        if cnt > best_cnt:
            best_cnt = cnt
            best = c
    return best


def find_best_new_art_col(new_df, tech_seller_set):
    # new_df is usually read with header=None -> columns are 0..n
    best_col = None
    best_matches = 0
    for c in new_df.columns:
        # normalize values in this column
        vals = new_df[c].dropna().astype(str).map(lambda x: normalize_art(x))
        matches = len(set(vals.dropna().unique()) & tech_seller_set)
        if matches > best_matches:
            best_matches = matches
            best_col = c
    return best_col, best_matches


# -------------------- UI: загрузка --------------------
st.markdown("Загрузите файлы: \n- `техно` (файл с колонкой 'Цена со скидкой', обычно `техно.xlsx`)\n- `Новый` (файл с вашими закупочными ценами)\n")
tech_file = st.file_uploader("📂 Загрузите файл (техно.xlsx) — содержит 'Цена со скидкой' (столбец M)", type=["xlsx", "xls"]) 
new_file = st.file_uploader("📂 Загрузите файл (Новый.xlsx) — содержит артикулы и закупки (обычно без заголовка)", type=["xlsx", "xls"]) 

if tech_file and new_file:
    # читаем техно с заголовком
    try:
        tech_df = pd.read_excel(tech_file, sheet_name=0, engine='openpyxl')
    except Exception:
        tech_df = pd.read_excel(tech_file, sheet_name=0)

    # читаем новый файл без заголовка (как в оригинальном скрипте)
    try:
        new_df = pd.read_excel(new_file, sheet_name=0, header=None, engine='openpyxl')
    except Exception:
        new_df = pd.read_excel(new_file, sheet_name=0, header=None)

    st.sidebar.markdown("### Настройки (если автоопределение некорректно, можно выбрать вручную)")

    # попытка определить колонки автоматически
    tech_price_col = detect_tech_price_col(tech_df)
    tech_art_col = detect_tech_art_col(tech_df)

    tech_cols = list(tech_df.columns)
    tech_price_col_user = st.sidebar.selectbox("Колонка с 'Ценой со скидкой' (техно)", options=tech_cols, index=tech_cols.index(tech_price_col) if tech_price_col in tech_cols else 0)
    tech_art_col_user = st.sidebar.selectbox("Колонка с 'Артикул продавца' (техно)", options=tech_cols, index=tech_cols.index(tech_art_col) if tech_art_col in tech_cols else 0)

    # создаём множество артикула продавца для поиска в новом файле
    tech_df['seller_art_norm'] = tech_df[tech_art_col_user].apply(normalize_art)
    tech_seller_set = set(tech_df['seller_art_norm'].dropna().astype(str))

    # попробуем найти колонку с артикулом в новом файле автоматически
    best_new_art_col, matches = find_best_new_art_col(new_df, tech_seller_set)
    st.sidebar.write(f"Авто: найден столбец артикулов в новом файле: {best_new_art_col} (совпадений: {matches})")

    new_cols = list(new_df.columns)
    new_art_col_user = st.sidebar.selectbox("Колонка с артикулом в 'Новый.xlsx'", options=new_cols, index=new_cols.index(best_new_art_col) if best_new_art_col in new_cols else 3)

    # определяем колонки закупки: попытаемся найти две числовые колонки с наибольшим количеством значений
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

    # Чистим и нормализуем
    tech_df = tech_df[tech_df[tech_art_col_user].notna()].copy()
    tech_df['seller_art_norm'] = tech_df[tech_art_col_user].apply(normalize_art)

    new_df = new_df[new_df[new_art_col_user].notna()].copy()
    new_df['art_norm'] = new_df[new_art_col_user].apply(normalize_art)

    # Колонки закупки как числа
    new_df['purchase_1'] = new_df[col_purchase_1].apply(to_float_safe)
    new_df['purchase_2'] = new_df[col_purchase_2].apply(to_float_safe)

    # Сливаем по seller_art_norm == art_norm
    merged = pd.merge(
        tech_df,
        new_df[['art_norm', 'purchase_1', 'purchase_2']],
        left_on='seller_art_norm',
        right_on='art_norm',
        how='inner'
    )

    st.write(f"Найдено совпадений после объединения: {len(merged)}")

    # Вычисления
    price_col = tech_price_col_user
    merged['price_discount'] = merged[price_col].apply(to_float_safe)
    merged['price_after_35pct'] = (merged['price_discount'] * 0.65).round(2)

    # определяем верхнюю/нижнюю закупку построчно
    merged['purchase_upper'] = merged[['purchase_1', 'purchase_2']].max(axis=1)
    merged['purchase_lower'] = merged[['purchase_1', 'purchase_2']].min(axis=1)

    merged['profit_upper'] = (merged['price_after_35pct'] - merged['purchase_upper']).round(2)
    merged['profit_lower'] = (merged['price_after_35pct'] - merged['purchase_lower']).round(2)

    # Формируем результат для отображения
    out_cols = [
        tech_art_col_user,
        'seller_art_norm',
        price_col,
        'price_discount',
        'price_after_35pct',
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
    })

    # Стилизация
    def color_profit(val):
        if pd.isna(val):
            return ''
        return f"color: {'green' if val > 0 else 'red'}; font-weight: bold"

    # Вкладки: общий расчёт и один артикул
    tab1, tab2 = st.tabs(["📑 Общий расчёт", "🔍 Один артикул"]) 

    with tab1:
        st.subheader("Результат расчёта для WB")
        st.dataframe(df_out.style.applymap(color_profit, subset=['profit_upper', 'profit_lower']), use_container_width=True)

        # Выгрузка
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_out.to_excel(writer, index=False, sheet_name='WB_profit')
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
                r = row.iloc[0]
                st.write(f"**Артикул продавца:** {r['seller_art_norm']}")
                st.write(f"**Цена со скидкой (исх.):** {r['price_discount']} ₽")
                st.write(f"**Цена после -35%:** {r['price_after_35pct']} ₽")
                st.write(f"**Закупка верхняя:** {r['purchase_upper']} ₽, **нижняя:** {r['purchase_lower']} ₽")
                st.write(f"**Прибыль верхняя:** {r['profit_upper']} ₽, **нижняя:** {r['profit_lower']} ₽")

else:
    st.info('Загрузите оба файла (техно и Новый) чтобы запустить расчёт.')

# Конец скрипта
