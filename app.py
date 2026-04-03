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

st.title("📈 標普500跌幅後「長線勝率」回測工具")

# ─── 側邊欄 ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 參數設定")
    ticker_input = st.text_area("📌 買入標的 (多個請用逗號隔開)", value="SPY, QQQ, NVDA").upper()
    drop_pct = st.slider("📉 S&P 500 從高點下跌 % 買入", 2, 50, 10, format="%d%%")
    lookback_window = st.selectbox("計算高點窗口 (日)", [30, 60, 90, 125, 252], index=2)
    start_year = st.slider("📅 資料起始年份", 1990, 2026, 2010)
    run_btn = st.button("🚀 開始分析並生成解說", use_container_width=True, type="primary")

ALL_PERIODS = {"1個月": 21, "3個月": 63, "6個月": 126, "1年": 252, "2年": 504, "3年": 756, "5年": 1260}

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
    with st.spinner("正在計算數據與生成解說..."):
        sp500 = get_portfolio_price("^GSPC", start_year)
        portfolio = get_portfolio_price(ticker_input, start_year)

    if sp500 is None or portfolio is None:
        st.error("讀取失敗，請確認代號正確。")
        st.stop()

    rolling_high = sp500.rolling(window=lookback_window).max()
    drawdown = (sp500 - rolling_high) / rolling_high * 100
    signals = sp500.index[(drawdown <= -drop_pct) & (drawdown.shift(1) > -drop_pct)]

    results = []
    for d in signals:
        avail = portfolio.index[portfolio.index >= d]
        if avail.empty: continue
        t0 = avail[0]
        row = {"買入日期": t0.strftime("%Y-%m-%d")}
        p0 = portfolio.loc[t0]
        for name, days in ALL_PERIODS.items():
            future = portfolio.index[portfolio.index > t0]
            if len(future) >= days:
                row[name] = (portfolio.loc[future[days-1]] - p0) / p0 * 100
            else:
                row[name] = np.nan
        results.append(row)

    df_res = pd.DataFrame(results)

    if df_res.empty:
        st.warning("此條件下無任何訊號。")
    else:
        st.markdown(f'<div class="result-header">📊 分析標的：{ticker_input} ｜ 歷史觸發次數：{len(df_res)} 次</div>', unsafe_allow_html=True)

        # ── 1. 核心指標卡片 ──
        cards_html = '<div class="mcard-row">'
        stats_list = []
        for p in ALL_PERIODS.keys():
            if p in df_res.columns:
                col = df_res[p].dropna()
                if col.empty: continue
                avg, wr, m_min = col.mean(), (col > 0).mean() * 100, col.min()
                stats_list.append({"持有期": p, "平均報酬": avg, "勝率": wr, "樣本數": len(col), "最低": m_min})
                cls = "pos" if avg >= 0 else "neg"
                cards_html += f'<div class="mcard"><div class="mcard-label">{p}</div><div class="mcard-value {cls}">{avg:+.1f}%</div><div class="mcard-sub">勝率 {wr:.0f}%</div></div>'
        st.markdown(cards_html + '</div>', unsafe_allow_html=True)

        # ── 2. 勝率進化圖 ──
        st.subheader("🎯 持有時間與賺錢機率關係圖")
        df_stats = pd.DataFrame(stats_list)
        fig_wr = go.Figure()
        fig_wr.add_trace(go.Scatter(x=df_stats["持有期"], y=df_stats["勝率"], mode='lines+markers+text', text=[f"{v:.0f}%" for v in df_stats["勝率"]], textposition="top center", line=dict(color='#34d399', width=4)))
        fig_wr.update_layout(template="plotly_dark", height=350, yaxis=dict(range=[0, 110]))
        st.plotly_chart(fig_wr, use_container_width=True)

        # ── 3. 自動生成的回測解說 (核心亮點) ──
        st.subheader("💡 投資績效深度解說")
        
        # 邏輯判斷
        best_period = df_stats.iloc[df_stats['平均報酬'].idxmax()]
        safe_period = df_stats[df_stats['勝率'] >= 85].iloc[0] if any(df_stats['勝_率'] >= 85) else None
        worst_loss = df_stats['最低'].min()
        
        commentary = f"""
        <div class="commentary-box">
        <b>1. 總體評價：</b><br>
        自 {start_year} 年以來，當 S&P 500 下跌 {drop_pct}% 時，買入這個組合的表現相當
        {"優秀，長線具有極高勝算" if best_period['平均報酬'] > 20 else "穩健，適合資產配置"}。
        在歷史上共出現過 {len(df_res)} 次機會。<br><br>
        
        <b>2. 勝率關鍵轉折點：</b><br>
        觀察勝率圖，買入後{"賺錢機率隨時間穩定爬升" if df_stats['勝率'].iloc[-1] > df_stats['勝率'].iloc[0] else "勝率變化波動較大"}。
        """
        if safe_period is not None:
            commentary += f"如果你追求高度安全性，<b>持有至少 {safe_period['持有期']}</b> 後，勝率將來到 {safe_period['勝率']:.0f}%，這是一個非常關鍵的心理防線。"
        else:
            commentary += "目前組合在各持有期的勝率尚未達到 85% 的絕對穩健水位，建議分批進場。"
            
        commentary += f"""<br><br>
        <b>3. 風險預警：</b><br>
        回測中最慘的一次紀錄是在短線出現過 <b>{worst_loss:+.1f}%</b> 的跌幅。這告訴我們，即便是在回檔後買入，
        短期內仍可能面臨陣痛期，但隨著持有時間拉長至 3-5 年，最低報酬已提升至 {df_stats.iloc[-1]['最低']:+.1f}%，顯示時間能有效稀釋風險。<br><br>
        
        <b>4. 執行建議：</b><br>
        本組合的最優持有期為 <b>{best_period['持有期']}</b>，預期平均報酬約為 <b>{best_period['平均報酬']:+.1f}%</b>。
        建議投資人若在標普回檔買入後，應保持耐心，避免在 6 個月內的波動中恐慌出場。
        </div>
        """
        st.markdown(commentary, unsafe_allow_html=True)

        # ── 4. 詳細對照表 ──
        st.subheader("📋 數據對照總表")
        display_df = df_stats.copy()
        display_df["平均報酬"] = display_df["平均報酬"].map("{:+.1f}%".format)
        display_df["勝率"] = display_df["勝率"].map("{:.0f}%".format)
        display_df["最低"] = display_df["最低"].map("{:+.1f}%".format)
        st.table(display_df[["持有期", "樣本數", "平均報酬", "勝率", "最低"]])

else:
    st.info("👈 設定左側參數後，點擊「開始分析」")
