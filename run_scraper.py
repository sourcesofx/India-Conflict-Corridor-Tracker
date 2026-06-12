import asyncio
import time
from datetime import datetime
from src.config import (
   NEWS_POLL_INTERVAL_SECONDS,
   USE_RSS,
   RSS_SOURCES,
   DATA_DIR,
   CIVIL_UNREST_SCORE,
   MAX_ARTICLE_AGE_DAYS
)
from src.scraper import scrape_all, ALL_LOCATIONS, ALL_ACTORS
from src.rss_ingester import fetch_rss_articles
from src.risk_classifier import RiskClassifier
from src.utils import extract_content_with_trafilatura, get_all_existing_articles, contains_keywords, is_article_too_old, archive_to_historical



def save_rss_article(article: dict):
   """Save a processed RSS article to the correct JSON and CSV files."""
   import json
   import pandas as pd


   source_key = article.get("source_key")
   if not source_key:
       print("   ⚠️ Cannot save RSS article: missing source_key")
       return


   json_path = DATA_DIR / f"{source_key}.json"
   csv_path = DATA_DIR / f"{source_key}.csv"


   existing_data = []
   if json_path.exists():
       try:
           with open(json_path, "r", encoding="utf-8") as f:
               existing_data = json.load(f)
       except Exception:
           existing_data = []


   existing_urls = {a.get("url") for a in existing_data if a.get("url")}
   if article.get("url") in existing_urls:
       return


   existing_data.append(article)
   try:
       with open(json_path, "w", encoding="utf-8") as f:
           json.dump(existing_data, f, ensure_ascii=False, indent=2)
   except Exception as e:
       print(f"   ❌ Failed to save JSON for {source_key}: {e}")


   try:
       df = pd.DataFrame([article])
       if not csv_path.exists():
           df.to_csv(csv_path, index=False)
       else:
           df.to_csv(csv_path, mode="a", header=False, index=False)
           
       archive_to_historical(article)
       
   except Exception as e:
       print(f"   ❌ Failed to append CSV for {source_key}: {e}")




def process_rss_article(article: dict, existing_articles: dict) -> dict | None:
   """
   Light pre-filter for RSS articles.
  
   This is the first step toward unified risk scoring.
   We use a relaxed filter here and let the full RiskClassifier
   do the heavy lifting later.
   """
   url = article.get("url")
   if not url or url in existing_articles:
       return None


   title = article.get("title", "")
   if not title:
       return None

   # ===Age Gate for RSS ===
   pub_date = article.get("published_date")
   if is_article_too_old(pub_date, MAX_ARTICLE_AGE_DAYS):
       return None
   matched = contains_keywords(title)
   has_keywords = len(matched) > 0
   has_regional_signal = any(
       kw in title.lower() for kw in (ALL_LOCATIONS | ALL_ACTORS)
   )


   if not (has_keywords or has_regional_signal):
       return None


   #Get full article content
   content = extract_content_with_trafilatura(url)
   if not content:
       content = article.get("summary", "")


   processed_article = {
       "timestamp": datetime.now().isoformat(),
       "source_key": article.get("source_key"),
       "source": article.get("source_name"),
       "title": title,
       "url": url,
       "matched_keywords": matched,
       "region": article.get("region"),
       "published_date": article.get("published_date"),
       "content": content[:4000] if content else "",
       "source_type": "rss"
   }


   return processed_article




def main():
   print("🚀 Conflict Corridor Real-Time Intelligence Pipeline")
   print("   Phase 1: News Scraper (RSS + Playwright Hybrid)")
   print("   Phase 2: SpaCy Risk Classifier")
   print("=" * 85)


   classifier = RiskClassifier()
   cycle_counter = 0
   CLEAN_CYCLE_THRESHOLD = 5


   while True:
       try:
           cycle_counter += 1
           print(f"\n🔄 Starting full cycle #{cycle_counter} at {time.strftime('%H:%M:%S')}")


           existing_articles = get_all_existing_articles()
           saved_from_rss = 0


           # ================== RSS INGESTION + PROCESSING ==================
           if USE_RSS and RSS_SOURCES:
               print("\n📡 Running RSS ingestion + processing...")
               try:
                   rss_articles = fetch_rss_articles()
                   saved_from_rss = 0


                   for raw_article in rss_articles:
                       processed = process_rss_article(raw_article, existing_articles)
                       if processed:
                           enriched_article = classifier.classify_article(processed)


                           final_score = enriched_article.get("final_risk_score", 0)


                           if final_score >= CIVIL_UNREST_SCORE:
                               save_rss_article(enriched_article)
                               saved_from_rss += 1
                               existing_articles[enriched_article["url"]] = enriched_article.get("published_date")
                               print(f"   ✅ RSS SAVED (score={final_score}) | {enriched_article['title'][:80]}...")
                           else:
                               print(f"   ⏭️  RSS FILTERED by classifier (score={final_score}) | {enriched_article['title'][:70]}...")


                   print(f"   ✅ RSS: {saved_from_rss} articles saved after classification")
               except Exception as e:
                   print(f"   ⚠️ RSS processing error: {e}")


           # ================== PLAYWRIGHT SCRAPING ==================
           print("\n📡 Running Playwright news scraper...")
           asyncio.run(scrape_all(existing_articles, classifier))


           # ================== AUTOMATED SCRUBBING VALVE ==================
           if cycle_counter % CLEAN_CYCLE_THRESHOLD == 0:
               print(f"\n🧼 [AUTOPILOT] Triggering Scheduled Retrospective Database Scrub (Cycle {cycle_counter})...")
               from src.clean_database import strict_retrospective_scrub
               strict_retrospective_scrub()


           print(f"\n✅ Full cycle #{cycle_counter} completed. Next run in {NEWS_POLL_INTERVAL_SECONDS // 60} minutes.")
           time.sleep(NEWS_POLL_INTERVAL_SECONDS)


       except KeyboardInterrupt:
           print("\n👋 Pipeline stopped by user. Goodbye!")
           break
       except Exception as e:
           print(f"⚠️ Error in cycle: {e}")
           time.sleep(60)




if __name__ == "__main__":
   main()
