# 盤前情報準備台 — Part 1 + Part 2

每個交易日早上自動產生一頁盤前情報，內容涵蓋（目前只做了你確認的前兩部分）：

**第一部分**
- 台指期夜盤走勢圖（WTXP&，玩股網）
- 美股四大指數前一夜漲跌幅（道瓊／S&P500／NASDAQ／費半）
- 日股／韓股 08:00 開盤走勢（日經225／KOSPI）

**第二部分**
- 差1次就處置的個股
- 目前處置中、且「剩餘」欄位顯示出關的個股

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

1. **台指期夜盤走勢圖目前完全抓不到資料 —— 還沒解決，需要你決定下一步**：
   玩股網頁面本身的分鐘K線是透過內部 API 動態載入的，直接呼叫那個 API 會回
   400，設計時已經放棄改用「這個工具自己每 30 分鐘記錄一次即時報價」的做法
   （抓 `https://www.wantgoo.com/futures/wtxp&` 這頁的文字快照）。

   **問題（2026-08-20 發現）**：正式排程第一次跑就失敗——`requests.get()`
   對這個網址回 403 Forbidden，即使同一個網址在真的瀏覽器裡完全正常（沒有
   驗證碼、沒有任何攔截畫面）。已經在 GitHub Actions 上實測兩種修法，都
   還是 403，沒有猜測、都是真的跑過確認：
   - 第一次：把 `requests` 的 headers 從只有 User-Agent 加到完整瀏覽器等級
     （Accept、Accept-Language、Referer、Sec-Fetch-* 等）——still 403。
   - 第二次：改用 `requests.Session()`，先 GET 首頁 `wantgoo.com/` 熱身拿
     cookie，再 GET 目標頁——首頁本身 200 成功，但目標頁 `/futures/wtxp&`
     依然 403。

   首頁能過、報價頁不能過，指向這不是整個網域被擋 IP，而是報價頁這類頁面
   有額外一層防護（很可能是 TLS/瀏覽器指紋辨識，例如 Cloudflare 之類的
   bot 防護，會在 TLS 握手層級分辨出 `requests`／`urllib3` 不是真瀏覽器，
   這一層調 Python 的 headers 沒用，因為問題不在 headers 內容）。

   **後續進度（2026-08-20，你選了「改用無頭瀏覽器」之後，已實測 3 輪）**：

   - 第一輪：改用 Playwright 真的無頭 Chromium 抓——403 問題確認解決（實測
     GitHub Actions 成功跑完），但拿到的資料整組欄位全是 null。查出原因：
     這個報價頁其實是「前端渲染」，開盤/最高/最低等數字不在一開始的 HTML
     裡（伺服器回來時是空的 `<span c-model=open></span>`），是頁面載入後
     才由前端 JS 補上去的，而原本的寫法是「固定等 1.5 秒」，等不到補上就
     把頁面內容抓走了，才會全是 null——job 本身顯示成功，掩蓋了這個問題，
     這也是這次踩到的教訓：job 綠燈不代表資料是對的，要實際打開存的資料
     檔案看內容才算數。
   - 第二輪：改成「等到真的抓到數值才繼續」而不是固定等 1.5 秒——這次
     GitHub Actions 上直接等到逾時失敗（`Timeout 20000ms exceeded`，抓不
     到值），比上一輪的「安靜地寫入垃圾資料」明確，但還是沒抓到資料。
   - 第三輪（查到目前最可能的真正原因）：在逾時當下多印出頁面實際狀態
     （網頁標題、內容長度等）才發現——GitHub Actions 這台機器拿到的頁面
     標題是「請稍候...」、內容只有 5000 多字，這是典型的機房 IP 被
     Cloudflare 這類服務攔下來的驗證頁（不是我們自己瀏覽器測試時看到的
     正常報價頁），也就是說問題不只是「用不用無頭瀏覽器」，是 GitHub
     Actions 這個機房 IP 本身就被判定為可疑來源，會被擋在一個真人瀏覽器
     不會卡住的驗證關卡前面。有先試過「隱藏無頭瀏覽器的常見破綻
     （navigator.webdriver 等自動化標記）＋拉長等待時間」，這輪也已經
     實測過還是被擋，代表破綻藏得不夠，或者根本上這一關是看 IP 名聲而非
     瀏覽器指紋，調瀏覽器行為救不回來。

   **目前狀態（2026-08-20，你已決定）：先擱置這個功能**。`collect-
   night-session.yml` 已經手動停用（GitHub Actions 頁面上會顯示
   disabled，排程跟手動 Run workflow 都不會再執行），程式碼跟這份調查記
   錄都保留、不影響其他功能——處置股清單、美股四大指數、日股／韓股開盤，
   這些照常運作。Part 1 的台指期夜盤走勢圖會持續顯示「尚無夜盤資料點」。

   之後想重啟這個功能，可以考慮的方向：改用更進階的反偵測技巧（不保證
   有效，如果是純 IP 名聲判斷就没用）、接一個付費的 residential proxy
   服務讓抓取改走非機房 IP（比較可能繞過，但要花錢）、或放棄
   wantgoo.com 改找別的夜盤報價來源（要重新調查）。要重新啟用排程，到
   repo 的 Actions → Collect TX night-session snapshot → 右上角「...」
   → Enable workflow 即可，程式碼不用改。

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

   **顯示範圍調整（2026-08-20，使用者要求）**：「目前處置中」原本列出所有
   處置中的股票（今天 13 檔），現在改成只顯示「剩餘」欄位是「出關」的那幾
   檔（今天是 3026 禾伸堂、4979 華星光、4991 環宇-KY、6213 聯茂，4 檔）。
   `disposal.json` 本身仍然保留全部 13 檔原始資料（`fetch_disposal.py` 沒
   改），只有 `premarket.html.j2` 這個模板在畫「目前處置中」表格時，用
   Jinja 的 `selectattr('trading_days_left', 'equalto', '出關')` 先篩過再
   顯示，標題旁的檔數也跟著改成篩選後的數字。已用當天真實 13 檔資料（含
   4 檔出關、9 檔非出關）驗證篩選結果正確、沒有誤篩或漏篩。

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
