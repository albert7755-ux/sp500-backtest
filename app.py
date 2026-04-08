import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import warnings
warnings.filterwarnings('ignore')

# ─── 頁面設定 ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="標普500回測工具",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700;900&family=Roboto+Mono:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; }

.cards-row {
    display: flex; gap: 10px; flex-wrap: nowrap;
    overflow-x: auto; padding-bottom: 6px;
}
.mcard {
    flex: 1 1 0; min-width: 100px;
    background: linear-gradient(160deg, #1a2332 0%, #111827 100%);
    border: 1px solid #2d3748; border-radius: 14px;
    padding: 14px 12px 12px; text-align: center;
}
.mcard-label { color: #d1d5db; font-size: 0.72rem; margin-bottom: 6px; }
.mcard-value {
    font-family: 'Roboto Mono', monospace;
    font-size: 1.55rem; font-weight: 700;
    line-height: 1; white-space: nowrap;
}
.mcard-sub { color: #d1d5db; font-size: 0.68rem; margin-top: 6px; }
.pos { color: #34d399; }
.neg { color: #f87171; }

.result-header {
    background: linear-gradient(90deg, #1d4ed8 0%, #2563eb 100%);
    border-radius: 12px; padding: 14px 20px; margin-bottom: 18px;
    color: white; font-weight: 700; font-size: 1rem;
}
.insight-box {
    background: linear-gradient(135deg, #0f2027 0%, #1a2a3a 100%);
    border-left: 4px solid #3b82f6; border-radius: 0 10px 10px 0;
    padding: 14px 18px; margin: 10px 0 18px;
    color: #f1f5f9; font-size: 0.88rem; line-height: 1.7;
}
</style>
""", unsafe_allow_html=True)

# ─── 標題 ────────────────────────────────────────────────────────────────────
st.title("📉 股市回測與走勢比較工具")
st.caption("跌幅後買入回測 ｜ 不同時期走勢比較")

# ─── 側邊欄 ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 回測設定")
    st.markdown("**📌 買入標的**")
    ticker_input = st.text_input(
        "買入標的代號", value="SPY",
        help="美股：SPY、QQQ、AAPL｜台股：0050.TW"
    ).upper().strip()

    st.markdown("---")
    st.markdown("**📉 觸發條件標的**")
    signal_ticker = st.text_input(
        "跌幅觸發標的代號", value="^GSPC",
        help="預設 ^GSPC（S&P 500）；也可填 QQQ、^SOX、^TWII、0050.TW 等"
    ).upper().strip()
    # 自動產生顯示名稱，不用手動填
    TICKER_NAMES = {
        "^GSPC": "S&P 500", "^NDX": "那斯達克100", "QQQ": "那斯達克100 ETF",
        "^SOX": "費城半導體", "SOXX": "半導體ETF", "^VIX": "恐慌指數VIX",
        "^TWII": "台灣加權指數", "0050.TW": "台灣50",
    }
    signal_name = TICKER_NAMES.get(signal_ticker, signal_ticker)

    drop_pct = st.slider(
        "從近期高點下跌 % 後買入",
        min_value=2, max_value=50, value=10, step=1, format="%d%%"
    )
    lookback_window = st.selectbox(
        "計算高點回看窗口",
        options=[30, 60, 90, 125, 252], index=2,
        format_func=lambda x: f"{x} 個交易日（約 {round(x/21)} 個月）"
    )
    st.markdown("---")
    start_year = st.slider("📅 資料起始年份", 1990, 2020, 2000)
    start_date = f"{start_year}-01-01"

    st.markdown("---")
    periods = st.multiselect(
        "⏱️ 持有期間",
        options=["1個月", "3個月", "6個月", "1年", "2年", "3年", "5年"],
        default=["1個月", "3個月", "6個月", "1年", "2年", "3年", "5年"]
    )
    run_btn = st.button("🚀 開始回測", use_container_width=True, type="primary")

# ─── 常數 ────────────────────────────────────────────────────────────────────
PERIOD_MAP = {
    "1個月": 21, "3個月": 63, "6個月": 126,
    "1年": 252, "2年": 504, "3年": 756, "5年": 1260,
}
COLORS = ["#60a5fa","#34d399","#fb923c","#a78bfa","#f472b6","#facc15","#38bdf8"]

# ─── 函數 ────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_data(ticker, start):
    for attempt in range(3):
        try:
            df = yf.download(ticker, start=start, progress=False,
                             auto_adjust=True, timeout=30)
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
    return sp500.index[signal & (~signal.shift(1).fillna(False))]

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
                row[pname] = round(
                    (float(target.loc[future[days-1]]) - buy_price) / buy_price * 100, 2)
            else:
                row[pname] = np.nan
        results.append(row)
    return pd.DataFrame(results)

def color_cell(val):
    if pd.isna(val): return "color: #9ca3af"
    return "color: #34d399; font-weight:600" if val >= 0 else "color: #f87171; font-weight:600"

def fmt_pct(x):
    return "—" if pd.isna(x) else f"{x:+.1f}%"

def draw_normal_dist(valid_df, period, period_cols):
    """畫常態分配圖，回傳 fig 和統計值"""
    dist_data = valid_df[period].dropna()
    mu    = float(dist_data.mean())
    sigma = float(dist_data.std())
    n     = len(dist_data)
    x_min  = min(float(dist_data.min()), mu - 3.5*sigma)
    x_max  = max(float(dist_data.max()), mu + 3.5*sigma)
    x_norm = np.linspace(x_min, x_max, 400)
    bin_w  = (x_max - x_min) / 30
    y_norm = (n * bin_w / (sigma * np.sqrt(2*np.pi))) * np.exp(-0.5*((x_norm-mu)/sigma)**2)

    fig = go.Figure()
    # ±2σ 陰影
    m2 = (x_norm >= mu-2*sigma) & (x_norm <= mu+2*sigma)
    fig.add_trace(go.Scatter(
        x=np.concatenate([x_norm[m2], x_norm[m2][::-1]]),
        y=np.concatenate([y_norm[m2], np.zeros(m2.sum())]),
        fill="toself", fillcolor="rgba(96,165,250,0.10)",
        line=dict(width=0), name="±2σ（約95%機率）", hoverinfo="skip"
    ))
    # ±1σ 陰影
    m1 = (x_norm >= mu-sigma) & (x_norm <= mu+sigma)
    fig.add_trace(go.Scatter(
        x=np.concatenate([x_norm[m1], x_norm[m1][::-1]]),
        y=np.concatenate([y_norm[m1], np.zeros(m1.sum())]),
        fill="toself", fillcolor="rgba(96,165,250,0.22)",
        line=dict(width=0), name="±1σ（約68%機率）", hoverinfo="skip"
    ))
    # 直方圖
    fig.add_trace(go.Histogram(
        x=dist_data, nbinsx=30, name="實際歷史分佈",
        marker_color="rgba(251,146,60,0.55)",
        marker_line=dict(color="rgba(251,146,60,0.9)", width=1),
    ))
    # 常態曲線
    fig.add_trace(go.Scatter(
        x=x_norm, y=y_norm, mode="lines", name="理論常態分配",
        line=dict(color="#60a5fa", width=2.5)
    ))
    # 垂直線
    fig.add_vline(x=mu, line_color="#facc15", line_dash="dash", line_width=2,
        annotation_text=f"μ={mu:+.1f}%", annotation_font_color="#facc15",
        annotation_position="top right")
    fig.add_vline(x=0, line_color="#6b7280", line_dash="dot", line_width=1.5,
        annotation_text="0%", annotation_font_color="#e5e7eb",
        annotation_position="top left")
    for val, lbl, pos in [
        (mu-sigma, f"-1σ={mu-sigma:+.1f}%", "top left"),
        (mu+sigma, f"+1σ={mu+sigma:+.1f}%", "top right")
    ]:
        fig.add_vline(x=val, line_color="#a78bfa", line_dash="dot", line_width=1,
            annotation_text=lbl, annotation_font_color="#a78bfa",
            annotation_position=pos)
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#111827", plot_bgcolor="#111827",
        font=dict(family="Noto Sans TC", color="#e5e7eb"),
        barmode="overlay",
        xaxis=dict(title="報酬率 (%)", gridcolor="#1f2937"),
        yaxis=dict(title="次數", gridcolor="#1f2937"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, bgcolor="rgba(0,0,0,0)"),
        height=460, margin=dict(t=50, b=50)
    )
    return fig, mu, sigma, n

# ─── 按下回測：計算並存入 session_state ─────────────────────────────────────
# ─── 頁籤 ───────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["📉 跌幅後買入回測", "📊 不同時期走勢比較"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 2：走勢比較（獨立，不依賴回測結果）
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("<div style='margin-top: 20px'></div>", unsafe_allow_html=True)
    st.subheader("📊 同一標的不同時期走勢比較")
    st.caption("將各時期走勢對齊到起跌點（0%），直觀比較跌幅與反彈速度")
    st.markdown("<div style='margin-bottom: 16px'></div>", unsafe_allow_html=True)

    col_l, col_r = st.columns([1, 2])
    with col_l:
        cmp_ticker = st.text_input(
            "比較標的代號", value="^GSPC",
            help="例如 ^GSPC、QQQ、^SOX、0050.TW"
        ).upper().strip()

        st.markdown("**選擇要比較的時期**（可多選）")
        st.caption("每個時期填入起始日期，程式自動抓之後 400 個交易日的走勢")

        # 預設幾個常見事件
        default_periods_cmp = [
            ("2022年升息熊市", "2022-01-03"),
            ("2020年疫情", "2020-02-19"),
            ("2018年修正", "2018-09-20"),
            ("2025年現在", "2025-01-01"),
        ]

        cmp_periods = []
        for i in range(6):
            c1, c2 = st.columns([2, 3])
            default_label = default_periods_cmp[i][0] if i < len(default_periods_cmp) else ""
            default_date  = default_periods_cmp[i][1] if i < len(default_periods_cmp) else ""
            with c1:
                label = st.text_input(f"名稱 {i+1}", value=default_label, key=f"cmp_label_{i}")
            with c2:
                date  = st.text_input(f"起始日 {i+1}", value=default_date,
                                      placeholder="YYYY-MM-DD", key=f"cmp_date_{i}")
            if label.strip() and date.strip():
                cmp_periods.append((label.strip(), date.strip()))

        days_to_show = st.slider("顯示天數（交易日）", 60, 600, 400, 20)
        align_mode = st.radio("對齊方式", ["從起始日對齊（絕對走勢）", "從高點跌幅對齊（跌幾%）"], index=1)
        cmp_btn = st.button("🔍 產生比較圖", type="primary", use_container_width=True)

    with col_r:
        if cmp_btn and cmp_ticker and cmp_periods:
            with st.spinner("載入資料中..."):
                # 抓足夠長的資料
                earliest = min(p[1] for p in cmp_periods)
                raw = load_data(cmp_ticker, earliest)

            if raw is None:
                st.error(f"❌ 無法載入「{cmp_ticker}」，請確認代號或稍後重試。")
            else:
                TICKER_NAMES2 = {
                    "^GSPC": "S&P 500", "^NDX": "那斯達克100", "QQQ": "QQQ",
                    "^SOX": "費城半導體", "^VIX": "VIX", "^TWII": "台灣加權",
                    "0050.TW": "台灣50",
                }
                disp_name = TICKER_NAMES2.get(cmp_ticker, cmp_ticker)
                fig_cmp = go.Figure()

                valid_count = 0
                for label, start_str in cmp_periods:
                    try:
                        start_dt = pd.Timestamp(start_str)
                    except Exception:
                        st.warning(f"「{label}」日期格式錯誤，請用 YYYY-MM-DD")
                        continue

                    # 找最近的交易日
                    future_idx = [d for d in raw.index if d >= start_dt]
                    if not future_idx:
                        st.warning(f"「{label}」的起始日 {start_str} 超出資料範圍")
                        continue
                    actual_start = future_idx[0]
                    segment = raw.loc[actual_start:].iloc[:days_to_show]
                    if len(segment) < 5:
                        continue

                    base_price = float(segment.iloc[0])
                    if "跌幅" in align_mode:
                        # 以起始點為 0%，計算每天相對漲跌
                        y_vals = ((segment / base_price) - 1) * 100
                        y_title = "相對起點漲跌幅 (%)"
                    else:
                        # 絕對價格，以起始點 = 100 標準化
                        y_vals = (segment / base_price) * 100
                        y_title = "相對指數（起始點 = 100）"

                    x_vals = list(range(len(segment)))  # x 軸用交易日天數

                    fig_cmp.add_trace(go.Scatter(
                        x=x_vals, y=y_vals.values,
                        mode="lines", name=label,
                        line=dict(width=2),
                        hovertemplate=f"<b>{label}</b><br>第%{{x}}個交易日<br>%{{y:+.1f}}%<extra></extra>"
                    ))
                    valid_count += 1

                if valid_count == 0:
                    st.warning("沒有有效的時期資料，請確認日期格式（YYYY-MM-DD）")
                else:
                    # 加 0 基準線
                    if "跌幅" in align_mode:
                        fig_cmp.add_hline(y=0, line_color="#6b7280", line_dash="dot", line_width=1)

                    fig_cmp.update_layout(
                        template="plotly_dark",
                        paper_bgcolor="#111827", plot_bgcolor="#111827",
                        font=dict(family="Noto Sans TC", color="#e5e7eb"),
                        xaxis=dict(title="交易日數（從各時期起始點）", gridcolor="#1f2937"),
                        yaxis=dict(title=y_title, gridcolor="#1f2937"),
                        legend=dict(orientation="h", yanchor="top", y=1.08,
                                    bgcolor="rgba(0,0,0,0)", font=dict(color="#f1f5f9")),
                        height=540, margin=dict(t=80, b=50),
                        title=dict(
                            text=f"{disp_name} 不同時期走勢比較",
                            font=dict(size=15, color="#f1f5f9"),
                            x=0, xanchor="left", y=0.01, yanchor="bottom"
                        )
                    )
                    st.plotly_chart(fig_cmp, use_container_width=True)

                    # 統計比較表
                    st.markdown("**📋 各時期統計**")
                    stat_rows = []
                    for label, start_str in cmp_periods:
                        try:
                            start_dt = pd.Timestamp(start_str)
                            future_idx = [d for d in raw.index if d >= start_dt]
                            if not future_idx: continue
                            segment = raw.loc[future_idx[0]:].iloc[:days_to_show]
                            if len(segment) < 5: continue
                            base = float(segment.iloc[0])
                            pct = ((segment / base) - 1) * 100
                            stat_rows.append({
                                "時期": label,
                                "起始日": start_str,
                                "最大跌幅": f"{pct.min():+.1f}%",
                                "最大漲幅": f"{pct.max():+.1f}%",
                                f"第{days_to_show}日報酬": f"{float(pct.iloc[-1]):+.1f}%" if len(pct)==days_to_show else "資料不足",
                            })
                        except Exception:
                            continue
                    if stat_rows:
                        st.dataframe(pd.DataFrame(stat_rows), use_container_width=True, hide_index=True)
        elif not cmp_btn:
            st.info("👈 設定標的與時期後，點擊「產生比較圖」")

# ════════════════════════════════════════════════════════════════════════════
# TAB 1：原本的回測功能
# ════════════════════════════════════════════════════════════════════════════
with tab1:

    if run_btn:
        selected_periods = {p: PERIOD_MAP[p] for p in periods if p in PERIOD_MAP}
        if not selected_periods:
            st.warning("請至少選擇一個持有期間")
            st.stop()

        with st.spinner("📡 從 Yahoo Finance 載入資料（最多重試3次）..."):
            sp500  = load_data(signal_ticker, start_date)
            target = load_data(ticker_input, start_date)

        if sp500 is None:
            st.error("❌ 無法載入 S&P 500 資料。Yahoo Finance 可能暫時限流，稍後 10 秒再按「開始回測」重試。")
            st.stop()
        if target is None:
            st.error(f"❌ 找不到代號「{ticker_input}」。美股直接輸入代號（SPY），台股請加 .TW（0050.TW）")
            st.stop()

        buy_dates   = find_buy_signals(sp500, drop_pct, lookback_window)
        df_results  = calc_returns(target, buy_dates, selected_periods)
        valid_df    = df_results.dropna(subset=list(selected_periods.keys()), how="all")
        period_cols = [p for p in selected_periods if p in valid_df.columns]

        if valid_df.empty or not period_cols:
            st.warning("觸發訊號後資料不足，請縮短持有期或調整條件。")
            st.stop()

        # ✅ 把所有結果存進 session_state，selectbox 切換時不會消失
        st.session_state["result"] = {
            "valid_df":      valid_df,
            "period_cols":   period_cols,
            "sp500":         sp500,
            "buy_dates":     buy_dates,
            "ticker":        ticker_input,
            "signal_ticker": signal_ticker,
            "signal_name":   signal_name,
            "drop_pct":      drop_pct,
            "lookback":      lookback_window,
            "start_year":    start_year,
        }

    # ─── 顯示結果（從 session_state 讀取，不依賴 run_btn）────────────────────────
    if "result" in st.session_state:
        R            = st.session_state["result"]
        valid_df     = R["valid_df"]
        period_cols  = R["period_cols"]
        sp500        = R["sp500"]
        buy_dates    = R["buy_dates"]
        ticker_input  = R["ticker"]
        signal_ticker = R.get("signal_ticker", "^GSPC")
        signal_name   = R.get("signal_name", "S&P 500")
        drop_pct      = R["drop_pct"]
        lookback_window = R["lookback"]
        start_year    = R["start_year"]
        n_signals    = len(valid_df)

        # ── 標題 ────────────────────────────────────────────────────────────────
        st.markdown(f"""
        <div class="result-header">
            📊 {signal_name} 從 {lookback_window} 日高點跌 {drop_pct}% → 買入 <b>{ticker_input}</b>
            &nbsp;｜&nbsp; 歷史共觸發 <b>{n_signals}</b> 次
        </div>""", unsafe_allow_html=True)

        # ── 卡片 ────────────────────────────────────────────────────────────────
        st.subheader("📈 各持有期平均報酬率")
        cards_html = '<div class="cards-row">'
        for period in period_cols:
            col_data = valid_df[period].dropna()
            avg      = col_data.mean()
            win_rate = (col_data > 0).mean() * 100
            cls      = "pos" if avg >= 0 else "neg"
            sign     = "+" if avg >= 0 else ""
            cards_html += f"""
            <div class="mcard">
                <div class="mcard-label">{period}</div>
                <div class="mcard-value {cls}">{sign}{avg:.1f}%</div>
                <div class="mcard-sub">勝率 {win_rate:.0f}%<br>{len(col_data)} 筆</div>
            </div>"""
        cards_html += '</div>'
        st.markdown(cards_html, unsafe_allow_html=True)

        # ── Insight ──────────────────────────────────────────────────────────────
        best_p  = max(period_cols, key=lambda p: valid_df[p].dropna().mean())
        best_v  = valid_df[best_p].dropna().mean()
        best_wr = (valid_df[best_p].dropna() > 0).mean() * 100
        first_p = period_cols[0]
        first_v = valid_df[first_p].dropna().mean()
        st.markdown(f"""
        <div class="insight-box">
        💡 <b>數據洞察</b>：{start_year} 年以來，每當 {signal_name} 從高點下跌 {drop_pct}%，
        買入 <b>{ticker_input}</b> 並持有 <b>{best_p}</b>，平均報酬達 <b>{best_v:+.1f}%</b>，勝率 <b>{best_wr:.0f}%</b>。
        即使只持有 {first_p}，平均也有 <b>{first_v:+.1f}%</b>。
        </div>""", unsafe_allow_html=True)

        st.markdown("---")

        # ════════════════════════════════════════════════════════════════════════
        # 圖 1：各持有期 平均報酬 + 勝率 雙柱狀圖
        # ════════════════════════════════════════════════════════════════════════
        st.subheader("🎯 各持有期勝率與平均報酬")
        st.caption("藍柱 = 平均報酬率（左軸）；橘柱 = 勝率（右軸）")

        wr_vals  = [(valid_df[p].dropna() > 0).mean() * 100 for p in period_cols]
        avg_vals = [valid_df[p].dropna().mean() for p in period_cols]

        fig_bars = go.Figure()
        fig_bars.add_trace(go.Bar(
            x=period_cols, y=avg_vals, name="平均報酬率",
            marker_color=["#34d399" if v >= 0 else "#f87171" for v in avg_vals],
            marker_line_width=0,
            text=[f"{v:+.1f}%" for v in avg_vals],
            textposition="outside",
            textfont=dict(color="white", size=11),
            yaxis="y1"
        ))
        fig_bars.add_trace(go.Bar(
            x=period_cols, y=wr_vals, name="勝率",
            marker_color="rgba(251,146,60,0.75)",
            marker_line_width=0,
            text=[f"{v:.0f}%" for v in wr_vals],
            textposition="outside",
            textfont=dict(color="white", size=11),
            yaxis="y2"
        ))
        fig_bars.update_layout(
            template="plotly_dark", paper_bgcolor="#111827", plot_bgcolor="#111827",
            font=dict(family="Noto Sans TC", color="#e5e7eb"),
            barmode="group",
            yaxis=dict(title="平均報酬率 (%)", gridcolor="#1f2937", side="left"),
            yaxis2=dict(title="勝率 (%)", overlaying="y", side="right",
                        range=[0, 130], showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, bgcolor="rgba(0,0,0,0)"),
            height=420, margin=dict(t=50, b=40)
        )
        st.plotly_chart(fig_bars, use_container_width=True)

        # ════════════════════════════════════════════════════════════════════════
        # 圖 2：每次觸發柱狀圖
        # ════════════════════════════════════════════════════════════════════════
        best_bar_p = "1年" if "1年" in period_cols else period_cols[-1]
        st.subheader(f"📅 每次觸發後持有 {best_bar_p} 的報酬")

        chart_df   = valid_df[["買入日期", best_bar_p]].dropna().copy()
        bar_colors = ["#34d399" if v >= 0 else "#f87171" for v in chart_df[best_bar_p]]
        avg_line   = chart_df[best_bar_p].mean()

        fig_bar = go.Figure(go.Bar(
            x=chart_df["買入日期"], y=chart_df[best_bar_p],
            marker_color=bar_colors, marker_line_width=0,
            hovertemplate="買入日：%{x}<br>報酬：%{y:+.1f}%<extra></extra>"
        ))
        fig_bar.add_hline(y=0, line_color="#6b7280", line_width=1)
        fig_bar.add_hline(y=avg_line, line_color="#facc15", line_dash="dash", line_width=1.5,
                          annotation_text=f"平均 {avg_line:+.1f}%",
                          annotation_font_color="#facc15", annotation_position="top left")
        fig_bar.update_layout(
            template="plotly_dark", paper_bgcolor="#111827", plot_bgcolor="#111827",
            font=dict(family="Noto Sans TC", color="#e5e7eb"),
            yaxis=dict(title=f"{best_bar_p}報酬率(%)", gridcolor="#1f2937"),
            xaxis=dict(gridcolor="#1f2937"),
            height=400, margin=dict(t=40, b=60)
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        # ════════════════════════════════════════════════════════════════════════
        # 圖 3：S&P 500 走勢 + 買入訊號
        # ════════════════════════════════════════════════════════════════════════
        st.subheader(f"📉 {signal_name} 走勢與買入訊號點")
        buy_pts = []
        for d in buy_dates:
            future = [x for x in sp500.index if x >= d]
            if future:
                bd = future[0]
                buy_pts.append((bd, float(sp500.loc[bd])))

        fig_sp = go.Figure()
        fig_sp.add_trace(go.Scatter(
            x=sp500.index, y=sp500.values, mode="lines", name=signal_name,
            line=dict(color="#60a5fa", width=1.5),
            fill="tozeroy", fillcolor="rgba(96,165,250,0.05)"
        ))
        if buy_pts:
            bx, by = zip(*buy_pts)
            fig_sp.add_trace(go.Scatter(
                x=list(bx), y=list(by), mode="markers", name="買入訊號 ▲",
                marker=dict(color="#fb923c", size=9, symbol="triangle-up",
                            line=dict(color="white", width=1))
            ))
        fig_sp.update_layout(
            template="plotly_dark", paper_bgcolor="#111827", plot_bgcolor="#111827",
            font=dict(family="Noto Sans TC", color="#e5e7eb"),
            yaxis=dict(title=f"{signal_name} 指數", gridcolor="#1f2937"),
            xaxis=dict(gridcolor="#1f2937"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, bgcolor="rgba(0,0,0,0)"),
            height=380, margin=dict(t=40, b=40)
        )
        st.plotly_chart(fig_sp, use_container_width=True)

        st.markdown("---")

        # ── 統計摘要表 ──────────────────────────────────────────────────────────
        st.subheader("📊 統計摘要")
        summary_rows = []
        for period in period_cols:
            col_data = valid_df[period].dropna()
            if col_data.empty: continue
            summary_rows.append({
                "持有期":   period,
                "樣本數":   len(col_data),
                "平均報酬": f"{col_data.mean():+.1f}%",
                "中位數":   f"{col_data.median():+.1f}%",
                "最佳":     f"{col_data.max():+.1f}%",
                "最差":     f"{col_data.min():+.1f}%",
                "勝率":     f"{(col_data > 0).mean()*100:.0f}%",
                "標準差":   f"{col_data.std():.1f}%",
            })
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

        # ════════════════════════════════════════════════════════════════════════
        # 圖 4：常態分配（selectbox 在這裡，切換不會閃退）
        # ════════════════════════════════════════════════════════════════════════
        st.markdown("---")
        st.subheader("🔔 報酬率常態分配圖")
        st.caption("橘色直方圖 = 實際歷史分佈；藍線 = 理論常態曲線；陰影 = ±1σ / ±2σ 機率區間")

        # selectbox 放在結果區塊內，session_state 保住資料後切換不會跳回首頁
        default_idx = min(3, len(period_cols)-1)
        dist_period = st.selectbox(
            "選擇要查看的持有期",
            options=period_cols,
            index=default_idx,
            key="dist_period"
        )

        fig_dist, mu, sigma, n = draw_normal_dist(valid_df, dist_period, period_cols)
        st.plotly_chart(fig_dist, use_container_width=True)

        p_positive = (valid_df[dist_period].dropna() > 0).mean() * 100
        st.markdown(f"""
        <div class="insight-box">
        <b>📐 {dist_period} 統計解讀（共 {n} 筆）</b><br><br>
        平均報酬 μ = <b>{mu:+.1f}%</b>&nbsp;&nbsp;｜&nbsp;&nbsp;標準差 σ = <b>{sigma:.1f}%</b><br><br>
        🔵 <b>±1σ（約68%機率）</b>：報酬落在 <b>{mu-sigma:+.1f}% ～ {mu+sigma:+.1f}%</b><br>
        🔷 <b>±2σ（約95%機率）</b>：報酬落在 <b>{mu-2*sigma:+.1f}% ～ {mu+2*sigma:+.1f}%</b><br><br>
        ✅ <b>歷史實際正報酬機率（勝率）：{p_positive:.0f}%</b>
        </div>""", unsafe_allow_html=True)

        st.markdown("---")

        # ── 每筆詳細（折疊）────────────────────────────────────────────────────
        with st.expander("📋 查看每筆買入詳細紀錄"):
            display_df = valid_df[["買入日期", "買入價格"] + period_cols].copy()
            styled = (display_df.style
                      .map(color_cell, subset=period_cols)
                      .format({p: fmt_pct for p in period_cols}))
            st.dataframe(styled, use_container_width=True, hide_index=True)

        # ── 下載 ────────────────────────────────────────────────────────────────
        csv = valid_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "⬇️ 下載完整回測資料（CSV）",
            data=csv,
            file_name=f"backtest_{ticker_input}_drop{drop_pct}pct.csv",
            mime="text/csv"
        )

    # ─── 說明頁（尚未回測）──────────────────────────────────────────────────────
    else:
        st.info("👈 請在左側設定條件，點擊「開始回測」查看結果")
        st.markdown("""
    ### 🗺️ 使用說明
    1. **輸入買入標的代號**：SPY、QQQ、AAPL、0050.TW...
    2. **設定觸發標的代號**：預設 `^GSPC`（S&P 500），可換成任何標的
    3. **設定跌幅門檻**：觸發標的從近期高點下跌幾 % 時買入
    3. **高點回看窗口**：建議 90 日（約 4 個月）
    4. **起始年份**：越早資料越多，統計越可靠
    5. **持有期**：選你想觀察的時間
    6. 點 **開始回測** ✅

    ### 📌 常見代號
    | 類型 | 代號 | 說明 |
    |------|------|------|
    | ETF | SPY | 標普500 ETF |
    | ETF | QQQ | 那斯達克100 |
    | ETF | VT | 全球股市 |
    | ETF | GLD | 黃金 |
    | 股票 | AAPL | 蘋果 |
    | 股票 | MSFT | 微軟 |
    | 台股 | 0050.TW | 元大台灣50 |

    > ⚠️ 資料來源：Yahoo Finance（免費）。偶爾被限流，若載入失敗稍等 10 秒再按即可。
    """)
