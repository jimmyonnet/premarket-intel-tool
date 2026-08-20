# 盤前情報準備台 — Part 1 + Part 2

每個交易日早上自動產生一頁盤前情報，內容涵蓋（目前只做了你確認的前兩部分）：

**第一部分**
- 台指期夜盤走勢圖（WTXP&，玩股網）
- 美股四大指數前一夜漲跌幅（道瓊／S&P500／NASDAQ／費半）
- 日股／韓股 08:00 開盤走勢（日經225／KOSPI）

**第二部分**
- 差1次就處置的個股
- 目前處置中的個股（含出關日）

跑在 GitHub Actions 上，全部免費，不需要 DeepSeek／Groq／Gemini 的 API key ——
這兩部分的資料來源都是純文字網頁，不需要 OCR 或摘要，用不到那些 key。等做到
第三、四部分（跟漲籌碼、統一期貨的圖片型報告）才會用到。

## 部署步驟（你要做的事）

1. 建一個新的 GitHub repository（public 或 private 都可以），把這個資料夾的內容全部推上去。
2. 到 repo 的 **Settings → Pages**，Source 選 "Deploy from a branch"，Branch 選
   `main` 、資料夾選 `/docs`，存檔。
3. 到 **Settings → Actions → General**，確認 "Workflow permissions" 是
   "Read and write permissions"（兩個 workflow 都需要 push 回 repo，預設有時是唯讀）。
4. 完成。兩個 workflow 會照排程自動跑；也可以到 Actions 頁籤手動點
   "Run workflow" 立刻測試，不用等排程時間到。
5. 跑過一次 build-premarket-page 之後，頁面網址會是
   `https://<你的帳號>.github.io/<repo名稱>/`。

不需要設定任何 Secrets。

## 兩個 workflow 在做什麼

- **collect-night-session.yml**：平日 15:00–05:00（台北時間）每 30 分鐘跑一次，
  抓一次台指期夜盤即時報價，累加寫進 `data/night_session/<日期>.jsonl`。
- **build-premarket-page.yml**：平日早上 07:35（台北時間）跑一次，抓美股/日韓
  指數、組合當晚累積的夜盤數據、抓處置股清單，組出 `docs/index.html` 並 commit。

## 已知限制（老實跟你說）

1. **台指期夜盤走勢圖不是玩股網原始的 K 線資料**：玩股網頁面本身的分鐘K線是
   透過內部 API 動態載入的，直接呼叫那個 API 會回 400（可能需要額外的參數或
   session 狀態，設計時沒有硬拆解它，怕造成網站負擔）。所以改成這個工具自己
   每 30 分鐘記錄一次即時報價，早上再把整晚記錄串成一條線。解析度是 30 分鐘一
   個點，不是逐筆／逐分鐘。如果之後想要更細的線，需要重新研究那個 API 或改用
   別的資料源。

2. ~~處置股解析器沒對照過真實原始碼~~ **已對照真實網站修正**（2026-08-20）：
   部署後直接拿 chengwaye.com 的即時內容測了 5 輪，抓到並修好兩個問題——區塊
   標題（差1次就處置／差2次處置／目前處置中）在真實頁面上是純 `<div>` 不是
   `<h1~h3>`，原本完全抓不到表格；表格列裡混了「▶ 展開明細」的隱藏列，導致
   資料錯位。兩者都已修正並用當天真實資料驗證過（`docs/index.html` 上的 1 檔
   差1次就處置、14 檔目前處置中都對得上網站）。順帶也修了 `fetch_indices.py`：
   美股四大指數的漲跌%在真實頁面是分行顯示，原本的 regex 要求同一行，導致
   道瓊/S&P500/NASDAQ/費半全部抓不到，現在也對得上即時報價了。

   **後續發現並修正（2026-08-20，使用者回報）**：頁面曾把費城半導體指數顯示
   成上漲 +2.12%，但當時實際是下跌 -2.12%。追查後發現 Yahoo 頁面上漲跌數字
   本身「不帶正負號」（純數字文字，例如「254.24」），漲跌方向完全只靠 CSS
   class（`c-trend-up` / `c-trend-down`，另外還有一個純圖示的小三角形，DOM
   文字裡也沒有）表示，之前的 regex 只抓數字，永遠是正值。修正方式：新增
   `find_card()` / `trend_sign()`，只在即時抓取（非離線 fixture）模式下，
   從抓到的原始 HTML 找出該指數所在的卡片／列，讀出 `c-trend-down` /
   `c-trend-up` class 來決定正負號，抓到後即時驗證（費半正確轉負、其他 5
   個指數維持正確不受影響）。離線 fixture 測試因為 fixture 是純文字、沒有
   HTML 結構可以查 class，這個訊號沒辦法用——這是目前唯一一處依賴 CSS class
   名稱的地方，也是刻意接受的例外（其餘解析都還是用中文標籤定位，理由同上）。

3. **日期核對失敗時不會讓整頁失敗**：`fetch_disposal.py` 原本設計是「日期核對
   不過就中止」，但正式排程改成 `--skip-date-check`，讓頁面照樣產生、只是在頁
   面最上面顯示紅色警告條——這樣你每天早上都有頁面可看，只是遇到異常會很明顯
   地被標出來，而不是那天完全沒有頁面。如果你比較想要「核對不過就整個不產生」
   的行為，把 `build-premarket-page.yml` 裡那行的 `--skip-date-check` 拿掉即可。

4. **沒有處理台灣股市的國定假日／颱風假**：排程用「平日」（週一到週五）判斷，
   遇到假日照樣會跑，只是抓到的資料沒意義（例如處置股頁面日期核對會失敗、觸發
   上面第 3 點的警告條），不會出錯，但也不會自動跳過。

## 本機測試（離線，不連網）

`fixtures/` 資料夾存了每個來源的樣本內容，可以離線測試三支抓取腳本：

```bash
pip install -r requirements.txt

python scripts/fetch_indices.py --fixture-dir fixtures
python scripts/tx_night_session.py collect --fixture fixtures/wantgoo_wtxp.txt --date 2026-08-21 --data-dir /tmp/night_test
python scripts/fetch_disposal.py --fixture fixtures/chengwaye_disposal.html --today 2026-08-20
```

## 還沒做的部分

第三部分（跟漲籌碼）跟第四部分（大盤走勢，含統一期貨的圖片型盤前晨報）還沒
討論資料來源，統一期貨那塊是圖片型報告，到時候會用到 Gemini 的圖片辨識能力。
