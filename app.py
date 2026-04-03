import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
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
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Roboto+Mono:wght@400;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans TC', sans-serif;
}

.main { background-color: #0d1117; }

.metric-card {
    background: linear-gradient(135deg, #1a1f2e 0%, #151b27 100%);
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 16px 20px;
    margin: 6px 0;
}

.metric-positive { color: #3fb950; font-weight: 700; font-family: 'Roboto Mono', monospace; }
.metric-negative { color: #f85149; font-weight: 700; font-family: 'Roboto Mono', monospace; }
.metric-neutral  { color: #58a6ff; font-weight: 700; font-family: 'Roboto Mono', monospace; }

.result-header {
    background: linear-gradient(90deg, #1f6feb 0%, #388bfd 100%);
    border-radius: 10px;
    padding: 14px 20px;
    margin-bottom: 16px;
    color: white;
    font-weight: 700;
    font-size: 1.05rem;
}

.stAlert { border-radius: 10px; }

div[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

.sidebar-section {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 14px;
    margin-bottom: 12px;
}
</style>
""", unsafe_allow_html=True)

# ─── 標題 ────────────────────────────────────────────────────────────────────
st.title("📉 標普500跌幅後買入回測工具")
st.caption("設定 S&P 500 跌幅條件，查看買入任何股票/ETF/基金後的歷史績效表現")

# ─── 側邊欄設定 ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 回測設定")

    st.markdown("**📌 買入標的**")
    ticker_input = st.text_input(
        "輸入代號（美股）",
        value="SPY",
        help="例如：SPY、QQQ、AAPL、0050.TW"
    ).upper().strip()

    st.markdown("---")
    st.markdown("**📉 標普500跌幅條件**")
    drop_pct = st.slider(
        "從近期高點下跌 % 後買入",
        min_value=2,
        max_value=50,
        value=10,
        step=1,
        format="%d%%"
    )

    lookback_window = st.selectbox(
        "計算高點的回看窗口",
        options=[30, 60, 90, 125, 252],
        index=2,
        format_func=lambda x: f"{x} 個交易日（約 {round(x/21)} 個月）"
    )

    st.markdown("---")
    st.markdown("**📅 回測期間**")
    start_year = st.slider("資料起始年份", 1990, 2020, 2000)
    start_date = f"{start_year}-01-01"
    end_date = datetime.today().strftime("%Y-%m-%d")

    st.markdown("---")
    st.markdown("**⏱️ 持有期間**")
    periods = st.multiselect(
        "選擇要分析的持有期",
        options=["1個月", "3個月", "6個月", "1年", "2年", "3年", "5年"],
        default=["1個月", "3個月", "6個月", "1年", "2年", "3年", "5年"]
    )

    run_btn = st.button("🚀 開始回測", use_container_width=True, type="primary")

# ─── 輔助函數 ─────────────────────────────────────────────────────────────────
PERIOD_MAP = {
    "1個月": 21,
    "3個月": 63,
    "6個月": 126,
    "1年": 252,
    "2年": 504,
    "3年": 756,
    "5年": 1260,
}

@st.cache_data(ttl=3600)
def load_data(ticker, start, end):
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if df.empty:
        return None
    return df["Close"].squeeze()

def find_buy_signals(sp500: pd.Series, drop_pct: float, window: int) -> pd.Series:
    """找出 S&P500 從近期高點下跌 drop_pct% 的日期"""
    rolling_high = sp500.rolling(window=window).max()
    drawdown = (sp500 - rolling_high) / rolling_high * 100
    # 跌幅 >= drop_pct 且前一天未觸發（避免連續觸發）
    signal = drawdown <= -drop_pct
    signal_filtered = signal & (~signal.shift(1).fillna(False))
    return sp500.index[signal_filtered]

def calc_returns(target: pd.Series, buy_dates, periods_days: dict) -> pd.DataFrame:
    results = []
    target_idx = target.index.tolist()

    for buy_date in buy_dates:
        if buy_date not in target.index:
            # 找最近的交易日
            future = [d for d in target_idx if d >= buy_date]
            if not future:
                continue
            buy_date = future[0]

        buy_price = target.loc[buy_date]
        row = {"買入日期": buy_date.strftime("%Y-%m-%d"), "買入價格": round(float(buy_price), 2)}

        for period_name, days in periods_days.items():
            future_dates = [d for d in target_idx if d > buy_date]
            if len(future_dates) >= days:
                sell_date = future_dates[days - 1]
                sell_price = target.loc[sell_date]
                ret = (float(sell_price) - float(buy_price)) / float(buy_price) * 100
                row[period_name] = round(ret, 2)
            else:
                row[period_name] = np.nan  # 資料不足

        results.append(row)

    return pd.DataFrame(results)

def color_return(val):
    if pd.isna(val):
        return "color: gray"
    return "color: #3fb950; font-weight:600" if val >= 0 else "color: #f85149; font-weight:600"

# ─── 主邏輯 ──────────────────────────────────────────────────────────────────
if run_btn:
    selected_periods = {p: PERIOD_MAP[p] for p in periods if p in PERIOD_MAP}

    if not selected_periods:
        st.warning("請至少選擇一個持有期間")
        st.stop()

    with st.spinner("載入資料中..."):
        sp500 = load_data("^GSPC", start_date, end_date)
        target = load_data(ticker_input, start_date, end_date)

    if sp500 is None:
        st.error("無法載入 S&P 500 資料，請檢查網路連線")
        st.stop()
    if target is None:
        st.error(f"找不到代號 **{ticker_input}**，請確認代號是否正確（台股請加 .TW，如 0050.TW）")
        st.stop()

    # 找買入訊號
    buy_dates = find_buy_signals(sp500, drop_pct, lookback_window)

    if len(buy_dates) == 0:
        st.warning(f"在設定期間內，S&P 500 從未從 {lookback_window} 日高點下跌 {drop_pct}%，請降低跌幅門檻或延長回測期間。")
        st.stop()

    # 計算報酬
    df_results = calc_returns(target, buy_dates, selected_periods)
    valid_df = df_results.dropna(subset=list(selected_periods.keys()), how="all")

    if valid_df.empty:
        st.warning("買入標的的資料期間不足以計算任何持有期報酬，請縮短持有期或調整標的。")
        st.stop()

    # ─── 結果顯示 ───────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="result-header">
        📊 回測結果：S&P 500 從 {lookback_window} 日高點跌 {drop_pct}% → 買入 <b>{ticker_input}</b>
        &nbsp;｜&nbsp; 共觸發 <b>{len(valid_df)}</b> 次訊號
    </div>
    """, unsafe_allow_html=True)

    # ─── 摘要統計 ───────────────────────────────────────────────────────────
    st.subheader("📈 各持有期平均報酬率")
    cols = st.columns(len(selected_periods))
    for i, period in enumerate(selected_periods.keys()):
        col_data = valid_df[period].dropna()
        if col_data.empty:
            continue
        avg = col_data.mean()
        win_rate = (col_data > 0).mean() * 100
        with cols[i]:
            color = "metric-positive" if avg >= 0 else "metric-negative"
            st.markdown(f"""
            <div class="metric-card">
                <div style="color:#8b949e;font-size:0.8rem;margin-bottom:4px">{period}</div>
                <div class="{color}" style="font-size:1.4rem">{avg:+.1f}%</div>
                <div style="color:#8b949e;font-size:0.75rem;margin-top:4px">
                    勝率 {win_rate:.0f}% · {len(col_data)} 筆
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # ─── 圖表：各持有期報酬分佈 ─────────────────────────────────────────────
    st.subheader("📦 各持有期報酬分佈（箱型圖）")
    period_cols = [p for p in selected_periods.keys() if p in valid_df.columns]
    melted = valid_df[period_cols].melt(var_name="持有期", value_name="報酬率(%)")
    melted = melted.dropna()

    fig_box = go.Figure()
    colors = ["#58a6ff","#3fb950","#f0883e","#bc8cff","#ffa657","#ff7b72","#79c0ff"]
    for i, period in enumerate(period_cols):
        data_p = melted[melted["持有期"] == period]["報酬率(%)"]
        fig_box.add_trace(go.Box(
            y=data_p,
            name=period,
            marker_color=colors[i % len(colors)],
            boxmean=True
        ))
    fig_box.add_hline(y=0, line_dash="dash", line_color="#8b949e", opacity=0.6)
    fig_box.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0d1117",
        plot_bgcolor="#0d1117",
        font=dict(family="Noto Sans TC"),
        yaxis_title="報酬率 (%)",
        showlegend=False,
        height=400,
        margin=dict(t=20, b=40)
    )
    st.plotly_chart(fig_box, use_container_width=True)

    # ─── 圖表：每次訊號報酬走勢 ─────────────────────────────────────────────
    if "1年" in period_cols:
        st.subheader("📅 每次買入後 1 年報酬（按日期排序）")
        chart_df = valid_df[["買入日期", "1年"]].dropna().copy()
        chart_df["顏色"] = chart_df["1年"].apply(lambda x: "#3fb950" if x >= 0 else "#f85149")
        fig_bar = go.Figure(go.Bar(
            x=chart_df["買入日期"],
            y=chart_df["1年"],
            marker_color=chart_df["顏色"],
            marker_line_width=0,
            text=chart_df["1年"].apply(lambda x: f"{x:+.1f}%"),
            textposition="outside",
            textfont=dict(color="white", size=10)
        ))
        fig_bar.add_hline(y=0, line_color="#ffffff", line_dash="dot", line_width=1)
        fig_bar.update_layout(
            template="plotly_dark",
            paper_bgcolor="#161b22",
            plot_bgcolor="#161b22",
            font=dict(family="Noto Sans TC", color="white"),
            yaxis=dict(
                title="1 年報酬率 (%)",
                gridcolor="#30363d",
                zerolinecolor="#8b949e"
            ),
            xaxis=dict(gridcolor="#30363d"),
            height=420,
            margin=dict(t=40, b=60)
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    # ─── S&P500 走勢 + 買入點 ───────────────────────────────────────────────
    st.subheader("📉 S&P 500 走勢與買入訊號點")
    buy_prices = []
    for d in buy_dates:
        future = [x for x in sp500.index if x >= d]
        if future:
            bd = future[0]
            buy_prices.append((bd, float(sp500.loc[bd])))

    fig_sp = go.Figure()
    fig_sp.add_trace(go.Scatter(
        x=sp500.index, y=sp500.values,
        mode="lines", name="S&P 500",
        line=dict(color="#58a6ff", width=1.5)
    ))
    if buy_prices:
        bx, by = zip(*buy_prices)
        fig_sp.add_trace(go.Scatter(
            x=list(bx), y=list(by),
            mode="markers", name="買入訊號",
            marker=dict(color="#f0883e", size=8, symbol="triangle-up")
        ))
    fig_sp.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0d1117",
        plot_bgcolor="#0d1117",
        font=dict(family="Noto Sans TC"),
        yaxis_title="S&P 500 指數",
        height=380,
        margin=dict(t=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02)
    )
    st.plotly_chart(fig_sp, use_container_width=True)

    # ─── 詳細資料表 ─────────────────────────────────────────────────────────
    st.subheader("📋 詳細每筆買入紀錄")
    display_cols = ["買入日期", "買入價格"] + period_cols
    display_df = valid_df[display_cols].copy()

    def fmt_return(x):
        if pd.isna(x):
            return "—"
        return f"{x:+.1f}%"

    styled = display_df.style.map(
        color_return,
        subset=period_cols
    ).format({p: fmt_return for p in period_cols})

    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ─── 統計摘要表 ─────────────────────────────────────────────────────────
    st.subheader("📊 統計摘要")
    summary_rows = []
    for period in period_cols:
        col_data = valid_df[period].dropna()
        if col_data.empty:
            continue
        summary_rows.append({
            "持有期": period,
            "樣本數": len(col_data),
            "平均報酬": f"{col_data.mean():+.1f}%",
            "中位數": f"{col_data.median():+.1f}%",
            "最佳": f"{col_data.max():+.1f}%",
            "最差": f"{col_data.min():+.1f}%",
            "勝率": f"{(col_data > 0).mean()*100:.0f}%",
            "標準差": f"{col_data.std():.1f}%",
        })

    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    # ─── 下載 ───────────────────────────────────────────────────────────────
    csv = valid_df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "⬇️ 下載完整回測資料（CSV）",
        data=csv,
        file_name=f"backtest_{ticker_input}_drop{drop_pct}pct.csv",
        mime="text/csv"
    )

else:
    st.info("👈 請在左側設定條件，點擊「開始回測」查看結果")

    st.markdown("""
    ### 🗺️ 使用說明
    1. **輸入買入標的代號**：例如 `SPY`（標普ETF）、`QQQ`（那斯達克ETF）、`AAPL`（蘋果股票）
    2. **設定跌幅門檻**：S&P 500 從近期高點下跌幾 % 時買入
    3. **選擇高點回看窗口**：計算「近期高點」時要往回看幾個交易日
    4. **選擇回測期間**：資料從哪一年開始
    5. **選擇持有期**：買入後持有多久觀察績效
    6. 點擊 **開始回測** 即可看到歷史上每次觸發條件的買入結果

    ### 📌 常見代號
    | 類型 | 代號 | 說明 |
    |------|------|------|
    | ETF | SPY | 標普500 ETF |
    | ETF | QQQ | 那斯達克100 ETF |
    | ETF | VT | 全球股市 ETF |
    | ETF | GLD | 黃金 ETF |
    | 股票 | AAPL | 蘋果 |
    | 股票 | MSFT | 微軟 |
    | 台股ETF | 0050.TW | 元大台灣50 |
    """)
