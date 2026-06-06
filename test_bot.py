import asyncio
from telegram import Bot
from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def test():
    bot = Bot(TOKEN)
    me = await bot.get_me()
    print(f"Bot works: @{me.username}")

asyncio.run(test())