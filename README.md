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

2. **處置股（chengwaye.com）的解析器沒有對照過真實網頁原始碼**：設計時瀏覽器
   工具擋下了大量擷取原始 HTML 的動作（安全機制判斷像是在打包頁面資料），所以
   `fetch_disposal.py` 是照著瀏覽時看到的文字內容和表格欄位手動重建的 HTML 結構
   去寫解析邏輯，邏輯本身刻意不依賴 CSS class（用標題文字＋表格順序去抓，比較
   耐改版），但**第一次正式跑起來後，麻煩對照一下 `docs/index.html` 跟
   chengwaye.com 本頁的內容是否吻合**，如果解析跑偏了，把實際內容回饋給
   Claude，一次就能對著真實原始碼修正。

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
