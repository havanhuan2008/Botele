from db import init_db, get_setting
from bot_manager import BotManager
import time

init_db()

bot = BotManager()
token = get_setting("bot_token")
if not token:
    raise SystemExit("No bot_token set. Set it via the Web panel after deploy.")

bot.configure(token)
bot.start()

# giữ process sống
while True:
    time.sleep(60)