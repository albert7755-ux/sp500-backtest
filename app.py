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
    page_title="標普500組合回測工具",
    page_icon="⚖️",
    layout="wide"
)

# ─── 自訂 CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700;900&family=Roboto+Mono:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; }
.cards-row { display: flex; gap: 10px; flex-wrap: nowrap; overflow-x: auto; padding-bottom: 10px; }
.mcard {
    flex: 1 1 0; min-width: 135px;
    background: linear-gradient(160deg, #1a2332 0%, #111827 100%);
    border: 1px solid #2d3748; border-radius: 14px;
    padding: 14px 8px 12px; text-align: center;
}
.mcard-label { color: #ffffff; font-size: 0.75rem; font-weight: 500; margin-bottom: 6px; }
.mcard-value { font-family: 'Roboto Mono', monospace; font-size: 1.35rem; font-weight: 700; line-height: 1.1; white-space: nowrap; }
.mcard-sub { color: #e5e7eb; font-size: 0.68rem; margin-top: 6px; line-height: 1.4; }
.pos { color: #34d399; }
.neg { color: #f87171; }
.result-header { background: linear-gradient(90deg, #1d4ed8 0%, #2563eb 100%); border-radius: 12px; padding: 14px 20px; margin-bottom: 18px; color: white; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

st.title("⚖️ 標普500跌幅後「組合投資」回測")
st.caption("輸入多個代號（如：AAPL, MSFT, NVDA），系統將以等權重組合計算績效")

# ─── 側邊欄 ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 設定")
    ticker_input = st.text_area("📌 買入標的 (多個請用逗號或空格隔開)", value="AAPL, MSFT, GOOG", help="例如: SPY, QQQ, TSLA").upper()
    
    st.markdown("---")
    drop_pct = st.slider("📉 S&P 500 下跌 % 買入", 2, 50, 10, format="%d%%")
    lookback_window = st.selectbox("回看窗口 (日)", [30, 60, 90, 125, 252], index=2)
    start_year = st.slider("📅 起始年份", 1990, 2026, 2010)
    
    st.markdown("---")
    periods = ["1個月", "3個月", "6個月", "1年", "2年", "3年", "5年"]
    selected_p = st.multiselect("持有期間", periods, default=periods)
    run_btn = st.button("🚀 開始回測", use_container_width=True, type="primary")

PERIOD_MAP = {"1個月": 21, "3個月": 63, "6個月": 126, "1年": 252, "2年": 504, "3年": 756, "5年": 1260}
COLORS = ["#60a5fa","#34d399","#fb923c","#a78bfa","#f472b6","#facc15","#38bdf8"]

# ─── 核心函數 ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def get_clean_data(tickers_str, start):
    tickers = [t.strip() for t in tickers_str.replace(',', ' ').split() if t.strip()]
    if not tickers: return None
    try:
        # 下載資料並確保欄位處理正確
        df = yf.download(tickers, start=f"{start}-01-01", progress=False, auto_adjust=True)
        if df.empty: return None
        
        # 提取收盤價並強制轉換為 Series (若多標的則計算等權重均值)
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            # 如果是 DataFrame，代表有多個標的或單一標的多重索引
            daily_returns = close.pct_change()
            portfolio_return = daily_returns.mean(axis=1) # 等權重組合
            portfolio_price = (1 + portfolio_return).cumprod()
            return portfolio_price.dropna()
        else:
            # 單一標的 Series
            return close.dropna()
    except: return None

def find_buy_signals(sp_price, drop, window):
    # 確保 sp_price 是 Series 格式以進行滾動計算
    if isinstance(sp_price, pd.DataFrame):
        sp_price = sp_price.iloc[:, 0]
        
    rolling_high = sp_price.rolling(window=window).max()
    drawdown = (sp_price - rolling_high) / rolling_high * 100
    
    # 修正：確保 signal 產出的是 Boolean Series
    signal = (drawdown <= -drop) & (drawdown.shift(1) > -drop)
    # 取出布林值為 True 的索引日期
    return sp_price.index[signal.values] 

# ─── 主邏輯 ──────────────────────────────────────────────────────────────────
if run_btn:
    with st.spinner("📡 正在獲取資料..."):
        # 標普500作為基準訊號
        sp500_raw = get_clean_data("^GSPC", start_year)
        # 投資標的組合
        portfolio = get_clean_data(ticker_input, start_year)

    if portfolio is None or sp500_raw is None:
        st.error("無法讀取代號，請檢查網路連線或代號是否正確。")
        st.stop()

    buy_dates = find_buy_signals(sp500_raw, drop_pct, lookback_window)
    
    results = []
    for d in buy_dates:
        # 尋找最接近的交易日
        available_dates = portfolio.index[portfolio.index >= d]
        if available_dates.empty: continue
        actual_buy_date = available_dates[0]
        
        row = {"買入日期": actual_buy_date.strftime("%Y-%m-%d")}
        buy_val = portfolio.loc[actual_buy_date]
        
        for p_name in selected_p:
            days = PERIOD_MAP[p_name]
            future_data = portfolio.index[portfolio.index > actual_buy_date]
            if len(future_data) >= days:
                sell_val = portfolio.loc[future_data[days-1]]
                row[p_name] = round((sell_val - buy_val) / buy_val * 100, 2)
        results.append(row)
    
    df_res = pd.DataFrame(results)
    
    if df_res.empty:
        st.warning("⚠️ 此條件下歷史上沒有觸發任何買入訊號。")
    else:
        st.markdown(f'<div class="result-header">📊 投資組合：{ticker_input} ｜ 觸發次數：{len(df_res)} 次</div>', unsafe_allow_html=True)
        
        # 指標卡片
        cards_html = '<div class="cards-row">'
        for p in selected_p:
            if p in df_res.columns and not df_res[p].isnull().all():
                avg = df_res[p].mean()
                wr = (df_res[p] > 0).mean() * 100
                cls = "pos" if avg >= 0 else "neg"
                cards_html += f"""
                <div class="mcard">
                    <div class="mcard-label">{p}平均報酬</div>
                    <div class="mcard-value {cls}">{avg:+.1f}%</div>
                    <div class="mcard-sub">勝率 {wr:.0f}%</div>
                </div>"""
        st.markdown(cards_html + '</div>', unsafe_allow_html=True)

        # 圖表 1：財富成長
        st.subheader("💰 每次買入後的財富變化 (假設投入 $100)")
        fig_w = go.Figure()
        fig_w.add_hline(y=100, line_dash="dash", line_color="#6b7280")
        for i, p in enumerate(selected_p):
            if p in df_res.columns:
                valid_data = df_res.dropna(subset=[p])
                fig_w.add_trace(go.Scatter(
                    x=valid_data["買入日期"], y=100*(1+valid_data[p]/100), 
                    name=p, mode='markers+lines', line=dict(color=COLORS[i%7], width=1.5),
                    marker=dict(size=6)
                ))
        fig_w.update_layout(template="plotly_dark", height=450, paper_bgcolor="#111827", plot_bgcolor="#111827")
        st.plotly_chart(fig_w, use_container_width=True)

        # 圖表 2：泡泡圖
        st.subheader("🎯 持有期勝率與報酬分佈")
        plot_p = [p for p in selected_p if p in df_res.columns]
        avg_v = [df_res[p].mean() for p in plot_p]
        wr_v = [(df_res[p] > 0).mean()*100 for p in plot_p]
        
        fig_b = go.Figure(go.Scatter(
            x=plot_p, y=wr_v, mode='markers+text',
            text=[f"{v:+.1f}%" for v in avg_v], textposition="top center",
            marker=dict(size=[max(15, abs(v)*1.5) for v in avg_v], color=wr_v, colorscale='Viridis', showscale=True)
        ))
        fig_b.update_layout(template="plotly_dark", yaxis_title="勝率 (%)", height=400, paper_bgcolor="#111827")
        st.plotly_chart(fig_b, use_container_width=True)

else:
    st.info("👈 請在左側設定條件，點擊「開始回測」查看結果")
