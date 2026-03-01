import json
import logging
import os
import re
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
import requests
from bs4 import BeautifulSoup
from discord.ext import tasks
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

BLOG_TAG_URL = os.getenv(
    "BLOG_TAG_URL",
    "https://supersolenoid.jp/?tag=CS%E5%85%A5%E8%B3%9E%E6%95%B0%E3%83%A9%E3%83%B3%E3%82%AD%E3%83%B3%E3%82%B0",
)
STATE_FILE = Path("state.json")
JST = ZoneInfo("Asia/Tokyo")
SEND_TIME = time(hour=9, minute=0, tzinfo=JST)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

ENTRY_ID_RE = re.compile(r"/blog-entry-(\d+)\.html")


def load_last_entry_id() -> int:
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f).get("last_entry_id", 0)
    return 0


def save_last_entry_id(entry_id: int) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_entry_id": entry_id}, f)


def get_og_image(url: str) -> str | None:
    """記事ページから og:image を取得する"""
    try:
        resp = requests.get(url, timeout=10, headers=HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            return og["content"]
    except Exception as e:
        logger.warning("og:image 取得失敗 %s: %s", url, e)
    return None


def scrape_articles() -> list[dict]:
    """タグページから記事一覧（タイトル・URL・サムネイル）を取得する"""
    resp = requests.get(BLOG_TAG_URL, timeout=15, headers=HEADERS)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    articles = []
    seen_urls: set[str] = set()
    article_pattern = re.compile(r"https://supersolenoid\.jp/blog-entry-\d+\.html")

    for link in soup.find_all("a", href=article_pattern):
        url = link["href"]
        if url in seen_urls:
            continue
        seen_urls.add(url)

        title_el = link.select_one(".fc2_recent_entry_thumb_blogtitle")
        img_el = link.find("img")

        title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
        thumbnail = img_el.get("src") if img_el else None

        m = ENTRY_ID_RE.search(url)
        entry_id = int(m.group(1)) if m else 0

        if title:
            articles.append({"url": url, "title": title, "thumbnail": thumbnail, "entry_id": entry_id})

    return articles


class DenenBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.channel_id = int(os.environ["DISCORD_CHANNEL_ID"])

    async def setup_hook(self) -> None:
        self.daily_post.start()

    async def on_ready(self) -> None:
        logger.info("Bot 起動: %s", self.user)

    @tasks.loop(time=SEND_TIME)
    async def daily_post(self) -> None:
        channel = self.get_channel(self.channel_id)
        if channel is None:
            logger.error("チャンネル ID %s が見つかりません", self.channel_id)
            return

        logger.info("タグページをスクレイピング中...")
        try:
            articles = scrape_articles()
        except Exception as e:
            logger.error("スクレイピング失敗: %s", e)
            return

        last_id = load_last_entry_id()
        new_articles = [a for a in articles if a["entry_id"] > last_id]

        if not new_articles:
            logger.info("新着記事なし")
            return

        # 古い順に送信する
        new_articles.sort(key=lambda a: a["entry_id"])

        logger.info("%d 件の新着記事を送信します", len(new_articles))
        for article in new_articles:
            og_image = get_og_image(article["url"]) or article["thumbnail"]

            embed = discord.Embed(
                title=article["title"],
                url=article["url"],
                color=discord.Color.blue(),
            )
            if og_image:
                embed.set_image(url=og_image)

            await channel.send(embed=embed)

        max_id = max(a["entry_id"] for a in new_articles)
        save_last_entry_id(max_id)
        logger.info("送信完了 (last_entry_id → %d)", max_id)

    @daily_post.before_loop
    async def before_daily_post(self) -> None:
        await self.wait_until_ready()


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("DISCORD_TOKEN が .env に設定されていません")

    client = DenenBot()
    client.run(token)
