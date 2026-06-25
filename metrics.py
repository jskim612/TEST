import pandas as pd

def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    safe = lambda num, den: num / den.where(den > 0)
    df["CPC"]        = safe(df["비용"], df["클릭_채널"]).round(0)
    df["CPP"]        = safe(df["비용"], df["구매_AF"]).round(0)
    df["CVR"]        = (safe(df["구매_AF"], df["클릭_채널"]) * 100).round(2)
    df["회원가입CVR"] = (safe(df["회원가입_AF"], df["클릭_채널"]) * 100).round(2)
    # 행 단위 ROAS는 EDA/Raw 탭 용도로만 사용 — 집계 탭에서는 sum/sum으로 재계산
    df["ROAS_row"]   = safe(df["구매매출_AF"], df["비용"]).round(2)
    return df

def compute_kpis(df: pd.DataFrame) -> dict:
    total_cost       = df["비용"].sum()
    total_revenue    = df["구매매출_AF"].sum()
    total_purchase   = df["구매_AF"].sum()
    total_signup     = df["회원가입_AF"].sum()
    total_click      = df["클릭_채널"].sum()
    total_impression = df["노출"].sum()

    roas = f"{(total_revenue / total_cost):.2f}x" if total_cost > 0 else "N/A"
    cpp  = f"₩{(total_cost / total_purchase):,.0f}" if total_purchase > 0 else "N/A"
    ctr  = (
        f"{(total_click / total_impression * 100):.2f}%"
        if pd.notna(total_impression) and total_impression > 0
        else "N/A"
    )

    return {
        "총 비용":   f"₩{total_cost:,.0f}",
        "총 매출":   f"₩{total_revenue:,.0f}",
        "ROAS":     roas,
        "총 구매":   f"{total_purchase:,.0f}건",
        "CPP":      cpp,
        "총 회원가입": f"{total_signup:,.0f}명",
        "총 클릭":   f"{total_click:,.0f}",
        "CTR":      ctr,
    }
