from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from datetime import datetime
import json
import pandas as pd
import random
import asyncio
from src.utils import contains_keywords, is_article_too_old, archive_to_historical, lexical_deduplicate
from src.config import NEWS_SITES, DATA_DIR, SCREENSHOT_DIR, MAX_ARTICLE_AGE_DAYS, MIN_RISK_SCORE




print("🔥 NEWS SCRAPER v9 🔥")


# ================== CONFIG ==================
HEADLESS = True
EXTRACT_FULL_CONTENT = True
MAX_CONCURRENT_SITES = 4
SCRAPER_MAX_RETRIES = 2
SCRAPER_TIMEOUT_MS = 60000


with open('keywords.json', 'r', encoding='utf-8') as f:
   KEYWORDS = json.load(f)


HIGH_RISK_KWS = set(KEYWORDS.get("base_high_risk", []) +
                  KEYWORDS["jk"].get("high_risk", []) +
                  KEYWORDS["ne"].get("high_risk", []))


MEDIUM_RISK_KWS = set(KEYWORDS.get("base_medium_risk", []) +
                    KEYWORDS["jk"].get("medium_risk", []) +
                    KEYWORDS["ne"].get("medium_risk", []))


JK_LOCATIONS = set(KEYWORDS["jk"]["locations"])
NE_LOCATIONS = set(KEYWORDS["ne"]["locations"])
ALL_LOCATIONS = JK_LOCATIONS | NE_LOCATIONS
ALL_ACTORS = set(KEYWORDS["jk"]["actors"] + KEYWORDS["ne"]["actors"])


def clean_text(text: str) -> str:
   return " ".join(str(text).split())


async def goto_with_retry(page, url: str, max_retries: int = 2, timeout: int = 60000) -> bool:
   """
   Advanced retry logic with error classification and smart backoff.
   Returns True if successful, False if all attempts failed.
   """
   for attempt in range(max_retries + 1):
       try:
           await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
           try:
               await page.wait_for_load_state("networkidle", timeout=15000)
           except:
               pass
          
           return True


       except PlaywrightTimeout:
           error_type = "Timeout"
           print(f"   ⚠️ [{error_type}] Attempt {attempt + 1}/{max_retries + 1} failed for {url}")
          
       except Exception as e:
           error_msg = str(e)
           if "ERR_NETWORK_IO_SUSPENDED" in error_msg or "net::ERR_" in error_msg:
               error_type = "Network Error"
           elif "Execution context was destroyed" in error_msg:
               error_type = "Navigation Error"
           else:
               error_type = "Other Error"
          
           print(f"   ⚠️ [{error_type}] Attempt {attempt + 1}/{max_retries + 1} failed: {error_msg[:80]}")


       if attempt == max_retries:
           print(f"   ❌ All {max_retries + 1} attempts failed for {url}")
           return False


       wait_time = (2 ** attempt) + random.uniform(0.5, 1.5)
       print(f"   ↻ Retrying in {wait_time:.1f}s...\n")
       await asyncio.sleep(wait_time)


   return False


async def extract_full_content(page, article_url: str) -> str:
   """
   Try Trafilatura first (better quality), fall back to Playwright paragraph extraction.
   """
   if not EXTRACT_FULL_CONTENT:
       return ""
   try:
       import trafilatura
       downloaded = trafilatura.fetch_url(article_url)
       if downloaded:
           text = trafilatura.extract(
               downloaded,
               include_comments=False,
               include_tables=False,
               include_formatting=False
           )
           if text and len(text) > 200:
               return text[:6000]
   except Exception:
       pass


   # Fallback - Playwright
   try:
       await page.goto(article_url, wait_until="domcontentloaded", timeout=60000)
       await page.wait_for_timeout(1500)
       paragraphs = await page.query_selector_all("p")
       content = []
       for p in paragraphs:
           text = clean_text(await p.inner_text())
           if len(text) > 30:
               content.append(text)
       return " ".join(content[:15])
   except Exception:
       return ""


async def extract_publication_date(page, article_url: str) -> str | None:
    """
    Robust publication date extraction.
    Tries URL Regex → JSON-LD → Meta tags → Visible selectors.
    Returns ISO format string (YYYY-MM-DD) or None.
    """
    import re
    try:
        url_match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', article_url)
        if url_match:
            return f"{url_match.group(1)}-{url_match.group(2)}-{url_match.group(3)}"
        json_ld_scripts = await page.query_selector_all('script[type="application/ld+json"]')
        for script in json_ld_scripts:
            try:
                content = await script.inner_text()
                data = json.loads(content)
                if isinstance(data, list):
                    data = data[0] if data else {}
                date_str = (
                    data.get("datePublished") or
                    data.get("dateCreated") or
                    data.get("dateModified")
                )
                if date_str:
                    try:
                        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        return dt.date().isoformat()
                    except:
                        return date_str[:10]
            except:
                continue

        meta_selectors = [
            'meta[property="article:published_time"]',
            'meta[property="og:article:published_time"]',
            'meta[name="pubdate"]',
            'meta[name="publishdate"]',
            'meta[name="date"]',
            'meta[itemprop="datePublished"]',
        ]
      
        for selector in meta_selectors:
            meta = await page.query_selector(selector)
            if meta:
                date_str = await meta.get_attribute("content")
                if date_str:
                    try:
                        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        return dt.date().isoformat()
                    except:
                        return date_str[:10]
        visible_selectors = [
            'time[datetime]',
            '.published-date',
            '.post-date',
            '.article-date',
            '[itemprop="datePublished"]',
        ]
      
        for selector in visible_selectors:
            element = await page.query_selector(selector)
            if element:
                date_str = await element.get_attribute("datetime") or await element.inner_text()
                if date_str and len(date_str) > 6:
                    try:
                        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        return dt.date().isoformat()
                    except:
                        for fmt in ("%B %d, %Y", "%d %B %Y", "%Y-%m-%d"):
                            try:
                                dt = datetime.strptime(date_str.strip()[:20], fmt)
                                return dt.date().isoformat()
                            except:
                                continue

        return None

    except Exception:
        return None


async def scrape_site(site_key: str, semaphore: asyncio.Semaphore, existing_articles: dict | None = None, classifier=None):
   site = NEWS_SITES[site_key]
   region_label = "JK" if site["region"] == "jk" else "NE"
   print(f"🚀 Scraping {site['name']} ({region_label})...")


   DATA_DIR.mkdir(parents=True, exist_ok=True)
   SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


   json_path = DATA_DIR / f"{site_key}.json"
   csv_path = DATA_DIR / f"{site_key}.csv"


   existing_data = []
   existing_urls = set()


   if json_path.exists():
       try:
           with open(json_path, "r", encoding="utf-8") as f:
               existing_data = json.load(f)
           existing_urls = {item.get("url") for item in existing_data if item.get("url")}
       except Exception:
           pass
   if existing_articles is None:
       existing_articles = {}
   existing_urls.update(existing_articles.keys())


   async with semaphore:
       try:
           async with async_playwright() as p:
               browser = await p.chromium.launch(headless=HEADLESS)
               page = await browser.new_page()


               success = await goto_with_retry(
                   page,
                   site["url"],
                   max_retries=SCRAPER_MAX_RETRIES,
                   timeout=SCRAPER_TIMEOUT_MS
               )
              
               if not success:
                   await browser.close()
                   return


               await asyncio.sleep(random.uniform(1.5, 3.0))


               scraped_data = []
               seen_urls = set()


               for selector in site["selectors"]:
                   elements = await page.query_selector_all(selector)
                   for elem in elements[:60]:
                       try:
                           title = clean_text(await elem.inner_text())
                           if len(title) < 20:
                               continue


                           href = await elem.get_attribute("href")
                           if href and href.startswith("/"):
                               href = site["url"].rstrip("/") + href
                           if not href or not href.startswith("http") or href in seen_urls or href in existing_urls:
                               continue


                           seen_urls.add(href)


                           matched = contains_keywords(title)
                           has_keywords = len(matched) > 0
                           has_regional_signal = any(
                               kw in title.lower() for kw in (ALL_LOCATIONS | ALL_ACTORS)
                           )


                           if not (has_keywords or has_regional_signal):
                               continue


                           full_content = await extract_full_content(page, href)
                           published_date = await extract_publication_date(page, href)

                           # ===Age Gate ===
                           if is_article_too_old(published_date, MAX_ARTICLE_AGE_DAYS):
                               print(f"   ⏭️ SKIPPED (too old): {title[:60]}...")
                               continue

                           article = {
                               "timestamp": datetime.now().isoformat(),
                               "source": site["name"],
                               "title": title,
                               "url": href,
                               "matched_keywords": matched,
                               "region": site["region"],
                               "published_date": published_date,
                               "content": full_content[:3000] if full_content else "",
                               "source_type": "playwright"
                           }

                           if classifier:
                               enriched_article = classifier.classify_article(article)
                           else:
                               enriched_article = article

                           # ===Use Dynamic Config Score & Push to Dashboard Archive ===
                           if enriched_article.get("final_risk_score", 0) >= MIN_RISK_SCORE:
                               scraped_data.append(enriched_article)
                               archive_to_historical(enriched_article)
                               print(f"   ✅ SAVED & ARCHIVED (score={enriched_article['final_risk_score']}) | {title[:70]}...")
                           else:
                               print(f"   ⏭️  FILTERED by classifier (score={enriched_article.get('final_risk_score')}) | {title[:70]}...")

                           await asyncio.sleep(random.uniform(0.8, 1.5))


                       except Exception:
                           continue


               await browser.close()


               if scraped_data:
                   scraped_df = pd.DataFrame(scraped_data)
                   deduped_df = lexical_deduplicate(scraped_df)
                   scraped_data = deduped_df.to_dict('records') if not deduped_df.empty else []

                   final_data = existing_data + scraped_data
                   with open(json_path, "w", encoding="utf-8") as f:
                       json.dump(final_data, f, ensure_ascii=False, indent=2)
                   if scraped_data:
                       pd.DataFrame(scraped_data).to_csv(csv_path, index=False)
                   print(f"   🎉 Saved {len(scraped_data)} new relevant articles (after lexical deduplication)!")
               else:
                   print("   ⚠️ No new relevant articles this run")


               print(f"   📊 Total unique articles processed: {len(seen_urls)}\n")


       except Exception as e:
           print(f"   ❌ Error scraping {site['name']}: {e}")
           print("   Continuing...\n")


async def scrape_all(existing_articles: dict | None = None, classifier=None):
   print(f"Starting async scrape of {len(NEWS_SITES)} news sources (J&K + Northeast)...\n")
   semaphore = asyncio.Semaphore(MAX_CONCURRENT_SITES)
   tasks = [scrape_site(site_key, semaphore, existing_articles, classifier) for site_key in NEWS_SITES.keys()]
   await asyncio.gather(*tasks, return_exceptions=True)
   print(f"\n🏁 Finished scraping all {len(NEWS_SITES)} sources.")


if __name__ == "__main__":
   asyncio.run(scrape_all())