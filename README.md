[README.md](https://github.com/user-attachments/files/26467016/README.md)
# 📉 標普500跌幅後買入回測工具

## 功能介紹

輸入任何美股股票、ETF 代號，設定 S&P 500 從近期高點跌幾 % 後買入，
自動回測歷史上每次觸發條件後，持有 1個月、3個月、6個月、1年、2年、3年、5年 的報酬表現。

---

## 部署步驟（完全不需要懂程式）

### 第一步：把程式碼放到 GitHub

1. 登入你的 [GitHub](https://github.com)
2. 點右上角 `+` → `New repository`
3. Repository name 填：`sp500-backtest`
4. 選 `Public`，點 `Create repository`
5. 點 `Add file` → `Upload files`
6. 把這兩個檔案上傳：
   - `app.py`
   - `requirements.txt`
7. 點 `Commit changes`

### 第二步：部署到 Streamlit Cloud

1. 前往 [share.streamlit.io](https://share.streamlit.io)
2. 用 GitHub 帳號登入
3. 點 `New app`
4. 選擇你的 repository：`sp500-backtest`
5. Main file path 填：`app.py`
6. 點 `Deploy!`（等 1~2 分鐘）
7. 完成！你會得到一個公開網址，例如：
   `https://yourname-sp500-backtest-app-xxxx.streamlit.app`

---

## 使用說明

| 設定項目 | 說明 |
|----------|------|
| 買入標的代號 | 輸入美股代號，如 SPY、QQQ、AAPL；台股加 .TW，如 0050.TW |
| 跌幅門檻 | S&P 500 從近期高點下跌幾 % 後觸發買入 |
| 高點回看窗口 | 計算「近期高點」時回看幾個交易日（建議 90 天） |
| 回測起始年份 | 資料從哪一年開始（越早訊號越多） |
| 持有期 | 買入後持有多久觀察績效 |

---

## 常見代號參考

| 類型 | 代號 | 說明 |
|------|------|------|
| ETF | SPY | 標普500 ETF |
| ETF | QQQ | 那斯達克100 ETF |
| ETF | VT | 全球股市 ETF |
| ETF | GLD | 黃金 ETF |
| 股票 | AAPL | 蘋果 |
| 股票 | MSFT | 微軟 |
| 台股ETF | 0050.TW | 元大台灣50 |

---

## 注意事項

- 資料來源為 Yahoo Finance，台灣基金代號可能不支援
- 回測結果為歷史績效，不代表未來表現
- 觸發訊號較少時（如設定跌 40%），統計意義有限
