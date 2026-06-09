#!/usr/bin/env python3
"""Omni Daily Podcast Generator — Feed on everything."""

import feedparser
import json
import os
import re
import sys
import time
import tempfile
from datetime import datetime, timezone, timedelta
from gtts import gTTS
from pydub import AudioSegment

BASE_URL  = "https://kaylad4-lgtm.github.io/omni-podcast"
SEEN_FILE = "seen_episodes.json"

# Voice config
VOICE_HOST   = dict(lang='en', tld='com')     # American — content
VOICE_SOURCE = dict(lang='en', tld='co.uk')   # British  — source callouts

# Category intros spoken before the source name
SOURCE_INTROS = {
    "New York Times":    "From the New York Times",
    "Los Angeles Times": "From the Los Angeles Times",
    "Bloomberg Markets": "In markets and finance, Bloomberg reports",
    "Inman Real Estate": "In real estate, Inman News",
    "The Real Deal":     "Also in real estate, The Real Deal is reporting",
    "ESPN":              "In sports, ESPN",
    "Hyperallergic":     "In the art world, Hyperallergic",
    "ARTnews":           "Also in art, ARTnews",
    "The Daily":         "Today's episode of The Daily from the New York Times",
    "Today Explained":   "On Today Explained from Vox",
    "Majority Report":   "On the Majority Report",
    "Planet Money":      "On Planet Money from NPR",
    "Marketplace":       "On Marketplace",
    "Freakonomics":      "On Freakonomics Radio",
    "How I Built This":  "On How I Built This",
    "Pivot":             "On Pivot with Kara Swisher and Scott Galloway",
}

SOURCES = [
    # News
    {"name": "New York Times",    "url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "count": 5},
    {"name": "Los Angeles Times", "url": "https://www.latimes.com/local/rss2.0.xml",                  "count": 4},
    {"name": "Bloomberg Markets", "url": "https://feeds.bloomberg.com/markets/news.rss",              "count": 4},
    {"name": "Inman Real Estate", "url": "https://www.inman.com/feed/",                               "count": 4},
    {"name": "The Real Deal",     "url": "https://therealdeal.com/feed/",                             "count": 4},
    {"name": "ESPN",              "url": "https://www.espn.com/espn/rss/news",                        "count": 4},
    {"name": "Hyperallergic",     "url": "https://hyperallergic.com/feed/",                           "count": 4},
    {"name": "ARTnews",           "url": "https://www.artnews.com/feed/",                             "count": 4},
    # Podcasts
    {"name": "The Daily",         "url": "https://feeds.simplecast.com/54nAGcIl",                     "count": 1},
    {"name": "Today Explained",   "url": "https://feeds.megaphone.fm/VMP7396924040",                  "count": 1},
    {"name": "Majority Report",   "url": "https://feeds.simplecast.com/KfEjJJNr",                     "count": 1},
    {"name": "Planet Money",      "url": "https://feeds.npr.org/510289/podcast.xml",                  "count": 1},
    {"name": "Marketplace",       "url": "https://www.marketplace.org/feed/podcast/marketplace",      "count": 1},
    {"name": "Freakonomics",      "url": "https://feeds.simplecast.com/Y7FDrNoH",                     "count": 1},
    {"name": "How I Built This",  "url": "https://feeds.npr.org/510313/podcast.xml",                  "count": 1},
    {"name": "Pivot",             "url": "https://feeds.megaphone.fm/recodedecode",                   "count": 1},
]

# ── helpers ───────────────────────────────────────────────────────────────────

def clean(text):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    for ent, rep in [("&amp;","&"),("&lt;","<"),("&gt;",">"),("&quot;",'"'),("&#39;","'"),("&nbsp;"," ")]:
        text = text.replace(ent, rep)
    return re.sub(r'\s+', ' ', text).strip()

def trim(text, n=700):
    if len(text) <= n:
        return text
    chunk = text[:n]
    for sep in ['. ', '! ', '? ']:
        idx = chunk.rfind(sep)
        if idx > 100:
            return chunk[:idx+1]
    return chunk.rstrip(',;:') + '.'

def entry_guid(entry):
    return entry.get("id") or entry.get("link") or entry.get("title", "")

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return json.load(f)
    return {}

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(seen, f, indent=2)

def fetch(source, seen):
    """Fetch source, skip if top entry unchanged since last run."""
    name = source["name"]
    try:
        feed = feedparser.parse(source["url"])
        if not feed.entries:
            print(f"  {name}: no entries found", file=sys.stderr)
            return [], seen

        # Check if anything is new compared to last run
        top_guid = entry_guid(feed.entries[0])
        if seen.get(name) == top_guid:
            print(f"  {name}: no new content, skipping")
            return [], seen

        # New content — update seen and collect entries
        seen[name] = top_guid
        out = []
        for e in feed.entries[:source["count"]]:
            title   = clean(e.get("title", ""))
            raw     = e.get("summary") or e.get("description") or ""
            if not raw and e.get("content"):
                raw = e["content"][0].get("value", "")
            summary = trim(clean(raw))
            if title:
                out.append((title, summary))
        return out, seen

    except Exception as ex:
        print(f"  ⚠ {name}: {ex}", file=sys.stderr)
        return [], seen

# ── audio builder ─────────────────────────────────────────────────────────────

def tts_segment(text, voice):
    """Generate a gTTS audio segment and return a pydub AudioSegment."""
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        path = tmp.name
    gTTS(text=text, **voice).save(path)
    seg = AudioSegment.from_mp3(path)
    os.unlink(path)
    return seg

def short_pause(ms=600):
    return AudioSegment.silent(duration=ms)

def build_audio(date_str, content):
    """Build full episode as a pydub AudioSegment using two voices."""
    audio = AudioSegment.empty()

    # Intro (host voice)
    intro = f"Welcome to Omni. Your daily briefing for {date_str}. Feed on everything. Let's get into it."
    audio += tts_segment(intro, VOICE_HOST) + short_pause(800)

    included = 0
    for name, items in content:
        if not items:
            continue
        included += 1

        # Source callout (British voice)
        callout = SOURCE_INTROS.get(name, f"From {name}")
        audio += tts_segment(callout, VOICE_SOURCE) + short_pause(400)

        # Stories (host voice)
        for title, summary in items:
            story = f"{title}. {summary}" if summary else f"{title}."
            audio += tts_segment(story, VOICE_HOST) + short_pause(500)

        audio += short_pause(400)

    # Outro (host voice)
    outro = (
        f"That's your Omni briefing for {date_str}. "
        f"You consumed {included} sources today. "
        "Stay curious, feed on everything, and I'll see you tomorrow."
    )
    audio += short_pause(600) + tts_segment(outro, VOICE_HOST)

    return audio

# ── RSS feed updater ──────────────────────────────────────────────────────────

def update_feed(date_slug, date_str, mp3_file, mp3_size, duration_secs):
    pub = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    dur = f"{duration_secs//60}:{duration_secs%60:02d}"

    new_item = f"""    <item>
      <title>Omni Daily — {date_str}</title>
      <description><![CDATA[Your daily briefing for {date_str}. Feed on everything.]]></description>
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
    print("  feed.xml updated")

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    pst      = timezone(timedelta(hours=-8))
    now      = datetime.now(timezone.utc).astimezone(pst)
    slug     = now.strftime("%Y-%m-%d")
    date_str = now.strftime("%A, %B %d, %Y")

    print(f"Omni — generating episode: {date_str}")

    seen = load_seen()

    content = []
    for src in SOURCES:
        print(f"  Fetching {src['name']}…")
        items, seen = fetch(src, seen)
        content.append((src["name"], items))
        time.sleep(0.3)

    print("  Building audio (two-voice)…")
    audio = build_audio(date_str, content)

    os.makedirs("episodes", exist_ok=True)
    mp3_file = f"{slug}.mp3"
    mp3_path = f"episodes/{mp3_file}"
    audio.export(mp3_path, format="mp3", bitrate="128k")

    size = os.path.getsize(mp3_path)
    secs = int(len(audio) / 1000)
    print(f"  Audio: {size:,} bytes  (~{secs//60}m {secs%60:02d}s)")

    save_seen(seen)
    update_feed(slug, date_str, mp3_file, size, secs)
    print("Done! ✓")

if __name__ == "__main__":
    main()
