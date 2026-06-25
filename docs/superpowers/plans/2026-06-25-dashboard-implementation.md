# 퍼포먼스 마케팅 대시보드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 홈(이상탐지) + 채널·캠페인 + 소재 + 퍼널 탭 4개로 구성된 Streamlit 대시보드를 구현한다.

**Architecture:** `data_loader.py`가 raw 폴더에서 channel/appsflyer CSV를 스캔·조인하고, `metrics.py`가 KPI·이상탐지를, `creative_parser.py`가 소재명 파싱을 담당한다. `dashboard_app.py`는 이 세 모듈을 조합해 탭 4개를 렌더링한다.

**Tech Stack:** Python 3.12+, Streamlit ≥1.35, pandas ≥2.0, plotly ≥5.18

## Global Constraints

- 데이터 경로: `marketing-analytics/raw/channel/YYYY-MM-DD.csv`, `raw/appsflyer/YYYY-MM-DD.csv`
- 조인 키 5개: 일, 채널, 캠페인, 그룹, 소재
- 채널 매핑: 구글↔`googleadwords_int`, 메타↔`Facebook Ads`, 네이버↔`naver_search`
- 브랜드KW 제외: `NVR_CMP_01_브랜드KW` 포함 캠페인은 ROAS 집계에서 제외
- 네이버는 채널 비교에서 `[자체]` 레이블 표기
- ROAS 임계값: 🟢 ≥4.0 / 🟡 2.0~4.0 / 🔴 <2.0
- 금액 포맷: 억 단위 `₩1.2억`, 만 단위 `₩3,450만`
- ROAS: 소수점 2자리, 퍼센트: 소수점 1자리
- 인코딩: utf-8-sig 우선
- 앱 포트: 8502
- 저장: 내부용 parquet, 공유용 utf-8-sig CSV

---

## 파일 구조

```
marketing-analytics/
├── data_loader.py        # 수정: raw 폴더 스캔 + 5-key 조인
├── metrics.py            # 수정: KPI 계산 + 이상탐지 + 데이터 품질 체크
├── creative_parser.py    # 신규: 소재명 → 5개 속성 파싱
├── dashboard_app.py      # 신규: 탭 4개 Streamlit 앱
├── 실행.bat              # 수정: port 8502
└── tests/
    ├── test_data_loader.py
    ├── test_metrics.py
    └── test_creative_parser.py
```

---

### Task 1: data_loader.py — 5-key 조인 + 채널 매핑

**Files:**
- Modify: `marketing-analytics/data_loader.py`
- Test: `marketing-analytics/tests/test_data_loader.py`

**Produces:**
- `load_all_data(data_dir: str) -> pd.DataFrame` — 조인된 전체 데이터프레임
- 컬럼: 일, 채널, 채널분류, 캠페인, 캠페인목적, 그룹, 소재, 노출, 클릭_채널, 비용, 회원가입_채널, 구매_채널, 구매매출_채널, 클릭_AF, 회원가입_AF, 구매_AF, 구매매출_AF

- [ ] **Step 1: 테스트 파일 생성**

```python
# tests/test_data_loader.py
import pandas as pd, os, pytest
from data_loader import load_all_data

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

def test_load_joins_channel_and_af(tmp_path):
    ch_dir = tmp_path / "raw" / "channel"
    af_dir = tmp_path / "raw" / "appsflyer"
    ch_dir.mkdir(parents=True); af_dir.mkdir(parents=True)

    ch = pd.DataFrame([{
        "일":"2025-01-01","채널":"구글","채널분류":"외부",
        "캠페인":"GGL_CMP_01_플러스가입","캠페인목적":"플러스가입",
        "그룹":"논타겟","소재":"IMG_적립혜택_겨울_v1",
        "노출":10000,"클릭":100,"비용":50000,
        "회원가입":5,"구매":2,"구매매출":100000
    }])
    af = pd.DataFrame([{
        "일":"2025-01-01","미디어소스":"googleadwords_int",
        "캠페인":"GGL_CMP_01_플러스가입",
        "그룹":"논타겟","소재":"IMG_적립혜택_겨울_v1",
        "클릭":90,"회원가입":4,"구매":2,"구매매출":90000
    }])
    ch.to_csv(ch_dir / "2025-01-01.csv", index=False, encoding="utf-8-sig")
    af.to_csv(af_dir / "2025-01-01.csv", index=False, encoding="utf-8-sig")

    df = load_all_data(str(tmp_path))
    assert len(df) == 1
    assert "클릭_채널" in df.columns
    assert "구매_AF" in df.columns
    assert df.iloc[0]["채널"] == "구글"
    assert df.iloc[0]["구매_AF"] == 2

def test_skips_date_without_pair(tmp_path):
    ch_dir = tmp_path / "raw" / "channel"
    ch_dir.mkdir(parents=True)
    (tmp_path / "raw" / "appsflyer").mkdir(parents=True)
    pd.DataFrame([{"일":"2025-01-01","채널":"구글","채널분류":"외부",
        "캠페인":"X","캠페인목적":"Y","그룹":"Z","소재":"W",
        "노출":1,"클릭":1,"비용":1,"회원가입":0,"구매":0,"구매매출":0
    }]).to_csv(ch_dir / "2025-01-01.csv", index=False, encoding="utf-8-sig")
    df = load_all_data(str(tmp_path))
    assert df.empty
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```
cd marketing-analytics
python -m pytest tests/test_data_loader.py -v
```
Expected: FAIL (ImportError 또는 함수 오류)

- [ ] **Step 3: data_loader.py 전체 교체**

```python
import os
import pandas as pd

JOIN_KEYS = ["일", "캠페인", "그룹", "소재"]
CHANNEL_MAP = {
    "googleadwords_int": "구글",
    "Facebook Ads":      "메타",
    "naver_search":      "네이버",
}

def _read_csv(path: str) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"인코딩 감지 실패: {path}")

def _scan_dates(data_dir: str) -> list:
    ch_dir = os.path.join(data_dir, "raw", "channel")
    af_dir = os.path.join(data_dir, "raw", "appsflyer")
    if not os.path.isdir(ch_dir) or not os.path.isdir(af_dir):
        return []
    ch_dates = {f.replace(".csv", "") for f in os.listdir(ch_dir) if f.endswith(".csv")}
    af_dates = {f.replace(".csv", "") for f in os.listdir(af_dir) if f.endswith(".csv")}
    return sorted(ch_dates & af_dates)

def load_all_data(data_dir: str) -> pd.DataFrame:
    dates = _scan_dates(data_dir)
    if not dates:
        return pd.DataFrame()

    frames = []
    for date in dates:
        ch = _read_csv(os.path.join(data_dir, "raw", "channel",   f"{date}.csv"))
        af = _read_csv(os.path.join(data_dir, "raw", "appsflyer", f"{date}.csv"))

        ch = ch.rename(columns={
            "클릭": "클릭_채널", "회원가입": "회원가입_채널",
            "구매": "구매_채널",  "구매매출": "구매매출_채널",
        })
        af["채널"] = af["미디어소스"].map(CHANNEL_MAP)
        af = af.rename(columns={
            "클릭": "클릭_AF", "회원가입": "회원가입_AF",
            "구매": "구매_AF",  "구매매출": "구매매출_AF",
        })

        merged = pd.merge(
            ch,
            af[JOIN_KEYS + ["채널", "클릭_AF", "회원가입_AF", "구매_AF", "구매매출_AF"]],
            on=JOIN_KEYS, how="left", suffixes=("", "_af_채널")
        )
        # 채널 컬럼: ch 쪽 우선, af 쪽은 검증용으로 drop
        if "채널_af_채널" in merged.columns:
            merged = merged.drop(columns=["채널_af_채널"])
        frames.append(merged)

    df = pd.concat(frames, ignore_index=True)
    df["일"] = pd.to_datetime(df["일"])
    return df
```

- [ ] **Step 4: 테스트 통과 확인**

```
python -m pytest tests/test_data_loader.py -v
```
Expected: 2 PASSED

- [ ] **Step 5: 커밋**

```
git add data_loader.py tests/test_data_loader.py
git commit -m "feat: 5-key 조인 + 채널 매핑 data_loader"
```

---

### Task 2: creative_parser.py — 소재명 파싱

**Files:**
- Create: `marketing-analytics/creative_parser.py`
- Test: `marketing-analytics/tests/test_creative_parser.py`

**Produces:**
- `parse_creative(name: str) -> dict` — `{소재타입, 카테고리, 시즌, AB, 버전}`
- `add_creative_cols(df: pd.DataFrame) -> pd.DataFrame` — 소재 컬럼 5개 추가

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_creative_parser.py
from creative_parser import parse_creative, add_creative_cols
import pandas as pd

def test_parse_full():
    r = parse_creative("VID_플러스멤버십_겨울_A_v2")
    assert r["소재타입"] == "VID"
    assert r["카테고리"] == "플러스멤버십"
    assert r["시즌"] == "겨울"
    assert r["AB"] == "A"
    assert r["버전"] == "v2"

def test_parse_no_ab():
    r = parse_creative("IMG_적립혜택_상시_v1")
    assert r["소재타입"] == "IMG"
    assert r["AB"] is None
    assert r["버전"] == "v1"

def test_parse_txt():
    r = parse_creative("TXT_할인쿠폰_겨울_A_v1")
    assert r["소재타입"] == "TXT"

def test_add_creative_cols():
    df = pd.DataFrame({"소재": ["VID_플러스멤버십_겨울_A_v2", "IMG_적립혜택_상시_v1"]})
    out = add_creative_cols(df)
    assert "소재타입" in out.columns
    assert out.iloc[0]["AB"] == "A"
    assert out.iloc[1]["AB"] is None
```

- [ ] **Step 2: FAIL 확인**

```
python -m pytest tests/test_creative_parser.py -v
```

- [ ] **Step 3: creative_parser.py 작성**

```python
import pandas as pd

VALID_TYPES = {"IMG", "VID", "CRS", "GIF", "TXT"}
VALID_AB    = {"A", "B"}

def parse_creative(name: str) -> dict:
    parts = str(name).split("_")
    result = {"소재타입": None, "카테고리": None, "시즌": None, "AB": None, "버전": None}

    if not parts:
        return result

    result["소재타입"] = parts[0] if parts[0] in VALID_TYPES else parts[0]

    if len(parts) >= 2:
        result["카테고리"] = parts[1]
    if len(parts) >= 3:
        result["시즌"] = parts[2]

    # 버전은 항상 마지막 파트 (v로 시작)
    if len(parts) >= 4 and parts[-1].startswith("v"):
        result["버전"] = parts[-1]
        # AB는 버전 바로 앞 파트가 A or B인지 확인
        candidate = parts[-2] if len(parts) >= 5 else parts[3] if len(parts) >= 5 else None
        # parts 예: ['VID','플러스멤버십','겨울','A','v2'] → len=5
        if len(parts) == 5 and parts[3] in VALID_AB:
            result["AB"] = parts[3]
        elif len(parts) == 4:
            # ['IMG','적립혜택','상시','v1'] → AB 없음
            pass

    return result

def add_creative_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    parsed = df["소재"].apply(parse_creative).apply(pd.Series)
    return pd.concat([df, parsed], axis=1)
```

- [ ] **Step 4: 테스트 통과**

```
python -m pytest tests/test_creative_parser.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: 커밋**

```
git add creative_parser.py tests/test_creative_parser.py
git commit -m "feat: 소재명 파싱 creative_parser"
```

---

### Task 3: metrics.py — KPI + 이상탐지 + 포맷

**Files:**
- Modify: `marketing-analytics/metrics.py`
- Test: `marketing-analytics/tests/test_metrics.py`

**Consumes:** `load_all_data()` 결과 DataFrame
**Produces:**
- `add_derived(df) -> pd.DataFrame` — ROAS, CPC, CPP, CVR 컬럼 추가
- `compute_kpis(df) -> dict` — KPI 카드용 딕셔너리
- `detect_anomalies(df) -> list[dict]` — 이상 징후 목록 `[{캠페인, 유형, 값, 임계값}]`
- `quality_check(df) -> list[str]` — 품질 경고 메시지 목록
- `fmt_krw(v) -> str` — ₩1.2억 / ₩3,450만 포맷
- `roas_status(roas) -> str` — "🟢" / "🟡" / "🔴"

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_metrics.py
import pandas as pd
from metrics import add_derived, compute_kpis, detect_anomalies, fmt_krw, roas_status, quality_check

def make_df(**kwargs):
    base = {
        "일": pd.Timestamp("2025-01-01"),
        "채널": "구글", "캠페인": "GGL_CMP_01_플러스가입",
        "그룹": "논타겟", "소재": "IMG_v1",
        "노출": 10000, "클릭_채널": 100, "비용": 50000,
        "회원가입_AF": 5, "구매_AF": 2, "구매매출_AF": 200000,
    }
    base.update(kwargs)
    return pd.DataFrame([base])

def test_roas():
    df = add_derived(make_df())
    assert df.iloc[0]["ROAS"] == round(200000 / 50000, 4)

def test_roas_zero_cost():
    df = add_derived(make_df(비용=0))
    import math
    assert math.isnan(df.iloc[0]["ROAS"])

def test_fmt_krw_eok():
    assert fmt_krw(120000000) == "₩1.2억"

def test_fmt_krw_man():
    assert fmt_krw(3450000) == "₩3,450만"

def test_fmt_krw_small():
    assert fmt_krw(50000) == "₩50,000"

def test_roas_status():
    assert roas_status(5.0) == "🟢"
    assert roas_status(3.0) == "🟡"
    assert roas_status(1.5) == "🔴"

def test_detect_anomaly_low_roas():
    df = add_derived(make_df(비용=50000, 구매매출_AF=50000))  # ROAS=1.0
    alerts = detect_anomalies(df)
    types = [a["유형"] for a in alerts]
    assert "ROAS 위험" in types

def test_quality_check_duplicate():
    df = pd.concat([make_df(), make_df()], ignore_index=True)
    warnings = quality_check(df)
    assert any("중복" in w for w in warnings)
```

- [ ] **Step 2: FAIL 확인**

```
python -m pytest tests/test_metrics.py -v
```

- [ ] **Step 3: metrics.py 전체 교체**

```python
import pandas as pd

BRAND_KW_CAMPAIGN = "NVR_CMP_01_브랜드KW"

def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    safe = lambda a, b: a / b.replace(0, float("nan"))
    df["ROAS"]  = safe(df["구매매출_AF"], df["비용"]).round(4)
    df["CPC"]   = safe(df["비용"], df["클릭_채널"]).round(0)
    df["CPP"]   = safe(df["비용"], df["구매_AF"]).round(0)
    df["CVR"]   = (safe(df["구매_AF"], df["클릭_채널"]) * 100).round(2)
    df["CAC"]   = safe(df["비용"], df["회원가입_AF"]).round(0)
    df["CTR"]   = (safe(df["클릭_채널"], df["노출"]) * 100).round(2)
    return df

def fmt_krw(v: float) -> str:
    if v >= 1_0000_0000:
        return f"₩{v/1_0000_0000:.1f}억"
    if v >= 10000:
        return f"₩{int(v/10000):,}만"
    return f"₩{int(v):,}"

def roas_status(roas: float) -> str:
    if roas >= 4.0: return "🟢"
    if roas >= 2.0: return "🟡"
    return "🔴"

def compute_kpis(df: pd.DataFrame) -> dict:
    # 브랜드KW 제외 ROAS
    roas_df = df[~df["캠페인"].str.contains(BRAND_KW_CAMPAIGN, na=False)]
    cost    = df["비용"].sum()
    rev     = roas_df["구매매출_AF"].sum()
    pur     = df["구매_AF"].sum()
    signup  = df["회원가입_AF"].sum()
    click   = df["클릭_채널"].sum()
    roas    = round(rev / cost, 2) if cost else 0
    cac     = round(cost / signup, 0) if signup else 0
    cvr     = round(pur / click * 100, 1) if click else 0
    return {
        "총 비용":   fmt_krw(cost),
        "ROAS":     f"{roas:.2f}",
        "플러스가입": f"{int(signup):,}명",
        "CAC":      fmt_krw(cac),
        "CVR":      f"{cvr:.1f}%",
    }

def detect_anomalies(df: pd.DataFrame) -> list:
    alerts = []
    cmp = df.groupby("캠페인").agg(
        비용=("비용", "sum"),
        구매매출_AF=("구매매출_AF", "sum"),
    ).reset_index()
    cmp["ROAS"] = (cmp["구매매출_AF"] / cmp["비용"].replace(0, float("nan"))).round(2)

    for _, row in cmp.iterrows():
        if pd.isna(row["ROAS"]):
            continue
        if row["ROAS"] < 2.0:
            alerts.append({"캠페인": row["캠페인"], "유형": "ROAS 위험",
                           "값": row["ROAS"], "임계값": 2.0, "심각도": "🔴"})
        elif row["ROAS"] < 4.0:
            alerts.append({"캠페인": row["캠페인"], "유형": "ROAS 관찰",
                           "값": row["ROAS"], "임계값": 4.0, "심각도": "🟡"})
    return alerts

def quality_check(df: pd.DataFrame) -> list:
    warnings = []
    keys = ["일", "채널", "캠페인", "그룹", "소재"]
    existing_keys = [k for k in keys if k in df.columns]
    dup = df.duplicated(subset=existing_keys).sum()
    if dup > 0:
        warnings.append(f"중복 행 {dup}개 발견 (키: {existing_keys})")
    zero_cost = (df["비용"] == 0).sum()
    if zero_cost > 0:
        warnings.append(f"비용=0 행 {zero_cost}개")
    if "구매매출_AF" in df.columns:
        neg = (df["구매매출_AF"] < 0).sum()
        if neg > 0:
            warnings.append(f"음수 매출 {neg}개 — 환불 제외 확인 필요")
    return warnings
```

- [ ] **Step 4: 테스트 통과**

```
python -m pytest tests/test_metrics.py -v
```
Expected: 8 PASSED

- [ ] **Step 5: 커밋**

```
git add metrics.py tests/test_metrics.py
git commit -m "feat: KPI·이상탐지·포맷 metrics"
```

---

### Task 4: dashboard_app.py — 탭 4개 Streamlit 앱

**Files:**
- Create: `marketing-analytics/dashboard_app.py`

**Consumes:**
- `load_all_data(data_dir: str) -> pd.DataFrame`
- `add_derived(df) -> pd.DataFrame`
- `compute_kpis(df) -> dict`
- `detect_anomalies(df) -> list`
- `quality_check(df) -> list`
- `add_creative_cols(df) -> pd.DataFrame`
- `roas_status(roas: float) -> str`
- `fmt_krw(v: float) -> str`

- [ ] **Step 1: dashboard_app.py 작성**

```python
import os
import streamlit as st
import pandas as pd
import plotly.express as px
from data_loader import load_all_data
from metrics import add_derived, compute_kpis, detect_anomalies, quality_check, roas_status, fmt_krw
from creative_parser import add_creative_cols

st.set_page_config(page_title="퍼포먼스 대시보드", layout="wide", page_icon="📊")

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
BRAND_KW = "NVR_CMP_01_브랜드KW"
NAVER_LABEL = "네이버 [자체]"
CH_COLORS = {"구글": "#4285F4", "메타": "#1877F2", "네이버": "#03C75A", NAVER_LABEL: "#03C75A"}

COL_CFG = {
    "비용":        st.column_config.NumberColumn("비용",   format="₩%,.0f"),
    "구매매출_AF": st.column_config.NumberColumn("매출",   format="₩%,.0f"),
    "CAC":         st.column_config.NumberColumn("CAC",   format="₩%,.0f"),
    "CPP":         st.column_config.NumberColumn("CPP",   format="₩%,.0f"),
    "ROAS":        st.column_config.NumberColumn("ROAS",  format="%.2f"),
    "CTR":         st.column_config.NumberColumn("CTR",   format="%.2f%%"),
    "CVR":         st.column_config.NumberColumn("CVR",   format="%.2f%%"),
    "노출":        st.column_config.NumberColumn("노출",   format="%,.0f"),
    "클릭_채널":   st.column_config.NumberColumn("클릭",   format="%,.0f"),
    "구매_AF":     st.column_config.NumberColumn("구매",   format="%,.0f"),
    "회원가입_AF": st.column_config.NumberColumn("가입",   format="%,.0f"),
}

def show_df(df: pd.DataFrame):
    cfg = {c: COL_CFG[c] for c in df.columns if c in COL_CFG}
    st.dataframe(df, use_container_width=True, hide_index=True, column_config=cfg)

@st.cache_data(ttl=60)
def get_data():
    df = load_all_data(DATA_DIR)
    if df.empty:
        return df
    df = add_derived(df)
    df = add_creative_cols(df)
    # 네이버 레이블 복사
    df["채널_표시"] = df["채널"].where(df["채널"] != "네이버", NAVER_LABEL)
    return df

# ── 헤더
st.title("📊 퍼포먼스 마케팅 대시보드")

df_all = get_data()
if df_all.empty:
    st.error("데이터 없음 — raw/channel/, raw/appsflyer/ 에 YYYY-MM-DD.csv 를 넣어주세요.")
    st.stop()

# ── 사이드바 공통 필터
st.sidebar.header("공통 필터")
date_min, date_max = df_all["일"].min().date(), df_all["일"].max().date()
date_range = st.sidebar.date_input("기간", value=(date_min, date_max),
                                   min_value=date_min, max_value=date_max)
if st.sidebar.button("🔄 새로고침"):
    st.cache_data.clear(); st.rerun()

def apply_date(df):
    if len(date_range) == 2:
        return df[(df["일"].dt.date >= date_range[0]) & (df["일"].dt.date <= date_range[1])]
    return df

# ── 탭
tab1, tab2, tab3, tab4 = st.tabs(["🏠 홈", "📺 채널·캠페인", "🖼️ 소재", "🔽 퍼널"])

# ══════════════════════════════════════════
# TAB 1: 홈
# ══════════════════════════════════════════
with tab1:
    fdf = apply_date(df_all)

    # KPI 카드
    kpis = compute_kpis(fdf)
    cols = st.columns(len(kpis))
    for col, (label, value) in zip(cols, kpis.items()):
        col.metric(label, value)

    st.divider()

    # 이상 징후
    alerts = detect_anomalies(fdf)
    warnings = quality_check(fdf)
    if not alerts and not warnings:
        st.success("이상 없음 ✅")
    else:
        if warnings:
            for w in warnings:
                st.warning(f"⚠️ {w}")
        for a in alerts:
            msg = f"{a['심각도']} **{a['캠페인']}** — ROAS {a['값']:.2f} (임계값 {a['임계값']})"
            if a["심각도"] == "🔴":
                st.error(msg)
            else:
                st.warning(msg)

    st.divider()

    # 트렌드 차트
    daily = fdf.groupby("일").agg(
        비용=("비용","sum"), ROAS=("구매매출_AF","sum"),
        가입=("회원가입_AF","sum"), CAC=("비용","sum"),
    ).reset_index()
    daily["ROAS"] = (daily["ROAS"] / daily["비용"].replace(0, float("nan"))).round(2)
    daily["CAC"]  = (daily["비용"] / daily["가입"].replace(0, float("nan"))).round(0)

    metric_opt = st.selectbox("트렌드 지표", ["비용", "ROAS", "가입", "CAC"])
    fig = px.line(daily, x="일", y=metric_opt, markers=True,
                  title=f"최근 추이 — {metric_opt}")
    fig.update_layout(xaxis_tickformat="%Y-%m-%d")
    st.plotly_chart(fig, use_container_width=True)

# ══════════════════════════════════════════
# TAB 2: 채널·캠페인
# ══════════════════════════════════════════
with tab2:
    # 필터
    c1, c2 = st.columns(2)
    sel_ch  = c1.selectbox("채널", ["전체"] + sorted(df_all["채널"].dropna().unique()))
    obj_opts = sorted(df_all["캠페인목적"].dropna().unique()) if "캠페인목적" in df_all.columns else []
    sel_obj = c2.selectbox("캠페인 목적", ["전체"] + obj_opts)

    fdf = apply_date(df_all)
    if sel_ch  != "전체": fdf = fdf[fdf["채널"] == sel_ch]
    if sel_obj != "전체" and "캠페인목적" in fdf.columns:
        fdf = fdf[fdf["캠페인목적"] == sel_obj]

    # 채널 집계 (브랜드KW 제외 ROAS)
    roas_fdf = fdf[~fdf["캠페인"].str.contains(BRAND_KW, na=False)]
    ch_agg = fdf.groupby("채널").agg(
        비용=("비용","sum"), 노출=("노출","sum"),
        클릭_채널=("클릭_채널","sum"), 구매_AF=("구매_AF","sum"),
        회원가입_AF=("회원가입_AF","sum"),
    ).reset_index()
    ch_roas = roas_fdf.groupby("채널")["구매매출_AF"].sum().reset_index()
    ch_agg = ch_agg.merge(ch_roas, on="채널", how="left")
    ch_agg["ROAS"] = (ch_agg["구매매출_AF"] / ch_agg["비용"].replace(0, float("nan"))).round(2)
    ch_agg["CAC"]  = (ch_agg["비용"] / ch_agg["회원가입_AF"].replace(0, float("nan"))).round(0)
    ch_agg["상태"] = ch_agg["ROAS"].apply(roas_status)

    col_metric = st.selectbox("비교 지표", ["비용", "ROAS", "CAC"], key="ch_metric")
    cv1, cv2 = st.columns(2)
    with cv1:
        fig = px.bar(ch_agg, x="채널", y="비용", title="채널별 비용", color="채널",
                     color_discrete_map=CH_COLORS)
        fig.update_layout(yaxis_tickformat=",.0f")
        st.plotly_chart(fig, use_container_width=True)
    with cv2:
        fig = px.bar(ch_agg, x="채널", y="ROAS", title="채널별 ROAS (브랜드KW 제외)",
                     color="채널", color_discrete_map=CH_COLORS)
        st.plotly_chart(fig, use_container_width=True)

    st.caption("⚠️ 네이버는 그룹사 자체 매체 — 외부 채널과 직접 비교 시 주의")
    show_df(ch_agg[["채널","비용","ROAS","CAC","구매_AF","회원가입_AF","상태"]])

    st.divider()

    # 캠페인 랭킹
    cmp_agg = fdf.groupby("캠페인").agg(
        비용=("비용","sum"), 구매_AF=("구매_AF","sum"),
        구매매출_AF=("구매매출_AF","sum"), 회원가입_AF=("회원가입_AF","sum"),
    ).reset_index()
    cmp_agg["ROAS"] = (cmp_agg["구매매출_AF"] / cmp_agg["비용"].replace(0, float("nan"))).round(2)
    cmp_agg["CAC"]  = (cmp_agg["비용"] / cmp_agg["회원가입_AF"].replace(0, float("nan"))).round(0)
    cmp_agg["상태"] = cmp_agg["ROAS"].apply(roas_status)
    cmp_agg = cmp_agg.sort_values("ROAS", ascending=False)

    st.subheader("캠페인 랭킹")
    show_df(cmp_agg[["캠페인","비용","ROAS","CAC","구매_AF","회원가입_AF","상태"]])

# ══════════════════════════════════════════
# TAB 3: 소재
# ══════════════════════════════════════════
with tab3:
    f1, f2, f3 = st.columns(3)
    sel_ch2   = f1.selectbox("채널", ["전체"] + sorted(df_all["채널"].dropna().unique()), key="cr_ch")
    sel_type  = f2.selectbox("소재타입", ["전체", "IMG", "VID", "CRS", "TXT", "GIF"])
    sel_ab    = f3.selectbox("AB 여부", ["전체", "A/B만", "단독만"])

    fdf = apply_date(df_all)
    if sel_ch2  != "전체": fdf = fdf[fdf["채널"] == sel_ch2]
    if sel_type != "전체" and "소재타입" in fdf.columns:
        fdf = fdf[fdf["소재타입"] == sel_type]
    if sel_ab == "A/B만" and "AB" in fdf.columns:
        fdf = fdf[fdf["AB"].notna()]
    elif sel_ab == "단독만" and "AB" in fdf.columns:
        fdf = fdf[fdf["AB"].isna()]

    # 소재타입별 ROAS
    if "소재타입" in fdf.columns:
        type_agg = fdf.groupby("소재타입").agg(
            비용=("비용","sum"), 구매매출_AF=("구매매출_AF","sum"),
        ).reset_index()
        type_agg["ROAS"] = (type_agg["구매매출_AF"] / type_agg["비용"].replace(0, float("nan"))).round(2)
        fig = px.bar(type_agg, x="소재타입", y="ROAS", title="소재타입별 ROAS", color="소재타입")
        st.plotly_chart(fig, use_container_width=True)

    # 소재 랭킹
    cr_cols = ["소재타입","카테고리","시즌","AB","버전"]
    grp_cols = ["소재"] + [c for c in cr_cols if c in fdf.columns]
    cr_agg = fdf.groupby(grp_cols, dropna=False).agg(
        비용=("비용","sum"), 클릭_채널=("클릭_채널","sum"),
        구매_AF=("구매_AF","sum"), 구매매출_AF=("구매매출_AF","sum"),
    ).reset_index()
    cr_agg["ROAS"] = (cr_agg["구매매출_AF"] / cr_agg["비용"].replace(0, float("nan"))).round(2)
    cr_agg["상태"] = cr_agg["ROAS"].apply(roas_status)
    cr_agg = cr_agg.sort_values("ROAS", ascending=False)

    top_n = st.slider("상위 소재 N개", 5, 30, 15)
    show_df(cr_agg.head(top_n))

    # AB 비교
    if "AB" in fdf.columns and fdf["AB"].notna().any():
        st.subheader("AB 비교")
        ab_agg = fdf.groupby(["소재타입","카테고리","시즌","AB"], dropna=False).agg(
            비용=("비용","sum"), 구매매출_AF=("구매매출_AF","sum"),
            구매_AF=("구매_AF","sum"),
        ).reset_index()
        ab_agg["ROAS"] = (ab_agg["구매매출_AF"] / ab_agg["비용"].replace(0, float("nan"))).round(2)
        show_df(ab_agg)

# ══════════════════════════════════════════
# TAB 4: 퍼널
# ══════════════════════════════════════════
with tab4:
    sel_ch3 = st.selectbox("채널", ["전체"] + sorted(df_all["채널"].dropna().unique()), key="fn_ch")
    fdf = apply_date(df_all)
    if sel_ch3 != "전체": fdf = fdf[fdf["채널"] == sel_ch3]

    total = {
        "노출":      fdf["노출"].sum(),
        "클릭":      fdf["클릭_채널"].sum(),
        "회원가입":   fdf["회원가입_AF"].sum(),
        "구매":      fdf["구매_AF"].sum(),
    }
    funnel_df = pd.DataFrame([
        {"단계": k, "수": v} for k, v in total.items()
    ])
    fig = px.funnel(funnel_df, x="수", y="단계", title="퍼널 전환")
    st.plotly_chart(fig, use_container_width=True)

    # 채널별 퍼널 비교
    fn_agg = df_all.pipe(apply_date).groupby("채널").agg(
        노출=("노출","sum"), 클릭=("클릭_채널","sum"),
        가입=("회원가입_AF","sum"), 구매=("구매_AF","sum"),
    ).reset_index()
    fn_agg["CTR"]  = (fn_agg["클릭"] / fn_agg["노출"].replace(0, float("nan")) * 100).round(2)
    fn_agg["가입CVR"] = (fn_agg["가입"] / fn_agg["클릭"].replace(0, float("nan")) * 100).round(2)
    fn_agg["구매CVR"] = (fn_agg["구매"] / fn_agg["클릭"].replace(0, float("nan")) * 100).round(2)

    st.subheader("채널별 퍼널 비교")
    show_df(fn_agg[["채널","노출","클릭","CTR","가입","가입CVR","구매","구매CVR"]])
```

- [ ] **Step 2: 앱 실행 확인**

```
cd marketing-analytics
python -m streamlit run dashboard_app.py --server.port 8502
```
Expected: 브라우저에서 탭 4개 렌더링 확인

- [ ] **Step 3: 커밋**

```
git add dashboard_app.py
git commit -m "feat: 탭 4개 Streamlit 대시보드"
```

---

### Task 5: 실행.bat 업데이트

**Files:**
- Modify: `marketing-analytics/실행.bat`

- [ ] **Step 1: 실행.bat 수정**

```bat
@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo 퍼포먼스 대시보드를 시작합니다... (port 8502)
streamlit run dashboard_app.py --server.port 8502 --server.headless false --browser.gatherUsageStats false
pause
```

- [ ] **Step 2: 더블클릭 실행 확인**

Expected: `http://localhost:8502` 에서 대시보드 오픈

- [ ] **Step 3: 커밋**

```
git add 실행.bat
git commit -m "chore: 포트 8502, dashboard_app.py 런처 업데이트"
```

---

## Self-Review

**스펙 커버리지 체크:**
- [x] 홈 탭 — KPI 카드, 이상탐지, 7일 트렌드 → Task 4 Tab1
- [x] 채널·캠페인 탭 — 브랜드KW 제외, 네이버 자체 표기, 랭킹 → Task 4 Tab2
- [x] 소재 탭 — 파싱, AB 비교, 타입별 ROAS → Task 2 + Task 4 Tab3
- [x] 퍼널 탭 — 채널별 퍼널 비교 → Task 4 Tab4
- [x] 데이터 품질 체크 → Task 3 `quality_check`
- [x] 포맷 규칙 (₩억/만, ROAS 2자리, % 1자리) → Task 3 `fmt_krw` + COL_CFG
- [x] 브랜드컬러 → CH_COLORS
- [x] 포트 8502 → Task 5
