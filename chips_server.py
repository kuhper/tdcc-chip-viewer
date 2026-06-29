#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""集保籌碼瀏覽器(本機網頁版)。輸入代號即時產圖;已查過的記在 chips_cache/;
會自動偵測集保新週並更新;支援「我的最愛」加入時點報酬追蹤。零相依(標準庫)。"""
import sys, re, time, json, os, threading, webbrowser
import urllib.request, urllib.parse, http.cookiejar, http.server
from datetime import datetime, timedelta

import base64
OUTDIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", OUTDIR)
CACHE = os.path.join(DATA_DIR, "chips_cache")
os.makedirs(CACHE, exist_ok=True)
FAVFILE = os.path.join(DATA_DIR, "favorites.json")
AUTH = os.environ.get("APP_PASSWORD", "")
BASE = "https://www.tdcc.com.tw/portal/zh/smWeb/qryStock"
LBL = ["1-999","1,000-5,000","5,001-10,000","10,001-15,000","15,001-20,000",
       "20,001-30,000","30,001-40,000","40,001-50,000","50,001-100,000",
       "100,001-200,000","200,001-400,000","400,001-600,000","600,001-800,000",
       "800,001-1,000,000","1,000,001以上"]

def make_opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent","Mozilla/5.0"),("Referer",BASE),
                     ("Content-Type","application/x-www-form-urlencoded")]
    return op

def form_fields(h):
    f = lambda n:(re.search(r'name="%s"[^>]*value="([^"]*)"'%n,h) or [None,None])[1]
    return f("SYNCHRONIZER_TOKEN"), f("SYNCHRONIZER_URI"), f("method"), f("firDate")

def parse_rows(h):
    rows=[]
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>',h,re.S):
        cells=[re.sub(r'<[^>]+>','',c).replace('&nbsp;','').strip()
               for c in re.findall(r'<td[^>]*>(.*?)</td>',tr,re.S)]
        if len(cells)>=5 and re.match(r'^\d+$',cells[0]):
            n=int(cells[0])
            if 1<=n<=15:
                rows.append([n,int(cells[2].replace(',','')),
                             int(cells[3].replace(',','')),float(cells[4].replace(',',''))])
    return rows if len(rows)==15 else None

def stock_name(h):
    m=re.search(r'證券名稱[：:]\s*([^\s<：:]+)',h)
    return m.group(1) if m else ""

def finmind(stock, start, end):
    url=("https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice"
         "&data_id=%s&start_date=%s&end_date=%s"%(stock,start,end))
    return json.load(urllib.request.urlopen(url,timeout=60)).get("data",[])

def fetch_price_aligned(stock,dates):
    try:
        s=dates[0][:4]+"-"+dates[0][4:6]+"-"+dates[0][6:8]
        e=dates[-1][:4]+"-"+dates[-1][4:6]+"-"+dates[-1][6:8]
        pdays=[(d["date"].replace("-",""),d["close"]) for d in finmind(stock,s,e)]
        if not pdays: return None
        out=[]
        for d in dates:
            pick=None
            for k,c in pdays:
                if k<=d: pick=c
                else: break
            out.append(pick)
        return out if any(x is not None for x in out) else None
    except Exception:
        return None

_LC={}
def latest_close(stock):
    e=_LC.get(stock)
    if e and time.time()-e[2]<600: return e[0],e[1]
    try:
        end=datetime.now().strftime("%Y-%m-%d")
        start=(datetime.now()-timedelta(days=21)).strftime("%Y-%m-%d")
        data=finmind(stock,start,end)
        if data:
            last=data[-1]; _LC[stock]=(last["close"],last["date"],time.time())
            return last["close"],last["date"]
    except Exception: pass
    return None,None

def scrape(stock):
    op=make_opener()
    h=op.open(BASE,timeout=30).read().decode("utf-8","replace")
    st=list(form_fields(h))
    dates=re.findall(r'<option[^>]*value="(\d{8})"',h)
    if not dates: raise RuntimeError("無法取得日期清單")
    out,name={},""
    for d in sorted(dates):
        body=urllib.parse.urlencode({"SYNCHRONIZER_TOKEN":st[0],"SYNCHRONIZER_URI":st[1],
            "method":st[2],"firDate":st[3],"scaDate":d,"sqlMethod":"StockNo",
            "stockNo":stock,"stockName":""}).encode()
        try:
            r=op.open(urllib.request.Request(BASE,data=body),timeout=30).read().decode("utf-8","replace")
        except Exception:
            continue
        nt=form_fields(r)
        if nt[0]: st=list(nt)
        rows=parse_rows(r)
        if rows:
            out[d]=rows
            if not name: name=stock_name(r)
        time.sleep(0.08)
    if not out: raise RuntimeError("查無資料(代號可能有誤)")
    dts=sorted(out)
    labels=[d[:4]+"/"+d[4:6]+"/"+d[6:8] for d in dts]
    pct=[[out[d][t][3] for t in range(15)] for d in dts]
    ppl=[[out[d][t][1] for t in range(15)] for d in dts]
    px=fetch_price_aligned(stock,dts)
    return {"stock":stock,"name":name,"labels":labels,"LBL":LBL,"PCT":pct,"PPL":ppl,"PX":px}

_NW={"v":None,"t":0.0}
def newest_week():
    if time.time()-_NW["t"]<1800 and _NW["v"]: return _NW["v"]
    try:
        op=make_opener()
        h=op.open(BASE,timeout=30).read().decode("utf-8","replace")
        ds=re.findall(r'value="(\d{8})"',h)
        _NW["v"]=max(ds) if ds else None; _NW["t"]=time.time()
    except Exception: pass
    return _NW["v"]

def cached_name(stock):
    fp=os.path.join(CACHE,"%s.json"%stock)
    if os.path.exists(fp):
        try: return json.load(open(fp,encoding="utf-8")).get("name","")
        except Exception: pass
    return ""

def get_payload(stock, force):
    fp=os.path.join(CACHE,"%s.json"%stock)
    cached=None
    if os.path.exists(fp):
        try: cached=json.load(open(fp,encoding="utf-8"))
        except Exception: cached=None
    if cached is not None and not force:
        nw=newest_week()
        clast=cached["labels"][-1].replace("/","")
        if (nw is None) or (clast>=nw):
            cached["_status"]="快取（已是最新 "+cached["labels"][-1]+"）"
            return cached
        print("  發現新週 %s，自動更新 %s ..."%(nw,stock))
    else:
        print("  抓取 %s ..."%stock)
    p=scrape(stock)
    json.dump(p,open(fp,"w",encoding="utf-8"),ensure_ascii=False)
    p["_status"]="已更新到 "+p["labels"][-1]
    return p

def list_saved():
    arr=[]
    for fn in os.listdir(CACHE):
        if fn.endswith(".json"):
            try:
                p=json.load(open(os.path.join(CACHE,fn),encoding="utf-8"))
                arr.append({"stock":p["stock"],"name":p.get("name",""),"last":p["labels"][-1]})
            except Exception: pass
    arr.sort(key=lambda o:o["stock"])
    return {"newest": newest_week(), "items": arr}

# ---- 我的最愛 ----
def load_fav():
    try: f=json.load(open(FAVFILE,encoding="utf-8"))
    except Exception: f={}
    f.setdefault("active",{}); f.setdefault("closed",[]); return f
def save_fav(f): json.dump(f,open(FAVFILE,"w",encoding="utf-8"),ensure_ascii=False)
def fav_add(stock):
    f=load_fav()
    if stock in f["active"]: return
    px,dt=latest_close(stock)
    f["active"][stock]={"stock":stock,"name":cached_name(stock),
        "add_date":datetime.now().strftime("%Y-%m-%d %H:%M"),"add_price":px,"add_close_date":dt}
    save_fav(f)
def fav_remove(stock):
    f=load_fav()
    a=f["active"].pop(stock,None)
    if a:
        px,dt=latest_close(stock)
        ret=round((px/a["add_price"]-1)*100,2) if (a.get("add_price") and px) else None
        a.update({"remove_date":datetime.now().strftime("%Y-%m-%d %H:%M"),
                  "remove_price":px,"remove_close_date":dt,"ret":ret})
        f["closed"].insert(0,a); save_fav(f)
def fav_view():
    f=load_fav(); act=[]
    for s,a in f["active"].items():
        px,dt=latest_close(s)
        ret=round((px/a["add_price"]-1)*100,2) if (a.get("add_price") and px) else None
        b=dict(a); b["cur_price"]=px; b["cur_date"]=dt; b["ret"]=ret; act.append(b)
    act.sort(key=lambda o:o["stock"])
    return {"active":act,"closed":f["closed"]}

class H(http.server.BaseHTTPRequestHandler):
    def _send(self,code,ctype,body):
        self.send_response(code); self.send_header("Content-Type",ctype)
        self.send_header("Content-Length",str(len(body))); self.end_headers()
        self.wfile.write(body)
    def _json(self,o): self._send(200,"application/json; charset=utf-8",json.dumps(o,ensure_ascii=False).encode("utf-8"))
    def check_auth(self):
        if not AUTH: return True
        hdr=self.headers.get("Authorization","")
        if hdr.startswith("Basic "):
            try:
                dec=base64.b64decode(hdr[6:]).decode("utf-8","replace")
                pw=dec.split(":",1)[1] if ":" in dec else dec
                if pw==AUTH: return True
            except Exception: pass
        self.send_response(401); self.send_header("WWW-Authenticate",'Basic realm="chips"')
        self.send_header("Content-Length","0"); self.end_headers(); return False
    def do_GET(self):
        if not self.check_auth(): return
        u=urllib.parse.urlparse(self.path); q=urllib.parse.parse_qs(u.query)
        sk=(q.get("stock",[""])[0]).strip()
        if u.path in ("/","/index.html"):
            self._send(200,"text/html; charset=utf-8",APP_HTML.encode("utf-8")); return
        if u.path=="/api/saved": self._json(list_saved()); return
        if u.path=="/api/fav": self._json(fav_view()); return
        if u.path=="/api/fav/add":
            if re.match(r'^\w{3,6}$',sk): fav_add(sk)
            self._json(fav_view()); return
        if u.path=="/api/fav/remove":
            fav_remove(sk); self._json(fav_view()); return
        if u.path=="/api/chips":
            if not re.match(r'^\w{3,6}$',sk): self._json({"error":"代號格式錯誤"}); return
            try: self._json(get_payload(sk,"force" in q))
            except Exception as e: self._json({"error":str(e)})
            return
        self._send(404,"text/plain; charset=utf-8","not found".encode())
    def log_message(self,*a): pass

APP_HTML = r"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>集保籌碼瀏覽器</title>
<style>
:root{--fg:#1c1c1c;--mut:#6b6b6b;--line:#e3e3e3;--card:#fff;--bg:#f6f6f4;--accent:#0F6E56}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:-apple-system,"Segoe UI","Noto Sans TC",Arial,sans-serif;line-height:1.6}
.wrap{max-width:1080px;margin:0 auto;padding:22px 18px 60px}
h1{font-size:22px;font-weight:600;margin:0 0 2px}
h2{font-size:17px;font-weight:600;margin:28px 0 8px}
.sub{color:var(--mut);font-size:13px;margin-bottom:6px}
#meta{font-size:18px;font-weight:600;color:#fff;background:var(--accent);display:inline-block;padding:4px 14px;border-radius:8px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-top:10px}
input,select,button{font:inherit;padding:6px 12px;border:1px solid #c9c9c9;border-radius:8px;background:#fff;cursor:pointer}
input{cursor:text}
button:hover{background:#f0f0ee}
button.on{background:#e7f1ee;border-color:var(--accent);font-weight:600}
button:disabled{opacity:.5;cursor:default}
.starbtn{border-color:#caa53a;background:#fdf7e6}
label{font-size:13px;color:var(--mut)}
.ctl{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.barrow{display:grid;grid-template-columns:130px 1fr 56px;align-items:center;gap:8px;margin:3px 0;font-size:12px}
.track{background:#f0f0ee;border-radius:4px;height:18px;overflow:hidden}
.bar{height:100%;background:var(--accent);border-radius:4px}
.bar.big{background:#0a4a3a}
.val{text-align:right;font-variant-numeric:tabular-nums;color:#333}
.tlbl{text-align:right;color:#555;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hmwrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
.legend{display:flex;gap:8px;align-items:center;font-size:12px;color:var(--mut);margin:8px 0}
.sw{display:inline-block;width:44px;height:12px;border-radius:2px}
.kv{display:flex;gap:18px;flex-wrap:wrap;font-size:13px;color:#333;margin-top:8px}
.kv b{color:var(--accent)}
#saved button{padding:4px 10px;margin:0 6px 6px 0;font-size:13px}
.favscroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table.fav{border-collapse:collapse;min-width:520px;font-size:13px;margin-top:6px}
table.fav th,table.fav td{border-bottom:1px solid #eee;padding:5px 8px;text-align:right;white-space:nowrap}
table.fav th:first-child,table.fav td:first-child{text-align:left}
.up{color:#c0392b;font-weight:600}.down{color:#0F6E56;font-weight:600}
a.favlink{color:var(--accent);text-decoration:none}
details{margin-top:8px}
@media(max-width:600px){
  .wrap{padding:12px 10px 50px}
  h1{font-size:18px}
  h2{font-size:15px;margin:20px 0 6px}
  .card{padding:10px 12px}
  .barrow{grid-template-columns:88px 1fr 46px;font-size:11px;gap:5px}
  #meta{font-size:14px;padding:3px 10px}
  .ctl{gap:7px}
  input,select,button{padding:7px 10px;font-size:14px}
  #saved button{font-size:12px}
  .sub{font-size:12px}
  .kv{font-size:12px;gap:10px}
  label{font-size:12px}
}
</style></head><body><div class="wrap">
<h1>集保籌碼瀏覽器</h1>
<div class="sub">輸入代號即時產生:z-score 熱力圖 + 各級距占比 + 焦點疊股價。點熱力圖任一格,下方兩張圖會跳到該週、該級距。</div>
<div class="card">
  <div class="ctl">
    <input id="code" placeholder="代號 例 6291" style="width:140px">
    <button id="go">查詢</button>
    <label><input type="checkbox" id="fc"> 強制重新抓取</label>
    <span id="status" style="margin-left:4px;font-size:13px;color:#555"></span>
  </div>
  <div><span style="font-size:13px;color:#6b6b6b">已查過:</span> <span id="saved"></span> <button id="refall" style="display:none"></button></div>
</div>

<div class="card">
  <div style="font-weight:600">★ 我的最愛 — 加入時點報酬追蹤</div>
  <div id="favbox"><span style="color:#999;font-size:13px">尚無,查一檔後按「加入最愛」</span></div>
  <details><summary style="font-size:13px;color:#6b6b6b;cursor:pointer">歷史紀錄(已移除的最愛)</summary><div id="closedbox"></div></details>
</div>

<div id="app" style="display:none">
<div style="display:flex;align-items:center;gap:12px;margin-top:16px;flex-wrap:wrap">
  <span id="meta"></span><button id="star" class="starbtn" style="display:none"></button>
</div>
<div class="kv" id="kv"></div>

<h2>① 逐級 z-score 熱力圖</h2>
<div class="sub">每列以自身歷史標準化:橫向色帶=真實遷移,零星斑點=雜訊。<b>點任一格</b>:②分布圖跳到該週、③焦點圖跳到該級距(綠框=所選格,綠線=所選列,橘框=所選週)。</div>
<div class="card">
  <div class="ctl">
    <button id="mp" class="on">占比% z-score</button>
    <button id="mn">人數 z-score</button>
    <label id="pxlbl" style="margin-left:6px"><input type="checkbox" id="pxck"> 疊加股價(對數)</label>
    <div class="legend" style="margin-left:auto">
      <span class="sw" style="background:#185FA5"></span>低 <span class="sw" style="background:#e9e9e9"></span>平 <span class="sw" style="background:#D85A30"></span>高
    </div>
  </div>
  <div class="hmwrap"><div id="pxstrip"></div><div id="hm"></div></div>
</div>

<h2>② 各級距占集保比例(乾淨版)</h2>
<div class="card">
  <div class="ctl"><label>資料日期</label><select id="wk"></select>
  <label style="margin-left:8px"><input type="checkbox" id="ex"> 排除 1,000,001以上(看清小級距)</label></div>
  <div id="bars"></div>
</div>

<h2>③ 焦點級距 vs 股價</h2>
<div class="sub">綠線=所選級距 z-score(隨①占比/人數切換);灰線=股價(對數)。看綠線轉折是否領先灰線。</div>
<div class="card"><div class="hmwrap"><div id="focus"></div></div></div>
</div>
</div>
<script>
let P=null,CURM='pct',SELT=10,SELW=0,W=0,CW=11,X0=120,FAVSET=new Set();
function calcDims(){const cw=el('hmwrap_inner')||el('hm');const mob=window.innerWidth<600;X0=mob?82:120;const avail=(cw?cw.clientWidth:window.innerWidth)-(mob?22:32);CW=Math.max(5,Math.min(13,Math.floor((avail-X0)/Math.max(W,1))));}

const el=id=>document.getElementById(id);
async function loadStock(code,force){
  code=(code||'').trim(); if(!code) return;
  el('status').textContent='抓取 '+code+' 中…(已存過的很快;新股約 40 秒)';
  el('go').disabled=true;
  try{
    const r=await fetch('/api/chips?stock='+encodeURIComponent(code)+(force?'&force=1':''));
    const j=await r.json();
    if(j.error){el('status').textContent='✗ '+code+'：'+j.error;el('go').disabled=false;return;}
    P=j;CURM='pct';
    el('status').textContent='✓ '+P.stock+' '+(P.name||'')+(P._status?'　'+P._status:'');
    el('app').style.display='block';
    renderAll();loadSaved();
  }catch(e){el('status').textContent='✗ 連線錯誤：'+e;}
  el('go').disabled=false;
}
async function loadSaved(){
  try{const r=await fetch('/api/saved');const j=await r.json();
    const items=j.items||[],newest=j.newest;
    if(!items.length){el('saved').innerHTML='<span style="color:#999;font-size:13px">尚無</span>';el('refall').style.display='none';return;}
    el('saved').innerHTML='';const stale=[];
    items.forEach(o=>{const sl=newest&&o.last.split('/').join('')<newest;if(sl)stale.push(o.stock);
      const b=document.createElement('button');b.innerHTML=(sl?'<span style="color:#D85A30">●</span> ':'')+o.stock+' '+(o.name||'');
      b.title=o.last+(sl?'（可更新到 '+newest.slice(0,4)+'/'+newest.slice(4,6)+'/'+newest.slice(6)+'）':'（已最新）');
      b.onclick=()=>loadStock(o.stock,false);el('saved').appendChild(b);});
    const ra=el('refall');ra.dataset.stale=JSON.stringify(stale);
    ra.style.display=stale.length?'':'none';ra.textContent='⟳ 一鍵更新過舊（'+stale.length+'）';
  }catch(e){}
}
function pctSpan(v){if(v==null)return '<span style="color:#999">—</span>';return '<span class="'+(v>=0?'up':'down')+'">'+(v>=0?'+':'')+v.toFixed(2)+'%</span>';}
async function loadFav(){
  try{const r=await fetch('/api/fav');const j=await r.json();
    FAVSET=new Set((j.active||[]).map(o=>o.stock));
    const a=j.active||[];
    if(!a.length){el('favbox').innerHTML='<span style="color:#999;font-size:13px">尚無,查一檔後按「加入最愛」</span>';}
    else{let h='<div class="favscroll"><table class="fav"><tr><th>標的</th><th>加入日</th><th>加入價</th><th>現價</th><th>報酬</th><th></th></tr>';
      a.forEach(o=>{h+='<tr><td><a href="#" class="favlink" data-s="'+o.stock+'">'+o.stock+' '+(o.name||'')+'</a></td><td>'+(o.add_date||'').slice(0,10)+'</td><td>'+(o.add_price!=null?o.add_price:'—')+'</td><td>'+(o.cur_price!=null?o.cur_price:'—')+'</td><td>'+pctSpan(o.ret)+'</td><td><button data-rm="'+o.stock+'" style="padding:2px 8px;font-size:12px">移除</button></td></tr>';});
      h+='</table></div>';el('favbox').innerHTML=h;
      el('favbox').querySelectorAll('.favlink').forEach(e=>e.onclick=ev=>{ev.preventDefault();loadStock(e.dataset.s,false);});
      el('favbox').querySelectorAll('[data-rm]').forEach(e=>e.onclick=async()=>{e.disabled=true;await fetch('/api/fav/remove?stock='+encodeURIComponent(e.dataset.rm));loadFav();});}
    const c=j.closed||[];
    if(!c.length){el('closedbox').innerHTML='<span style="color:#999;font-size:13px">(無)</span>';}
    else{let h='<table class="fav"><tr><th>標的</th><th>加入→移除</th><th>加入價</th><th>移除價</th><th>報酬</th></tr>';
      c.forEach(o=>{h+='<tr><td>'+o.stock+' '+(o.name||'')+'</td><td>'+(o.add_date||'').slice(0,10)+' → '+(o.remove_date||'').slice(0,10)+'</td><td>'+(o.add_price!=null?o.add_price:'—')+'</td><td>'+(o.remove_price!=null?o.remove_price:'—')+'</td><td>'+pctSpan(o.ret)+'</td></tr>';});
      h+='</table>';el('closedbox').innerHTML=h;}
    updateStar();
  }catch(e){}
}
function updateStar(){const b=el('star');if(!P){b.style.display='none';return;}b.style.display='';b.textContent=FAVSET.has(P.stock)?'★ 移除最愛':'☆ 加入最愛';}
function renderAll(){
  W=P.labels.length; calcDims();
  SELW=W-1; if(SELT>14)SELT=10;
  el('meta').textContent=P.stock+' '+(P.name||'')+'　'+P.labels[0]+' ~ '+P.labels[W-1]+'　共 '+W+' 週';
  const f=P.PCT[W-1],g=(a,b)=>f.slice(a,b).reduce((x,y)=>x+y,0);
  el('kv').innerHTML='最新('+P.labels[W-1]+'):  散戶(≤1萬股) <b>'+g(0,3).toFixed(2)+'%</b>  中實戶 <b>'+g(3,11).toFixed(2)+'%</b>  大戶(≥400張) <b>'+g(11,15).toFixed(2)+'%</b>  千張大戶 <b>'+f[14].toFixed(2)+'%</b>';
  const wk=el('wk');wk.innerHTML='';
  P.labels.forEach((d,i)=>{const o=document.createElement('option');o.value=i;o.textContent=d;wk.appendChild(o);});
  wk.value=SELW;
  el('pxlbl').style.display=P.PX?'':'none';
  setMode('pct'); updateStar();
}
function drawBars(){
  const i=SELW,v=P.PCT[i],excl=el('ex').checked;
  const idx=excl?[...Array(14).keys()]:[...Array(15).keys()];
  const mx=Math.max(...idx.map(k=>v[k]),0.001);
  let h='<div style="font-size:12px;color:#6b6b6b;margin-bottom:6px">所選週:<b style="color:#0F6E56">'+P.labels[i]+'</b></div>';
  for(const k of idx){const w=(v[k]/mx*100).toFixed(1);const hl=(k===SELT);
    h+='<div class="barrow"><div class="tlbl" style="'+(hl?'color:#0F6E56;font-weight:600':'')+'" title="'+P.LBL[k]+'">'+(hl?'▸ ':'')+P.LBL[k]+'</div><div class="track"><div class="bar'+(k===14?' big':'')+'" style="width:'+w+'%"></div></div><div class="val">'+v[k].toFixed(2)+'%</div></div>';}
  el('bars').innerHTML=h;
}
function zmat(M){const z=[];for(let t=0;t<15;t++){const c=M.map(r=>r[t]);const mu=c.reduce((a,b)=>a+b,0)/W;
  const sd=Math.sqrt(c.reduce((a,b)=>a+(b-mu)**2,0)/W)||1e-9;z.push(c.map(x=>(x-mu)/sd));}return z;}
function col(z){const a=Math.min(Math.abs(z)/2.2,1);if(Math.abs(z)<1e-6)return'#ededed';
  return z>0?'rgba(216,90,48,'+(a*0.9).toFixed(2)+')':'rgba(24,95,165,'+(a*0.9).toFixed(2)+')';}
function drawHM(){
  const M=CURM==='pct'?P.PCT:P.PPL,z=zmat(M);
  let h='<div style="display:grid;grid-template-columns:'+X0+'px repeat('+W+','+CW+'px);gap:1px;align-items:center;font-size:11px">';
  for(let t=0;t<15;t++){const selRow=(t===SELT);
    h+='<div class="tlbl" data-t="'+t+'" style="padding-right:6px;cursor:pointer;'+(selRow?'color:#0F6E56;font-weight:600':'')+'">'+(selRow?'▸ ':'')+P.LBL[t]+'</div>';
    for(let w=0;w<W;w++){const raw=M[w][t];let stl='height:19px;border-radius:2px;cursor:pointer;background:'+col(z[t][w]);
      if(selRow&&w===SELW)stl+=';outline:2px solid #0F6E56;z-index:1';
      else if(selRow)stl+=';outline:1px solid #0F6E56';
      else if(w===SELW)stl+=';outline:1px solid #c9a36a';
      h+='<div data-t="'+t+'" data-w="'+w+'" title="'+P.LBL[t]+' '+P.labels[w]+' 值='+raw+(CURM==='pct'?'%':'人')+' z='+z[t][w].toFixed(2)+'" style="'+stl+'"></div>';}
  }
  h+='<div></div>';
  for(let w=0;w<W;w++){const lab=(w===SELW)?('<b style="color:#0F6E56">'+P.labels[w].slice(5)+'</b>'):(w%4===0?P.labels[w].slice(5):'');
    h+='<div style="font-size:9px;color:#aaa;writing-mode:vertical-rl;height:38px;overflow:hidden">'+lab+'</div>';}
  h+='</div>';
  const c=el('hm');c.innerHTML=h;
  c.querySelectorAll('[data-t]').forEach(e=>{e.onclick=()=>{
    SELT=+e.dataset.t;
    if(e.dataset.w!==undefined){SELW=+e.dataset.w;el('wk').value=SELW;drawBars();}
    drawHM();drawFocus();
  };});
}
function priceLine(X,Yfn){
  if(!P.PX) return null;
  const pts=[];for(let i=0;i<W;i++){if(P.PX[i]!=null)pts.push([i,P.PX[i]]);}
  if(pts.length<2) return null;
  const lv=pts.map(p=>Math.log(p[1])),lo=Math.min(...lv),hi=Math.max(...lv),rng=(hi-lo)||1;
  let d='';pts.forEach((p,k)=>{d+=(k?'L':'M')+X(p[0]).toFixed(1)+' '+Yfn((Math.log(p[1])-lo)/rng).toFixed(1)+' ';});
  return {d:d,lo:Math.exp(lo),hi:Math.exp(hi)};
}
function fmtP(v){return v>=100?Math.round(v).toLocaleString():v.toFixed(1);}
function drawPrice(){
  const box=el('pxstrip');
  if(!P.PX||!el('pxck').checked){box.innerHTML='';return;}
  const x0=X0,pitch=CW+1,w=x0+W*pitch,h=92,top=10,bot=18;
  const X=i=>x0+i*pitch+CW/2,Yfn=fr=>top+(h-top-bot)*(1-fr);
  const pl=priceLine(X,Yfn);if(!pl){box.innerHTML='';return;}
  let s='<svg width="'+w+'" height="'+h+'" style="display:block">';
  s+='<line x1="'+x0+'" y1="'+top+'" x2="'+w+'" y2="'+top+'" stroke="#eee"/><line x1="'+x0+'" y1="'+(h-bot)+'" x2="'+w+'" y2="'+(h-bot)+'" stroke="#eee"/>';
  const sx=X(SELW);s+='<line x1="'+sx+'" y1="'+top+'" x2="'+sx+'" y2="'+(h-bot)+'" stroke="#c9a36a"/>';
  s+='<path d="'+pl.d+'" fill="none" stroke="#111" stroke-width="1.6"/>';
  s+='<text x="'+(x0-6)+'" y="'+(top+4)+'" text-anchor="end" font-size="10" fill="#999">'+fmtP(pl.hi)+'</text>';
  s+='<text x="'+(x0-6)+'" y="'+(h-bot+4)+'" text-anchor="end" font-size="10" fill="#999">'+fmtP(pl.lo)+'</text>';
  s+='<text x="6" y="'+((top+h-bot)/2)+'" font-size="10" fill="#666">股價</text></svg>';
  box.innerHTML=s;
}
function drawFocus(){
  const box=el('focus');
  const x0=X0,pitch=CW+1,w=x0+W*pitch,h=150,top=28,bot=24;
  const z=zmat(CURM==='pct'?P.PCT:P.PPL)[SELT];
  const zmax=Math.max(2.2,...z.map(v=>Math.abs(v)));
  const X=i=>x0+i*pitch+CW/2,Yz=v=>top+(h-top-bot)*(1-(v+zmax)/(2*zmax)),Yfn=fr=>top+(h-top-bot)*(1-fr);
  let s='<svg width="'+w+'" height="'+h+'" style="display:block">';
  s+='<line x1="'+x0+'" y1="'+Yz(0)+'" x2="'+w+'" y2="'+Yz(0)+'" stroke="#e2e2e2"/>';
  const sx=X(SELW);s+='<line x1="'+sx+'" y1="'+top+'" x2="'+sx+'" y2="'+(h-bot)+'" stroke="#c9a36a"/>';
  const pl=priceLine(X,Yfn);
  if(pl){s+='<path d="'+pl.d+'" fill="none" stroke="#bcbcbc" stroke-width="1.4"/>';
    s+='<text x="'+(w-2)+'" y="'+(top+10)+'" text-anchor="end" font-size="10" fill="#999">股價 '+fmtP(pl.hi)+'</text>';}
  let dz='';for(let i=0;i<W;i++){dz+=(i?'L':'M')+X(i).toFixed(1)+' '+Yz(z[i]).toFixed(1)+' ';}
  s+='<path d="'+dz+'" fill="none" stroke="#0F6E56" stroke-width="1.9"/>';
  for(let i=0;i<W;i++){s+='<circle cx="'+X(i).toFixed(1)+'" cy="'+Yz(z[i]).toFixed(1)+'" r="1.6" fill="'+(z[i]>=0?'#D85A30':'#185FA5')+'"/>';}
  s+='<text x="'+x0+'" y="16" font-size="12" fill="#0F6E56">焦點:'+P.LBL[SELT]+'　'+(CURM==='pct'?'占比':'人數')+' z-score(綠)vs 股價(灰)</text>';
  s+='<text x="'+(x0-6)+'" y="'+(Yz(zmax)+4)+'" text-anchor="end" font-size="10" fill="#999">+'+zmax.toFixed(1)+'</text>';
  s+='<text x="'+(x0-6)+'" y="'+(Yz(0)+4)+'" text-anchor="end" font-size="10" fill="#bbb">0</text>';
  s+='<text x="'+(x0-6)+'" y="'+(Yz(-zmax)+4)+'" text-anchor="end" font-size="10" fill="#999">-'+zmax.toFixed(1)+'</text></svg>';
  box.innerHTML=s;
}
function setMode(m){CURM=m;el('mp').classList.toggle('on',m==='pct');el('mn').classList.toggle('on',m==='ppl');drawHM();drawPrice();drawBars();drawFocus();}
el('go').onclick=()=>loadStock(el('code').value,el('fc').checked);
el('code').addEventListener('keydown',e=>{if(e.key==='Enter')el('go').click();});
el('wk').onchange=()=>{SELW=+el('wk').value;drawBars();drawHM();drawPrice();drawFocus();};
el('ex').onchange=drawBars;
el('mp').onclick=()=>setMode('pct'); el('mn').onclick=()=>setMode('ppl');
el('pxck').onchange=drawPrice;
el('star').onclick=async()=>{if(!P)return;const inf=FAVSET.has(P.stock);el('star').disabled=true;
  try{await fetch('/api/fav/'+(inf?'remove':'add')+'?stock='+encodeURIComponent(P.stock));}catch(e){}
  el('star').disabled=false;loadFav();};
el('refall').onclick=async()=>{
  const list=JSON.parse(el('refall').dataset.stale||'[]');if(!list.length)return;
  el('refall').disabled=true;
  for(let i=0;i<list.length;i++){el('status').textContent='更新中 '+(i+1)+'/'+list.length+'：'+list[i]+' …（每檔約40秒）';
    try{await fetch('/api/chips?stock='+encodeURIComponent(list[i]));}catch(e){}}
  el('status').textContent='✓ 已更新 '+list.length+' 檔';el('refall').disabled=false;loadSaved();
};
loadSaved(); loadFav();
let _rt;window.addEventListener('resize',()=>{clearTimeout(_rt);_rt=setTimeout(()=>{if(P){calcDims();drawHM();drawPrice();drawFocus();}},200);});
</script></body></html>"""

def main():
    envport=os.environ.get("PORT")
    if envport:
        port=int(envport)
        httpd=http.server.ThreadingHTTPServer(("0.0.0.0",port),H)
        print("server on 0.0.0.0:%d (cloud mode, auth=%s)"%(port,"on" if AUTH else "OFF"))
        try: httpd.serve_forever()
        except KeyboardInterrupt: pass
        return
    port=8830; httpd=None
    for p in range(8830,8851):
        try:
            httpd=http.server.ThreadingHTTPServer(("127.0.0.1",p),H); port=p; break
        except OSError: continue
    if not httpd: raise SystemExit("找不到可用埠號")
    url="http://127.0.0.1:%d"%port
    print("="*48); print(" 集保籌碼瀏覽器已啟動  %s"%url)
    print(" (若沒自動開啟,手動貼上網址;關閉本視窗即停止)"); print("="*48)
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try: httpd.serve_forever()
    except KeyboardInterrupt: pass

if __name__=="__main__":
    main()
