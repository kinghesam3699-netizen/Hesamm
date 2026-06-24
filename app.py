import os
import re
import io
import json
import time
import base64
import random
import logging
import socket
import asyncio
import aiohttp
import geoip2.database
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import urlparse
from tenacity import retry, stop_after_attempt, wait_exponential
import pytz

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
import aiosqlite
# تنظیم لوکال لاگر با خروجی استاندارد سازگار با پلتفرم Railway
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class Config:
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    ADMIN_ID = os.environ.get("ADMIN_ID", "8136134031")
    CHANNEL_ID = os.environ.get("CHANNEL_ID", "")
    
    CACHE_REFRESH_INTERVAL = int(os.environ.get("CACHE_REFRESH_INTERVAL", 1200))
    CHANNEL_POST_INTERVAL = int(os.environ.get("CHANNEL_POST_INTERVAL", 300))
    
    MAX_DAILY_REQUESTS = int(os.environ.get("MAX_DAILY_REQUESTS", 5))
    MAX_DAILY_CONFIGS = int(os.environ.get("MAX_DAILY_CONFIGS", 50))
    MAX_CONFIGS_PER_REQUEST = int(os.environ.get("MAX_CONFIGS_PER_REQUEST", 50000))
    
    CHANNEL_FILTER_PROTOCOL = os.environ.get("CHANNEL_FILTER_PROTOCOL", "VLESS").upper()
    CHANNEL_FILTER_COUNTRIES = [
        c.strip().lower() for c in os.environ.get("CHANNEL_FILTER_COUNTRIES", "de,nl,fi,se,fr,gb,us,ca").split(",") if c.strip()
    ]
    
    GEOIP_DB_PATH = os.environ.get("GEOIP_DB_PATH", "GeoLite2-Country.mmdb")
    DB_PATH = "bot_database.db"

    @classmethod
    def validate(cls):
        if not cls.BOT_TOKEN:
            logger.critical("❌ خطای متغیر محیطی: BOT_TOKEN یافت نشد!")
            raise ValueError("BOT_TOKEN تنظیم نشده است.")
        if not cls.ADMIN_ID:
            logger.critical("❌ خطای متغیر محیطی: ADMIN_ID یافت نشد!")
            raise ValueError("ADMIN_ID تنظیم نشده است.")
        logger.info("✅ اعتبارسنجی متغیرهای محیطی سیستم با موفقیت انجام شد.")
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
    "https://mifa.world/ss",
    "https://mifa.world/trojan",
    "https://mifa.world/hysteria",
    "https://mifa.world/other",
    "https://mifa.world/vmess",
    "https://mifa.world/vless",
    "https://empty-mouse-fbb7.alizareh4024.workers.dev/sync?sub=%D8%B3%D9%88%D8%B3%D9%85%D8%A7%D8%B1%F0%9F%A6%8E",
    "https://raw.githubusercontent.com/pytimusprime/FreeV2ray/refs/heads/main/all_servers.txt",
    "https://raw.githubusercontent.com/ThomasJasperthecat/sub/main/sublist1.txt",
    "https://raw.githubusercontent.com/masir-sefid/Sub/main/@Masir_Sefid.txt",
    "https://sub.iampedi5.live/sub/base64.txt",
    "https://sub.whitedns.one/sub/mihomo.yaml",
    "http://main.pythash.tr/FRkh99yBGCllN/01736620-2086-4c0b-a86e-52ebfe64dd12/#pythash",
    "https://raw.githubusercontent.com/masir-sefid/Sub/main/Telegram-Channel-@Masir_Sefid.txt",
    "https://c6et83fe1u99lr8j5w4s9iwik9565bqx.pages.dev/sub/fragment/g4lWgI*%40zehfoOEK?app=xray",
    "https://raw.githubusercontent.com/AmyraxVPN-Main/AmyraxVPN/refs/heads/main/AmyraxVPN.txt",
    "https://raw.githubusercontent.com/arshiacomplus/v2rayExtractor/refs/heads/main/mix/sub.html",
    "https://raw.githubusercontent.com/MahsaNetConfigTopic/config/refs/heads/main/xray_final.txt",
    "https://raw.githubusercontent.com/10ium/free-config/refs/heads/main/free-mihomo-sub/MultiCountryNoRule.yaml",
    "https://raw.githubusercontent.com/10ium/free-config/refs/heads/main/free-mihomo-sub/freedom_house_countries__NoRule.yaml",
    "https://sub.elitev2.ir:88/sub/djMsNDEsMTc4MTc5NDQ4Ng2eb707f649"
]
class DatabaseManager:
    @staticmethod
    async def init_db():
        async with aiosqlite.connect(Config.DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS prefs (
                    user_id INTEGER PRIMARY KEY,
                    protocol TEXT DEFAULT 'ALL',
                    country TEXT DEFAULT 'ALL',
                    awaiting_count INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    enabled INTEGER DEFAULT 1,
                    fail_count INTEGER DEFAULT 0,
                    last_fail_time REAL DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS daily_usage (
                    user_id INTEGER,
                    date TEXT,
                    requests_count INTEGER DEFAULT 0,
                    configs_received INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, date)
                )
            """)
            await db.commit()
        logger.info("⚙️ ساختار دیتابیس SQLite با موفقیت آماده‌سازی شد.")
    @staticmethod
    async def populate_default_sources(default_sources_list):
        async with aiosqlite.connect(Config.DB_PATH) as db:
            async with db.execute("SELECT COUNT(*) FROM sources") as cursor:
                count = (await cursor.fetchone())[0]
            if count == 0:
                logger.info("📥 تزریق خودکار سورس‌های مخازن پیش‌فرض آغاز شد...")
                for url in default_sources_list:
                    try:
                        await db.execute("INSERT OR IGNORE INTO sources (url, enabled) VALUES (?, 1)", (url,))
                    except Exception as e:
                        logger.error(f"خطای جدی در ثبت سورس اولیه: {e}")
                await db.commit()
                logger.info("✅ فرآیند تزریق سورس‌ها پایان یافت.")

    @staticmethod
    async def get_user_prefs(user_id: int) -> dict:
        async with aiosqlite.connect(Config.DB_PATH) as db:
            async with db.execute("SELECT protocol, country, awaiting_count FROM prefs WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {"protocol": row[0], "country": row[1], "awaiting_count": bool(row[2])}
                await db.execute("INSERT INTO prefs (user_id) VALUES (?)", (user_id,))
                await db.commit()
                return {"protocol": "ALL", "country": "ALL", "awaiting_count": False}
    @staticmethod
    async def set_user_pref(user_id: int, key: str, value) -> None:
        async with aiosqlite.connect(Config.DB_PATH) as db:
            if key == "protocol":
                await db.execute("UPDATE prefs SET protocol = ? WHERE user_id = ?", (value, user_id))
            elif key == "country":
                await db.execute("UPDATE prefs SET country = ? WHERE user_id = ?", (value, user_id))
            elif key == "awaiting_count":
                await db.execute("UPDATE prefs SET awaiting_count = ? WHERE user_id = ?", (1 if value else 0, user_id))
            await db.commit()

    @staticmethod
    async def check_rate_limit(user_id: int) -> tuple:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        async with aiosqlite.connect(Config.DB_PATH) as db:
            async with db.execute(
                "SELECT requests_count, configs_received FROM daily_usage WHERE user_id = ? AND date = ?", 
                (user_id, today)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row[0], row[1]
                return 0, 0

    @staticmethod
    async def increment_usage(user_id: int, configs_count: int) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        async with aiosqlite.connect(Config.DB_PATH) as db:
            await db.execute("""
                INSERT INTO daily_usage (user_id, date, requests_count, configs_received)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(user_id, date) DO UPDATE SET
                    requests_count = requests_count + 1,
                    configs_received = configs_received + ?
            """, (user_id, today, configs_count, configs_count))
            await db.commit()
    @staticmethod
    async def add_source(url: str) -> bool:
        async with aiosqlite.connect(Config.DB_PATH) as db:
            try:
                await db.execute("INSERT INTO sources (url, enabled) VALUES (?, 1)", (url,))
                await db.commit()
                return True
            except Exception as e:
                logger.warning(f"عدم امکان ثبت سورس جدید [{url}]: {e}")
                return False

    @staticmethod
    async def remove_source(source_id: int) -> bool:
        async with aiosqlite.connect(Config.DB_PATH) as db:
            async with db.execute("SELECT id FROM sources WHERE id = ?", (source_id,)) as cursor:
                if not await cursor.fetchone():
                    return False
            await db.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            await db.commit()
            return True

    @staticmethod
    async def get_all_sources() -> list:
        async with aiosqlite.connect(Config.DB_PATH) as db:
            async with db.execute("SELECT id, url, enabled, fail_count, last_fail_time FROM sources") as cursor:
                return await cursor.fetchall()

    @staticmethod
    async def update_source_status(url: str, failed: bool) -> None:
        async with aiosqlite.connect(Config.DB_PATH) as db:
            if failed:
                await db.execute("UPDATE sources SET fail_count = fail_count + 1, last_fail_time = ? WHERE url = ?", (time.time(), url))
                await db.execute("UPDATE sources SET enabled = 0 WHERE url = ? AND fail_count >= 3", (url,))
            else:
                await db.execute("UPDATE sources SET fail_count = 0, last_fail_time = 0, enabled = 1 WHERE url = ?", (url,))
            await db.commit()

    @staticmethod
    async def dynamic_reenable_sources() -> None:
        cooldown = time.time() - 1800
        async with aiosqlite.connect(Config.DB_PATH) as db:
            await db.execute("UPDATE sources SET enabled = 1, fail_count = 0 WHERE enabled = 0 AND last_fail_time < ? AND fail_count >= 3", (cooldown,))
            await db.commit()
COUNTRY_MAP = {
    "de": ("🇩🇪", "آلمان"), "nl": ("🇳🇱", "هلند"), "fi": ("🇫🇮", "فنلاند"),
    "se": ("🇸🇪", "سوئد"), "fr": ("🇫🇷", "فرانسه"), "gb": ("🇬🇧", "انگلستان"),
    "us": ("🇺🇸", "آمریکا"), "ca": ("🇨🇦", "کانادا"), "jp": ("🇯🇵", "ژاپن"),
    "sg": ("🇸🇬", "سنگاپور"), "ru": ("🇷🇺", "روسیه"), "ua": ("🇺🇦", "اوکراین"),
    "br": ("🇧🇷", "برزیل"), "au": ("🇦🇺", "استرالیا"), "in": ("🇮🇳", "هند"),
    "kr": ("🇰🇷", "کره جنوبی"), "tr": ("🇹🇷", "ترکیه"), "at": ("🇦🇹", "اتریش"),
    "ch": ("🇨🇭", "سوئیس"), "pl": ("🇵🇱", "لهستان"), "cz": ("🇨🇿", "جمهوری چک"),
    "ro": ("🇷🇴", "رومانی"), "hu": ("🇭🇺", "مجارستان"), "lt": ("🇱🇹", "لیتوانی")
}

class CountryDetector:
    _reader = None
    try:
        if os.path.exists(Config.GEOIP_DB_PATH):
            _reader = geoip2.database.Reader(Config.GEOIP_DB_PATH)
            logger.info("🎯 پایگاه اطلاعات مکان‌سنجی GeoIP با موفقیت متصل شد.")
        else:
            logger.warning("⚠️ دیتابیس لوکال GeoIP یافت نشد. استفاده از شناسه متنی رشته‌ها فعال گردید.")
    except Exception as e:
        logger.warning(f"⚠️ خطای لود دیتابیس GeoIP (سوئیچ خودکار به لایه متنی): {e}")

    @staticmethod
    @lru_cache(maxsize=8192)
    def _sync_resolve_and_detect(hostname: str) -> str:
        if not hostname:
            return "ALL"
        
        if CountryDetector._reader:
            try:
                ip = socket.gethostbyname(hostname)
                response = CountryDetector._reader.country(ip)
                code = str(response.country.iso_code).lower()
                if code in COUNTRY_MAP:
                    return code
            except Exception as e:
                logger.debug(f"عدم تفکیک IP برای میزبان {hostname}: {e}")
                pass
        
        h_lower = hostname.lower()
        for code in COUNTRY_MAP.keys():
            if f".{code}" in h_lower or h_lower.endswith(f".{code}"):
                return code
        return "ALL"
    @classmethod
    async def resolve_and_detect(cls, hostname: str) -> str:
        try:
            # اعمال سقف زمان مجاز ۵ ثانیه‌ای جهت ممانعت از قفل شدن روال اجرای بات بر روی رکوردهای خراب DNS
            return await asyncio.wait_for(asyncio.to_thread(cls._sync_resolve_and_detect, hostname), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning(f"⏳ مهلت زمانی درخواست برطرف‌سازی آدرس دی‌ان‌اس برای [{hostname}] به پایان رسید.")
            return "ALL"
        except Exception as e:
            logger.debug(f"خطای پیش‌بینی نشده در متد نهایی تفکیک موقعیت: {e}")
            return "ALL"

    @classmethod
    async def parse_config_country(cls, config_str: str) -> str:
        search_str = config_str.lower()
        if search_str.startswith("vmess://"):
            try:
                b64_part = config_str[8:].strip()
                b64_part += "=" * ((4 - len(b64_part) % 4) % 4)
                data = json.loads(base64.b64decode(b64_part).decode('utf-8', errors='ignore'))
                search_str += " " + str(data.get("add", "")).lower() + " " + str(data.get("ps", "")).lower()
            except Exception as e:
                logger.debug(f"خطای تحلیل داده‌های متنی داخلی سورس VMESS: {e}")
                pass
        
        for code, (_, name) in COUNTRY_MAP.items():
            if name in search_str or f"-{code}" in search_str or f"_{code}" in search_str:
                return code

        host_match = re.search(r'@([^:/@\s]+)', config_str)
        if host_match:
            return await cls.resolve_and_detect(host_match.group(1))
            
        return "ALL"
class ConfigValidator:
    @staticmethod
    def is_valid(config_str: str) -> bool:
        config_str = config_str.strip()
        if not config_str:
            return False
            
        lower_uri = config_str.lower()
        try:
            if lower_uri.startswith("vless://") or lower_uri.startswith("trojan://") or lower_uri.startswith("tuic://"):
                return "@" in config_str and ":" in config_str
                
            elif lower_uri.startswith("vmess://"):
                b64_part = config_str[8:].strip()
                b64_part += "=" * ((4 - len(b64_part) % 4) % 4)
                decoded = base64.b64decode(b64_part).decode('utf-8', errors='ignore')
                data = json.loads(decoded)
                # استفاده ایمن از ساختار دایرکتوری .get جهت جلوگیری از بروز چالش سرریز کلیدواژه
                return data.get("add") is not None and data.get("port") is not None
                
            elif lower_uri.startswith("ss://"):
                return "@" in config_str or ":" in config_str
                
            elif lower_uri.startswith("hysteria2://") or lower_uri.startswith("hy2://"):
                return "@" in config_str
                
            elif lower_uri.startswith("wireguard://") or lower_uri.startswith("wg://"):
                return "@" in config_str or ":" in config_str
        except Exception as e:
            logger.warning(f"⚠️ خطای ساختاری غیرمجاز در اعتبارسنجی الگو کانفیگ: {e} | داده خام: {config_str[:60]}")
            return False
            
        return False
class SourceManager:
    @staticmethod
    def extract_raw_links(text: str) -> list:
        pattern = r'(?:vless|vmess|trojan|ss|hysteria2|hy2|tuic|wireguard|wg)://[^\s\n\r,"\'\]\[<>{}|\\^`]+'
        return re.findall(pattern, text, re.IGNORECASE)

    @staticmethod
    def try_decode_base64_safely(raw_text: str) -> str:
        cleaned = "".join(raw_text.split())
        if len(cleaned) < 20 or not re.match(r'^[A-Za-z0-9+/=_-]+$', cleaned):
            return ""
        cleaned += "=" * ((4 - len(cleaned) % 4) % 4)
        try:
            return base64.b64decode(cleaned).decode('utf-8', errors='ignore')
        except Exception as e:
            try:
                return base64.urlsafe_b64decode(cleaned.encode()).decode('utf-8', errors='ignore')
            except Exception as ex:
                logger.debug(f"عدم امکان مچ‌گیری دی‌کد Base64: {e} | لایه دوم: {ex}")
                return ""

    @classmethod
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
    async def fetch_with_retry(cls, session: aiohttp.ClientSession, url: str) -> str:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Xray/1.8.4"}
        async with session.get(url, headers=headers, timeout=15, ssl=False) as response:
            if response.status == 200:
                return await response.text()
            raise RuntimeError(f"HTTP Status {response.status}")
    @classmethod
    async def process_source(cls, session: aiohttp.ClientSession, url: str) -> list:
        extracted = []
        try:
            text = await cls.fetch_with_retry(session, url)
            raw_links = cls.extract_raw_links(text)
            
            decoded_text = cls.try_decode_base64_safely(text)
            if decoded_text:
                raw_links.extend(cls.extract_raw_links(decoded_text))

            for link in raw_links:
                if ConfigValidator.is_valid(link):
                    proto = link.split("://")[0].lower()
                    if proto == "hy2": proto = "hysteria2"
                    if proto == "wg": proto = "wireguard"
                    
                    country = await CountryDetector.parse_config_country(link)
                    extracted.append({"config": link, "protocol": proto, "country": country})

            await DatabaseManager.update_source_status(url, failed=False)
            return extracted
        except Exception as e:
            logger.warning(f"❌ چالش پایش اطلاعات منبع رخ داد [{url}]: {e}")
            await DatabaseManager.update_source_status(url, failed=True)
            return []
class CacheManager:
    CONFIG_CACHE = []
    LAST_UPDATE_TIME = "بروزرسانی نشده"
    IS_INITIAL_LOADING = True  # فلگ وضعیت بارگذاری اولیه پس‌زمینه برای افزایش سرعت لود اولیه Railway

    @classmethod
    async def reload_cache(cls) -> int:
        logger.info("🔄 روال هماهنگ‌سازی سراسری انبار کش سیستم آغاز شد...")
        try:
            await DatabaseManager.dynamic_reenable_sources()
            all_sources = await DatabaseManager.get_all_sources()
            active_urls = [row[1] for row in all_sources if row[2] == 1]
            
            new_cache = []
            seen = set()

            async with aiohttp.ClientSession() as session:
                tasks = [SourceManager.process_source(session, url) for url in active_urls]
                results = await asyncio.gather(*tasks)
                
                for res in results:
                    for item in res:
                        if item["config"] not in seen:
                            seen.add(item["config"])
                            new_cache.append(item)

            if new_cache:
                cls.CONFIG_CACHE = new_cache
                tehran_tz = pytz.timezone("Asia/Tehran")
                cls.LAST_UPDATE_TIME = datetime.now(tehran_tz).strftime("%H:%M:%S")
                logger.info(f"✨ انبار کش با موفقیت بازسازی شد. رکوردهای فعال زنده: {len(cls.CONFIG_CACHE)}")
        except Exception as e:
            logger.error(f"❌ خطای غیرمنتظره در بارگذاری و ریلود مجدد سیستم کش: {e}")
        finally:
            cls.IS_INITIAL_LOADING = False
        return len(cls.CONFIG_CACHE)

    @classmethod
    def get_filtered(cls, proto: str, country: str) -> list:
        res = cls.CONFIG_CACHE
        if proto != "ALL":
            res = [c for c in res if c["protocol"] == proto.lower()]
        if country != "ALL":
            res = [c for c in res if c["country"] == country.lower()]
        return [item["config"] for item in res]
def make_main_keyboard() -> InlineKeyboardMarkup:
    # چیدمان هوشمند دکمه‌های ناوبری اصلی بات تلگرام
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 دریافت هوشمند کانفیگ", callback_data="get_configs")],
        [
            InlineKeyboardButton("🔧 فیلتر پروتکل‌ها", callback_data="menu_proto"),
            InlineKeyboardButton("🌍 فیلتر لوکیشن‌ها", callback_data="menu_country")
        ],
        [InlineKeyboardButton("🎲 استخراج تک کانفیگ تصادفی", callback_data="random_cfg")]
    ])

def get_help_text() -> str:
    return (
        "❓ **راهنمای جامع استفاده از ربات مخزن کانفیگ:**\n\n"
        "1️⃣ **تنظیم فیلتر:** با استفاده از دکمه‌های `فیلتر پروتکل‌ها` و `فیلتر لوکیشن‌ها` می‌توانید خروجی دریافتی خود را محدود کنید.\n\n"
        "2️⃣ **دریافت کانفیگ:** پس از انتخاب دکمه `دریافت هوشمند کانفیگ` ربات از شما درخواست ارسال یک عدد می‌کند.\n"
        "   - شما می‌توانید **هر عدد دلخواهی** را به ربات ارسال کنید.\n"
        "   - اگر عدد ارسالی کمتر از ۱۰ باشد، به صورت پیام متنی مستقیم ارسال می‌شود.\n"
        "   - اگر عدد ارسالی ۱۰ یا بیشتر باشد، برای کپی راحت‌تر یک فایل متنی `.txt` تحویل می‌گیرید.\n\n"
        "3️⃣ **محدودیت‌ها:** سیستم دارای سقف دریافت روزانه جهت پایداری سرورها می‌باشد که در منوی اصلی به شما نشان داده می‌شود.\n\n"
        "📌 دستور /start برای بازگشت به منوی اصلی در دسترس است."
    )
async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
    user_id = update.effective_user.id
    prefs = await DatabaseManager.get_user_prefs(user_id)
    
    # مدیریت تعاملی حالت بارگذاری پس‌زمینه برای فرآیند تأیید صلاحیت اپلیکیشن در ریل‌وی
    if CacheManager.IS_INITIAL_LOADING:
        text = "🔄 **ربات راه‌اندازی شد! در حال بارگذاری اولیه انبار کش در پس‌زمینه...**\n\nلطفاً چند ثانیه تحمل کرده و سپس دستور /start را مجدداً ارسال کنید."
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode="Markdown")
        return

    proto_txt = prefs["protocol"]
    country_txt = "همه لوکیشن‌ها 🌍" if prefs["country"] == "ALL" else f"{COUNTRY_MAP[prefs['country']][1]} {COUNTRY_MAP[prefs['country']][0]}"
    
    text = (
        f"🤖 **به ربات پیشرفته مدیریت مخازن V2Ray خوش آمدید**\n\n"
        f"⏰ آخرین هماهنگ‌سازی انبار: `{CacheManager.LAST_UPDATE_TIME}`\n"
        f"📊 کل موجودی کانفیگ‌های زنده: `{len(CacheManager.CONFIG_CACHE)}`\n\n"
        f"⚙️ **پیکربندی فیلتر فعلی حساب شما:**\n"
        f"🔹 نوع پروتکل: `{proto_txt}`\n"
        f"🔸 لوکیشن انتخابی: `{country_txt}`\n\n"
        f"👇 جهت دریافت فایل یا شخصی‌سازی فیلترها، گزینه‌های زیر را لمس کنید:"
    )
    
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=make_main_keyboard(), parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=make_main_keyboard(), parse_mode="Markdown")
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await DatabaseManager.set_user_pref(update.effective_user.id, "awaiting_count", False)
        await send_main_menu(update, context, edit=False)
    except Exception as e:
        logger.error(f"خطا در اجرای دستور استارت: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await DatabaseManager.set_user_pref(update.effective_user.id, "awaiting_count", False)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=get_help_text(),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"خطا در اجرای دستور هلپ: {e}")
async def handle_filter_menus(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str, prefs: dict):
    query = update.callback_query
    user_id = update.effective_user.id
    
    # اصلاحیه مهم ۵: پاک‌سازی خودکار و آنی حالت فرآیند awaiting_count برای جلوگیری از انجماد یا گام خطای جفت ورودی عدد
    await DatabaseManager.set_user_pref(user_id, "awaiting_count", False)

    if data == "menu_proto":
        protocols = ["ALL", "VLESS", "VMESS", "TROJAN", "SS", "HYSTERIA2", "WIREGUARD", "TUIC"]
        kb = []
        for i in range(0, len(protocols), 2):
            row = []
            for p in protocols[i:i+2]:
                mark = " ✅" if prefs["protocol"] == p else ""
                row.append(InlineKeyboardButton(f"{p}{mark}", callback_data=f"set_proto_{p}"))
            kb.append(row)
        kb.append([InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu")])
        await query.edit_message_text("🔧 **پروتکل مورد نظر خود را جهت اعمال فیلترینگ انتخاب کنید:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data.startswith("set_proto_"):
        new_p = data.split("_")[2]
        await DatabaseManager.set_user_pref(user_id, "protocol", new_p)
        prefs["protocol"] = new_p
        await handle_filter_menus(update, context, "menu_proto", prefs)
    elif data == "menu_country":
        kb = []
        all_mark = " ✅" if prefs["country"] == "ALL" else ""
        kb.append([InlineKeyboardButton(f"🌍 همه کشورها{all_mark}", callback_data="set_cty_ALL")])
        
        codes = list(COUNTRY_MAP.keys())
        for i in range(0, len(codes), 3):
            row = []
            for code in codes[i:i+3]:
                flag, name = COUNTRY_MAP[code]
                mark = " ✅" if prefs["country"] == code else ""
                row.append(InlineKeyboardButton(f"{flag} {name}{mark}", callback_data=f"set_cty_{code}"))
            kb.append(row)
        kb.append([InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu")])
        await query.edit_message_text("🌍 **کشور مقصد مورد نظر خود را فیلتر کنید:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data.startswith("set_cty_"):
        new_c = data.split("_")[2]
        await DatabaseManager.set_user_pref(user_id, "country", new_c)
        prefs["country"] = new_c
        await handle_filter_menus(update, context, "menu_country", prefs)
async def user_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    prefs = await DatabaseManager.get_user_prefs(user_id)
    data = query.data

    if data == "main_menu":
        await DatabaseManager.set_user_pref(user_id, "awaiting_count", False)
        await send_main_menu(update, context, edit=True)
        
    elif data in ["menu_proto", "menu_country"] or data.startswith("set_proto_") or data.startswith("set_cty_"):
        await handle_filter_menus(update, context, data, prefs)
        
    elif data == "get_configs":
        matches = CacheManager.get_filtered(prefs["protocol"], prefs["country"])
        
        # اصلاحیه مهم ۹: نمایش دقیق فیلترهای کنونی در صورت تهی بودن مقدار خروجی مطابقت کش
        if not matches:
            c_label = "همه کشورها" if prefs["country"] == "ALL" else f"{COUNTRY_MAP[prefs['country']][1]} {COUNTRY_MAP[prefs['country']][0]}"
            await query.edit_message_text(
                f"❌ متأسفانه هیچ کانفیگی با فیلترهای فعلی شما یافت نشد:\n📌 پروتکل: `{prefs['protocol']}`\n📌 کشور: `{c_label}`\n\n💡 پیشنهاد می‌شود فیلترهای خود را به حالت ترکیبی یا 'همه' تغییر دهید تا خروجی تولید شود.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu")]]),
                parse_mode="Markdown"
            )
            return
            
        reqs, total_cfgs = await DatabaseManager.check_rate_limit(user_id)
        if str(user_id) != str(Config.ADMIN_ID) and reqs >= Config.MAX_DAILY_REQUESTS:
            await query.edit_message_text(
                f"⚠️ حد مجاز تعداد دفعات درخواست روزانه شما ({Config.MAX_DAILY_REQUESTS} بار) به اتمام رسیده است. فردا مجدداً تلاش کنید.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منو", callback_data="main_menu")]])
            )
            return

        await DatabaseManager.set_user_pref(user_id, "awaiting_count", True)
        await query.edit_message_text(
            f"🔢 **تعداد کانفیگ درخواستی خود را به صورت عدد ارسال کنید:**\n"
            f"💡 شما می‌توانید هر عددی (مثلاً ۵، ۵۰ یا ۱۰۰) وارد کنید.\n\n"
            f"📊 موارد آماده با فیلتر شما: `{len(matches)}` کانفیگ",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data="main_menu")]]),
            parse_mode="Markdown"
        )
    elif data == "random_cfg":
        matches = CacheManager.get_filtered(prefs["protocol"], prefs["country"])
        if not matches:
            await query.edit_message_text("❌ کانفیگی پیدا نشد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]]))
            return
        await query.edit_message_text(
            f"🎲 **کانفیگ تصادفی شما:**\n\n`{random.choice(matches)}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 یکی دیگه", callback_data="random_cfg")],
                [InlineKeyboardButton("🔙 منوی اصلی", callback_data="main_menu")]
            ]), parse_mode="Markdown"
        )

async def user_message_count_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    prefs = await DatabaseManager.get_user_prefs(user_id)
    
    if not prefs["awaiting_count"]:
        return

    text = update.message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("❌ ورودی نامعتبر است! لطفاً فقط یک عدد صحیح و مثبت ارسال کنید:")
        return

    requested_count = int(text)
    
    # اعمال محدودیت سقف دریافت در هر تراکنش درخواستی بر اساس ساختار بند ۱ نیازمندی‌ها
    if requested_count > Config.MAX_CONFIGS_PER_REQUEST:
        await update.message.reply_text(f"⚠️ تعداد درخواستی شما فراتر از سقف مجاز هر درخواست ({Config.MAX_CONFIGS_PER_REQUEST}) است. مقدار تنظیم شد روی حد مجاز.")
        requested_count = Config.MAX_CONFIGS_PER_REQUEST

    reqs, total_cfgs_today = await DatabaseManager.check_rate_limit(user_id)
    remaining_configs = max(0, Config.MAX_DAILY_CONFIGS - total_cfgs_today)
    
    if str(user_id) != str(Config.ADMIN_ID):
        if remaining_configs <= 0:
            # اصلاحیه مهم ۹: اطلاع رسانی دقیق مانده ظرفیت مصرفی
            await update.message.reply_text("⚠️ ظرفیت کانفیگ‌های مجاز امروز شما به پایان رسیده است (باقی‌مانده: 0). فردا مجدداً مراجعه فرمایید.")
            await DatabaseManager.set_user_pref(user_id, "awaiting_count", False)
            return

    matches = CacheManager.get_filtered(prefs["protocol"], prefs["country"])
    if not matches:
        await update.message.reply_text("❌ در حال حاضر کانفیگی منطبق بر فیلتر شما موجود نیست.")
        await DatabaseManager.set_user_pref(user_id, "awaiting_count", False)
        return

    # تصمیم‌گیری نهایی روی تعداد خروجی بر مبنای موجودی کش و سقف روزانه کاربری
    final_count = min(requested_count, len(matches))
    if str(user_id) != str(Config.ADMIN_ID):
        final_count = min(final_count, remaining_configs)

    if final_count < requested_count:
        await update.message.reply_text(f"⚠️ به دلیل محدودیت‌های روزانه شما یا محدودیت کل حجم مخزن فعال، تعداد کانفیگ تحویلی به `{final_count}` عدد تقلیل یافت.")

    selected = random.sample(matches, final_count)
    await DatabaseManager.set_user_pref(user_id, "awaiting_count", False)
    await DatabaseManager.increment_usage(user_id, len(selected))
    
    # اصلاحیه بند ۲: سوئیچ هوشمند فرستنده متنی مستقیم یا فایل پیوست بر مبنای سقف تعداد ۱۰ عدد
    if len(selected) < 10:
        payload = f"📦 **کانفیگ‌های سفارشی شما (تعداد: {len(selected)}):**\n\n"
        for cfg in selected:
            payload += f"`{cfg}`\n\n"
        await update.message.reply_text(payload, parse_mode="Markdown")
    else:
        file_data = "\n".join(selected)
        bio = io.BytesIO(file_data.encode('utf-8'))
        p_name = prefs["protocol"]
        bio.name = f"{p_name}_Configs_{len(selected)}.txt"
        
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=bio,
            filename=f"{p_name}_Configs_{len(selected)}.txt",
            caption=f"📦 فایل متنی شامل `{len(selected)}` کانفیگ فیلتر شده پروتکل {p_name} با موفقیت صادر شد.",
            parse_mode="Markdown"
        )
    await send_main_menu(update, context, edit=False)
async def check_admin(update: Update) -> bool:
    return str(update.effective_user.id) == str(Config.ADMIN_ID)

async def admin_add_source(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    if not context.args:
        await update.message.reply_text("❌ دستور ناقص است. مثال:\n`/addsource https://link.com/sub.txt`", parse_mode="Markdown")
        return
        
    url = context.args[0].strip()
    
    # اصلاحیه بند ۱۲: راه‌اندازی فرآیند راستی‌آزمایی دقیق آدرس با متد بومی urlparse
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc or parsed.scheme not in ['http', 'https']:
        await update.message.reply_text("❌ آدرس هدر رفته نامعتبر است! مطمئن شوید فرمت ارسالی شامل ساختار کامل http یا https باشد.")
        return

    success = await DatabaseManager.add_source(url)
    await update.message.reply_text("✅ منبع جدید با موفقیت در پایگاه داده سراسری به ثبت رسید." if success else "❌ منبع ارسالی تکراری است یا خطایی رخ داد.")

async def admin_remove_source(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ شناسه نامعتبر است. مثال:\n`/removesource 3`", parse_mode="Markdown")
        return
    s_id = int(context.args[0])
    success = await DatabaseManager.remove_source(s_id)
    await update.message.reply_text("✅ منبع با موفقیت حذف شد." if success else "❌ سورسی با شناسه فوق یافت نشد.")

async def admin_list_sources(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    srcs = await DatabaseManager.get_all_sources()
    text = "🔗 **لیست کامل مخازن ثبت شده در سیستم:**\n\n"
    for r in srcs:
        status = "🟢 فعال" if r[2] == 1 else "🔴 مسدود"
        text += f"🆔 `{r[0]}` | {status} | خطا: `{r[3]}`\n🌐 `{r[1]}`\n\n"
    await update.message.reply_text(text[:4000], parse_mode="Markdown")
async def admin_force_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    msg = await update.message.reply_text("🔄 در حال فچ آنی سورس‌ها و همگام‌سازی اجباری انبار کش...")
    count = await CacheManager.reload_cache()
    await msg.edit_text(f"✅ همگام‌سازی اجباری به پایان رسید. مجموع کانفیگ‌های فعال کش: `{count}`", parse_mode="Markdown")

async def admin_post_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update) or not Config.CHANNEL_ID: return
    matches = CacheManager.CONFIG_CACHE
    p_filter = Config.CHANNEL_FILTER_PROTOCOL
    c_filter = Config.CHANNEL_FILTER_COUNTRIES
    
    filtered = [
        c["config"] for c in matches 
        if (p_filter == "ALL" or c["protocol"] == p_filter.lower()) and 
           (not c_filter or c["country"] in c_filter)
    ]
    
    if not filtered:
        await update.message.reply_text("❌ هیچ کانفیگی منطبق بر الگوی پیش‌فرض فیلتر کانال شما در کش نبود.")
        return
        
    sampled_count = min(10, len(filtered))
    sampled = random.sample(filtered, sampled_count)
    
    payload = "🚀 **مجموعه اختصاصی جدید مستخرج از ربات مخزن برای اعضای کانال:**\n\n" + "\n\n".join([f"`{c}`" for c in sampled])
    await context.bot.send_message(chat_id=Config.CHANNEL_ID, text=payload, parse_mode="Markdown")
    await update.message.reply_text(f"✅ تعداد {sampled_count} کانفیگ با موفقیت به کانال ارسال شد.")

class JobManager:
    # اصلاحیه مهم ۱۰: تعبیه جاگذاری ترای کچ داخلی درون بدنه جاب‌ها جهت تضمین پایداری بدون فریز
    @staticmethod
    async def cron_cache_refresh(context: ContextTypes.DEFAULT_TYPE):
        try:
            await CacheManager.reload_cache()
        except Exception as e:
            logger.error(f"Error inside cron_cache_refresh core handler: {e}")

    @staticmethod
    async def cron_channel_autopost(context: ContextTypes.DEFAULT_TYPE):
        if not Config.CHANNEL_ID: return
        try:
            matches = CacheManager.CONFIG_CACHE
            p_filter = Config.CHANNEL_FILTER_PROTOCOL
            c_filter = Config.CHANNEL_FILTER_COUNTRIES
            
            filtered = [
                c["config"] for c in matches 
                if (p_filter == "ALL" or c["protocol"] == p_filter.lower()) and 
                   (not c_filter or c["country"] in c_filter)
            ]
            
            if filtered:
                sampled_count = min(10, len(filtered))
                sampled = random.sample(filtered, sampled_count)
                payload = "📡 **بروزرسانی خودکار و دوره‌ای کانفیگ‌ها:**\n\n" + "\n\n".join([f"`{c}`" for c in sampled])
                await context.bot.send_message(chat_id=Config.CHANNEL_ID, text=payload, parse_mode="Markdown")
                logger.info("✅ تسک ارسال زمان‌بندی شده به کانال با موفقیت انجام پذیرفت.")
        except Exception as e:
            logger.error(f"Error inside cron_channel_autopost scheduler task: {e}")
async def admin_force_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    msg = await update.message.reply_text("🔄 در حال فچ آنی سورس‌ها و همگام‌سازی اجباری انبار کش...")
    count = await CacheManager.reload_cache()
    await msg.edit_text(f"✅ همگام‌سازی اجباری به پایان رسید. مجموع کانفیگ‌های فعال کش: `{count}`", parse_mode="Markdown")

async def admin_post_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update) or not Config.CHANNEL_ID: return
    matches = CacheManager.CONFIG_CACHE
    p_filter = Config.CHANNEL_FILTER_PROTOCOL
    c_filter = Config.CHANNEL_FILTER_COUNTRIES
    
    filtered = [
        c["config"] for c in matches 
        if (p_filter == "ALL" or c["protocol"] == p_filter.lower()) and 
           (not c_filter or c["country"] in c_filter)
    ]
    
    if not filtered:
        await update.message.reply_text("❌ هیچ کانفیگی منطبق بر الگوی پیش‌فرض فیلتر کانال شما در کش نبود.")
        return
        
    sampled_count = min(10, len(filtered))
    sampled = random.sample(filtered, sampled_count)
    
    payload = "🚀 **مجموعه اختصاصی جدید مستخرج از ربات مخزن برای اعضای کانال:**\n\n" + "\n\n".join([f"`{c}`" for c in sampled])
    await context.bot.send_message(chat_id=Config.CHANNEL_ID, text=payload, parse_mode="Markdown")
    await update.message.reply_text(f"✅ تعداد {sampled_count} کانفیگ با موفقیت به کانال ارسال شد.")

class JobManager:
    # اصلاحیه مهم ۱۰: تعبیه جاگذاری ترای کچ داخلی درون بدنه جاب‌ها جهت تضمین پایداری بدون فریز
    @staticmethod
    async def cron_cache_refresh(context: ContextTypes.DEFAULT_TYPE):
        try:
            await CacheManager.reload_cache()
        except Exception as e:
            logger.error(f"Error inside cron_cache_refresh core handler: {e}")

    @staticmethod
    async def cron_channel_autopost(context: ContextTypes.DEFAULT_TYPE):
        if not Config.CHANNEL_ID: return
        try:
            matches = CacheManager.CONFIG_CACHE
            p_filter = Config.CHANNEL_FILTER_PROTOCOL
            c_filter = Config.CHANNEL_FILTER_COUNTRIES
            
            filtered = [
                c["config"] for c in matches 
                if (p_filter == "ALL" or c["protocol"] == p_filter.lower()) and 
                   (not c_filter or c["country"] in c_filter)
            ]
            
            if filtered:
                sampled_count = min(10, len(filtered))
                sampled = random.sample(filtered, sampled_count)
                payload = "📡 **بروزرسانی خودکار و دوره‌ای کانفیگ‌ها:**\n\n" + "\n\n".join([f"`{c}`" for c in sampled])
                await context.bot.send_message(chat_id=Config.CHANNEL_ID, text=payload, parse_mode="Markdown")
                logger.info("✅ تسک ارسال زمان‌بندی شده به کانال با موفقیت انجام پذیرفت.")
        except Exception as e:
            logger.error(f"Error inside cron_channel_autopost scheduler task: {e}")
async def main():
    # ۱. اعتبارسنجی اولیه متغیرهای محیطی
    Config.validate()
    
    # ۲. آماده‌سازی ساختار لایه‌های پایگاه داده محلی
    await DatabaseManager.init_db()
    await DatabaseManager.populate_default_sources(DEFAULT_SOURCES)
    
    # ۳. اصلاحیه بند ۳: راه‌اندازی تسک پس‌زمینه برای بارگذاری کش جهت سرعت بخشیدن به بالا آمدن در ریلی‌وی
    asyncio.create_task(CacheManager.reload_cache())
    
    # ۴. نمونه‌سازی موتور اصلی ربات تلگرام
    app = Application.builder().token(Config.BOT_TOKEN).build()
    
    # ۵. فعال‌سازی سرویس زمان‌بندی دقیق جاب کیو
    jq = app.job_queue
    jq.run_repeating(JobManager.cron_cache_refresh, interval=Config.CACHE_REFRESH_INTERVAL, first=15)
    jq.run_repeating(JobManager.cron_channel_autopost, interval=Config.CHANNEL_POST_INTERVAL, first=45)
    
    # ۶. نگاشت ثبت‌نام هندلرهای فرامین تلگرامی ادمین و کاربر
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command)) # اصلاحیه بند ۱۱: منو راهنما
    app.add_handler(CommandHandler("addsource", admin_add_source))
    app.add_handler(CommandHandler("removesource", admin_remove_source))
    app.add_handler(CommandHandler("sources", admin_list_sources))
    app.add_handler(CommandHandler("refreshcache", admin_force_refresh))
    app.add_handler(CommandHandler("postchannel", admin_post_channel))
    
    app.add_handler(CallbackQueryHandler(user_callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user_message_count_handler))
    
    logger.info("🚀 موتور پولینگ بات تلگرام در بستر ناهمزمان فعال گردید.")
    
    # ۷. متد نهایی اجرا بدون فلگ حذفی close_loop مطابق مستندات نسخه نهایی
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
