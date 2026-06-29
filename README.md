# 集保籌碼瀏覽器 (TDCC Chip Viewer)

輸入台股代號,即時產生視覺化的「集保戶股權分散」分析。零安裝相依(只用 Python 標準庫)。

## 功能
- 逐級 z-score 熱力圖(占比/人數,可疊股價;點任一格切換週與級距)
- 各級距占集保比例(乾淨版,可切週、可排除 >1M)
- 焦點級距 vs 股價(對數)
- 我的最愛:加入時點報酬追蹤(記加入日與收盤價,即時算漲跌;移除凍結為歷史)
- 自動偵測集保新週並更新

## 需求
- Python 3.8+(不需 pip install);需網路。

## 本機執行
```bash
python3 chips_server.py        # 或 Windows 雙擊 籌碼瀏覽器.bat
```
啟動後開 http://127.0.0.1:8830 。本機模式不需密碼。

## 資料來源
- 籌碼:台灣集中保管結算所 qryStock(約一年週資料)
- 股價:FinMind 開放 API

## 雲端部署(24 小時遠端可開)
程式已支援雲端:會讀環境變數 `PORT` 綁 0.0.0.0;設 `APP_PASSWORD` 後啟用密碼保護(HTTP Basic,平台提供 HTTPS 故傳輸加密)。

### Render(最簡單,有免費方案)
1. 先把本資料夾推到 GitHub(見下)。
2. Render → New → Web Service → 連你的 repo。
3. Runtime 選 Python;Start Command:`python chips_server.py`。
4. Environment 加一個變數 `APP_PASSWORD` = 你的密碼(**務必設**,否則任何人都能看你的最愛)。
5. Deploy。完成後用 Render 給的 https 網址打開,瀏覽器會跳帳密框,帳號隨意、密碼填上面那組。

也可用 `render.yaml`(已附)一鍵 blueprint;或用附的 `Dockerfile` 部署到 Railway / Fly.io / 任何支援 Docker 的平台。

### ⚠️ 雲端的真實限制(務必先知道)
1. **機房 IP 可能被集保擋**:從雲端抓 qryStock 不一定成功;若查詢一直失敗或查無資料,多半是被擋,這時請改用「自己電腦 + 內網穿透(Tailscale/Cloudflare Tunnel)」。
2. **FinMind 有流量限制**:匿名額度有限,股價偶爾取不到屬正常。
3. **資料持久性**:免費方案多為臨時磁碟,重新部署/重啟後 `favorites.json` 與快取會歸零。要保留請掛持久磁碟並設 `DATA_DIR` 指向它。
4. **務必設 `APP_PASSWORD`**:否則你的「我的最愛」會公開可見。
5. 第一次查某檔需逐週抓約 40 秒,屬正常。

## 上傳到 GitHub
```bash
git init && git add . && git commit -m "TDCC chip viewer"
git branch -M main
git remote add origin https://github.com/<你的帳號>/<repo>.git
git push -u origin main
```
`.gitignore` 已排除個資(favorites.json)、快取與產生的 HTML。

## 免責聲明
本工具僅供研究與視覺化,非投資建議。實測顯示單一個股籌碼分布對未來報酬無穩定預測力;請當「找線索」用,而非進出場訊號。
