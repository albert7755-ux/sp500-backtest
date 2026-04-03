import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import warnings
warnings.filterwarnings('ignore')

# ─── 頁面設定 ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="標普500多重跌幅回測", page_icon="📉", layout="wide")

# ─── 自訂 CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700&family=Roboto+Mono:wght@700&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; }
.mcard-row { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 15px; }
.mcard {
    flex: 1; min-width: 140px; background: #1a2332; border: 1px solid #2d3748;
    border-radius: 12px; padding: 15px 5px; text-align: center;
}
.mcard-label { color: #ffffff; font-size: 0.8rem; margin-bottom: 8px; }
.mcard-value { font-family: 'Roboto Mono', monospace; font-size: 1.3rem; font-weight: 700; }
.mcard-sub { color: #cbd5e1; font-size: 0.75rem; margin-top: 5px; }
.pos { color: #34d399; } .neg { color: #f87171; }
.result-header { background: #2563eb; border-radius: 10px; padding: 15px; color: white; font-weight: 700; margin-bottom: 20px; }
.commentary-box { background: #0f172a; border: 1px solid #3b82f6; padding: 20px; border-radius: 12px; line-height: 1.8; color: #e2e8f0; }
</style>
""", unsafe_allow_html=True)

st.title("📉 標普500「多重跌幅門檻」回測工具")

# ─── 側邊欄 ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 策略設定")
    ticker_input = st.text_area("📌 買入標的 (多個請用逗號隔開)", value="SPY, QQQ").upper()
    
    # 這裡改成多選，可以設定多個波段跌幅
    drop_options = [5, 10, 15, 20, 25, 30, 40, 50]
    selected_drops = st.multiselect(
        "📉 設定觸發買入的跌幅 (%)",
        options=drop_options,
        default=[10, 20],
        help="例如選 10% 與 20%，程式會分別抓出這兩個點的表現"
    )
    
    lookback_window = st.selectbox("計算高點窗口 (日)", [30, 60, 90, 125, 252], index=2)
    start_year = st.slider("📅 資料起始年份", 1990, 2026, 2010)
    run_btn = st.button("🚀 開始多重回測", use_container_width=True, type="primary")

ALL_PERIODS = {"1個月": 21, "3個月": 63, "6個月": 126, "1年": 252, "3年": 756, "5年": 1260}

# ─── 核心計算函數 ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def get_portfolio_price(tickers_str, start):
    tickers = [t.strip() for t in tickers_str.replace(',', ' ').split() if t.strip()]
    if not tickers: return None
    try:
        df = yf.download(tickers, start=f"{start}-01-01", progress=False, auto_adjust=True)
        if df.empty: return None
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            portfolio_price = (1 + close.pct_change().mean(axis=1)).cumprod()
            return portfolio_price.dropna()
        return close.dropna()
    except: return None

# ─── 執行回測 ────────────────────────────────────────────────────────────────
if run_btn:
    if not selected_drops:
        st.warning("請至少選擇一個跌幅門檻。")
        st.stop()

    with st.spinner("正在計算多重跌幅數據..."):
        sp500_raw = yf.download("^GSPC", start=f"{start_year}-01-01", progress=False, auto_adjust=True)["Close"]
        if isinstance(sp500_raw, pd.DataFrame): sp500_raw = sp500_raw.iloc[:, 0]
        portfolio = get_portfolio_price(ticker_input, start_year)

    if sp500_raw is None or portfolio is None:
        st.error("讀取失敗，請確認代號正確。")
        st.stop()

    # 計算訊號
    rolling_high = sp500_raw.rolling(window=lookback_window).max()
    drawdown = (sp500_raw - rolling_high) / rolling_high * 100

    # 針對每個跌幅門檻分開計算
    all_stats = []
    
    for drop in selected_drops:
        # 抓取該門檻的訊號日期
        signals = sp500_raw.index[(drawdown <= -drop) & (drawdown.shift(1) > -drop)]
        
        drop_results = []
        for d in signals:
            avail = portfolio.index[portfolio.index >= d]
            if avail.empty: continue
            t0, p0 = avail[0], portfolio.loc[avail[0]]
            
            row = {"跌幅門檻": f"{drop}%"}
            for name, days in ALL_PERIODS.items():
                future = portfolio.index[portfolio.index > t0]
                if len(future) >= days:
                    row[name] = (portfolio.loc[future[days-1]] - p0) / p0 * 100
            drop_results.append(row)
        
        if drop_results:
            temp_df = pd.DataFrame(drop_results)
            for p_name in ALL_PERIODS.keys():
                if p_name in temp_df.columns:
                    col_data = temp_df[p_name].dropna()
                    if not col_data.empty:
                        all_stats.append({
                            "跌幅門檻": f"{drop}%",
                            "持有期": p_name,
                            "平均報酬": col_data.mean(),
                            "勝率": (col_data > 0).mean() * 100,
                            "樣本數": len(col_data)
                        })

    df_final = pd.DataFrame(all_stats)

    if df_final.empty:
        st.warning("⚠️ 這些條件下皆未觸發任何訊號。")
    else:
        st.markdown(f'<div class="result-header">📊 組合：{ticker_input} ｜ 多重跌幅比較分析</div>', unsafe_allow_html=True)

        # ── 1. 視覺化：不同跌幅下的勝率比較 ──
        st.subheader("🎯 不同跌幅買入後的勝率比較 (柱狀圖)")
        fig_compare = go.Figure()
        for drop in sorted(selected_drops):
            subset = df_final[df_final["跌幅門檻"] == f"{drop}%"]
            fig_compare.add_trace(go.Bar(
                x=subset["持有期"], y=subset["勝率"], 
                name=f"跌 {drop}% 後買",
                text=[f"{v:.0f}%" for v in subset["勝率"]],
                textposition='auto'
            ))
        fig_compare.update_layout(template="plotly_dark", barmode='group', yaxis_title="勝率 (%)", height=450)
        st.plotly_chart(fig_compare, use_container_width=True)

        # ── 2. 自動解說 ──
        st.subheader("💡 多重跌幅數據洞察")
        deepest_drop = max(selected_drops)
        deep_stats = df_final[df_final["跌幅門檻"] == f"{deepest_drop}%"]
        
        insight = f"""
        <div class="commentary-box">
        <b>1. 跌幅深度與勝率的關係：</b><br>
        根據數據顯示，當標普 500 下跌至 <b>{deepest_drop}%</b> 時買入，
        其 1 年後的平均勝率為 <b>{deep_stats[deep_stats['持有期']=='1年']['勝率'].values[0]:.0f}%</b>。
        通常跌得越深進場，長線的獲利空間與勝算會顯著高於小幅度回檔。<br><br>
        
        <b>2. 策略建議：</b><br>
        如果你打算分批進場，可以參考下方表格中的「平均報酬」。若發現 10% 與 20% 的長線勝率差異不大，
        代表此標的具備極強的抗跌性，即便在小回檔時介入也具備相當的安全性。
        </div>
        """
        st.markdown(insight, unsafe_allow_html=True)

        # ── 3. 詳細數據表格 ──
        st.subheader("📋 多重門檻對照總表")
        pivot_df = df_final.pivot(index="跌幅門檻", columns="持有期", values="平均報酬")
        # 重新排序欄位
        pivot_df = pivot_df[list(ALL_PERIODS.keys())]
        st.write("平均報酬率 (%) 對照表：")
        st.dataframe(pivot_df.style.format("{:+.1f}%").background_gradient(cmap="RdYlGn", axis=None), use_container_width=True)

        st.write("勝率 (%) 對照表：")
        pivot_wr = df_final.pivot(index="跌幅門檻", columns="持有期", values="勝率")
        pivot_wr = pivot_wr[list(ALL_PERIODS.keys())]
        st.dataframe(pivot_wr.style.format("{:.0f}%").background_gradient(cmap="Greens", axis=None), use_container_width=True)

else:
    st.info("👈 請在左側「策略設定」中選擇多個跌幅門檻，看看不同深度進場的差異。")
