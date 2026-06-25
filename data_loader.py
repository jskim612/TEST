import os
import glob
import pandas as pd
import streamlit as st

CHANNEL_MAP = {
    "googleadwords_int": "구글",
    "Facebook Ads":      "메타",
    "naver_search":      "네이버",
}
JOIN_KEYS = ["일", "채널", "캠페인", "그룹", "소재"]
AF_FILL_COLS = ["클릭_AF", "회원가입_AF", "구매_AF", "구매매출_AF"]

def _read_csv(path: str) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"인코딩 감지 실패: {path}")

def _glob_csvs(base_dir: str) -> dict:
    """base_dir 아래 flat + 월별 폴더 모두 스캔 → {날짜: 절대경로}"""
    result = {}
    duplicates = []
    for path in glob.glob(os.path.join(base_dir, "**", "*.csv"), recursive=True):
        fname = os.path.splitext(os.path.basename(path))[0]
        if len(fname) == 10 and fname[4] == "-" and fname[7] == "-":
            if fname in result:
                duplicates.append(f"{fname}: {result[fname]} vs {path}")
            else:
                result[fname] = path
    if duplicates:
        st.warning(f"⚠️ 중복 날짜 파일 감지 — 첫 번째 파일만 사용합니다:\n" + "\n".join(duplicates))
    return result

def _scan_dates(data_dir: str):
    ch_dir = os.path.join(data_dir, "raw", "channel")
    af_dir = os.path.join(data_dir, "raw", "appsflyer")
    if not os.path.isdir(ch_dir) or not os.path.isdir(af_dir):
        return [], {}, {}
    ch_map = _glob_csvs(ch_dir)
    af_map = _glob_csvs(af_dir)
    return sorted(ch_map.keys() & af_map.keys()), ch_map, af_map

def load_all_data(data_dir: str) -> pd.DataFrame:
    dates, ch_map, af_map = _scan_dates(data_dir)
    if not dates:
        return pd.DataFrame()

    frames = []
    for date in dates:
        ch = _read_csv(ch_map[date])
        af = _read_csv(af_map[date])

        ch = ch.rename(columns={
            "클릭": "클릭_채널",
            "회원가입": "회원가입_채널",
            "구매": "구매_채널",
            "구매매출": "구매매출_채널",
        })

        # 미디어소스 → 채널명 변환
        af["채널"] = af["미디어소스"].map(CHANNEL_MAP)
        unknown = af[af["채널"].isna()]["미디어소스"].unique().tolist()
        if unknown:
            st.warning(f"⚠️ [{date}] CHANNEL_MAP 미등록 미디어소스: {unknown} — 해당 행 제외됩니다.")
        af = af[af["채널"].notna()]

        af = af.rename(columns={
            "클릭": "클릭_AF",
            "회원가입": "회원가입_AF",
            "구매": "구매_AF",
            "구매매출": "구매매출_AF",
        }).drop(columns=["미디어소스"], errors="ignore")

        merged = pd.merge(ch, af, on=JOIN_KEYS, how="left")
        # AF 미매칭 행의 NaN → 0 (비용은 채널 데이터에서 정상 집계되므로 매출 NaN 방치 시 ROAS 과대계산)
        for col in AF_FILL_COLS:
            if col in merged.columns:
                merged[col] = merged[col].fillna(0)

        frames.append(merged)

    df = pd.concat(frames, ignore_index=True)
    df["일"] = pd.to_datetime(df["일"])
    return df
