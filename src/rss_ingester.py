import feedparser
import requests
from datetime import datetime


from src.config import RSS_SOURCES, RSS_MAX_ARTICLES_PER_SOURCE


def parse_rss_date(entry) -> str | None:
   """
   Robustly extract and format publication date from RSS entry.
   Returns ISO date string (YYYY-MM-DD) or None.
   """
   date_fields = ["published_parsed", "updated_parsed", "created_parsed"]


   for field in date_fields:
       if field in entry and entry[field]:
           try:
               dt = datetime(*entry[field][:6])
               return dt.date().isoformat()
           except Exception:
               continue


   raw_fields = ["published", "updated", "created"]
   for field in raw_fields:
       if field in entry and entry[field]:
           try:
               for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
                   try:
                       dt = datetime.strptime(entry[field][:25], fmt)
                       return dt.date().isoformat()
                   except Exception:
                       continue
           except Exception:
               continue


   return None




def fetch_rss_articles() -> list[dict]:
   """
   Fetch RSS articles with robust encoding handling.
   Fixes the Assam Tribune 'us-ascii' warning.
   """
   import os
   import certifi


   os.environ['SSL_CERT_FILE'] = certifi.where()


   all_articles = []


   custom_headers = {
       'User-Agent': 'ConflictCorridor/1.0[](https://github.com/sourcesofx/Conflict-Corridor)'
   }


   for source_key, source_info in RSS_SOURCES.items():
       try:
           resp = requests.get(
               source_info["rss_url"],
               headers=custom_headers,
               timeout=30
           )
           resp.raise_for_status()
           content_type = resp.headers.get("content-type", "").lower()
           encoding = (resp.encoding or "").lower()
           if "us-ascii" in content_type or encoding in ("iso-8859-1", "us-ascii", "latin1"):
               resp.encoding = resp.apparent_encoding or "utf-8"


           feed = feedparser.parse(resp.content)


           if feed.bozo:
               error = getattr(feed, "bozo_exception", "Unknown parsing error")
               print(f"   ⚠️ RSS parsing issue for {source_info['name']}: {error}")
               continue


           count = 0
           for entry in feed.entries:
               if count >= RSS_MAX_ARTICLES_PER_SOURCE:
                   break


               title = str(entry.get("title") or "").strip()
               link = str(entry.get("link") or "").strip()


               if not title or not link:
                   continue


               published_date = parse_rss_date(entry)
               summary = str(entry.get("summary") or entry.get("description") or "")[:500]


               article = {
                   "source_key": source_key,
                   "source_name": source_info["name"],
                   "region": source_info["region"],
                   "title": title,
                   "url": link,
                   "published_date": published_date,
                   "summary": summary,
                   "source_type": "rss"
               }


               all_articles.append(article)
               count += 1


           print(f"   📡 RSS: Fetched {count} articles from {source_info['name']}")


       except Exception as e:
           print(f"   ❌ Error fetching RSS for {source_info['name']}: {e}")


   return all_articles
