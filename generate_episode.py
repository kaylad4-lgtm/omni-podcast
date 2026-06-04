#!/usr/bin/env python3
"""Omni Daily Podcast Generator — Feed on everything."""

import feedparser
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from gtts import gTTS

BASE_URL = "https://kaylad4-lgtm.github.io/omni-podcast"

SOURCES = [
    {"name": "New York Times",    "url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "count": 3},
    {"name": "Los Angeles Times", "url": "https://www.latimes.com/local/rss2.0.xml",                  "count": 2},
    {"name": "Bloomberg Markets", "url": "https://feeds.bloomberg.com/markets/news.rss",              "count": 2},
    {"name": "Inman Real Estate", "url": "https://www.inman.com/feed/",                               "count": 2},
    {"name": "The Real Deal",     "url": "https://therealdeal.com/feed/",                             "count": 2},
    {"name": "ESPN",              "url": "https://www.espn.com/espn/rss/news",                        "count": 2},
    {"name": "Hyperallergic",     "url": "https://hyperallergic.com/feed/",                           "count": 2},
    {"name": "ARTnews",           "url": "https://www.artnews.com/feed/",                             "count": 2},
    {"name": "The Daily",         "url": "https://feeds.simplecast.com/54nAGcIl",                     "count": 1},
    {"name": "Today Explained",   "url": "https://feeds.megaphone.fm/VMP7396924040",                  "count": 1},
    {"name": "Majority Report",   "url": "https://feeds.simplecast.com/KfEjJJNr",                     "count": 1},
    {"name": "Planet Money",      "url": "https://feeds.npr.org/510289/podcast.xml",                  "count": 1},
    {"name": "Marketplace",       "url": "https://www.marketplace.org/feed/podcast/marketplace",      "count": 1},
    {"name": "Freakonomics",      "url": "https://feeds.simplecast.com/Y7FDrNoH",                     "count": 1},
    {"name": "How I Built This",  "url": "https://feeds.npr.org/510313/podcast.xml",                  "count": 1},
    {"name": "Pivot",             "url": "https://feeds.megaphone.fm/recodedecode",                   "count": 1},
]

def clean(text):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    for ent, rep in [("&amp;","&"),("&lt;","<"),("&gt;",">"),("&quot;",'"'),("&#39;","'"),("&nbsp;"," ")]:
        text = text.replace(ent, rep)
    return re.sub(r'\s+', ' ', text).strip()

def trim(text, n=200):
    if len(text) <= n:
        return text
    chunk = text[:n]
    for sep in ['. ','! ','? ']:
        idx = chunk.rfind(sep)
        if idx > 60:
            return chunk[:idx+1]
    return chunk.rstrip(',;:') + '.'

def fetch(source):
    try:
        feed = feedparser.parse(source["url"])
        out = []
        for e in feed.entries[:source["count"]]:
            title = clean(e.get("title", ""))
            raw = e.get("summary") or e.get("description") or ""
            if not raw and e.get("content"):
                raw = e["content"][0].get("value", "")
            summary = trim(clean(raw))
            if title:
                out.append((title, summary))
        return out
    except Exception as ex:
        print(f"  Warning: {source['name']}: {ex}", file=sys.stderr)
        return []

def build_script(date_str, content):
    parts = [f"Welcome to Omni. Your daily briefing for {date_str}. Feed on everything. Let's get into it."]
    for name, items in content:
        if not items:
            continue
        parts.append(f"  {name}.")
        for title, summary in items:
            parts.append(f"  {title}. {summary}" if summary else f"  {title}.")
    parts.append("  That's your Omni briefing. Stay curious, feed on everything, and I'll see you tomorrow.")
    return "  ".join(parts)

def update_feed(date_slug, date_str, mp3_file, mp3_size, duration_secs, blurb):
    pub = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    dur = f"{duration_secs//60}:{duration_secs%60:02d}"
    new_item = f"""    <item>
      <title>Omni Daily — {date_str}</title>
      <description><![CDATA[{blurb[:300]}]]></description>
      <enclosure url="{BASE_URL}/episodes/{mp3_file}" length="{mp3_size}" type="audio/mpeg"/>
      <guid isPermaLink="false">omni-{date_slug}</guid>
      <pubDate>{pub}</pubDate>
      <itunes:duration>{dur}</itunes:duration>
      <itunes:summary>Your daily briefing for {date_str}. Feed on everything.</itunes:summary>
    </item>"""
    old_items = ""
    if os.path.exists("feed.xml"):
        with open("feed.xml") as f:
            raw = f.read()
        existing = re.findall(r'<item>.*?</item>', raw, re.DOTALL)
        old_items = "\n".join(existing[:29])
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Omni</title>
    <link>{BASE_URL}</link>
    <description>Feed on everything. Daily digest of news, podcasts, finance, art, sports, and real estate.</description>
    <language>en-us</language>
    <itunes:author>Omni</itunes:author>
    <itunes:summary>Feed on everything. Daily briefings across news, finance, sports, art, real estate, and culture.</itunes:summary>
    <itunes:image href="{BASE_URL}/artwork.jpg"/>
    <itunes:category text="News"/>
    <itunes:explicit>false</itunes:explicit>
    <itunes:owner>
      <itunes:name>Omni</itunes:name>
      <itunes:email>kayla.dixon4@gmail.com</itunes:email>
    </itunes:owner>
{new_item}
{old_items}
  </channel>
</rss>"""
    with open("feed.xml", "w") as f:
        f.write(feed)

def main():
    pst = timezone(timedelta(hours=-8))
    now = datetime.now(timezone.utc).astimezone(pst)
    slug = now.strftime("%Y-%m-%d")
    date_str = now.strftime("%A, %B %d, %Y")
    print(f"Omni — generating episode: {date_str}")
    content = []
    for src in SOURCES:
        print(f"  Fetching {src['name']}...")
        content.append((src["name"], fetch(src)))
        time.sleep(0.3)
    script = build_script(date_str, content)
    print(f"  Script: {len(script):,} chars")
    os.makedirs("episodes", exist_ok=True)
    mp3_file = f"{slug}.mp3"
    mp3_path = f"episodes/{mp3_file}"
    print("  Generating audio...")
    gTTS(text=script, lang='en', slow=False).save(mp3_path)
    size = os.path.getsize(mp3_path)
    secs = int(len(script.split()) / 150 * 60)
    print(f"  Audio: {size:,} bytes (~{secs//60}m {secs%60:02d}s)")
    update_feed(slug, date_str, mp3_file, size, secs, script[:400])
    print("Done!")

if __name__ == "__main__":
    main()
