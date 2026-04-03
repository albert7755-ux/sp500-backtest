import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import warnings
warnings.filterwarnings('ignore')

# ─── 頁面設定 ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="標普500回測工具",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── 自訂 CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700;900&family=Roboto+Mono:wght@400;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; }

.cards-row {
    display: flex;
    gap: 10px;
    flex-wrap: nowrap;
    overflow-x: auto;
    padding-bottom: 10px;
}
.mcard {
    flex: 1 1 0;
    min-width: 125px; /* 增加最小寬度防止溢位 */
    background: linear-gradient(160deg, #1a2332 0%, #111827 100%);
    border: 1px solid #2d3748;
    border-radius: 14px;
    padding: 14px 8px 12px; /* 減少左右內邊距，給文字更多空間 */
    text-align: center;
}
.mcard-label  { 
    color: #ffffff; /* 標題改為純白 */
    font-size: 0.75rem; 
    font-weight: 500;
    margin-bottom: 6px; 
}
.mcard-value  {
    font-family: 'Roboto Mono', monospace;
    font-size: 1.4rem; /* 稍微調低字體大小 (原 1.55) 確保三位數能放入 */
    font-weight: 700;
    line-height: 1.1;
    white-space: nowrap;
}
.mcard-sub    { 
    color: #e5e7eb; /* 子標籤改為淺亮灰色，提高對比度 */
    font-size: 0.68rem; 
    margin-top: 6px; 
    line-height: 1.4;
}
.pos { color: #34d399; }
.neg { color: #f87171; }

.result-header {
    background: linear-gradient(90deg, #1d4ed8 0%, #2563eb 100%);
    border-radius: 12px;
    padding: 14px 20px;
    margin-bottom: 18px;
    color: white;
    font-weight: 700;
    font-size: 1rem;
}

.insight-box {
    background: linear-gradient(135deg, #0f2027 0%, #1a2a3a 100%);
    border-left: 4px solid #3b82f6;
    border-radius: 0 10px 10px 0;
    padding: 14px 18px;
    margin: 10px 0 18px;
    color: #cbd5e1;
    font-size: 0.88rem;
    line-height: 1.65;
}
</style>
""", unsafe_allow_html=True)

# ─── 標題 ────────────────────────────────────────────────────────────────────
st.title("📉 標普500跌幅後買入回測工具")
st.caption("設定 S&P 500 跌幅條件，回測買入任何股票／ETF 後的歷史績效")

# ─── 側邊欄 ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 回測設定")

    ticker_input = st.text_input(
        "📌 買入標的代號",
        value="SPY",
        help="美股：SPY、QQQ、AAPL｜台股：0050.TW"
    ).upper().strip()

    st.markdown("---")
    drop_pct = st.slider(
        "📉 S&P 500 從近期高點下跌 % 後買入",
        min_value=2, max_value=50, value=10, step=1, format="%d%%"
    )
    lookback_window = st.selectbox(
        "計算高點回看窗口",
        options=[30, 60, 90, 125, 252],
        index=2,
        format_func=lambda x: f"{x} 個交易日（約 {round(x/21)} 個月）"
    )

    st.markdown("---")
    start_year = st.slider("📅 資料起始年份", 1990, 2020, 2010) # 預設改2010讓圖表更清晰
    start_date = f"{start_year}-01-01"

    st.markdown("---")
    periods = st.multiselect(
        "⏱️ 持有期間",
        options=["1個月", "3個月", "6個月", "1年", "2年", "3年", "5年"],
        default=["1個月", "3個月", "6個月", "1年", "2年", "3年", "5年"]
    )

    run_btn = st.button("🚀 開始回測", use_container_width=True, type="primary")

# ─── 常數 ─────────────────────────────────────────────────────────────────────
PERIOD_MAP = {
    "1個月": 21, "3個月": 63, "6個月": 126,
    "1年": 252, "2年": 504, "3年": 756, "5年": 1260,
}
COLORS = ["#60a5fa","#34d399","#fb923c","#a78bfa","#f472b6","#facc15","#38bdf8"]

# ─── 函數 ─────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_data(ticker, start):
    """下載資料，失敗自動重試 3 次"""
    for attempt in range(3):
        try:
            df = yf.download(
                ticker, start=start,
                progress=False, auto_adjust=True,
                timeout=30
            )
            if not df.empty:
                close = df["Close"]
                if isinstance(close, pd.DataFrame):
                    close = close.iloc[:, 0]
                close = close.dropna()
                if len(close) > 10:
                    return close
        except Exception:
            pass
        if attempt < 2:
            time.sleep(3)
    return None

def find_buy_signals(sp500, drop_pct, window):
    rolling_high = sp500.rolling(window=window).max()
    drawdown = (sp500 - rolling_high) / rolling_high * 100
    signal = drawdown <= -drop_pct
    signal_filtered = signal & (~signal.shift(1).fillna(False))
    return sp500.index[signal_filtered]

def calc_returns(target, buy_dates, periods_days):
    results = []
    idx = target.index.tolist()
    for buy_date in buy_dates:
        future_all = [d for d in idx if d >= buy_date]
        if not future_all:
            continue
        actual_buy = future_all[0]
        buy_price = float(target.loc[actual_buy])
        row = {"買入日期": actual_buy.strftime("%Y-%m-%d"), "買入價格": round(buy_price, 2)}
        for pname, days in periods_days.items():
            future = [d for d in idx if d > actual_buy]
            if len(future) >= days:
                sell_price = float(target.loc[future[days - 1]])
                row[pname] = round((sell_price - buy_price) / buy_price * 100, 2)
            else:
                row[pname] = np.nan
        results.append(row)
    return pd.DataFrame(results)

def color_cell(val):
    if pd.isna(val):
        return "color: #6b7280"
    return "color: #34d399; font-weight:600" if val >= 0 else "color: #f87171; font-weight:600"

def fmt_pct(x):
    return "—" if pd.isna(x) else f"{x:+.1f}%"

# ─── 主邏輯 ──────────────────────────────────────────────────────────────────
if run_btn:
    selected_periods = {p: PERIOD_MAP[p] for p in periods if p in PERIOD_MAP}
    if not selected_periods:
        st.warning("請至少選擇一個持有期間")
        st.stop()

    with st.spinner("📡 從 Yahoo Finance 載入資料..."):
        sp500  = load_data("^GSPC", start_date)
        target = load_data(ticker_input, start_date)

    if sp500 is None:
        st.error("❌ 無法載入 S&P 500 資料。請稍後重試。")
        st.stop()
    if target is None:
        st.error(f"❌ 找不到代號「{ticker_input}」。")
        st.stop()

    buy_dates  = find_buy_signals(sp500, drop_pct, lookback_window)
    df_results = calc_returns(target, buy_dates, selected_periods)
    valid_df   = df_results.dropna(subset=list(selected_periods.keys()), how="all")
    period_cols = [p for p in selected_periods if p in valid_df.columns]

    if valid_df.empty or not period_cols:
        st.warning("觸發訊號後資料不足，請調整條件。")
        st.stop()

    n_signals = len(valid_df)

    # ── 結果標題 ────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="result-header">
        📊 S&P 500 從 {lookback_window} 日高點跌 {drop_pct}% → 買入 <b>{ticker_input}</b>
        &nbsp;｜&nbsp; 歷史共觸發 <b>{n_signals}</b> 次
    </div>""", unsafe_allow_html=True)

    # ── 各持有期平均報酬率卡片 ───────────────────────────────────────────────
    st.subheader("📈 各持有期平均報酬率")
    cards_html = '<div class="cards-row">'
    for period in period_cols:
        col_data = valid_df[period].dropna()
        if col_data.empty: continue
        avg      = col_data.mean()
        win_rate = (col_data > 0).mean() * 100
        cls      = "pos" if avg >= 0 else "neg"
        sign     = "+" if avg >= 0 else ""
        cards_html += f"""
        <div class="mcard">
            <div class="mcard-label">{period}</div>
            <div class="mcard-value {cls}">{sign}{avg:.1f}%</div>
            <div class="mcard-sub">勝率 {win_rate:.0f}%<br>{len(col_data)} 筆資料</div>
        </div>"""
    cards_html += '</div>'
    st.markdown(cards_html, unsafe_allow_html=True)

    # ── 數據洞察 ─────────────────────────────────────────────────────────────
    best_p  = max(period_cols, key=lambda p: valid_df[p].dropna().mean() if not valid_df[p].dropna().empty else -999)
    best_v  = valid_df[best_p].dropna().mean()
    best_wr = (valid_df[best_p].dropna() > 0).mean() * 100
    st.markdown(f"""
    <div class="insight-box">
    💡 <b>數據洞察</b>：{start_year} 年以來，每當 S&P 500 從高點下跌 {drop_pct}%，
    買入 <b>{ticker_input}</b> 並持有 <b>{best_p}</b>，平均報酬達 <b>{best_v:+.1f}%</b>，勝率 <b>{best_wr:.0f}%</b>。
    </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ════════════════════════════════════════════════════════════════════════
    # 圖表區塊 (財富成長、勝率泡泡、柱狀圖、走勢圖)
    # ════════════════════════════════════════════════════════════════════════
    
    # 圖 1：財富成長
    st.subheader("💰 每次買入後的財富成長曲線")
    fig_wealth = go.Figure()
    fig_wealth.add_hline(y=100, line_dash="dash", line_color="#6b7280")
    for i, period in enumerate(period_cols):
        col_data = valid_df[period].dropna()
        wealth   = 100 * (1 + col_data / 100)
        x_vals   = valid_df.loc[col_data.index, "買入日期"].tolist()
        fig_wealth.add_trace(go.Scatter(
            x=x_vals, y=wealth.values, mode="lines+markers", name=period,
            line=dict(color=COLORS[i % len(COLORS)], width=2), marker=dict(size=5)
        ))
    fig_wealth.update_layout(template="plotly_dark", paper_bgcolor="#111827", plot_bgcolor="#111827", height=420)
    st.plotly_chart(fig_wealth, use_container_width=True)

    # 圖 2：勝率泡泡圖
    st.subheader("🎯 各持有期勝率與平均報酬")
    wr_vals  = [(valid_df[p].dropna() > 0).mean() * 100 for p in period_cols]
    avg_vals = [valid_df[p].dropna().mean() for p in period_cols]
    fig_bubble = go.Figure(go.Scatter(
        x=period_cols, y=wr_vals, mode="markers+text", text=[f"{v:+.1f}%" for v in avg_vals],
        textposition="top center", marker=dict(size=[max(20, abs(v) * 2.5) for v in avg_vals], color=wr_vals, colorscale='Viridis', showscale=True)
    ))
    fig_bubble.update_layout(template="plotly_dark", paper_bgcolor="#111827", plot_bgcolor="#111827", height=400, yaxis=dict(title="勝率 (%)", range=[0, 115]))
    st.plotly_chart(fig_bubble, use_container_width=True)

    # 圖 4：S&P 500 走勢 + 訊號
    st.subheader("📉 S&P 500 走勢與買入訊號點")
    fig_sp = go.Figure()
    fig_sp.add_trace(go.Scatter(x=sp500.index, y=sp500.values, mode="lines", name="S&P 500", line=dict(color="#60a5fa")))
    buy_pts = [(d, float(sp500.loc[sp500.index[sp500.index >= d][0]])) for d in buy_dates if any(sp500.index >= d)]
    if buy_pts:
        bx, by = zip(*buy_pts)
        fig_sp.add_trace(go.Scatter(x=list(bx), y=list(by), mode="markers", name="買入點", marker=dict(color="#fb923c", size=10, symbol="triangle-up")))
    fig_sp.update_layout(template="plotly_dark", paper_bgcolor="#111827", plot_bgcolor="#111827", height=380)
    st.plotly_chart(fig_sp, use_container_width=True)

    # ── 統計摘要表 ──────────────────────────────────────────────────────────
    st.subheader("📊 統計摘要")
    summary_rows = []
    for period in period_cols:
        col_data = valid_df[period].dropna()
        if col_data.empty: continue
        summary_rows.append({
            "持有期": period, "樣本數": len(col_data), "平均報酬": f"{col_data.mean():+.1f}%",
            "勝率": f"{(col_data > 0).mean()*100:.0f}%", "最佳": f"{col_data.max():+.1f}%", "最差": f"{col_data.min():+.1f}%"
        })
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    # ── 下載 ────────────────────────────────────────────────────────────────
    csv = valid_df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button("⬇️ 下載完整回測資料（CSV）", data=csv, file_name=f"backtest_{ticker_input}.csv", mime="text/csv")

else:
    st.info("👈 請在左側設定條件，點擊「開始回測」查看結果")
    st.markdown("""
### 🗺️ 使用說明
1. **輸入代號**：SPY (美股)、0050.TW (台股)...
2. **設定跌幅**：設定標普500跌多少 % 時「買入」
3. **持有期**：觀察不同持時的時間長度表現
""")
