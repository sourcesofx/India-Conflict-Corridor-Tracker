import os
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

# ================== CLOUD-SAFE PATHS ==================
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "raw"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOT_DIR = BASE_DIR / "data" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# ================== LOAD KEYWORDS ==================
with open(BASE_DIR / "keywords.json", "r", encoding="utf-8") as f:
   KEYWORDS = json.load(f)

# ================== SYSTEM SETTINGS (ENV DRIVEN) ==================
HEADLESS = os.getenv("HEADLESS", "True").lower() in ('true', '1', 't')
EXTRACT_FULL_CONTENT = os.getenv("EXTRACT_FULL_CONTENT", "True").lower() in ('true', '1', 't')
NEWS_POLL_INTERVAL_SECONDS = int(os.getenv("NEWS_POLL_INTERVAL_SECONDS", 900))
MAX_ARTICLES_PER_SITE = int(os.getenv("MAX_ARTICLES_PER_SITE", 80))
MAX_ARTICLE_AGE_DAYS = int(os.getenv("MAX_ARTICLE_AGE_DAYS", 14))

# ================== MEMORY MANAGEMENT ==================
JSON_RETENTION_DAYS = int(os.getenv("JSON_RETENTION_DAYS", 60))

# ================== THRESHOLD RADAR ==================
MIN_RISK_SCORE = float(os.getenv("MIN_RISK_SCORE", 8.0))
CIVIL_UNREST_SCORE = float(os.getenv("CIVIL_UNREST_SCORE", 7.5))
HIGH_RISK_THRESHOLD = float(os.getenv("HIGH_RISK_THRESHOLD", 8.0))
MEDIUM_RISK_THRESHOLD = float(os.getenv("MEDIUM_RISK_THRESHOLD", 5.0))


# ================== RSS + HYBRID SETTINGS ==================
USE_RSS = True
RSS_MAX_ARTICLES_PER_SOURCE = 50
RSS_SOURCES = {
   "greater_kashmir": {
       "name": "Greater Kashmir",
       "rss_url": "https://www.greaterkashmir.com/feed/",
       "region": "jk"
   },
   "assam_tribune": {
       "name": "The Assam Tribune",
       "rss_url": "https://assamtribune.com/feed",
       "region": "ne"
   },
   "rising_kashmir": {
       "name": "Rising Kashmir",
       "rss_url": "https://risingkashmir.com/feed/",
       "region": "jk"
   },
}


# ================== NEWS SITES ==================
NEWS_SITES = {
   # ================== J&K SOURCES ==================
   "greater_kashmir": {
       "name": "Greater Kashmir",
       "url": "https://www.greaterkashmir.com/",
       "selectors": ["a[class*='title']", "article a", "h2 a"],
       "region": "jk"
   },
   "daily_excelsior": {
       "name": "Daily Excelsior",
       "url": "https://www.dailyexcelsior.com/",
       "selectors": ["h2 a", "h3 a", ".entry-title a", "article a"],
       "region": "jk"
   },
   "kashmir_observer": {
       "name": "Kashmir Observer",
       "url": "https://kashmirobserver.net/",
       "selectors": ["h2 a", "h3 a", "article a", ".title a"],
       "region": "jk"
   },
   "rising_kashmir": {
       "name": "Rising Kashmir",
       "url": "https://risingkashmir.com/",
       "selectors": ["h2 a", "h3 a", "article a", ".post-title a"],
       "region": "jk"
   },
   "state_times": {
       "name": "State Times",
       "url": "https://statetimes.in/",
       "selectors": ["h2 a", "h3 a", "article a", ".title a"],
       "region": "jk"
   },
   "kashmir_walla": {
       "name": "The Kashmir Walla",
       "url": "https://thekashmirwalla.com/",
       "selectors": ["h2 a", "h3 a", "article a", ".title a"],
       "region": "jk"
   },
   "kashmir_life": {
       "name": "Kashmir Life",
       "url": "https://kashmirlife.net/",
       "selectors": ["h2 a", "h3 a", "article a", ".title a"],
       "region": "jk"
   },
   "early_times": {
       "name": "Early Times",
       "url": "https://www.earlytimes.in/",
       "selectors": ["h2 a", "h3 a", "article a", ".title a"],
       "region": "jk"
   },
   "free_press_kashmir": {
       "name": "Free Press Kashmir",
       "url": "https://freepresskashmir.news/",
       "selectors": ["h2 a", "h3 a", "article a", ".title a"],
       "region": "jk"
   },
   "kns_kashmir": {
       "name": "Kashmir News Service (KNS)",
       "url": "https://www.knskashmir.com/",
       "selectors": ["h2 a", "h3 a", "article a", ".title a"],
       "region": "jk"
   },
   "kashmir_media_watch": {
       "name": "Kashmir Media Watch",
       "url": "https://www.kashmirmediawatch.com/",
       "selectors": ["h2 a", "h3 a", "article a", ".title a"],
       "region": "jk"
   },
   "top_news_jk": {
       "name": "Top News J&K",
       "url": "https://topnewsjk.in/",
       "selectors": ["h2 a", "h3 a", "article a", ".title a"],
       "region": "jk"
   },
   "northlines": {
       "name": "The Northlines",
       "url": "https://thenorthlines.com/",
       "selectors": ["h2 a", "h3 a", "article a", ".title a"],
       "region": "jk"
   },
   "kashmir_monitor": {
       "name": "The Kashmir Monitor",
       "url": "https://www.thekashmirmonitor.net/",
       "selectors": ["h2 a", "h3 a", "article a", ".title a"],
       "region": "jk"
   },


   # ================== NORTHEAST SOURCES ==================
   "sangai_express": {
       "name": "The Sangai Express",
       "url": "https://www.thesangaiexpress.com/",
       "selectors": ["h2 a", "h3 a", "article a", ".title a"],
       "region": "ne"
   },
   "assam_tribune": {
       "name": "The Assam Tribune",
       "url": "https://assamtribune.com/",
       "selectors": ["h2 a", "h3 a", "article a"],
       "region": "ne"
   },
   "nagaland_post": {
       "name": "Nagaland Post",
       "url": "https://nagalandpost.com/",
       "selectors": ["h2 a", "h3 a", "article a"],
       "region": "ne"
   },
   "east_mojo": {
       "name": "East Mojo",
       "url": "https://eastmojo.com/",
       "selectors": ["h2 a", "h3 a", "article a", ".title a"],
       "region": "ne"
   },
   "shillong_times": {
       "name": "The Shillong Times",
       "url": "https://theshillongtimes.com/",
       "selectors": ["h2 a", "h3 a", "article a"],
       "region": "ne"
   },
   "morung_express": {
       "name": "Morung Express",
       "url": "https://www.morungexpress.com/",
       "selectors": ["h2 a", "h3 a", "article a"],
       "region": "ne"
   },
   "nenow": {
       "name": "NorthEast Now",
       "url": "https://nenow.in/",
       "selectors": ["h2 a", "h3 a", "article a", ".title a"],
       "region": "ne"
   },
   "sentinel": {
       "name": "The Sentinel",
       "url": "https://www.sentinelassam.com/",
       "selectors": ["h2 a", "h3 a", "article a"],
       "region": "ne"
   },
   "india_today_ne": {
       "name": "India Today NE",
       "url": "https://www.indiatodayne.in/",
       "selectors": ["h2 a", "h3 a", "article a"],
       "region": "ne"
   },
   "northeast_news": {
       "name": "Northeast News",
       "url": "https://nenews.in/",
       "selectors": ["h2 a", "h3 a", "article a"],
       "region": "ne"
   },
   "northeast_today": {
       "name": "Northeast Today",
       "url": "https://northeasttoday.in/",
       "selectors": ["h2 a", "h3 a", "article a"],
       "region": "ne"
   },
   "northeast_post": {
       "name": "The Northeast Post",
       "url": "https://www.thenortheastpost.com/",
       "selectors": ["h2 a", "h3 a", "article a"],
       "region": "ne"
   }
}


# ================== GEOSPATIAL ANCHORS ==================
DISTRICT_COORDS = {
   # === Jammu & Kashmir ===
   "anantnag": (33.73, 75.15), "bandipora": (34.42, 74.65), "bandipore": (34.42, 74.65),
   "baramulla": (34.20, 74.34), "budgam": (34.00, 74.73), "ganderbal": (34.22, 74.78),
   "kulgam": (33.64, 75.02), "kupwara": (34.53, 74.25), "pulwama": (33.87, 74.92),
   "shopian": (33.72, 74.83), "srinagar": (34.08, 74.80), "sopore": (34.29, 74.47),
   "jammu": (32.73, 74.87), "doda": (33.15, 75.55), "kathua": (32.38, 75.52),
   "kishtwar": (33.31, 75.77), "poonch": (33.77, 74.09), "rajouri": (33.38, 74.30),
   "ramban": (33.24, 75.19), "reasi": (33.08, 74.83), "samba": (32.55, 74.98),
   "udhampur": (32.92, 75.13),


   # === Arunachal Pradesh ===
   "anjaw": (27.92, 96.65), "changlang": (27.13, 95.73), "dibang valley": (28.80, 95.84),
   "east kameng": (27.29, 92.89), "east siang": (28.06, 95.32), "itanagar": (27.08, 93.62),
   "kra daadi": (27.80, 93.63), "kurung kumey": (27.89, 93.30), "leparada": (27.80, 94.69),
   "lohit": (27.92, 96.16), "longding": (26.91, 95.32), "lower dibang valley": (28.14, 95.67),
   "lower siang": (27.76, 94.88), "lower subansiri": (27.50, 93.84), "namsai": (27.67, 95.87),
   "pakke kessang": (27.14, 93.02), "papum pare": (27.10, 93.62), "shi yomi": (28.46, 94.40),
   "siang": (28.37, 94.90), "tawang": (27.58, 91.86), "tirap": (27.01, 95.53),
   "upper siang": (28.62, 94.95), "upper subansiri": (28.13, 94.13), "west kameng": (27.25, 92.20),
   "west siang": (28.40, 94.42), "kamle": (27.80, 94.00), "bomdila": (27.25, 92.40),
   "pasighat": (28.07, 95.33), "ziro": (27.55, 93.85), "tezu": (27.90, 96.15), "roing": (28.15, 95.85),


   # === Assam ===
   "baksa": (26.65, 91.33), "barpeta": (26.32, 91.00), "bongaigaon": (26.47, 90.56),
   "cachar": (24.83, 92.77), "charaideo": (26.93, 94.94), "chirang": (26.63, 90.57),
   "darrang": (26.45, 92.03), "dhemaji": (27.48, 94.58), "dhubri": (26.02, 89.98),
   "dibrugarh": (27.47, 94.91), "dima hasao": (25.18, 93.03), "goalpara": (26.17, 90.62),
   "golaghat": (26.51, 93.97), "hailakandi": (24.68, 92.56), "hojai": (26.00, 92.86),
   "jorhat": (26.75, 94.20), "kamrup": (26.31, 91.35), "kamrup metropolitan": (26.14, 91.73),
   "guwahati": (26.14, 91.74), "karbi anglong": (26.00, 93.50), "karimganj": (24.86, 92.35),
   "kokrajhar": (26.40, 90.27), "lakhimpur": (27.23, 94.10), "majuli": (26.95, 94.17),
   "morigaon": (26.25, 92.33), "nagaon": (26.35, 92.68), "nalbari": (26.43, 91.44),
   "sivasagar": (26.98, 94.63), "sonitpur": (26.63, 92.80), "south salmara-mankachar": (25.75, 89.92),
   "tinsukia": (27.48, 95.35), "udalguri": (26.75, 92.11), "west karbi anglong": (25.96, 92.63),
   "bajali": (26.50, 91.19), "biswanath": (26.73, 93.15),


   # === Manipur ===
   "bishnupur": (24.63, 93.76), "chandel": (24.32, 94.02), "churachandpur": (24.30, 93.67),
   "imphal east": (24.81, 94.02), "imphal west": (24.80, 93.90), "imphal": (24.80, 93.94),
   "jiribam": (24.80, 93.11), "kakching": (24.49, 93.98), "kamjong": (24.87, 94.52),
   "kangpokpi": (25.15, 93.97), "noney": (24.81, 93.63), "pherzawl": (24.26, 93.18),
   "senapati": (25.27, 94.02), "tamenglong": (24.98, 93.50), "tengnoupal": (24.32, 94.14),
   "thoubal": (24.63, 94.01), "ukhrul": (25.10, 94.35),


   # === Meghalaya ===
   "east garo hills": (25.60, 90.61), "east jaintia hills": (25.33, 92.40), "east khasi hills": (25.43, 91.80),
   "eastern west khasi hills": (25.53, 91.43), "north garo hills": (25.88, 90.57), "ri bhoi": (25.90, 91.88),
   "south garo hills": (25.28, 90.64), "south west garo hills": (25.47, 89.96), "south west khasi hills": (25.30, 91.24),
   "west garo hills": (25.52, 90.22), "west jaintia hills": (25.43, 92.20), "west khasi hills": (25.52, 91.26),
   "shillong": (25.58, 91.89), "williamnagar": (25.52, 90.60), "baghmara": (25.20, 90.65),


   # === Mizoram ===
   "aizawl": (23.73, 92.72), "champhai": (23.47, 93.33), "hnahthial": (22.96, 92.93),
   "khawzawl": (23.53, 93.18), "kolasib": (24.22, 92.67), "lawngtlai": (22.52, 92.89),
   "lunglei": (22.88, 92.73), "mamit": (23.92, 92.48), "saiha": (22.48, 92.97),
   "siaha": (22.48, 92.97), "saitual": (23.68, 92.96), "serchhip": (23.31, 92.83),


   # === Nagaland ===
   "chümoukedima": (25.81, 93.77), "dimapur": (25.90, 93.73), "kiphire": (25.87, 94.78),
   "kohima": (25.67, 94.11), "longleng": (26.46, 94.80), "meluri": (25.66, 94.61),
   "mokokchung": (26.33, 94.52), "mon": (26.74, 94.94), "niuland": (25.89, 93.98),
   "noklak": (26.19, 94.98), "peren": (25.51, 93.73), "phek": (25.68, 94.46),
   "shamator": (25.99, 94.88), "tseminyü": (25.90, 94.19), "tuensang": (26.23, 94.83),
   "wokha": (26.10, 94.26), "zünheboto": (25.96, 94.52),


   # === Sikkim ===
   "gangtok": (27.33, 88.62), "geyzing": (27.29, 88.23), "gyalshing": (27.29, 88.23),
   "mangan": (27.49, 88.53), "namchi": (27.17, 88.35), "pakyong": (27.23, 88.58),
   "soreng": (27.17, 88.20),


   # === Tripura ===
   "agartala": (23.83, 91.28), "dhalai": (23.85, 91.90), "gomati": (23.53, 91.49),
   "khowai": (24.06, 91.60), "north tripura": (24.16, 92.05), "sepahijala": (23.66, 91.28),
   "south tripura": (23.28, 91.56), "unakoti": (24.13, 92.00), "west tripura": (23.83, 91.27)
}


print(f"✅ Config loaded successfully!")
print(f"   • News sites (Playwright): {len(NEWS_SITES)}")
print(f"   • RSS Sources: {len(RSS_SOURCES)}")