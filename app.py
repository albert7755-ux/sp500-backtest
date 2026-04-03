import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import warnings
warnings.filterwarnings('ignore')

# ─── 頁面設定 ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="標普500長線勝率分析", page_icon="📈", layout="wide")

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
.mcard-value { font-family: 'Roboto Mono', monospace; font-size: 1.4rem; font-weight: 700; }
.mcard-sub { color: #cbd5e1; font-size: 0.75rem; margin-top: 5px; }
.pos { color: #34d399; } .neg { color: #f87171; }
.result-header { background: #2563eb; border-radius: 10px; padding: 15px; color: white; font-weight: 700; margin-bottom: 20px; }
.commentary-box { background: #0f172a; border: 1px solid #3b82f6; padding: 20px; border-radius: 12px; line-height: 1.8; color: #e2e8f0; }
</style>
""", unsafe_allow_html=True)

st.title("📈 標普500跌幅後「長線勝率」分析")

# ─── 側邊欄 ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 參數設定")
    ticker_input = st.text_area("📌 買入標的 (多個請用逗號隔開)", value="MSFT").upper()
    drop_pct = st.slider("📉 S&P 500 從波段高點下跌 % 買入", 2, 50, 25, format="%d%%")
    
    # 這裡將窗口拉大，最高支援 1260 日 (約 5 年)
    lookback_window = st.selectbox(
        "計算高點窗口 (交易日)", 
        options=[30, 60, 90, 125, 252, 504, 756, 1260], 
        index=4, 
        format_func=lambda x: f"{x} 日 (約 {round(x/252, 1)} 年)"
    )
    
    start_year = st.slider("📅 資料起始年份", 1990, 2026, 2014)
    run_btn = st.button("🚀 開始分析績效", use_container_width=True, type="primary")

ALL_PERIODS = {"1個月": 21, "3個月": 63, "6個月": 126, "1年": 252, "2年": 504, "3年": 756, "5年": 1260}

# ─── 核心計算函數 ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def get_combined_price(tickers_str, start):
    tickers = [t.strip() for t in tickers_str.replace(',', ' ').split() if t.strip()]
    if not tickers: return None
    try:
        df = yf.download(tickers, start=f"{start}-01-01", progress=False, auto_adjust=True)
        if df.empty: return None
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            return (1 + close.pct_change().mean(axis=1)).cumprod().dropna()
        return close.dropna()
    except: return None

# ─── 執行回測 ────────────────────────────────────────────────────────────────
if run_btn:
    with st.spinner("正在追蹤訊號並計算績效..."):
        # 下載標普 500
        sp500_df = yf.download("^GSPC", start=f"{start_year}-05-01", progress=False, auto_adjust=True) # 提前下載確保窗口計算
        sp500 = sp500_df["Close"]
        if isinstance(sp500, pd.DataFrame): sp500 = sp500.iloc[:, 0]
        
        # 下載投資標的
        portfolio = get_combined_price(ticker_input, start_year)

    if sp500 is None or portfolio is None:
        st.error("讀取失敗，請確認代號是否正確。")
        st.stop()

    # 計算跌幅訊號
    rolling_high = sp500.rolling(window=lookback_window).max()
    drawdown = (sp500 - rolling_high) / rolling_high * 100
    signals = sp500.index[(drawdown <= -drop_pct) & (drawdown.shift(1) > -drop_pct)]

    results = []
    for d in signals:
        avail = portfolio.index[portfolio.index >= d]
        if avail.empty: continue
        t0, p0 = avail[0], portfolio.loc[avail[0]]
        row = {"買入日期": t0.strftime("%Y-%m-%d")}
        for name, days in ALL_PERIODS.items():
            future = portfolio.index[portfolio.index > t0]
            if len(future) >= days:
                row[name] = (portfolio.loc[future[days-1]] - p0) / p0 * 100
            else:
                row[name] = np.nan
        results.append(row)

    df_res = pd.DataFrame(results)

    if df_res.empty:
        st.warning(f"⚠️ 在 {lookback_window} 日窗口下，未偵測到下跌 {drop_pct}% 的進場訊號。")
    else:
        st.markdown(f'<div class="result-header">📊 標的：{ticker_input} ｜ 高點基準：{lookback_window}日 ｜ 進場：-{drop_pct}%</div>', unsafe_allow_html=True)

        # ── 1. 指標卡片 ──
        cards_html = '<div class="mcard-row">'
        stats_list = []
        for p in ALL_PERIODS.keys():
            if p in df_res.columns:
                col = df_res[p].dropna()
                if col.empty: continue
                avg, wr, m_min = col.mean(), (col > 0).mean() * 100, col.min()
                stats_list.append({"持有期": p, "平均報酬": avg, "勝率": wr, "最低": m_min})
                cls = "pos" if avg >= 0 else "neg"
                cards_html += f'<div class="mcard"><div class="mcard-label">{p}</div><div class="mcard-value {cls}">{avg:+.1f}%</div><div class="mcard-sub">勝率 {wr:.0f}%</div></div>'
        st.markdown(cards_html + '</div>', unsafe_allow_html=True)

        df_stats = pd.DataFrame(stats_list)

        # ── 2. 勝率柱狀圖 ──
        st.subheader("🎯 各持有期賺錢機率 (勝率)")
        fig_wr = go.Figure(go.Bar(
            x=df_stats["持有期"], y=df_stats["勝率"], 
            text=[f"{v:.0f}%" for v in df_stats["勝率"]], textposition="auto",
            marker_color='#34d399', opacity=0.8
        ))
        fig_wr.update_layout(template="plotly_dark", height=350, yaxis=dict(range=[0, 110]))
        st.plotly_chart(fig_wr, use_container_width=True)

        # ── 3. 深度解說 ──
        st.subheader("💡 投資績效深度解說")
        best_row = df_stats.loc[df_stats['平均報酬'].idxmax()]
        worst_loss = df_stats['最低'].min()
        
        st.markdown(f"""
        <div class="commentary-box">
        <b>1. 策略背景：</b><br>
        本回測採用 <b>{lookback_window} 日 (約 {round(lookback_window/252, 1)} 年)</b> 的高點作為基準。
        這意味著我們只會在市場相對於過去幾年的高位跌掉 {drop_pct}% 時才進場，這通常能過濾掉雜訊，抓到真正的歷史級買點。<br><br>
        
        <b>2. 績效表現：</b><br>
        歷史上共出現過 {len(df_res)} 次符合此條件的進場點。持有 <b>{best_row['持有期']}</b> 的平均獲利為 <b>{best_row['平均報酬']:+.1f}%</b>。
        最慘的一次曾出現過 <b>{worst_loss:+.1f}%</b> 的短期帳面浮虧，但隨時間推移，勝率最終穩定在 {df_stats.iloc[-1]['勝率']:.0f}%。<br><br>
        
        <b>3. 操作結論：</b><br>
        窗口越大，訊號越珍貴。目前的設定屬於「大週期撈底策略」。對於標的 <b>{ticker_input}</b> 來說，
        一旦滿足此回檔條件，長線勝算極高。
        </div>
        """, unsafe_allow_html=True)

        # ── 4. 數據總表 ──
        st.subheader("📋 詳細數據表")
        display_df = df_stats.copy()
        display_df["平均報酬"] = display_df["平均報酬"].map("{:+.1f}%".format)
        display_df["勝率"] = display_df["勝率"].map("{:.0f}%".format)
        display_df["最低紀錄"] = display_df["最低"].map("{:+.1f}%".format)
        st.table(display_df[["持有期", "平均報酬", "勝率", "最低紀錄"]])

else:
    st.info("👈 建議將窗口設為 252 日或 504 日，以獲得更具參考價值的波段高點數據。")
