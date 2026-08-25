# 盤前情報準備台 — Part 1 + Part 2 + Part 3

每個交易日早上自動產生一頁盤前情報，內容涵蓋：

**第一部分**
- 台指期夜盤走勢圖（WTXP&，玩股網）
- 美股四大指數前一夜漲跌幅（道瓊／S&P500／NASDAQ／費半）
- 日股／韓股 08:00 開盤走勢（日經225／KOSPI）

**第二部分**
- 差1次就處置的個股
- 目前處置中、且「剩餘」欄位顯示出關的個股

**第三部分**
- PressPlay 最新一篇盤前文章裡的兩份族群清單（「目前沒找到族群」／「目前發現
  有族群」）
- 把清單裡的每一檔逐一比對 chengwaye.com/daily 當天成交行情，補上收盤、量、
  外資／投信／自營、AI理由等欄位；比對不到的（可能是打錯字或非台股代號）會
  另外列出來，不會悄悄漏掉

跑在 GitHub Actions 上，資料抓取與頁面建置採可降級的排程流程。第一、二部分的
資料來源是公開網頁；第三部分若要取得 PressPlay 族群清單，需要設定帳密 Secrets。
Gemini AI 摘要是選配功能：設定 `GEMINI_API_KEY` 才會啟用，失敗或未設定時會保留
確定性的 fallback，不會阻擋主要頁面建置。

## 部署步驟（你要做的事）

1. 建一個新的 GitHub repository（public 或 private 都可以），把這個資料夾的內容全部推上去。
2. 到 repo 的 **Settings → Pages**，Source 選 "Deploy from a branch"，Branch 選
   `main` 、資料夾選 `/docs`，存檔。
3. 到 **Settings → Actions → General**，確認 "Workflow permissions" 是
   "Read and write permissions"（兩個 workflow 都需要 push 回 repo，預設有時是唯讀）。
4. 到 **Settings → Secrets and variables → Actions**，依需要新增 Repository
   secrets（所有值都由你自行輸入，程式只在 workflow 執行時讀取，不會寫入 repository）：
   - `PRESSPLAY_EMAIL`：PressPlay 登入帳號（email）
   - `PRESSPLAY_PASSWORD`：PressPlay 登入密碼
   - `GEMINI_API_KEY`：選配；啟用 Gemini 新聞/隔夜摘要與資料品質敘述
   - `DISCORD_WEBHOOK_URL`、`SUMMARY_WEBHOOK_URL`、`ERROR_WEBHOOK_URL` 或 `WEBHOOK_URL`：選配通知
   - `LINE_CHANNEL_ACCESS_TOKEN` 與 `LINE_USER_ID`：選配 LINE Messaging API push；兩者需同時設定

   沒設定 PressPlay 或 Gemini secrets 也不會阻斷主要頁面；相關區塊會顯示尚無資料或
   deterministic fallback。此專案不再呼叫已終止的 LINE Notify endpoint。
5. 完成。兩個 workflow 會照排程自動跑；也可以到 Actions 頁籤手動點
   "Run workflow" 立刻測試，不用等排程時間到。
6. 跑過一次 build-premarket-page 之後，頁面網址會是
   `https://<你的帳號>.github.io/<repo名稱>/`。

## 前端現況與資料包架構

目前頁面是由 Jinja 在建置時產生的單檔 server-rendered HTML，樣式與互動 JavaScript
仍內嵌在 `scripts/templates/premarket.html.j2`；建置後另外輸出 `docs/data/*.json`、
`docs/data_meta.json` 與 `docs/sw.js`。頁面不載入 `assets/app.js`，也不存在
`assets/tokens.css` 或 `assets/layout.css`，因此 workflow 不再下載或執行未鎖定的 Terser
bundle。公告區塊直接使用 `financials.json`／`announcements.json` 原生渲染，目前沒有
iframe；Service Worker 對 JSON 採 network-first revalidation。

首屏以三欄 Action Deck 呈現「處置倒數」、「今日出關」與「自選命中」，處置表提供最短
路徑條與觸發價靶心，候選股表提供量能背景長條，財報公告則是可折疊的原生資料表格。
所有外部來源資料都經過 `validate_data.py` 契約檢查，抓取失敗時會在頁面狀態中標示
warning 或 fallback，而不是把空資料假裝成正常資料。

本機可用以下指令驗證：

```bash
python -m pytest -q
python scripts/build_page.py --indices data/latest/indices.json --night-session data/latest/night_session.json --disposal data/latest/disposal.json --pressplay data/latest/pressplay.json --chengwaye-daily data/latest/chengwaye_daily.json --stock-history data/latest/stock_history.json --calendar data/latest/calendar.json --financials data/latest/financials.json --news data/latest/news.json --ai-summary data/latest/ai_summary.json --twse-summary data/latest/twse_summary.json --source-status data/latest/source_status.json --out docs/index.html
```

## 測試規範

新增前端或模板測試時，應先用代表性 fixture render 出完整 HTML，再以
BeautifulSoup/DOM 斷言實際元素、狀態與互動契約；不要只用模板字串比對推論畫面一定正確。
資料處理、通知與 workflow 等非 UI 測試則直接驗證可觀測行為，例如回傳值、退出碼與
mock 呼叫內容。既有的字串契約測試先維持不動，等對應 UI 區塊下次修改時再順手轉成
render 後的 DOM 測試，避免為了整理而進行大規模重構。

## 如何觸發手動 Rebuild（即時更新頁面）

若盤前想即時手動更新數據，不用等 GitHub Actions 排程時間：
1. 進入你的 GitHub Repo 頁面 ➔ 點選頂部 **Actions** 頁籤。
2. 左側點選 **Build premarket page** 工作流程。
3. 右側點擊 **Run workflow** ➔ 選擇 `Branch: main` ➔ 點擊綠色 **Run workflow** 按鈕。
4. 預計 2 分鐘內執行完畢並自動推送到 `main` 分支，GitHub Pages 頁面將自動更新。
5. 在盤前工作台頁面點擊頂部 **「🔄 手動更新資料」** 按鈕即可開啟上述 workflow。

## 兩個 workflow 在做什麼

- **collect-night-session.yml**：平日 15:00–05:00（台北時間）每 30 分鐘跑一次，
  抓一次台指期夜盤即時報價，累加寫進 `data/night_session/<日期>.jsonl`。
- **build-premarket-page.yml**：依排程在台北時間晚間與早上更新資料；抓美股/日韓
  指數、組合當晚累積的夜盤數據、處置股清單、PressPlay 族群清單、chengwaye
  成交資料、金融公告與新聞，驗證契約後組出 `docs/index.html` 並 commit。PR、Push
  與手動執行會先通過完整品質檢查；Scheduled build 則執行 smoke/data-contract 檢查。

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
     瀏覽器指紋，調瀏覽器行為救不图來。

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

5. **第三部分（PressPlay 族群清單）有兩個刻意接受的風險，已經跟你確認過**：

   - **PressPlay 服務條款風險**：第三部分用 Playwright 自動登入 PressPlay 讀
     文章內容，不是官方提供的 API，屬於自動化存取，理論上可能違反其服務條款
     （例如帳號被停權）。這個風險你已經確認接受。
   - **GitHub Actions 機房 IP 可能被擋**：跟上面第 1 點「台指期夜盤」踩過的坑
     類似，PressPlay 的登入頁如果也有 Cloudflare 之類的 bot 防護，GitHub
     Actions 的機房 IP 就有被判定成可疑來源、卡在驗證頁的可能——實際會不會
     發生要等排程真的跑過才知道，目前還沒實測過正式排程環境。

   **設計上已經做了容錯**：PressPlay 登入或抓取失敗（帳密錯誤、ToS 擋下、
   IP 被擋，不管哪一種）都不會讓整頁失敗——`fetch_pressplay_groups.py` 失敗
   時 workflow 自動回退成空 JSON，第三部分改顯示「尚無資料（PressPlay 收集
   流程還沒跑過，或今天沒有盤前文章）」，第一、二部分照常運作、不受影響。

   **想暫停/關閉第三部分**：到 repo 的 **Settings → Secrets and variables →
   Actions**，把 `PRESSPLAY_EMAIL`／`PRESSPLAY_PASSWORD` 這兩個 Secrets 刪掉
   即可——腳本抓不到帳密會報清楚的錯誤，自動回退成空 JSON，第一、二部分不受
   影響。想整頁（含第一、二部分）都停掉，才需要到 Actions →
   build-premarket-page → 右上角「...」→ Disable workflow（跟上面第 1 點
   停用夜盤收集的做法一樣）。

## 本機測試（離線，不連網）

`fixtures/` 目前存有可重播的 disposal、PressPlay 文章與 Chengwaye daily 樣本，
可以離線測試不需登入的抓取腳本：

```bash
pip install -r requirements.txt

python scripts/fetch_indices.py --fixture-dir fixtures
# 目前沒有可重播的 Wantgoo fixture；夜盤來源仍依 README 已知限制處理。
python scripts/fetch_disposal.py --fixture fixtures/chengwaye_disposal.html --today 2026-08-20
python scripts/fetch_pressplay_groups.py --fixture-article fixtures/pressplay_article.txt --fixture-daily fixtures/chengwaye_daily.html
```

第三部分的離線測試不會真的登入 PressPlay——`--fixture-article` 直接餵一篇
文章的純文字內容，跳過瀏覽器登入與抓取那段。想測試真的登入流程，本機另外設
`PRESSPLAY_EMAIL`／`PRESSPLAY_PASSWORD` 環境變數、拿掉這兩個 `--fixture-*`
參數執行即可，但沒事不需要這樣做——正式排程會自己跑。

## 還沒做的部分

第四部分（大盤走勢，含統一期貨的圖片型盤前晨報）還沒討論資料來源，那塊是
圖片型報告，到時候會用到 Gemini 的圖片辨識能力。
