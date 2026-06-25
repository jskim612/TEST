import os
import streamlit as st
import pandas as pd
import plotly.express as px
from data_loader import load_all_data
from metrics import add_derived, compute_kpis

st.set_page_config(page_title="마케팅 대시보드", layout="wide", page_icon="📊")

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

# ── 컬럼 포맷 설정
COL_CONFIG = {
    # 원본 컬럼명
    "비용":          st.column_config.NumberColumn("비용",    format="₩%,.0f"),
    "노출":          st.column_config.NumberColumn("노출",    format="%,.0f"),
    "클릭_채널":     st.column_config.NumberColumn("클릭",    format="%,.0f"),
    "구매_AF":       st.column_config.NumberColumn("구매",    format="%,.0f"),
    "구매매출_AF":   st.column_config.NumberColumn("매출",    format="₩%,.0f"),
    "회원가입_AF":   st.column_config.NumberColumn("회원가입", format="%,.0f"),
    # 집계 후 rename된 컬럼명
    "매출":          st.column_config.NumberColumn("매출",    format="₩%,.0f"),
    "클릭":          st.column_config.NumberColumn("클릭",    format="%,.0f"),
    "구매":          st.column_config.NumberColumn("구매",    format="%,.0f"),
    "회원가입":      st.column_config.NumberColumn("회원가입", format="%,.0f"),
    # 파생 지표
    "CPP":           st.column_config.NumberColumn("CPP",    format="₩%,.0f"),
    "CPC":           st.column_config.NumberColumn("CPC",    format="₩%,.0f"),
    "ROAS":          st.column_config.NumberColumn("ROAS",   format="%.2fx"),
    "CVR":           st.column_config.NumberColumn("CVR",    format="%.2f%%"),
    "ROAS%":         st.column_config.NumberColumn("ROAS%",  format="%.1f%%"),
}

def show_df(df):
    cfg = {c: COL_CONFIG[c] for c in df.columns if c in COL_CONFIG}
    st.dataframe(df, use_container_width=True, hide_index=True, column_config=cfg)

def roas_pct(df, col="ROAS"):
    """ROAS 비율값을 % 컬럼으로 변환 (차트용)"""
    df = df.copy()
    df["ROAS%"] = (df[col] * 100).round(1)
    return df

@st.cache_data(ttl=60)
def get_data():
    df = load_all_data(DATA_DIR)
    if df.empty:
        return df
    return add_derived(df)

# ── 헤더
st.title("📊 마케팅 퍼포먼스 대시보드")
st.caption(f"데이터 폴더: {DATA_DIR}")

df = get_data()
if df.empty:
    st.error("데이터 없음 — YYYY-MM-DD_channel.csv / YYYY-MM-DD_appsflyer.csv 파일을 같은 폴더에 넣어주세요.")
    st.stop()

# ── 사이드바 필터
st.sidebar.header("필터")
date_min, date_max = df["일"].min().date(), df["일"].max().date()
date_range = st.sidebar.date_input("기간", value=(date_min, date_max), min_value=date_min, max_value=date_max)

channels = ["전체"] + sorted(df["채널"].dropna().unique().tolist())
sel_channel = st.sidebar.selectbox("채널", channels)

campaigns = ["전체"] + sorted(df["캠페인"].dropna().unique().tolist())
sel_campaign = st.sidebar.selectbox("캠페인", campaigns)

if st.sidebar.button("🔄 데이터 새로고침"):
    st.cache_data.clear()
    st.rerun()

# ── 필터 적용
fdf = df.copy()
if len(date_range) == 2:
    fdf = fdf[(fdf["일"].dt.date >= date_range[0]) & (fdf["일"].dt.date <= date_range[1])]
elif len(date_range) == 1:
    fdf = fdf[fdf["일"].dt.date == date_range[0]]
    st.sidebar.info(f"{date_range[0]} 하루 데이터를 표시합니다.")

if sel_channel != "전체":
    fdf = fdf[fdf["채널"] == sel_channel]
if sel_campaign != "전체":
    fdf = fdf[fdf["캠페인"] == sel_campaign]

# ── KPI 카드
kpis = compute_kpis(fdf)
cols = st.columns(len(kpis))
for col, (label, value) in zip(cols, kpis.items()):
    col.metric(label, value)

st.divider()

# ── 탭 구성
tab1, tab2, tab3, tab4 = st.tabs(["📅 일별 트렌드", "📺 채널 비교", "🎯 캠페인 분석", "🖼️ 소재 분석"])

with tab1:
    daily = fdf.groupby("일").agg(
        비용=("비용", "sum"),
        구매=("구매_AF", "sum"),
        매출=("구매매출_AF", "sum"),
        클릭=("클릭_채널", "sum"),
    ).reset_index()
    daily["ROAS"] = (daily["매출"] / daily["비용"].replace(0, float("nan"))).round(4)
    daily = roas_pct(daily)

    metric_opt = st.selectbox("지표 선택", ["비용", "구매", "매출", "클릭", "ROAS%"], key="daily_metric")
    fig = px.line(daily, x="일", y=metric_opt, markers=True, title=f"일별 {metric_opt.replace('%','')}")
    if metric_opt == "ROAS%":
        fig.update_layout(yaxis_ticksuffix="%", yaxis_tickformat=",.1f", xaxis_tickformat="%Y-%m-%d")
    else:
        fig.update_layout(yaxis_tickformat=",.0f", xaxis_tickformat="%Y-%m-%d")
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    ch_agg = fdf.groupby("채널").agg(
        비용=("비용", "sum"),
        노출=("노출", "sum"),
        클릭=("클릭_채널", "sum"),
        구매=("구매_AF", "sum"),
        매출=("구매매출_AF", "sum"),
    ).reset_index()
    ch_agg["ROAS"] = (ch_agg["매출"] / ch_agg["비용"].replace(0, float("nan"))).round(4)
    ch_agg["CPP"] = (ch_agg["비용"] / ch_agg["구매"].replace(0, float("nan"))).round(0)
    ch_agg = roas_pct(ch_agg)

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(ch_agg, x="채널", y="비용", title="채널별 비용", color="채널")
        fig.update_layout(yaxis_tickformat="₩,.0f")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.bar(ch_agg, x="채널", y="ROAS%", title="채널별 ROAS", color="채널")
        fig.update_layout(yaxis_ticksuffix="%", yaxis_tickformat=",.1f")
        st.plotly_chart(fig, use_container_width=True)
    show_df(ch_agg.drop(columns=["ROAS%"]))

with tab3:
    cmp_agg = fdf.groupby("캠페인").agg(
        비용=("비용", "sum"),
        구매=("구매_AF", "sum"),
        매출=("구매매출_AF", "sum"),
        회원가입=("회원가입_AF", "sum"),
    ).reset_index()
    cmp_agg["ROAS"] = (cmp_agg["매출"] / cmp_agg["비용"].replace(0, float("nan"))).round(4)
    cmp_agg["CPP"] = (cmp_agg["비용"] / cmp_agg["구매"].replace(0, float("nan"))).round(0)
    cmp_agg = roas_pct(cmp_agg)

    fig = px.scatter(cmp_agg, x="비용", y="ROAS%", size="구매", color="캠페인",
                     hover_name="캠페인", title="캠페인별 비용 vs ROAS (버블 = 구매수)")
    fig.update_layout(
        xaxis_tickformat="₩,.0f",
        yaxis_ticksuffix="%", yaxis_tickformat=",.1f"
    )
    st.plotly_chart(fig, use_container_width=True)
    show_df(cmp_agg.drop(columns=["ROAS%"]).sort_values("ROAS", ascending=False))

with tab4:
    cr_agg = fdf.groupby("소재").agg(
        비용=("비용", "sum"),
        클릭=("클릭_채널", "sum"),
        구매=("구매_AF", "sum"),
        매출=("구매매출_AF", "sum"),
    ).reset_index()
    cr_agg["ROAS"] = (cr_agg["매출"] / cr_agg["비용"].replace(0, float("nan"))).round(4)
    cr_agg["CVR"] = (cr_agg["구매"] / cr_agg["클릭"].replace(0, float("nan")) * 100).round(2)
    cr_agg = roas_pct(cr_agg)

    top_n = st.slider("상위 소재 N개", 5, 30, 10, key="creative_n")
    top_cr = cr_agg.nlargest(top_n, "ROAS")
    fig = px.bar(top_cr, x="ROAS%", y="소재", orientation="h",
                 title=f"ROAS 상위 {top_n}개 소재", color="ROAS%", color_continuous_scale="RdYlGn")
    fig.update_layout(xaxis_ticksuffix="%", xaxis_tickformat=",.1f")
    st.plotly_chart(fig, use_container_width=True)
    show_df(top_cr.drop(columns=["ROAS%"]))
