# ╔══════════════════════════════════════════════════════════════╗
# ║   Config Collector Bot — v6.0 FIXED                          ║
# ║   🔴 FIX: CONFIG_PATTERN non-capturing group                 ║
# ║   🔴 FIX: کیبورد بعد از کلیک حذف میشه                     ║
# ║   🔴 FIX: BASE_URL برای Railway                              ║
# ║   🔴 FIX: آمار در caption نه پیام جداگانه                  ║
# ╚══════════════════════════════════════════════════════════════╝
import os, re, json, asyncio, aiohttp, base64, random
import logging, threading, time
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from io import BytesIO
from logging.handlers import RotatingFileHandler
from flask import Flask, Response, request, render_template_string, redirect, url_for, jsonify

import nest_asyncio
nest_asyncio.apply()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)
import pytz

LOG_FILE = "bot.log"
_fh = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding='utf-8')
_fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger = logging.getLogger()
logger.setLevel(logging.INFO)
if not logger.handlers:
    _sh = logging.StreamHandler()
    _sh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(_sh)
    logger.addHandler(_fh)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# ══════════════════════════════════════════════
TOKEN      = os.environ.get("BOT_TOKEN", "")
if not TOKEN:
    raise ValueError("❌ BOT_TOKEN تنظیم نشده!")
ADMIN_ID   = int(os.environ.get("ADMIN_ID", "8136134031"))
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@Configcollecter")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "@ConfigggCollectorBot")
if not BOT_USERNAME.startswith("@"):
    BOT_USERNAME = "@" + BOT_USERNAME
PORT       = int(os.environ.get("PORT", 8080))
AI_API_KEY = os.environ.get("AI_API_KEY", "")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin2026")
TEHRAN_TZ  = pytz.timezone('Asia/Tehran')

# ✅ FIX: BASE_URL برای Railway
_raw_url = (
    os.environ.get("PUBLIC_URL") or
    os.environ.get("RAILWAY_PUBLIC_DOMAIN") or
    os.environ.get("RAILWAY_STATIC_URL") or
    f"localhost:{PORT}"
)
BASE_URL = _raw_url.rstrip('/')
if BASE_URL and not BASE_URL.startswith("http"):
    BASE_URL = f"https://{BASE_URL}"

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

FILES = {
    "stats":          os.path.join(DATA_DIR, "stats.json"),
    "users":          os.path.join(DATA_DIR, "users.json"),
    "groups":         os.path.join(DATA_DIR, "groups.json"),
    "settings":       os.path.join(DATA_DIR, "settings.json"),
    "sources":        os.path.join(DATA_DIR, "sources.json"),
    "referrals":      os.path.join(DATA_DIR, "referrals.json"),
    "custom_configs": os.path.join(DATA_DIR, "custom_configs.txt"),
    "vip_users":      os.path.join(DATA_DIR, "vip_users.json"),
}
LOCKS = {k: threading.Lock() for k in FILES}

DEFAULT_STATS    = {"users":0,"total_configs_sent":0,"total_requests":0,"errors":0,"daily":{}}
DEFAULT_SETTINGS = {"channel_interval":600,"group_interval":10800,"cache_interval":1800}
PROTOCOLS        = ["vless","vmess","trojan","ss","hysteria2","tuic"]
RATE_LIMIT_SECS  = 4.0
CONFIG_CACHE: Dict[str,Any] = {"configs":[],"last_update":0}
USER_LAST_REQ: Dict[int,float] = {}
FETCH_SEMAPHORE  = asyncio.Semaphore(10)

# ✅ FIX اصلی: (?:...) به جای (...) — non-capturing group
# قبلاً findall فقط 'vless','trojan' برمیگشت نه کانفیگ کامل!
CONFIG_PATTERN = re.compile(
    r'(?:vless|vmess|trojan|ss|hysteria2|tuic)://[^\s\n\r,\"\'\]\[<>{}|\\^`]+',
    re.IGNORECASE
)

SPECIAL_SOURCES = [
    "https://raw.githubusercontent.com/iboxz/free-v2ray-collector/main/main/mix.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-config/main/Sub2.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-config/main/Sub3.txt",
]

COUNTRY_MAP: Dict[str,Tuple[str,str]] = {
    'de':('🇩🇪','آلمان'),'nl':('🇳🇱','هلند'),'fi':('🇫🇮','فنلاند'),
    'se':('🇸🇪','سوئد'),'fr':('🇫🇷','فرانسه'),'gb':('🇬🇧','انگلیس'),
    'at':('🇦🇹','اتریش'),'ch':('🇨🇭','سوئیس'),'pl':('🇵🇱','لهستان'),
    'cz':('🇨🇿','چک'),'ro':('🇷🇴','رومانی'),'hu':('🇭🇺','مجارستان'),
    'lt':('🇱🇹','لیتوانی'),'us':('🇺🇸','آمریکا'),'ca':('🇨🇦','کانادا'),
    'jp':('🇯🇵','ژاپن'),'sg':('🇸🇬','سنگاپور'),'tr':('🇹🇷','ترکیه'),
    'ru':('🇷🇺','روسیه'),'ua':('🇺🇦','اوکراین'),
}

# ══════════════════════════════════════════════
# منابع — لیست کامل آپدیت‌شده
# ══════════════════════════════════════════════
DEFAULT_SOURCES = [
    "https://sub.whitedns.shop/sub/base64.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/Vless-Reality-White-Lists-Rus-Mobile.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/Vless-Reality-White-Lists-Rus-Mobile-2.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/BLACK_VLESS_RUS_mobile.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/WHITE-CIDR-RU-checked.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/BLACK_VLESS_RUS.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/BLACK_SS+All_RUS.txt",
    "https://raw.githubusercontent.com/Mosifree/-FREE2CONFIG/refs/heads/main/FRAGMENT",
    "https://raw.githubusercontent.com/ShadowException/VPN/refs/heads/main/configs/VPN-cat",
    "https://raw.githubusercontent.com/F0rc3Run/F0rc3Run/main/splitted-by-protocol/vless.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-config/main/Sub1.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-Config/main/Sub2.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-Config/main/Sub3.txt",
    "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/refs/heads/main/V2Ray-Config-By-EbraSha.txt",
    "https://raw.githubusercontent.com/MohammadBahemmat/V2ray-Collector/main/subscriptions/all.txt",
    "https://raw.githubusercontent.com/ALIILAPRO/v2rayNG-Config/main/sub.txt",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge.txt",
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub",
    "https://raw.githubusercontent.com/mfuu/v2ray/master/v2ray.txt",
    "https://raw.githubusercontent.com/ermaozi/get_subscribe/main/subscribe/v2ray.txt",
    "https://raw.githubusercontent.com/iboxz/free-v2ray-collector/main/main/mix.txt",
    "https://mifa.world/ss",
    "https://mifa.world/trojan",
    "https://mifa.world/hysteria",
    "https://mifa.world/other",
    "https://mifa.world/vmess",
    "https://mifa.world/vless",
    "https://raw.githubusercontent.com/pytimusprime/FreeV2ray/refs/heads/main/all_servers.txt",
    "https://raw.githubusercontent.com/ThomasJasperthecat/sub/main/sublist1.txt",
    "https://raw.githubusercontent.com/masir-sefid/Sub/main/@Masir_Sefid.txt",
    "https://sub.iampedi5.live/sub/base64.txt",
    "https://raw.githubusercontent.com/masir-sefid/Sub/main/Telegram-Channel-@Masir_Sefid.txt",
    "https://raw.githubusercontent.com/AmyraxVPN-Main/AmyraxVPN/refs/heads/main/AmyraxVPN.txt",
    "https://raw.githubusercontent.com/arshiacomplus/v2rayExtractor/refs/heads/main/mix/sub.html",
    "https://raw.githubusercontent.com/MahsaNetConfigTopic/config/refs/heads/main/xray_final.txt",
    "https://c6et83fe1u99lr8j5w4s9iwik9565bqx.pages.dev/sub/fragment/g4lWgI*%40zehfoOEK?app=xray",
    "http://main.pythash.tr/FRkh99yBGCllN/01736620-2086-4c0b-a86e-52ebfe64dd12/",
    "https://empty-mouse-fbb7.alizareh4024.workers.dev/sync?sub=%D8%B3%D9%88%D8%B3%D9%85%D8%A7%D8%B1%F0%9F%A6%8E",
    "https://sub.elitev2.ir:88/sub/djMsNDEsMTc4MTc5NDQ4Ng2eb707f649",
]

# ══════════════════════════════════════════════
# DB Functions
# ══════════════════════════════════════════════
def load_json(key:str, default:Any)->Any:
    with LOCKS[key]:
        p = FILES[key]
        if not os.path.exists(p):
            with open(p,'w',encoding='utf-8') as f: json.dump(default,f,ensure_ascii=False,indent=2)
            return default
        try:
            with open(p,'r',encoding='utf-8') as f: return json.load(f)
        except Exception as e:
            logger.error(f"load_json [{key}]: {e}"); return default

def save_json(key:str, data:Any):
    with LOCKS[key]:
        p = FILES[key]; tmp = p+".tmp"
        try:
            with open(tmp,'w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,indent=2)
            os.replace(tmp,p)
        except Exception as e:
            logger.error(f"save_json [{key}]: {e}")
            if os.path.exists(tmp): os.remove(tmp)

def load_custom_configs()->List[str]:
    with LOCKS["custom_configs"]:
        p = FILES["custom_configs"]
        if not os.path.exists(p): return []
        with open(p,'r',encoding='utf-8') as f: return [l.strip() for l in f if l.strip()]

def save_custom_configs(configs:List[str]):
    with LOCKS["custom_configs"]:
        with open(FILES["custom_configs"],'w',encoding='utf-8') as f:
            f.write("\n".join(configs)+("\n" if configs else ""))

def add_stat(key:str, amount:int=1):
    stats = load_json("stats",DEFAULT_STATS)
    stats[key] = stats.get(key,0)+amount
    today = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")
    stats.setdefault("daily",{})[today] = stats["daily"].get(today,0)+amount
    save_json("stats",stats)

# ══════════════════════════════════════════════
# Config Engine — FIXED
# ══════════════════════════════════════════════
def extract_configs(text:str)->List[str]:
    if not text: return []
    # تلاش برای decode base64
    cleaned = text.strip()
    if len(cleaned) < 200000:
        try:
            if not any(p+"://" in cleaned for p in PROTOCOLS):
                decoded = base64.b64decode(cleaned+"==").decode('utf-8',errors='ignore')
                if any(p+"://" in decoded for p in PROTOCOLS):
                    text = decoded
        except Exception: pass
    # ✅ از finditer استفاده می‌کنیم نه findall — گروه‌ها را دور می‌زنیم
    raw = [m.group().rstrip('.,;)') for m in CONFIG_PATTERN.finditer(text)]
    return list(set(c for c in raw if len(c)>20))

def filter_configs(configs:List[str], protocol:str)->List[str]:
    if not protocol or protocol=="ALL": return configs
    return [c for c in configs if c.lower().startswith(f"{protocol.lower()}://")]

def detect_country(cfg:str)->Optional[str]:
    try:
        host = ""
        if "@" in cfg:
            host = cfg.split("@",1)[1].split(":")[0].split("?")[0].lower()
        elif "://" in cfg:
            host = cfg.split("://",1)[1].split(":")[0].split("?")[0].lower()
        if not host: return None
        h = f".{host}."
        for cc in COUNTRY_MAP:
            if any(p in h for p in [f'.{cc}.',f'-{cc}.',f'.{cc}-',f'-{cc}-']):
                return cc
    except Exception: pass
    return None

def filter_by_country(configs:List[str],cc:str)->List[str]:
    return [c for c in configs if detect_country(c)==cc]

def get_available_countries(configs:List[str])->Dict[str,int]:
    counts:Dict[str,int]={}
    for c in configs:
        cc=detect_country(c)
        if cc and cc in COUNTRY_MAP: counts[cc]=counts.get(cc,0)+1
    return dict(sorted(counts.items(),key=lambda x:x[1],reverse=True))

async def fetch_one_source(session:aiohttp.ClientSession,url:str)->List[str]:
    async with FETCH_SEMAPHORE:
        try:
            async with session.get(url,timeout=aiohttp.ClientTimeout(total=12),ssl=False) as r:
                if r.status==200:
                    return extract_configs(await r.text(errors='ignore'))
        except Exception as e:
            logger.debug(f"fetch {url[:50]}: {e}")
    return []

async def update_cache(sources:Optional[List[str]]=None):
    if sources is None:
        db=load_json("sources",{"list":DEFAULT_SOURCES})
        sources=db.get("list",DEFAULT_SOURCES)
    logger.info(f"🔄 Fetching {len(sources)} sources")
    connector=aiohttp.TCPConnector(limit=20,ssl=False)
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks=[fetch_one_source(session,u) for u in sources]
            try: results=await asyncio.wait_for(asyncio.gather(*tasks,return_exceptions=True),timeout=90.0)
            except asyncio.TimeoutError: results=[]
        all_cfgs=[]
        for r in results:
            if isinstance(r,list): all_cfgs.extend(r)
        unique=list(set(all_cfgs))
        CONFIG_CACHE['configs']=unique
        CONFIG_CACHE['last_update']=time.time()
        logger.info(f"✅ Cache: {len(unique)} configs")
    except Exception as e:
        logger.error(f"update_cache: {e}"); add_stat("errors")

async def fetch_configs_fresh(sources:List[str])->List[str]:
    connector=aiohttp.TCPConnector(limit=10,ssl=False)
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks=[fetch_one_source(session,u) for u in sources]
            try: results=await asyncio.wait_for(asyncio.gather(*tasks,return_exceptions=True),timeout=35.0)
            except asyncio.TimeoutError: return []
        all_cfgs=[]
        for r in results:
            if isinstance(r,list): all_cfgs.extend(r)
        return list(set(all_cfgs))
    except Exception as e:
        logger.error(f"fetch_fresh: {e}"); return []

# ══════════════════════════════════════════════
# User Management
# ══════════════════════════════════════════════
def get_user(user_id:int)->dict:
    users=load_json("users",{})
    uid=str(user_id)
    if uid not in users:
        users[uid]={"is_vip":False,"protocol_filter":"ALL","daily_requests":0,
            "last_reset":datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d"),"bonus_limit":0,
            "sub_token":os.urandom(12).hex(),"invited_by":None,"username":"","first_name":"",
            "join_date":datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H:%M"),"total_requests":0}
        stats=load_json("stats",DEFAULT_STATS); stats["users"]=stats.get("users",0)+1
        save_json("stats",stats); save_json("users",users)
    u=users[uid]
    for fld,dft in [("sub_token",os.urandom(12).hex()),("invited_by",None),
                     ("username",""),("first_name",""),("total_requests",0),("join_date","")]:
        if fld not in u: u[fld]=dft
    return u

def save_user(uid:int,data:dict):
    users=load_json("users",{}); users[str(uid)]=data; save_json("users",users)

def update_user_info(uid:int,username:str,first_name:str):
    u=get_user(uid); u["username"]=username or ""; u["first_name"]=first_name or ""
    save_user(uid,u)

def check_limit(user_id:int)->tuple:
    if user_id==ADMIN_ID: return True,"VIP"
    u=get_user(user_id)
    if u.get("is_vip"): return True,"VIP"
    today=datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")
    if u.get("last_reset")!=today:
        u["daily_requests"]=0; u["last_reset"]=today; save_user(user_id,u)
    total=3+u.get("bonus_limit",0); used=u.get("daily_requests",0)
    if used<total:
        u["daily_requests"]=used+1; u["total_requests"]=u.get("total_requests",0)+1
        save_user(user_id,u); return True,f"{total-used-1} درخواست باقی"
    return False,(f"❌ سهمیه روزانه ({total} درخواست) تمام شد.\n"
                  "⏳ ریست در ۰۰:۰۰\n💡 /invite دوست دعوت کن → سهمیه بیشتر!")

def is_spamming(uid:int)->bool:
    if uid==ADMIN_ID: return False
    now=time.time()
    if now-USER_LAST_REQ.get(uid,0)<RATE_LIMIT_SECS: return True
    USER_LAST_REQ[uid]=now; return False

def process_referral(new_id:int,inv_id:int)->bool:
    if new_id==inv_id: return False
    u=get_user(new_id)
    if u.get("invited_by") is not None: return False
    refs=load_json("referrals",{}); key=str(inv_id)
    refs.setdefault(key,[])
    if new_id in refs[key]: return False
    refs[key].append(new_id); save_json("referrals",refs)
    u["invited_by"]=inv_id; save_user(new_id,u)
    inv=get_user(inv_id); inv["bonus_limit"]=inv.get("bonus_limit",0)+1; save_user(inv_id,inv)
    return True

def get_all_users_info()->List[dict]:
    users=load_json("users",{})
    return sorted([{"uid":k,**v} for k,v in users.items()],
                  key=lambda x:x.get("total_requests",0),reverse=True)

# ══════════════════════════════════════════════
# AI + Ping + Send Helper
# ══════════════════════════════════════════════
def run_async_safe(coro):
    loop=asyncio.new_event_loop()
    try: return loop.run_until_complete(coro)
    finally: loop.close()

async def ask_ai_async(prompt:str)->str:
    if not AI_API_KEY: return "❌ AI_API_KEY در Railway تنظیم نشده."
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization":f"Bearer {AI_API_KEY}","Content-Type":"application/json",
                         "HTTP-Referer":BASE_URL,"X-Title":"Config Collector Bot"},
                json={"model":"meta-llama/llama-3.1-8b-instruct:free",
                      "messages":[{"role":"system","content":"پاسخ فارسی کوتاه و مفید."},
                                  {"role":"user","content":prompt}],"max_tokens":600},
                timeout=aiohttp.ClientTimeout(total=25)
            ) as resp:
                if resp.status==200:
                    data=await resp.json()
                    return data.get('choices',[{}])[0].get('message',{}).get('content','') or "❌ پاسخ خالی."
                return f"❌ سرور AI: {resp.status}"
    except asyncio.TimeoutError: return "⏱ AI timeout"
    except Exception as e: return f"❌ {str(e)[:80]}"

async def ping_host_async(host:str)->str:
    clean=host.strip().replace("https://","").replace("http://","").split("/")[0]
    try:
        start=asyncio.get_event_loop().time()
        async with aiohttp.ClientSession() as session:
            async with session.head(f"https://{clean}",
                timeout=aiohttp.ClientTimeout(total=6),allow_redirects=True,ssl=False) as r:
                ms=int((asyncio.get_event_loop().time()-start)*1000)
                s="🟢 عالی" if ms<150 else "🟠 متوسط" if ms<300 else "🔴 ضعیف"
                return f"🏓 {ms}ms — {s}\n📡 {clean}\n🔢 {r.status}"
    except asyncio.TimeoutError: return f"❌ Timeout — {clean}"
    except Exception as e: return f"❌ {str(e)[:80]}"

async def send_configs_to_msg(msg, configs:List[str], count:int=10,
                               as_json:bool=False, prefix:str="configs"):
    """✅ FIXED: آمار در caption، نه پیام جداگانه"""
    if not configs:
        await msg.reply_text("⚠️ کانفیگی یافت نشد.\n💡 از ⚡ اسکن لحظه‌ای استفاده کنید."); return

    total_in=len(configs)
    seen,unique=[],set()
    for c in configs:
        if c not in seen: seen; unique.add(c)
    # حذف تکراری
    unique_list=list(dict.fromkeys(configs))
    dupes=total_in-len(unique_list)
    # حذف خراب
    valid=[c for c in unique_list if len(c)>20 and "://" in c and
           any(c.lower().startswith(p+"://") for p in PROTOCOLS)]
    invalid=len(unique_list)-len(valid)

    if not valid:
        await msg.reply_text("⚠️ کانفیگ معتبر یافت نشد.\n💡 ⚡ اسکن لحظه‌ای را امتحان کنید."); return

    pool=valid.copy(); random.shuffle(pool)
    selected=pool[:count] if (count and count<len(pool)) else pool
    rnd=random.randint(100,999)

    # ✅ آمار در caption نه پیام جداگانه
    stats_line=(f"📥{total_in:,} | 🔄{dupes:,} حذف تکراری | 🗑️{invalid} خراب | ✅{len(selected):,} پاک")

    if as_json:
        fname=f"{prefix}_{len(selected)}_{rnd}.json"
        payload=json.dumps({"configs":selected,"count":len(selected),
            "timestamp":datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H:%M"),
            "bot":BOT_USERNAME},ensure_ascii=False,indent=2).encode('utf-8')
        caption=f"📋 <b>{len(selected):,} کانفیگ | JSON</b>\n{stats_line}\n🤖 {BOT_USERNAME}"
    else:
        fname=f"{prefix}_{len(selected)}_{rnd}.txt"
        payload="\n".join(selected).encode('utf-8')
        caption=f"📄 <b>{len(selected):,} کانفیگ | TXT</b>\n{stats_line}\n🤖 {BOT_USERNAME}"

    buf=BytesIO(payload); buf.name=fname
    try:
        await msg.reply_document(document=InputFile(buf,filename=fname),
                                  caption=caption,parse_mode='HTML')
        add_stat("total_configs_sent",len(selected))
    except Exception as e:
        logger.error(f"send_configs: {e}")
        await msg.reply_text(f"❌ خطا: {str(e)[:80]}")

# ══════════════════════════════════════════════
# Flask App
# ══════════════════════════════════════════════
flask_app=Flask(__name__)

USER_PANEL_HTML="""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="UTF-8"><title>داشبورد</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;700&display=swap');
:root{--bg:#060d1a;--card:#0f1d30;--text:#e2eaf6;--muted:#6b7fa3;--accent:#00d4ff;--accent2:#7c3aed;
  --success:#10d97b;--border:#1e3050;--glow:0 0 20px rgba(0,212,255,.15);}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:'Vazirmatn',sans-serif;padding:16px;}
.container{max-width:860px;margin:auto;}
.header{text-align:center;padding:24px 0 20px;border-bottom:1px solid var(--border);margin-bottom:24px;}
.header h1{font-size:1.4rem;color:var(--accent);font-weight:700;}
.badge{display:inline-block;padding:4px 12px;border-radius:20px;font-size:.75rem;font-weight:600;
  background:rgba(0,212,255,.12);color:var(--accent);border:1px solid rgba(0,212,255,.3);margin-top:6px;}
.badge.vip{background:rgba(124,58,237,.2);color:#a78bfa;border-color:rgba(124,58,237,.4);}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin-bottom:20px;}
.card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:20px;
  box-shadow:var(--glow);transition:.2s;}
.card:hover{border-color:var(--accent);}
.card-title{font-size:.8rem;color:var(--muted);margin-bottom:12px;}
.stat-num{font-size:2rem;font-weight:700;color:var(--accent);}
select,input[type=text]{width:100%;padding:10px;background:#0a1520;border:1px solid var(--border);
  color:var(--text);border-radius:8px;font-family:inherit;font-size:.9rem;margin-bottom:10px;outline:none;}
.btn{display:block;width:100%;padding:11px;border:none;border-radius:8px;font-family:inherit;
  font-size:.9rem;font-weight:600;cursor:pointer;transition:.2s;text-align:center;}
.btn-primary{background:linear-gradient(135deg,#0096c7,#7c3aed);color:#fff;}
.btn-outline{background:transparent;border:1px solid var(--accent);color:var(--accent);}
pre{background:#040a12;color:var(--success);padding:14px;border-radius:10px;font-size:.78rem;
  max-height:200px;overflow-y:auto;border:1px solid var(--border);white-space:pre-wrap;word-break:break-all;margin-top:10px;}
.copy-box{display:flex;gap:8px;align-items:center;}
.copy-box input{margin:0;flex:1;font-size:.75rem;direction:ltr;}
.copy-btn{padding:10px 14px;background:var(--card);border:1px solid var(--border);
  color:var(--accent);border-radius:8px;cursor:pointer;font-size:.8rem;}
.toast{position:fixed;bottom:20px;right:20px;background:var(--success);color:#000;
  padding:10px 20px;border-radius:8px;display:none;font-weight:600;z-index:999;}
.sec{font-size:1rem;color:var(--accent);font-weight:600;margin:20px 0 12px;
  padding-bottom:8px;border-bottom:1px solid var(--border);}
</style></head><body>
<div class="container">
  <div class="header"><div style="font-size:2rem">🛡️</div>
  <h1>داشبورد کاربری Config Collector</h1>
  <span class="badge {{ 'vip' if user.is_vip else '' }}">{{ '👑 VIP' if user.is_vip else '👤 عادی' }}</span>
  <span class="badge" style="margin-right:8px">🆔 {{ uid }}</span></div>
  <div class="grid">
    <div class="card"><div class="card-title">📊 مصرف امروز</div>
      <div class="stat-num">{{ user.daily_requests }}</div>
      <div style="color:var(--muted);font-size:.85rem;margin-top:4px">از {{ 'نامحدود' if user.is_vip else (3+user.bonus_limit) }}</div></div>
    <div class="card"><div class="card-title">🎁 بونوس دعوت</div>
      <div class="stat-num" style="color:var(--success)">+{{ user.bonus_limit }}</div></div>
  </div>
  <div class="sec">🔗 اشتراک هوشمند</div>
  <div class="card" style="margin-bottom:16px">
    <div class="copy-box">
      <input type="text" value="{{ sub_link }}" readonly id="subLink" dir="ltr">
      <button class="copy-btn" onclick="copy('subLink')">📋 کپی</button>
    </div>
    <div style="color:var(--muted);font-size:.8rem;margin-top:8px">در v2rayNG/Nekobox → افزودن اشتراک → لینک بالا</div>
  </div>
  <div class="sec">⚙️ فیلتر پروتکل</div>
  <div class="card" style="margin-bottom:16px">
    <select id="protoSel">
      <option value="ALL" {{ 'selected' if user.protocol_filter=='ALL' }}>همه</option>
      <option value="vless" {{ 'selected' if user.protocol_filter=='vless' }}>VLESS</option>
      <option value="vmess" {{ 'selected' if user.protocol_filter=='vmess' }}>VMESS</option>
      <option value="trojan" {{ 'selected' if user.protocol_filter=='trojan' }}>TROJAN</option>
      <option value="ss" {{ 'selected' if user.protocol_filter=='ss' }}>Shadowsocks</option>
    </select>
    <button class="btn btn-outline" onclick="saveProto()">💾 ذخیره</button>
    <div id="protoMsg" style="color:var(--success);font-size:.85rem;margin-top:8px;display:none"></div>
  </div>
  <div class="sec">🛠️ ابزارها</div>
  <div class="grid">
    <div class="card"><div class="card-title">🏓 پینگ</div>
      <input type="text" id="pingIn" placeholder="google.com">
      <button class="btn btn-outline" onclick="tool('ping')">تست</button>
      <pre id="pingOut">...</pre></div>
    <div class="card"><div class="card-title">🤖 AI</div>
      <input type="text" id="aiIn" placeholder="سوالت را بنویس...">
      <button class="btn btn-outline" onclick="tool('ai')">ارسال</button>
      <pre id="aiOut">...</pre></div>
  </div>
  <div class="sec">📦 کانفیگ تصادفی</div>
  <div class="card">
    <button class="btn btn-primary" onclick="getCfg()">🎲 دریافت</button>
    <pre id="cfgOut">...</pre>
  </div>
  <div style="text-align:center;margin-top:20px;padding-bottom:20px">
    <a href="https://t.me/{{ bot_u }}" style="color:var(--muted);text-decoration:none;font-size:.85rem">🤖 بازگشت به ربات</a>
  </div>
</div>
<div class="toast" id="toast">✅ کپی شد!</div>
<script>
const API='/api/panel/{{ uid }}/{{ user.sub_token }}';
async function apiCall(ep,body={}){
  try{const r=await fetch(API+ep,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});return await r.json();}
  catch(e){return{error:'خطا: '+e.message};}
}
function copy(id){
  const el=document.getElementById(id);
  navigator.clipboard.writeText(el.value).catch(()=>{el.select();document.execCommand('copy');});
  const t=document.getElementById('toast');t.style.display='block';setTimeout(()=>t.style.display='none',2000);
}
async function saveProto(){
  const p=document.getElementById('protoSel').value;
  const r=await apiCall('/protocol',{protocol:p});
  const m=document.getElementById('protoMsg');m.style.display='block';
  m.innerText=r.success?'✅ ذخیره شد.':'❌ '+r.error;
}
async function tool(type){
  const inp=document.getElementById(type==='ping'?'pingIn':'aiIn').value.trim();
  const out=document.getElementById(type==='ping'?'pingOut':'aiOut');
  if(!inp){out.innerText='⚠️ خالی است.';return;}
  out.innerText='⏳...';
  const r=await apiCall('/tool',{type,input:inp});
  out.innerText=r.result||r.error||'خطا';
}
async function getCfg(){
  const out=document.getElementById('cfgOut');out.innerText='⏳...';
  const r=await apiCall('/config');out.innerText=r.config||r.error||'خطا';
}
</script></body></html>"""

ADMIN_HTML="""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>ADMIN</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
:root{--bg:#03070f;--panel:#080f1c;--border:#0d2035;--cyan:#00ffff;--green:#00ff88;
  --red:#ff3355;--yellow:#ffcc00;--muted:#3a5570;--text:#c8dff0;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:'JetBrains Mono',monospace;padding:16px;font-size:13px;}
.hdr{border:1px solid var(--border);padding:14px 20px;margin-bottom:20px;
  background:linear-gradient(135deg,#030d1a,#060f20);display:flex;justify-content:space-between;align-items:center;}
.title{color:var(--cyan);font-size:1rem;font-weight:700;}
.online{color:var(--green);font-size:.75rem;border:1px solid var(--green);padding:3px 10px;}
.sg{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:20px;}
.sb{background:var(--panel);border:1px solid var(--border);padding:14px;border-left:3px solid var(--cyan);}
.sb.err{border-left-color:var(--red);}.sb.warn{border-left-color:var(--yellow);}
.sl{font-size:.65rem;color:var(--muted);letter-spacing:.1em;margin-bottom:6px;}
.sv{font-size:1.6rem;font-weight:700;color:var(--cyan);}.sv.red{color:var(--red);}
.panel{background:var(--panel);border:1px solid var(--border);padding:16px;margin-bottom:16px;}
.pt{color:var(--cyan);font-size:.8rem;letter-spacing:.1em;margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid var(--border);}
table{width:100%;border-collapse:collapse;}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--border);font-size:.75rem;}
th{color:var(--cyan);background:#040c18;}td{color:#8fb0cc;}
.fr{display:flex;gap:8px;margin-bottom:12px;}
input[type=text]{flex:1;background:#040c18;border:1px solid var(--border);color:var(--cyan);
  padding:8px 12px;font-family:inherit;font-size:.8rem;outline:none;}
input:focus{border-color:var(--cyan);}
.btn{background:transparent;border:1px solid currentColor;padding:6px 14px;cursor:pointer;
  font-family:inherit;font-size:.75rem;font-weight:700;transition:.15s;}
.bc{color:var(--cyan);}.bc:hover{background:rgba(0,255,255,.08);}
.br{color:var(--red);}.br:hover{background:rgba(255,51,85,.08);}
.by{color:var(--yellow);}.by:hover{background:rgba(255,204,0,.08);}
.tag-vip{background:rgba(255,204,0,.12);color:var(--yellow);padding:2px 8px;font-size:.7rem;}
</style></head><body>
<div class="hdr"><div class="title">&gt; SYS_CORE :: CONFIG_COLLECTOR_ADMIN</div>
<div class="online">● ONLINE // {{ last_sync }}</div></div>
<div class="sg">
  <div class="sb"><div class="sl">USERS</div><div class="sv">{{ stats.users }}</div></div>
  <div class="sb"><div class="sl">REQUESTS</div><div class="sv">{{ stats.total_requests }}</div></div>
  <div class="sb"><div class="sl">SENT</div><div class="sv">{{ stats.total_configs_sent }}</div></div>
  <div class="sb warn"><div class="sl">CACHED</div><div class="sv" style="color:var(--yellow)">{{ cached }}</div></div>
  <div class="sb err"><div class="sl">ERRORS</div><div class="sv red">{{ stats.errors }}</div></div>
  <div class="sb"><div class="sl">SOURCES</div><div class="sv">{{ sources|length }}</div></div>
  <div class="sb"><div class="sl">VIP</div><div class="sv">{{ vip_count }}</div></div>
</div>
<div class="panel"><div class="pt">&gt; SOURCES [{{ sources|length }}]</div>
  <form method="POST" class="fr">
    <input type="text" name="source_link" placeholder="https://raw.githubusercontent.com/...">
    <button class="btn bc" name="action" value="add_source">+ ADD</button>
  </form>
  <table><tr><th>#</th><th>URL</th><th>ACT</th></tr>
  {% for i,s in sources %}<tr><td>{{ i+1 }}</td><td>{{ s[:70] }}{% if s|length>70 %}...{% endif %}</td>
  <td><form method="POST" style="margin:0"><input type="hidden" name="src_id" value="{{ i }}">
  <button class="btn br" name="action" value="del_source">DEL</button></form></td></tr>{% endfor %}
  </table></div>
<div class="panel"><div class="pt">&gt; CUSTOM_NODES [{{ custom_configs|length }}]</div>
  <form method="POST" class="fr">
    <input type="text" name="config_link" placeholder="vless://...">
    <button class="btn by" name="action" value="add_config">+ ADD</button>
  </form>
  <table><tr><th>#</th><th>CONFIG</th><th>ACT</th></tr>
  {% for i,c in custom_configs %}<tr><td>{{ i+1 }}</td><td style="color:var(--yellow)">{{ c[:80] }}...</td>
  <td><form method="POST" style="margin:0"><input type="hidden" name="cfg_id" value="{{ i }}">
  <button class="btn br" name="action" value="del_config">DEL</button></form></td></tr>{% endfor %}
  </table></div>
<div class="panel"><div class="pt">&gt; USERS [TOP 20]</div>
  <table><tr><th>ID</th><th>NAME</th><th>VIP</th><th>REQS</th></tr>
  {% for u in top_users %}<tr><td>{{ u.uid }}</td><td>{{ u.first_name or u.username or '—' }}</td>
  <td>{% if u.is_vip %}<span class="tag-vip">VIP</span>{% else %}—{% endif %}</td>
  <td>{{ u.total_requests }}</td></tr>{% endfor %}</table></div>
<div class="panel"><div class="pt">&gt; VIP_CTRL</div>
  <form method="POST" class="fr">
    <input type="text" name="vip_id" placeholder="USER_ID">
    <button class="btn by" name="action" value="add_vip">+VIP</button>
    <button class="btn br" name="action" value="del_vip">-VIP</button>
  </form></div>
<div class="panel"><div class="pt">&gt; CACHE_CTRL</div>
  <form method="POST" style="display:inline">
    <button class="btn bc" name="action" value="refresh_cache">⟳ SYNC</button>
  </form>&nbsp;
  <form method="POST" style="display:inline">
    <button class="btn br" name="action" value="clear_cache">⚠ PURGE</button>
  </form></div>
</body></html>"""

# ══════════════════════════════════════════════
# Flask Routes
# ══════════════════════════════════════════════
@flask_app.route('/')
def index():
    return jsonify({"status":"online","bot":BOT_USERNAME,"cached":len(CONFIG_CACHE['configs'])})

@flask_app.route('/panel/<int:uid>/<token>')
def user_panel(uid,token):
    u=get_user(uid)
    if u.get('sub_token')!=token: return Response("401",status=401)
    return render_template_string(USER_PANEL_HTML,uid=uid,user=u,
        sub_link=f"{BASE_URL}/sub/{uid}/{token}",bot_u=BOT_USERNAME.lstrip('@'))

@flask_app.route('/api/panel/<int:uid>/<token>/<action>',methods=['POST'])
def api_panel(uid,token,action):
    u=get_user(uid)
    if u.get('sub_token')!=token: return jsonify({"error":"Unauthorized"}),401
    data=request.json or {}
    if action=='protocol':
        p=data.get('protocol','ALL')
        if p in ["ALL"]+PROTOCOLS:
            u["protocol_filter"]=p; save_user(uid,u); return jsonify({"success":True})
        return jsonify({"error":"Invalid"})
    elif action=='tool':
        t=data.get('type',''); inp=data.get('input','').strip()
        if not inp: return jsonify({"error":"Empty"})
        result=run_async_safe(ping_host_async(inp) if t=='ping' else ask_ai_async(inp))
        return jsonify({"result":result})
    elif action=='config':
        if not check_limit(uid)[0]: return jsonify({"error":"سهمیه تمام شد"})
        pool=load_custom_configs()+filter_configs(CONFIG_CACHE['configs'],u["protocol_filter"])
        return jsonify({"config":random.choice(pool)}) if pool else jsonify({"error":"کش خالی"})
    return jsonify({"error":"Bad request"}),400

@flask_app.route('/sub/<int:uid>/<token>')
def user_sub(uid,token):
    u=get_user(uid)
    if u.get('sub_token')!=token: return Response("401",status=401)
    plain=request.args.get('plain','0')=='1'
    customs=load_custom_configs()
    all_cfgs=filter_configs(CONFIG_CACHE['configs'],u.get("protocol_filter","ALL"))
    seed=sum(ord(c) for c in token)+int(CONFIG_CACHE.get('last_update',0)//1800)
    rng=random.Random(seed)
    if len(all_cfgs)>500:
        shuffled=all_cfgs.copy(); rng.shuffle(shuffled)
        chunk=max(1,len(shuffled)//5); selected=[]
        for i in range(5):
            s=rng.randint(0,max(0,len(shuffled)-chunk-1))
            selected.extend(shuffled[s:s+chunk])
        selected=list(dict.fromkeys(selected))[:600]
    else: selected=all_cfgs
    final=list(dict.fromkeys(customs+selected))
    content="\n".join(final) if final else "# empty"
    if plain: return Response(content,mimetype='text/plain; charset=utf-8')
    return Response(base64.b64encode(content.encode()).decode(),mimetype='text/plain; charset=utf-8')

@flask_app.route('/dashboard')
def dashboard():
    g=load_json("stats",DEFAULT_STATS)
    return jsonify({"status":"ok","cached":len(CONFIG_CACHE['configs']),"users":g.get("users",0)})

@flask_app.route('/admin',methods=['GET','POST'])
def admin_web():
    auth=request.authorization
    if not auth or auth.username!="admin" or auth.password!=ADMIN_PASS:
        return Response('Auth Required',401,{'WWW-Authenticate':'Basic realm="Admin"'})
    if request.method=='POST':
        action=request.form.get("action","")
        if action=="add_source":
            s=request.form.get("source_link","").strip()
            if s and s.startswith("http"):
                db=load_json("sources",{"list":DEFAULT_SOURCES})
                if s not in db["list"]: db["list"].append(s); save_json("sources",db)
        elif action=="del_source":
            idx=int(request.form.get("src_id",-1))
            db=load_json("sources",{"list":DEFAULT_SOURCES})
            if 0<=idx<len(db["list"]): db["list"].pop(idx); save_json("sources",db)
        elif action=="add_config":
            c=request.form.get("config_link","").strip()
            if c and any(c.startswith(p+"://") for p in PROTOCOLS):
                cfgs=load_custom_configs()
                if c not in cfgs: cfgs.append(c); save_custom_configs(cfgs)
        elif action=="del_config":
            idx=int(request.form.get("cfg_id",-1))
            cfgs=load_custom_configs()
            if 0<=idx<len(cfgs): cfgs.pop(idx); save_custom_configs(cfgs)
        elif action=="add_vip":
            vid=request.form.get("vip_id","").strip()
            if vid:
                u=get_user(int(vid)); u["is_vip"]=True; save_user(int(vid),u)
        elif action=="del_vip":
            vid=request.form.get("vip_id","").strip()
            if vid:
                u=get_user(int(vid)); u["is_vip"]=False; save_user(int(vid),u)
        elif action=="refresh_cache":
            threading.Thread(target=lambda:run_async_safe(update_cache()),daemon=True).start()
        elif action=="clear_cache":
            CONFIG_CACHE['configs']=[]; CONFIG_CACHE['last_update']=0
        return redirect(url_for('admin_web'))
    stats=load_json("stats",DEFAULT_STATS)
    db=load_json("sources",{"list":DEFAULT_SOURCES})
    users_all=get_all_users_info()
    ls=(datetime.fromtimestamp(CONFIG_CACHE['last_update'],TEHRAN_TZ).strftime('%H:%M:%S')
        if CONFIG_CACHE['last_update'] else "NEVER")
    return render_template_string(ADMIN_HTML,stats=stats,cached=len(CONFIG_CACHE['configs']),
        sources=list(enumerate(db["list"])),custom_configs=list(enumerate(load_custom_configs())),
        top_users=users_all[:20],vip_count=sum(1 for u in users_all if u.get("is_vip")),last_sync=ls)

def run_flask():
    flask_app.run(host="0.0.0.0",port=PORT,use_reloader=False,debug=False)

# ══════════════════════════════════════════════
# Keyboards — رنگارنگ و متنوع
# ══════════════════════════════════════════════
def start_keyboard()->InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🆓 کانفیگ رایگان",      callback_data="free_config")],
        [InlineKeyboardButton("📦 دریافت از کش",         callback_data="get_configs"),
         InlineKeyboardButton("⚡ اسکن لحظه‌ای",         callback_data="live_scan")],
        [InlineKeyboardButton("🎲 کانفیگ تصادفی",        callback_data="random_cfg"),
         InlineKeyboardButton("🔐 کانفیگ ادمین",         callback_data="admin_cfgs")],
        [InlineKeyboardButton("🔧 فیلتر پروتکل",         callback_data="filter_proto"),
         InlineKeyboardButton("🌍 فیلتر کشور",           callback_data="country_filter")],
        [InlineKeyboardButton("🌐 داشبورد وب",            callback_data="web_dash"),
         InlineKeyboardButton("🔗 اشتراک هوشمند",        callback_data="sub_link_smart")],
        [InlineKeyboardButton("📊 آمار من",               callback_data="my_stats"),
         InlineKeyboardButton("🏆 آمار کل",               callback_data="global_stats")],
        [InlineKeyboardButton("🎁 دعوت دوستان",           callback_data="invite"),
         InlineKeyboardButton("📖 راهنمای کامل",          callback_data="help")],
    ])

def admin_panel_keyboard()->InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 آمار کامل",   callback_data="adm_stats"),
         InlineKeyboardButton("👥 کاربران",     callback_data="adm_users")],
        [InlineKeyboardButton("👑 لیست VIP",    callback_data="adm_viplist"),
         InlineKeyboardButton("📡 گروه‌ها",     callback_data="adm_groups")],
        [InlineKeyboardButton("📢 ارسال کانال", callback_data="adm_postchannel"),
         InlineKeyboardButton("💾 بکاپ",        callback_data="adm_backup")],
        [InlineKeyboardButton("✅ افزودن VIP",  callback_data="adm_addvip"),
         InlineKeyboardButton("❌ حذف VIP",     callback_data="adm_removevip")],
        [InlineKeyboardButton("🗑️ پاک کش",     callback_data="adm_clearcache"),
         InlineKeyboardButton("🔄 آپدیت کش",   callback_data="adm_refreshcache")],
        [InlineKeyboardButton("⚙️ وضعیت",      callback_data="adm_health"),
         InlineKeyboardButton("📋 لاگ‌ها",      callback_data="adm_logs")],
        [InlineKeyboardButton("🌐 پنل وب",      url=f"{BASE_URL}/admin")],
    ])

def proto_keyboard()->InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 ALL",       callback_data="proto_ALL"),
         InlineKeyboardButton("⚡ VLESS",     callback_data="proto_vless")],
        [InlineKeyboardButton("🔵 VMESS",     callback_data="proto_vmess"),
         InlineKeyboardButton("🛡️ TROJAN",    callback_data="proto_trojan")],
        [InlineKeyboardButton("🔒 SS",        callback_data="proto_ss"),
         InlineKeyboardButton("🚀 HYSTERIA2", callback_data="proto_hysteria2")],
        [InlineKeyboardButton("🔙 بازگشت",    callback_data="back_start")],
    ])

def count_format_keyboard(source:str="cache")->InlineKeyboardMarkup:
    pm={'cache':'gc','live':'ls','special':'gs','bulk':'gb'}
    p=pm.get(source,'gc')
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("━━━ 📄 TXT ━━━",callback_data="noop_info")],
        [InlineKeyboardButton("5️⃣",  callback_data=f"{p}_5_t"),
         InlineKeyboardButton("1️⃣0️⃣",callback_data=f"{p}_10_t"),
         InlineKeyboardButton("2️⃣0️⃣",callback_data=f"{p}_20_t"),
         InlineKeyboardButton("5️⃣0️⃣",callback_data=f"{p}_50_t")],
        [InlineKeyboardButton("💯",  callback_data=f"{p}_100_t"),
         InlineKeyboardButton("🔢200",callback_data=f"{p}_200_t"),
         InlineKeyboardButton("♾️",  callback_data=f"{p}_0_t")],
        [InlineKeyboardButton("━━━ 📋 JSON ━━━",callback_data="noop_info")],
        [InlineKeyboardButton("1️⃣0️⃣📋",callback_data=f"{p}_10_j"),
         InlineKeyboardButton("5️⃣0️⃣📋",callback_data=f"{p}_50_j"),
         InlineKeyboardButton("💯📋",  callback_data=f"{p}_100_j")],
        [InlineKeyboardButton("🔙 بازگشت",callback_data="back_start")],
    ])

def free_config_keyboard()->InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ کانفیگ ویژه — سریع و گزیده",  callback_data="fc_special")],
        [InlineKeyboardButton("🌊 کانفیگ انبوه — همه منابع",     callback_data="fc_bulk")],
        [InlineKeyboardButton("📡 کانفیگ‌های ذخیره‌شده — کش",   callback_data="fc_cached")],
        [InlineKeyboardButton("🔙 بازگشت",                        callback_data="back_start")],
    ])

def country_keyboard()->InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇩🇪 آلمان",callback_data="cf_de"),
         InlineKeyboardButton("🇳🇱 هلند", callback_data="cf_nl")],
        [InlineKeyboardButton("🇫🇮 فنلاند",callback_data="cf_fi"),
         InlineKeyboardButton("🇸🇪 سوئد", callback_data="cf_se")],
        [InlineKeyboardButton("🔍 نمایش همه کشورها",callback_data="cf_all")],
        [InlineKeyboardButton("🔙 بازگشت",callback_data="back_start")],
    ])

def all_countries_keyboard(configs:List[str])->InlineKeyboardMarkup:
    countries=get_available_countries(configs)
    btns=[]; row=[]
    for cc,cnt in list(countries.items())[:14]:
        flag,name=COUNTRY_MAP.get(cc,('🌍',cc.upper()))
        row.append(InlineKeyboardButton(f"{flag}{name}({cnt})",callback_data=f"cf_{cc}"))
        if len(row)==2: btns.append(row); row=[]
    if row: btns.append(row)
    btns.append([InlineKeyboardButton("🔙 بازگشت",callback_data="country_filter")])
    return InlineKeyboardMarkup(btns)

def country_action_keyboard(cc:str)->InlineKeyboardMarkup:
    flag,name=COUNTRY_MAP.get(cc,('🌍',cc.upper()))
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"━━ {flag} {name} ━━",callback_data="noop_info")],
        [InlineKeyboardButton("5️⃣📄", callback_data=f"cget_{cc}_5_t"),
         InlineKeyboardButton("1️⃣0️⃣📄",callback_data=f"cget_{cc}_10_t"),
         InlineKeyboardButton("♾️📄",  callback_data=f"cget_{cc}_0_t")],
        [InlineKeyboardButton("1️⃣0️⃣📋",callback_data=f"cget_{cc}_10_j"),
         InlineKeyboardButton("5️⃣0️⃣📋",callback_data=f"cget_{cc}_50_j")],
        [InlineKeyboardButton("🔙 بازگشت",callback_data="country_filter")],
    ])

# ══════════════════════════════════════════════
# Commands
# ══════════════════════════════════════════════
async def start_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    user=update.effective_user; chat=update.effective_chat
    update_user_info(user.id,user.username or "",user.first_name or "")
    if context.args and context.args[0].startswith("ref_"):
        try:
            ref_id=int(context.args[0].split("ref_")[1])
            if process_referral(user.id,ref_id):
                try:
                    b=get_user(ref_id).get("bonus_limit",0)
                    await context.bot.send_message(ref_id,f"🎉 عضو جدید با لینک شما!\n💡 بونوس: +{b}/روز")
                except: pass
        except: pass
    g=load_json("stats",DEFAULT_STATS); u=get_user(user.id)
    lim="♾️ نامحدود" if (u.get("is_vip") or user.id==ADMIN_ID) else f"{3+u.get('bonus_limit',0)}/روز"
    text=(f"✨ <b>Config Collector Bot</b> ✨\n"
          "━━━━━━━━━━━━━━━━━━━━━\n"
          f"👥 کاربران: {g.get('users',0)} | 📦 کش: {len(CONFIG_CACHE['configs']):,}\n"
          f"🏷️ {'👑 VIP' if u.get('is_vip') else '👤 عادی'} | 🎯 {lim}\n"
          "━━━━━━━━━━━━━━━━━━━━━")
    if chat.type=="private":
        await update.message.reply_text(text,parse_mode='HTML',reply_markup=start_keyboard())
    else:
        await update.message.reply_text(f"👋 برای دریافت کانفیگ به {BOT_USERNAME} پیام بده.")

async def help_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    text=("📖 <b>راهنمای کامل</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
          "🆓 کانفیگ رایگان:\n  ⚡ ویژه | 🌊 انبوه | 📡 ذخیره‌شده\n\n"
          "📦 از کش | ⚡ اسکن لحظه‌ای | 🎲 تصادفی\n"
          "🌍 فیلتر کشور | 🔧 فیلتر پروتکل\n"
          "🔗 اشتراک هوشمند — یک‌بار ثبت، همیشه آپدیت\n\n"
          "🧹 حذف خودکار تکراری + خراب\n"
          "🤖 /ask [سوال] | 🏓 /ping [host]\n\n"
          "━━━━━━━━━━━━━━━━━━━━━\n"
          "👤 ۳/روز | 👑 VIP: نامحدود")
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت",callback_data="back_start")]])
    if update.message: await update.message.reply_text(text,parse_mode='HTML',reply_markup=kb)
    elif update.callback_query: await update.callback_query.message.reply_text(text,parse_mode='HTML',reply_markup=kb)

async def myid_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    u=update.effective_user
    await update.message.reply_text(
        f"🆔 <code>{u.id}</code>\n👤 @{u.username or '—'}\n📛 {u.first_name or '—'}",parse_mode='HTML')

async def invite_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; info=await context.bot.get_me()
    link=f"https://t.me/{info.username}?start=ref_{uid}"
    u=get_user(uid); refs=load_json("referrals",{})
    await update.message.reply_text(
        f"🎁 <b>دعوت دوستان</b>\n🔗 <code>{link}</code>\n"
        f"👥 دعوت: {len(refs.get(str(uid),[]))} | 💡 بونوس: +{u.get('bonus_limit',0)}",parse_mode='HTML')

async def ask_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("🤖 /ask [سوال]"); return
    msg=await update.message.reply_text("🤖 در حال پردازش...")
    ans=await ask_ai_async(" ".join(context.args))
    await msg.edit_text(f"🤖 <b>AI:</b>\n\n{ans}",parse_mode='HTML')

async def ping_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("🏓 /ping [host]"); return
    msg=await update.message.reply_text("🏓 در حال تست...")
    await msg.edit_text(await ping_host_async(context.args[0]))

async def health_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID: return
    try:
        import psutil; cpu=psutil.cpu_percent(0.5); ram=psutil.virtual_memory()
        bar=lambda p:"🟩"*int(p/10)+"⬜"*(10-int(p/10))
        text=(f"⚙️ <b>وضعیت سرور</b>\n🧠 CPU: {cpu:.1f}% {bar(cpu)}\n"
              f"📟 RAM: {ram.percent:.1f}% {bar(ram.percent)}\n"
              f"📦 کش: {len(CONFIG_CACHE['configs']):,}\n🌐 {BASE_URL}")
    except: text=f"📦 کش: {len(CONFIG_CACHE['configs']):,}\n🌐 {BASE_URL}"
    await update.message.reply_text(text,parse_mode='HTML')

async def admin_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID:
        await update.message.reply_text("⛔ دسترسی ندارید."); return
    await update.message.reply_text("🔐 <b>پنل ادمین</b>",parse_mode='HTML',
                                    reply_markup=admin_panel_keyboard())

async def makevip_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID: return
    if not context.args: await update.message.reply_text("/makevip [id]"); return
    try:
        uid=int(context.args[0]); u=get_user(uid); u["is_vip"]=True; save_user(uid,u)
        await update.message.reply_text(f"✅ <code>{uid}</code> VIP شد.",parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ {e}")

async def unvip_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID: return
    if not context.args: await update.message.reply_text("/unvip [id]"); return
    try:
        uid=int(context.args[0]); u=get_user(uid); u["is_vip"]=False; save_user(uid,u)
        await update.message.reply_text(f"✅ <code>{uid}</code> از VIP خارج شد.",parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ {e}")

async def viplist_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID: return
    vips=[u for u in get_all_users_info() if u.get("is_vip")]
    if not vips: await update.message.reply_text("👑 هیچ VIPی ندارید."); return
    text="👑 <b>VIPها:</b>\n"+"\n".join([f"• <code>{v['uid']}</code>" for v in vips])
    await update.message.reply_text(text,parse_mode='HTML')

async def addconfig_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID: return
    cfg=" ".join(context.args) if context.args else ""
    if not cfg and update.message.reply_to_message: cfg=update.message.reply_to_message.text or ""
    if not cfg or not any(cfg.startswith(p+"://") for p in PROTOCOLS):
        await update.message.reply_text("❌ /addconfig vless://..."); return
    cfgs=load_custom_configs()
    if cfg in cfgs: await update.message.reply_text("⚠️ قبلاً اضافه شده."); return
    cfgs.append(cfg); save_custom_configs(cfgs)
    await update.message.reply_text(f"✅ اضافه شد! ({len(cfgs)} کانفیگ)")

async def postchannel_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID: return
    msg=await update.message.reply_text("📢...")
    ok=await send_to_channel(context.bot)
    await msg.edit_text("✅ ارسال شد." if ok else "❌ خطا.")

async def addgroup_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID: return
    cid=update.effective_chat.id; db=load_json("groups",{"list":[]})
    if cid not in db["list"]: db["list"].append(cid); save_json("groups",db)
    await update.message.reply_text(f"✅ گروه <code>{cid}</code> اضافه شد.",parse_mode='HTML')

async def removegroup_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID: return
    cid=update.effective_chat.id; db=load_json("groups",{"list":[]})
    if cid in db["list"]: db["list"].remove(cid); save_json("groups",db)
    await update.message.reply_text("✅ گروه حذف شد.")

async def grouplist_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID: return
    lst=load_json("groups",{"list":[]}).get("list",[])
    text="📡 <b>گروه‌ها:</b>\n"+("\n".join([f"• <code>{g}</code>" for g in lst]) or "ندارد")
    await update.message.reply_text(text,parse_mode='HTML')

async def backup_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID: return
    for key in ["stats","users","groups","referrals"]:
        p=FILES[key]
        if os.path.exists(p):
            with open(p,'rb') as f:
                await context.bot.send_document(ADMIN_ID,document=f,filename=os.path.basename(p))

async def logs_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID: return
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE,'rb') as f:
            await context.bot.send_document(ADMIN_ID,document=f,filename="bot.log")

# ══════════════════════════════════════════════
# Admin Callback
# ══════════════════════════════════════════════
async def handle_admin_callback(query,context):
    data=query.data; uid=query.from_user.id
    if uid!=ADMIN_ID: await query.answer("⛔ فقط ادمین",show_alert=True); return
    if data=="adm_stats":
        g=load_json("stats",DEFAULT_STATS)
        h7=sorted(g.get("daily",{}).items())[-7:]
        hist="\n".join([f"  {d}: {c}" for d,c in h7]) or "  ندارد"
        await query.message.reply_text(
            f"📊 <b>آمار</b>\n👥 {g.get('users',0)} | 📤 {g.get('total_requests',0):,}\n"
            f"📦 ارسالی: {g.get('total_configs_sent',0):,} | 💾 کش: {len(CONFIG_CACHE['configs']):,}\n"
            f"📅 ۷ روز:\n{hist}",parse_mode='HTML')
    elif data=="adm_users":
        users=get_all_users_info()[:15]
        lines=[f"{i}. {'👑' if u.get('is_vip') else '👤'} {u.get('first_name') or '—'} "
               f"(<code>{u['uid']}</code>) {u.get('total_requests',0)}req"
               for i,u in enumerate(users,1)]
        await query.message.reply_text("👥 <b>کاربران:</b>\n"+"\n".join(lines),parse_mode='HTML')
    elif data=="adm_viplist":
        vips=[u for u in get_all_users_info() if u.get("is_vip")]
        if not vips: await query.message.reply_text("👑 ندارید."); return
        await query.message.reply_text("👑 <b>VIP:</b>\n"+
            "\n".join([f"• <code>{v['uid']}</code>" for v in vips]),parse_mode='HTML')
    elif data=="adm_groups":
        lst=load_json("groups",{"list":[]}).get("list",[])
        await query.message.reply_text("📡 <b>گروه‌ها:</b>\n"+
            ("\n".join([f"• <code>{g}</code>" for g in lst]) or "ندارد"),parse_mode='HTML')
    elif data=="adm_postchannel":
        ok=await send_to_channel(context.bot)
        await query.message.reply_text("✅ ارسال شد." if ok else "❌ خطا.")
    elif data=="adm_backup":
        for key in ["stats","users","groups","referrals"]:
            p=FILES[key]
            if os.path.exists(p):
                with open(p,'rb') as f:
                    await context.bot.send_document(ADMIN_ID,document=f,filename=os.path.basename(p))
    elif data=="adm_addvip":
        context.user_data['waiting_for']='add_vip'
        await query.message.reply_text("✅ آیدی کاربر را ارسال کنید:")
    elif data=="adm_removevip":
        context.user_data['waiting_for']='remove_vip'
        await query.message.reply_text("❌ آیدی کاربر را ارسال کنید:")
    elif data=="adm_clearcache":
        CONFIG_CACHE['configs']=[]; CONFIG_CACHE['last_update']=0
        await query.message.reply_text("🗑️ کش پاک شد.")
    elif data=="adm_refreshcache":
        await query.message.reply_text("🔄 در حال آپدیت...")
        await update_cache()
        await query.message.reply_text(f"✅ کش آپدیت: <b>{len(CONFIG_CACHE['configs']):,}</b>",parse_mode='HTML')
    elif data=="adm_health":
        try:
            import psutil; cpu=psutil.cpu_percent(0.5); ram=psutil.virtual_memory()
            bar=lambda p:"🟩"*int(p/10)+"⬜"*(10-int(p/10))
            text=f"⚙️ CPU: {cpu:.1f}% {bar(cpu)}\n📟 RAM: {ram.percent:.1f}% {bar(ram.percent)}\n📦 {len(CONFIG_CACHE['configs']):,}"
        except: text=f"📦 کش: {len(CONFIG_CACHE['configs']):,}\n🌐 {BASE_URL}"
        await query.message.reply_text(text,parse_mode='HTML')
    elif data=="adm_logs":
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE,'rb') as f:
                await context.bot.send_document(ADMIN_ID,document=f,filename="bot.log")

# ══════════════════════════════════════════════
# Main Callback Handler — ✅ کیبورد بعد از کلیک حذف میشه
# ══════════════════════════════════════════════
async def remove_kb(query):
    """✅ حذف کیبورد از پیام قبلی"""
    try: await query.edit_message_reply_markup(reply_markup=None)
    except Exception: pass

async def handle_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    query=update.callback_query
    await query.answer()
    data=query.data; uid=query.from_user.id

    if data=="noop_info": return
    if data.startswith("adm_"):
        await handle_admin_callback(query,context); return

    # ── کانفیگ رایگان ──
    if data=="free_config":
        await remove_kb(query)
        await query.message.reply_text(
            "🆓 <b>کانفیگ رایگان</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚡ <b>ویژه</b> — منابع گزیده، سرعت بالا\n"
            "🌊 <b>انبوه</b> — تمامی منابع، حجم بالاتر\n"
            "📡 <b>ذخیره‌شده</b> — آپدیت هر ۳۰ دقیقه\n\n"
            "👇 انتخاب کن:",
            parse_mode='HTML',reply_markup=free_config_keyboard()); return

    elif data=="fc_special":
        await remove_kb(query)
        await query.message.reply_text("⚡ <b>کانفیگ ویژه</b> — تعداد انتخاب کن:",
            parse_mode='HTML',reply_markup=count_format_keyboard("special")); return
    elif data=="fc_bulk":
        await remove_kb(query)
        await query.message.reply_text("🌊 <b>کانفیگ انبوه</b> — تعداد انتخاب کن:",
            parse_mode='HTML',reply_markup=count_format_keyboard("bulk")); return
    elif data=="fc_cached":
        await remove_kb(query)
        await query.message.reply_text("📡 <b>کانفیگ ذخیره‌شده</b> — تعداد انتخاب کن:",
            parse_mode='HTML',reply_markup=count_format_keyboard("cache")); return

    # ── دکمه‌های اصلی ──
    elif data=="get_configs":
        await remove_kb(query)
        await query.message.reply_text("📦 <b>دریافت از کش</b> — تعداد انتخاب کن:",
            parse_mode='HTML',reply_markup=count_format_keyboard("cache")); return
    elif data=="live_scan":
        await remove_kb(query)
        await query.message.reply_text("⚡ <b>اسکن لحظه‌ای</b> — تعداد انتخاب کن:",
            parse_mode='HTML',reply_markup=count_format_keyboard("live")); return

    # ✅ پردازش کانفیگ — gc/ls/gs/gb
    elif (data.startswith("gc_") or data.startswith("ls_") or
          data.startswith("gs_") or data.startswith("gb_")):
        parts=data.split("_")
        if len(parts)!=3: await query.answer("❌ خطا",show_alert=True); return
        src,cnt_s,fmt=parts
        try: count=int(cnt_s)
        except: count=10
        as_json=(fmt=="j")
        await remove_kb(query)
        if is_spamming(uid):
            await query.message.reply_text(f"⚠️ صبر کن {RATE_LIMIT_SECS:.0f}ثانیه."); return
        ok,msg_txt=check_limit(uid)
        if not ok: await query.message.reply_text(msg_txt); return
        u=get_user(uid)
        if src=="gs":
            pm=await query.message.reply_text("⚡ دریافت از منابع ویژه...")
            fresh=await fetch_configs_fresh(SPECIAL_SOURCES); await pm.delete()
            cfgs=filter_configs(fresh,u.get("protocol_filter","ALL"))
            all_cfgs=list(dict.fromkeys(load_custom_configs()+cfgs))
        elif src in ("gb","ls"):
            pm=await query.message.reply_text(
                "🌊 اسکن تمام منابع..." if src=="gb" else "⚡ اسکن لحظه‌ای...")
            try:
                db=load_json("sources",{"list":DEFAULT_SOURCES})
                await update_cache(db.get("list",DEFAULT_SOURCES))
            except Exception as e: logger.error(e)
            await pm.delete()
            cfgs=filter_configs(CONFIG_CACHE['configs'],u.get("protocol_filter","ALL"))
            all_cfgs=list(dict.fromkeys(load_custom_configs()+cfgs))
        else:
            cfgs=filter_configs(CONFIG_CACHE['configs'],u.get("protocol_filter","ALL"))
            all_cfgs=list(dict.fromkeys(load_custom_configs()+cfgs))
        pmap={"gs":"special","gb":"bulk","ls":"live","gc":"cache"}
        await send_configs_to_msg(query.message,all_cfgs,
            count=count if count else len(all_cfgs),as_json=as_json,prefix=pmap.get(src,"configs"))
        return

    # ── فیلتر کشور ──
    elif data=="country_filter":
        await remove_kb(query)
        await query.message.reply_text("🌍 <b>فیلتر کشور</b> — انتخاب کن:",
            parse_mode='HTML',reply_markup=country_keyboard()); return
    elif data=="cf_all":
        await remove_kb(query)
        countries=get_available_countries(CONFIG_CACHE['configs'])
        if not countries:
            await query.message.reply_text("❌ کانفیگ کشوری در کش نیست.\n💡 اسکن لحظه‌ای بزن."); return
        await query.message.reply_text(
            f"🌍 <b>{sum(countries.values()):,} کانفیگ کشوری موجود</b> — انتخاب کن:",
            parse_mode='HTML',reply_markup=all_countries_keyboard(CONFIG_CACHE['configs'])); return
    elif data.startswith("cf_"):
        cc=data[3:]
        flag,name=COUNTRY_MAP.get(cc,('🌍',cc.upper()))
        avail=filter_by_country(CONFIG_CACHE['configs'],cc)
        await remove_kb(query)
        if not avail:
            await query.message.reply_text(f"❌ کانفیگ {flag}{name} در کش نیست."); return
        await query.message.reply_text(
            f"{flag} <b>{name}</b> — {len(avail):,} کانفیگ — فرمت انتخاب کن:",
            parse_mode='HTML',reply_markup=country_action_keyboard(cc)); return
    elif data.startswith("cget_"):
        parts=data.split("_")
        if len(parts)!=4: await query.answer("❌",show_alert=True); return
        _,cc,cnt_s,fmt=parts
        flag,name=COUNTRY_MAP.get(cc,('🌍',cc.upper()))
        try: count=int(cnt_s)
        except: count=10
        as_json=(fmt=="j")
        await remove_kb(query)
        if is_spamming(uid): await query.message.reply_text(f"⚠️ {RATE_LIMIT_SECS:.0f}ثانیه."); return
        ok,msg_txt=check_limit(uid)
        if not ok: await query.message.reply_text(msg_txt); return
        filtered=filter_by_country(CONFIG_CACHE['configs'],cc)
        if not filtered:
            await query.message.reply_text(f"❌ {flag}{name} یافت نشد."); return
        await send_configs_to_msg(query.message,filtered,
            count=count if count else len(filtered),as_json=as_json,prefix=f"country_{cc}"); return

    # ── اشتراک هوشمند ──
    elif data=="sub_link_smart":
        await remove_kb(query)
        u=get_user(uid); tok=u.get("sub_token","")
        lnk=f"{BASE_URL}/sub/{uid}/{tok}"
        await query.message.reply_text(
            f"🔗 <b>اشتراک هوشمند</b>\n\n<code>{lnk}</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <b>چرا اشتراک؟</b>\n"
            "یک‌بار ثبت کن — خودِ برنامه هر ۳۱ دقیقه آپدیت می‌کند ✅\n\n"
            "📲 v2rayNG/NekoBox ← افزودن اشتراک ← Paste ← Update\n\n"
            f"🔐 پلین: <code>{lnk}?plain=1</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت",callback_data="back_start")]])); return

    # ── گزینه‌های دیگر ──
    elif data=="random_cfg":
        await remove_kb(query)
        ok,msg_txt=check_limit(uid)
        if not ok: await query.message.reply_text(msg_txt); return
        u=get_user(uid)
        pool=load_custom_configs()+filter_configs(CONFIG_CACHE['configs'],u.get("protocol_filter","ALL"))
        if pool:
            cfg=random.choice(pool)
            await query.message.reply_text(f"🎲 <b>کانفیگ تصادفی:</b>\n\n<code>{cfg}</code>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 دیگری",callback_data="random_cfg"),
                    InlineKeyboardButton("🔙 بازگشت",callback_data="back_start")]]))
        else: await query.message.reply_text("❌ کش خالی.")

    elif data=="admin_cfgs":
        await remove_kb(query)
        customs=load_custom_configs()
        if not customs: await query.message.reply_text("ℹ️ کانفیگ ادمین ندارد."); return
        txt="🔐 <b>کانفیگ‌های ادمین:</b>\n\n"
        for i,c in enumerate(customs[:5],1): txt+=f"{i}. <code>{c}</code>\n\n"
        await query.message.reply_text(txt,parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت",callback_data="back_start")]]))

    elif data=="filter_proto":
        await remove_kb(query)
        u=get_user(uid)
        await query.message.reply_text(
            f"🔧 پروتکل فعلی: <b>{u.get('protocol_filter','ALL')}</b>",
            parse_mode='HTML',reply_markup=proto_keyboard())

    elif data.startswith("proto_"):
        proto=data.split("_",1)[1]; u=get_user(uid)
        u["protocol_filter"]=proto; save_user(uid,u)
        await remove_kb(query)
        await query.message.reply_text(f"✅ پروتکل: <b>{proto}</b>",parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت",callback_data="back_start")]]))

    elif data=="web_dash":
        await remove_kb(query)
        u=get_user(uid); tok=u.get("sub_token","")
        url=f"{BASE_URL}/panel/{uid}/{tok}"
        await query.message.reply_text(
            f"🌐 <b>داشبورد:</b>\n{url}\n\n🔔 <b>ساب:</b>\n<code>{BASE_URL}/sub/{uid}/{tok}</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🌐 باز کردن",url=url)]]))

    elif data=="my_stats":
        await remove_kb(query)
        u=get_user(uid); vip=u.get("is_vip") or uid==ADMIN_ID
        tot=3+u.get("bonus_limit",0)
        await query.message.reply_text(
            f"📊 <b>آمار من</b>\n{'👑 VIP' if vip else '👤 عادی'}\n"
            f"📅 امروز: {u.get('daily_requests',0)}/{'∞' if vip else tot}\n"
            f"📦 کل: {u.get('total_requests',0):,} | 🎁 بونوس: +{u.get('bonus_limit',0)}\n"
            f"🔧 {u.get('protocol_filter','ALL')}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت",callback_data="back_start")]]))

    elif data=="global_stats":
        await remove_kb(query)
        g=load_json("stats",DEFAULT_STATS)
        lu=(datetime.fromtimestamp(CONFIG_CACHE['last_update'],TEHRAN_TZ).strftime('%H:%M')
            if CONFIG_CACHE['last_update'] else "هنوز نشده")
        await query.message.reply_text(
            f"🏆 <b>آمار کل</b>\n👥 {g.get('users',0)} | 📤 {g.get('total_requests',0):,}\n"
            f"📦 ارسالی: {g.get('total_configs_sent',0):,} | 💾 کش: {len(CONFIG_CACHE['configs']):,}\n"
            f"🕐 آپدیت: {lu}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت",callback_data="back_start")]]))

    elif data=="invite":
        await remove_kb(query)
        info=await context.bot.get_me()
        link=f"https://t.me/{info.username}?start=ref_{uid}"
        u=get_user(uid); refs=load_json("referrals",{})
        await query.message.reply_text(
            f"🎁 <b>دعوت دوستان</b>\n🔗 <code>{link}</code>\n"
            f"👥 {len(refs.get(str(uid),[]))} دعوت | 💡 +{u.get('bonus_limit',0)} بونوس",
            parse_mode='HTML')

    elif data=="help":
        await remove_kb(query)
        text=("📖 <b>راهنمای کامل</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
              "🆓 رایگان: ⚡ویژه | 🌊انبوه | 📡ذخیره‌شده\n"
              "📦 کش | ⚡ لحظه‌ای | 🎲 تصادفی\n"
              "🌍 فیلتر کشور | 🔧 فیلتر پروتکل\n"
              "🔗 اشتراک هوشمند\n"
              "🧹 حذف تکراری+خراب خودکار\n"
              "🤖 /ask | 🏓 /ping\n\n"
              "👤 ۳/روز | 👑 VIP: نامحدود")
        await query.message.reply_text(text,parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت",callback_data="back_start")]]))

    elif data=="back_start":
        await remove_kb(query)
        g=load_json("stats",DEFAULT_STATS); u=get_user(uid)
        vip=u.get("is_vip") or uid==ADMIN_ID
        await query.message.reply_text(
            f"✨ <b>Config Collector Bot</b>\n"
            f"📦 کش: {len(CONFIG_CACHE['configs']):,} | 👥 {g.get('users',0)}\n"
            f"{'♾️ VIP' if vip else f'{3+u.get(chr(98)+chr(111)+chr(110)+chr(117)+chr(115)+chr(95)+chr(108)+chr(105)+chr(109)+chr(105)+chr(116),0)}/روز'}",
            parse_mode='HTML',reply_markup=start_keyboard())

# ══════════════════════════════════════════════
# handle_text + Channel + Jobs + main
# ══════════════════════════════════════════════
async def handle_text(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type!="private": return
    uid=update.effective_user.id; text=update.message.text.strip()
    waiting=context.user_data.get('waiting_for')
    if uid==ADMIN_ID and waiting:
        context.user_data['waiting_for']=None
        try:
            tid=int(text.strip()); u=get_user(tid)
            if waiting=='add_vip': u["is_vip"]=True; save_user(tid,u)
            elif waiting=='remove_vip': u["is_vip"]=False; save_user(tid,u)
            action="VIP شد" if waiting=='add_vip' else "از VIP خارج شد"
            await update.message.reply_text(f"✅ <code>{tid}</code> {action}.",parse_mode='HTML')
        except: await update.message.reply_text("❌ آیدی نامعتبر.")
        return
    extracted=extract_configs(text)
    if extracted:
        await send_configs_to_msg(update.message,extracted,count=len(extracted),prefix="extracted")
        return
    if is_spamming(uid):
        await update.message.reply_text(f"⚠️ {RATE_LIMIT_SECS:.0f}ثانیه صبر کن."); return
    add_stat("total_requests")
    update_user_info(uid,update.effective_user.username or "",update.effective_user.first_name or "")
    await update.message.reply_text("💬 دستور ناشناخته. /start",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 منو",callback_data="back_start")]]))

# ══ رنگ‌های متنوع برای کانال ══
CHAN_COLORS=["🔴","🟠","🟡","🟢","🔵","🟣","🔶","🔷","🟤","⚫","🔴","🟢"]

async def send_to_channel(bot)->bool:
    try:
        if not CONFIG_CACHE['configs']: return False
        sel=random.sample(CONFIG_CACHE['configs'],min(6,len(CONFIG_CACHE['configs'])))
        random.shuffle(CHAN_COLORS)
        # ✅ FIX: کانفیگ کامل ارسال میشه
        cfgs="\n\n".join([f"{CHAN_COLORS[i%len(CHAN_COLORS)]} <code>{c}</code>"
                           for i,c in enumerate(sel)])
        ts=datetime.now(TEHRAN_TZ).strftime("%H:%M")
        now_date=datetime.now(TEHRAN_TZ).strftime("%d %b")
        text=(f"📡 <b>کانفیگ‌های تازه</b> — {now_date} ساعت {ts}\n"
              "━━━━━━━━━━━━━━━━━━━━━\n\n"
              f"{cfgs}\n\n"
              f"━━━━━━━━━━━━━━━━━━━━━\n"
              f"🤖 {BOT_USERNAME} | 📦 {len(CONFIG_CACHE['configs']):,} کانفیگ در کش")
        # بررسی طول پیام (Telegram حداکثر 4096 کاراکتر)
        if len(text)>4000:
            sel=sel[:3]; cfgs="\n\n".join([f"{CHAN_COLORS[i]} <code>{c}</code>" for i,c in enumerate(sel)])
            text=(f"📡 <b>کانفیگ‌های تازه</b> — {ts}\n━━━━━━━━━━━━━━━━━━━━━\n\n"
                  f"{cfgs}\n\n🤖 {BOT_USERNAME}")
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("📥 دریافت بیشتر",
            url=f"https://t.me/{BOT_USERNAME.lstrip('@')}")]])
        await bot.send_message(chat_id=CHANNEL_ID,text=text,parse_mode='HTML',reply_markup=kb)
        return True
    except Exception as e:
        logger.warning(f"Channel: {e}"); return False

async def send_to_groups(bot)->int:
    db=load_json("groups",{"list":[]}); groups=db.get("list",[])
    if not groups or not CONFIG_CACHE['configs']: return 0
    sel=random.sample(CONFIG_CACHE['configs'],min(4,len(CONFIG_CACHE['configs'])))
    cfgs="\n\n".join([f"<code>{c}</code>" for c in sel])
    text=(f"🛰️ <b>کانفیگ تازه</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n{cfgs}\n\n🤖 {BOT_USERNAME}")
    ok_count=0; to_remove=[]
    for gid in groups:
        try: await bot.send_message(gid,text,parse_mode='HTML'); ok_count+=1; await asyncio.sleep(0.3)
        except Exception as e:
            if any(x in str(e).lower() for x in ["kicked","blocked","forbidden","not found"]): to_remove.append(gid)
    if to_remove: db["list"]=[g for g in groups if g not in to_remove]; save_json("groups",db)
    return ok_count

async def job_cache_refresh(context:ContextTypes.DEFAULT_TYPE):
    await update_cache()

async def job_auto_channel(context:ContextTypes.DEFAULT_TYPE):
    if CONFIG_CACHE['configs']: await send_to_channel(context.bot)

async def job_auto_groups(context:ContextTypes.DEFAULT_TYPE):
    await send_to_groups(context.bot)

async def job_source_report(context:ContextTypes.DEFAULT_TYPE):
    db=load_json("sources",{"list":DEFAULT_SOURCES}); sources=db.get("list",DEFAULT_SOURCES)
    stats=load_json("stats",DEFAULT_STATS); ts=datetime.now(TEHRAN_TZ).strftime("%H:%M")
    active=0; errors=[]
    connector=aiohttp.TCPConnector(ssl=False,limit=8)
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            for url in sources[:15]:
                try:
                    async with session.head(url,timeout=aiohttp.ClientTimeout(total=6),ssl=False) as r:
                        if r.status<400: active+=1
                        else: errors.append(f"• {url.split('/')[-1][:25]} [{r.status}]")
                except: errors.append(f"• {url.split('/')[-1][:25]} ❌")
    except Exception as e: logger.error(f"report: {e}"); return
    err_txt=("\n⚠️ <b>خطادار:</b>\n"+"\n".join(errors[:5])) if errors else ""
    text=(f"📊 <b>گزارش منابع</b> {ts}\n━━━━━━━━━━━━━━━━━━━\n"
          f"✅ فعال: {active}/15 | ❌ خطا: {len(errors)}\n"
          f"💾 کش: {len(CONFIG_CACHE['configs']):,} | 👥 {stats.get('users',0)}"+err_txt)
    try: await context.bot.send_message(ADMIN_ID,text,parse_mode='HTML')
    except Exception as e: logger.error(f"report send: {e}")

async def job_daily_backup(context:ContextTypes.DEFAULT_TYPE):
    for key in ["stats","users","groups","referrals"]:
        p=FILES[key]
        if os.path.exists(p):
            try:
                with open(p,'rb') as f:
                    await context.bot.send_document(ADMIN_ID,document=f,
                        filename=os.path.basename(p),caption=f"🗄️ بکاپ — {key}")
            except: pass

def main():
    threading.Thread(target=run_flask,daemon=True).start()
    logger.info(f"🌐 Flask PORT:{PORT} BASE_URL:{BASE_URL}")
    app=Application.builder().token(TOKEN).build()
    for cmd,handler in [
        ("admin",admin_cmd),("makevip",makevip_cmd),("unvip",unvip_cmd),
        ("viplist",viplist_cmd),("addconfig",addconfig_cmd),("postchannel",postchannel_cmd),
        ("addgroup",addgroup_cmd),("removegroup",removegroup_cmd),("grouplist",grouplist_cmd),
        ("backup",backup_cmd),("logs",logs_cmd),("health",health_cmd),
        ("start",start_cmd),("help",help_cmd),("myid",myid_cmd),
        ("invite",invite_cmd),("ask",ask_cmd),("ping",ping_cmd),
    ]:
        app.add_handler(CommandHandler(cmd,handler))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,handle_text))
    sett=load_json("settings",DEFAULT_SETTINGS)
    app.job_queue.run_once(job_cache_refresh,when=5)
    app.job_queue.run_repeating(job_cache_refresh,interval=sett.get("cache_interval",1800),first=30)
    app.job_queue.run_repeating(job_auto_channel,interval=sett.get("channel_interval",600),first=60)
    app.job_queue.run_repeating(job_auto_groups,interval=sett.get("group_interval",10800),first=120)
    app.job_queue.run_repeating(job_source_report,interval=10800,first=300)
    tz=pytz.timezone('Asia/Tehran')
    app.job_queue.run_daily(job_daily_backup,
        time=datetime.now(tz).replace(hour=23,minute=30,second=0).timetz())
    logger.info("🚀 Bot v6.0 FIXED — RUNNING")
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    main()
