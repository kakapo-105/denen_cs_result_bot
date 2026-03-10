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
    "https://supersolenoid.jp/?tag=%E5%A4%A7%E4%BC%9A%E7%B5%90%E6%9E%9C",
)
STATE_FILE = Path(os.getenv("STATE_FILE", "state.json"))
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



def scrape_articles() -> list[dict]:
    """タグページから記事一覧（タイトル・URL・サムネイル）を取得する"""
    resp = requests.get(BLOG_TAG_URL, timeout=15, headers=HEADERS)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    main_column = soup.select_one("#main-column")
    if main_column is None:
        logger.warning("#main-column が見つかりません")
        return []

    articles = []
    for entry in main_column.select(".EntryBlock"):
        title_el = entry.select_one(".EntryTitle a[href]")
        if title_el is None:
            continue

        url = title_el.get("href", "")
        m = ENTRY_ID_RE.search(url)
        if not m:
            continue

        title = title_el.get_text(strip=True)
        if not title:
            continue

        img_el = entry.select_one(".EntryBody img")
        thumbnail = img_el.get("src") if img_el else None
        entry_id = int(m.group(1))

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

        # 初回起動時（state.json未作成）は送信せず最新IDを保存して終了
        if last_id == 0:
            max_id = max(a["entry_id"] for a in new_articles)
            save_last_entry_id(max_id)
            logger.info("初回起動: 現在の最新記事IDを保存しました (last_entry_id → %d)", max_id)
            return

        # 古い順に送信する
        new_articles.sort(key=lambda a: a["entry_id"])

        logger.info("%d 件の新着記事を送信します", len(new_articles))
        for article in new_articles:
            embed = discord.Embed(
                title=article["title"],
                url=article["url"],
                color=discord.Color.blue(),
            )
            if article["thumbnail"]:
                embed.set_image(url=article["thumbnail"])

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
