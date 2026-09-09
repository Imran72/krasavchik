import asyncio
import os

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

MESSAGE = """
⚔️ <b>Важное обновление!</b>

С завтрашнего дня меняются правила заполнения нормативов.

📅 Добавлять и изменять данные можно будет только:

• за <b>текущий день</b>;
• за <b>вчерашний день</b>.

Более ранние даты станут недоступны для редактирования.

Поэтому не откладывай заполнение нормативов надолго 🫡
""".strip()

def notification_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🤝 Я понял, двигаемся дальше",
                    callback_data="ack_rules_update",
                )
            ]
        ]
    )

async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    users = (
        supabase.table("bot_users")
        .select("telegram_id")
        .eq("is_active", True)
        .execute()
        .data
    )

    success = 0
    failed = 0

    for user in users:
        telegram_id = user.get("telegram_id")
        if not telegram_id:
            continue

        try:
            await bot.send_message(
                chat_id=telegram_id,
                text=MESSAGE,
                reply_markup=notification_keyboard(),
            )
            success += 1
            print(f"OK: {telegram_id}")
        except Exception as e:
            failed += 1
            print(f"ERROR {telegram_id}: {e}")

        await asyncio.sleep(0.05)

    await bot.session.close()

    print("==============================")
    print(f"Отправлено: {success}")
    print(f"Ошибок: {failed}")
    print("==============================")

if __name__ == "__main__":
    asyncio.run(main())
