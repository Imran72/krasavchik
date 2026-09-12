import asyncio
import os

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
from supabase import create_client


# =========================================================
# ENV
# =========================================================

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]


# =========================================================
# SUPABASE
# =========================================================

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
)


# =========================================================
# УВЕДОМЛЕНИЕ
# =========================================================

def notice_text() -> str:

    return (
        "📢 <b>Дорогие участники!</b>\n\n"
        "По вашим просьбам даём возможность "
        "дозаполнить метрики с "
        "<b>01.09.2026</b> по текущий день.\n\n"
        "Такая возможность будет доступна "
        "<b>сейчас и до 00:00 по Москве</b>.\n\n"
        "После полуночи снова можно будет "
        "заполнять только текущий и предыдущий день."
    )


def notice_kb() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Понял, принял",
                    callback_data="ack_refill_notice",
                )
            ]
        ]
    )


# =========================================================
# РАССЫЛКА
# =========================================================

async def main():

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    users = (
        supabase
        .table("bot_users")
        .select("*")
        .eq(
            "is_active",
            True,
        )
        .execute()
        .data
    )

    sent_count = 0
    failed_count = 0

    for user in users:

        telegram_id = user.get(
            "telegram_id"
        )

        if not telegram_id:
            continue

        old_message_id = user.get(
            "last_ui_message_id"
        )

        # 1. Удаляем предыдущее отслеживаемое сообщение
        if old_message_id:

            try:

                await bot.delete_message(
                    chat_id=telegram_id,
                    message_id=old_message_id,
                )

            except Exception:
                pass

        # 2. Отправляем уведомление
        try:

            sent = await bot.send_message(
                chat_id=telegram_id,
                text=notice_text(),
                reply_markup=notice_kb(),
            )

            (
                supabase
                .table("bot_users")
                .update(
                    {
                        "last_ui_message_id": sent.message_id,
                        "ui_state": "refill_notice",
                    }
                )
                .eq(
                    "id",
                    user["id"],
                )
                .execute()
            )

            sent_count += 1

        except Exception as exc:

            failed_count += 1

            print(
                f"Ошибка для {telegram_id}: {exc}"
            )

        await asyncio.sleep(
            0.05
        )

    print(
        f"Готово. Отправлено: {sent_count}. "
        f"Ошибок: {failed_count}."
    )

    await bot.session.close()


if __name__ == "__main__":

    asyncio.run(
        main()
    )
