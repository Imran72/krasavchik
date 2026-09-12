import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from dotenv import load_dotenv
from supabase import create_client


# =========================================================
# ENV
# =========================================================

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

TIMEZONE = ZoneInfo(
    os.getenv("TIMEZONE") or "Europe/Moscow"
)

COMPETITION_START = date.fromisoformat(
    os.getenv("COMPETITION_START") or "2026-09-01"
)

REMINDER_HOUR = int(
    os.getenv("REMINDER_HOUR") or "22"
)

REMINDER_MINUTE = int(
    os.getenv("REMINDER_MINUTE") or "0"
)

REMINDER_TTL_HOURS = int(
    os.getenv("REMINDER_TTL_HOURS") or "2"
)


# =========================================================
# SUPABASE / ROUTER
# =========================================================

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
)

router = Router()


# =========================================================
# ПРИЗЫ
# =========================================================

PRIZES = {
    1: 4500,
    2: 4000,
    3: 3500,
    4: 3200,
    5: 3000,
    6: 2800,
    7: 2600,
    8: 2400,
    9: 2100,
    10: 1900,
}


# =========================================================
# НОРМАТИВЫ
# =========================================================

NORM_FIELDS = [
    ("morning_sport", "Утренний совместный спорт", 1.0),
    ("night_sport", "Ночной совместный спорт", 1.0),
    ("breakfast", "Совместный завтрак", 1.0),
    ("dinner", "Совместный ужин", 1.0),
    ("cooked_breakfast", "Приготовил завтрак", 0.5),
    ("cooked_dinner", "Приготовил ужин", 0.5),
    ("story_speaker", "Проведение рассказа", 1.0),
    ("story_listener", "Прослушивание рассказа", 1.0),
    ("academic_hour", "Академический час", 1.0),
]

NORM_KEYS = {item[0] for item in NORM_FIELDS}


# =========================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================================================

def now_local() -> datetime:
    return datetime.now(TIMEZONE)


def today() -> date:
    return now_local().date()


def yesterday() -> date:
    return today() - timedelta(days=1)


def is_allowed_date(norm_date: date) -> bool:
    if norm_date < COMPETITION_START:
        return False

    return norm_date in {
        today(),
        yesterday(),
    }


def calc_points(row: dict) -> float:
    total = 0.0

    for key, _, points in NORM_FIELDS:
        if bool(row.get(key)):
            total += points

    return round(total, 1)


def fmt_points(value) -> str:
    value = float(value or 0)

    if value.is_integer():
        return str(int(value))

    return f"{value:.1f}"


def telegram_full_name(tg_user) -> str:
    first_name = (tg_user.first_name or "").strip()
    last_name = (tg_user.last_name or "").strip()

    full_name = f"{first_name} {last_name}".strip()

    if full_name:
        return full_name

    if tg_user.username:
        return tg_user.username

    return f"Участник {tg_user.id}"


def place_label(place: int) -> str:
    if place == 1:
        return "🥇"
    if place == 2:
        return "🥈"
    if place == 3:
        return "🥉"

    return f"{place}."


def next_reminder_datetime() -> datetime:
    current = now_local()

    target = current.replace(
        hour=REMINDER_HOUR,
        minute=REMINDER_MINUTE,
        second=0,
        microsecond=0,
    )

    if current >= target:
        target += timedelta(days=1)

    return target


# =========================================================
# КЛАВИАТУРЫ
# =========================================================

def base_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚔️ Заполнить текущий день",
                    callback_data="fill_today",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 Заполнить предыдущий день",
                    callback_data="fill_yesterday",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏆 Рейтинг",
                    callback_data="rating",
                )
            ],
        ]
    )


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Вернуться в меню",
                    callback_data="menu",
                )
            ]
        ]
    )


def reminder_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Понял, согласен",
                    callback_data="ack_daily_reminder",
                )
            ]
        ]
    )


def day_keyboard(
    row: dict,
    norm_date: date,
) -> InlineKeyboardMarkup:
    buttons = []

    for key, label, points in NORM_FIELDS:
        checked = "✅" if row.get(key) else "⬜"

        buttons.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{checked} "
                        f"{label} "
                        f"(+{fmt_points(points)})"
                    ),
                    callback_data=(
                        f"toggle:"
                        f"{norm_date.isoformat()}:"
                        f"{key}"
                    ),
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="✅ Завершить день",
                callback_data="menu",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


# =========================================================
# БАЗА — ПОЛЬЗОВАТЕЛИ
# =========================================================

def get_user(telegram_id: int):
    rows = (
        supabase
        .table("bot_users")
        .select("*")
        .eq("telegram_id", telegram_id)
        .execute()
        .data
    )

    if not rows:
        return None

    return rows[0]


def get_or_create_user(tg_user) -> dict:
    existing = get_user(tg_user.id)

    username = (
        tg_user.username
        if tg_user.username
        else None
    )

    full_name = telegram_full_name(tg_user)

    if existing:
        updates = {}

        if existing.get("telegram_username") != username:
            updates["telegram_username"] = username

        if existing.get("full_name") != full_name:
            updates["full_name"] = full_name

        if not existing.get("is_active", True):
            updates["is_active"] = True

        if updates:
            updated_rows = (
                supabase
                .table("bot_users")
                .update(updates)
                .eq("id", existing["id"])
                .execute()
                .data
            )

            if updated_rows:
                return updated_rows[0]

        return existing

    created_rows = (
        supabase
        .table("bot_users")
        .insert(
            {
                "telegram_id": tg_user.id,
                "telegram_username": username,
                "full_name": full_name,
                "is_active": True,
                "last_ui_message_id": None,
                "ui_state": "menu",
                "ui_state_updated_at": (
                    now_local()
                    .astimezone(ZoneInfo("UTC"))
                    .isoformat()
                ),
            }
        )
        .execute()
        .data
    )

    return created_rows[0]


def update_ui_state(
    user_id,
    message_id,
    ui_state: str,
):
    (
        supabase
        .table("bot_users")
        .update(
            {
                "last_ui_message_id": message_id,
                "ui_state": ui_state,
                "ui_state_updated_at": (
                    now_local()
                    .astimezone(ZoneInfo("UTC"))
                    .isoformat()
                ),
            }
        )
        .eq("id", user_id)
        .execute()
    )


# =========================================================
# БАЗА — НОРМАТИВЫ
# =========================================================

def get_or_create_day(
    user_id,
    norm_date: date,
) -> dict:
    rows = (
        supabase
        .table("daily_norms")
        .select("*")
        .eq("user_id", user_id)
        .eq("norm_date", norm_date.isoformat())
        .execute()
        .data
    )

    if rows:
        return rows[0]

    created_rows = (
        supabase
        .table("daily_norms")
        .insert(
            {
                "user_id": user_id,
                "norm_date": norm_date.isoformat(),
            }
        )
        .execute()
        .data
    )

    return created_rows[0]


# =========================================================
# ТЕКСТЫ
# =========================================================

def base_menu_text() -> str:
    return (
        "⚔️ <b>ЛИГА КРАСАВЧИКОВ</b>\n\n"
        "Заполнять нормативы можно только "
        "за <b>текущий</b> и "
        "<b>предыдущий</b> день.\n\n"
        "Выбирай действие:"
    )


def day_text(
    norm_date: date,
    points: float,
) -> str:
    label = (
        "Сегодня"
        if norm_date == today()
        else "Вчера"
    )

    return (
        f"⚔️ <b>{label} — "
        f"{norm_date.strftime('%d.%m.%Y')}</b>\n\n"
        f"Набрано баллов: "
        f"<b>{fmt_points(points)}</b>\n\n"
        "Отмечай выполненные нормативы.\n"
        "Изменения сохраняются сразу."
    )


def reminder_text() -> str:
    return (
        "⏰ <b>Напоминание</b>\n\n"
        "Не забудь заполнить нормативы за сегодня."
    )


# =========================================================
# ОДНО СООБЩЕНИЕ НА ЧАТ
# =========================================================

async def delete_tracked_message(
    bot: Bot,
    user: dict,
):
    message_id = user.get(
        "last_ui_message_id"
    )

    if not message_id:
        return

    try:
        await bot.delete_message(
            chat_id=user["telegram_id"],
            message_id=message_id,
        )
    except Exception:
        pass


async def send_fresh_ui(
    bot: Bot,
    user: dict,
    text: str,
    reply_markup,
    ui_state: str,
):
    await delete_tracked_message(
        bot,
        user,
    )

    sent = await bot.send_message(
        chat_id=user["telegram_id"],
        text=text,
        reply_markup=reply_markup,
    )

    update_ui_state(
        user["id"],
        sent.message_id,
        ui_state,
    )

    return sent


async def edit_current_ui(
    callback: CallbackQuery,
    text: str,
    reply_markup,
    ui_state: str,
):
    user = get_or_create_user(
        callback.from_user
    )

    if callback.message:
        try:
            await callback.message.edit_text(
                text,
                reply_markup=reply_markup,
            )

            update_ui_state(
                user["id"],
                callback.message.message_id,
                ui_state,
            )

            return

        except Exception:
            pass

    await send_fresh_ui(
        callback.bot,
        user,
        text,
        reply_markup,
        ui_state,
    )


# =========================================================
# /START
# =========================================================

@router.message(CommandStart())
async def start(message: Message):
    user = get_or_create_user(
        message.from_user
    )

    await send_fresh_ui(
        message.bot,
        user,
        base_menu_text(),
        base_menu_kb(),
        "menu",
    )

    try:
        await message.delete()
    except Exception:
        pass


# =========================================================
# МЕНЮ
# =========================================================

@router.callback_query(
    F.data == "menu"
)
async def menu(callback: CallbackQuery):
    await callback.answer()

    await edit_current_ui(
        callback,
        base_menu_text(),
        base_menu_kb(),
        "menu",
    )


# =========================================================
# ТЕКУЩИЙ ДЕНЬ
# =========================================================

@router.callback_query(
    F.data == "fill_today"
)
async def fill_today(callback: CallbackQuery):
    await callback.answer()

    user = get_or_create_user(
        callback.from_user
    )

    norm_date = today()

    row = get_or_create_day(
        user["id"],
        norm_date,
    )

    points = calc_points(row)

    await edit_current_ui(
        callback,
        day_text(
            norm_date,
            points,
        ),
        day_keyboard(
            row,
            norm_date,
        ),
        "today",
    )


# =========================================================
# ПРЕДЫДУЩИЙ ДЕНЬ
# =========================================================

@router.callback_query(
    F.data == "fill_yesterday"
)
async def fill_yesterday(callback: CallbackQuery):
    await callback.answer()

    norm_date = yesterday()

    if not is_allowed_date(
        norm_date
    ):
        await callback.answer(
            "Предыдущий день недоступен",
            show_alert=True,
        )
        return

    user = get_or_create_user(
        callback.from_user
    )

    row = get_or_create_day(
        user["id"],
        norm_date,
    )

    points = calc_points(row)

    await edit_current_ui(
        callback,
        day_text(
            norm_date,
            points,
        ),
        day_keyboard(
            row,
            norm_date,
        ),
        "yesterday",
    )


# =========================================================
# БЛОКИРУЕМ СТАРЫЕ КНОПКИ ДОЗАПОЛНЕНИЯ
# =========================================================

@router.callback_query(
    F.data == "choose_date"
)
async def choose_date_disabled(
    callback: CallbackQuery,
):
    await callback.answer(
        (
            "Дозаполнение завершено. "
            "Теперь доступны только сегодня и вчера."
        ),
        show_alert=True,
    )

    await edit_current_ui(
        callback,
        base_menu_text(),
        base_menu_kb(),
        "menu",
    )


@router.callback_query(
    F.data.startswith("date:")
)
async def old_date_disabled(
    callback: CallbackQuery,
):
    await callback.answer(
        (
            "Эта дата больше недоступна. "
            "Теперь доступны только сегодня и вчера."
        ),
        show_alert=True,
    )

    await edit_current_ui(
        callback,
        base_menu_text(),
        base_menu_kb(),
        "menu",
    )


@router.callback_query(
    F.data == "ack_refill_notice"
)
async def old_refill_notice(
    callback: CallbackQuery,
):
    await callback.answer(
        "Окно дозаполнения уже закрыто.",
        show_alert=True,
    )

    user = get_or_create_user(
        callback.from_user
    )

    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass

    sent = await callback.bot.send_message(
        chat_id=user["telegram_id"],
        text=base_menu_text(),
        reply_markup=base_menu_kb(),
    )

    update_ui_state(
        user["id"],
        sent.message_id,
        "menu",
    )


# =========================================================
# ПЕРЕКЛЮЧЕНИЕ НОРМАТИВА
# =========================================================

@router.callback_query(
    F.data.startswith("toggle:")
)
async def toggle_norm(callback: CallbackQuery):
    user = get_or_create_user(
        callback.from_user
    )

    _, date_str, field = (
        callback.data.split(
            ":",
            2,
        )
    )

    if field not in NORM_KEYS:
        await callback.answer(
            "Неизвестный норматив",
            show_alert=True,
        )
        return

    norm_date = date.fromisoformat(
        date_str
    )

    if not is_allowed_date(
        norm_date
    ):
        await callback.answer(
            (
                "Эту дату уже нельзя редактировать. "
                "Доступны только сегодня и вчера."
            ),
            show_alert=True,
        )

        await edit_current_ui(
            callback,
            base_menu_text(),
            base_menu_kb(),
            "menu",
        )

        return

    row = get_or_create_day(
        user["id"],
        norm_date,
    )

    new_value = not bool(
        row.get(field)
    )

    updated_rows = (
        supabase
        .table("daily_norms")
        .update(
            {
                field: new_value,
            }
        )
        .eq(
            "id",
            row["id"],
        )
        .execute()
        .data
    )

    if updated_rows:
        row = updated_rows[0]
    else:
        row[field] = new_value

    points = calc_points(row)

    await callback.answer(
        "✅ Сохранено"
    )

    await edit_current_ui(
        callback,
        day_text(
            norm_date,
            points,
        ),
        day_keyboard(
            row,
            norm_date,
        ),
        (
            "today"
            if norm_date == today()
            else "yesterday"
        ),
    )


# =========================================================
# РЕЙТИНГ
# =========================================================

@router.callback_query(
    F.data == "rating"
)
async def rating(callback: CallbackQuery):
    await callback.answer()

    current_user = get_or_create_user(
        callback.from_user
    )

    users = (
        supabase
        .table("bot_users")
        .select(
            "id,"
            "telegram_id,"
            "full_name"
        )
        .eq(
            "is_active",
            True,
        )
        .execute()
        .data
    )

    daily_rows = (
        supabase
        .table("daily_norms")
        .select("*")
        .gte(
            "norm_date",
            COMPETITION_START.isoformat(),
        )
        .lte(
            "norm_date",
            today().isoformat(),
        )
        .execute()
        .data
    )

    score_by_user = {
        user["id"]: 0.0
        for user in users
    }

    for row in daily_rows:
        uid = row["user_id"]

        score_by_user[uid] = (
            score_by_user.get(
                uid,
                0.0,
            )
            + calc_points(row)
        )

    ranked = sorted(
        users,
        key=lambda user: (
            -score_by_user.get(
                user["id"],
                0.0,
            ),
            (
                user.get("full_name")
                or ""
            ).lower(),
        ),
    )

    my_place = None

    my_score = score_by_user.get(
        current_user["id"],
        0.0,
    )

    for index, user in enumerate(
        ranked,
        start=1,
    ):
        if (
            user["id"]
            == current_user["id"]
        ):
            my_place = index
            break

    lines = [
        "🏆 <b>РЕЙТИНГ КАЙФАРИКОВ</b>",
        "",
    ]

    for place in range(
        1,
        11,
    ):
        prize = PRIZES[place]

        prize_text = (
            f"{prize:,}"
            .replace(
                ",",
                " ",
            )
        )

        if place <= len(ranked):
            user = ranked[
                place - 1
            ]

            score = (
                score_by_user.get(
                    user["id"],
                    0.0,
                )
            )

            if (
                user["id"]
                == current_user["id"]
            ):
                shown_name = (
                    "⚔️ "
                    + user["full_name"]
                )
            else:
                shown_name = (
                    "Скрыто"
                )

            score_text = fmt_points(
                score
            )

        else:
            shown_name = "Скрыто"
            score_text = "0"

        lines.append(
            (
                f"{place_label(place)} "
                f"{shown_name} — "
                f"<b>{score_text}</b> б. — "
                f"💰 {prize_text} ₽"
            )
        )

    lines.append("")
    lines.append(
        "⚔️ <b>ТВОЯ ПОЗИЦИЯ</b>"
    )

    if my_place is not None:
        lines.append(
            f"Место: <b>{my_place}</b>"
        )

        lines.append(
            (
                "Баллы: "
                f"<b>{fmt_points(my_score)}</b>"
            )
        )

    await edit_current_ui(
        callback,
        "\n".join(lines),
        back_to_menu_kb(),
        "rating",
    )


# =========================================================
# ЕЖЕДНЕВНОЕ НАПОМИНАНИЕ
# =========================================================

@router.callback_query(
    F.data == "ack_daily_reminder"
)
async def ack_daily_reminder(
    callback: CallbackQuery,
):
    await callback.answer(
        "Принято 🤝"
    )

    user = get_or_create_user(
        callback.from_user
    )

    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass

    sent = await callback.bot.send_message(
        chat_id=user["telegram_id"],
        text=base_menu_text(),
        reply_markup=base_menu_kb(),
    )

    update_ui_state(
        user["id"],
        sent.message_id,
        "menu",
    )


async def send_daily_reminders(
    bot: Bot,
):
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

    for user in users:
        telegram_id = user.get(
            "telegram_id"
        )

        if not telegram_id:
            continue

        try:
            await delete_tracked_message(
                bot,
                user,
            )

            sent = await bot.send_message(
                chat_id=telegram_id,
                text=reminder_text(),
                reply_markup=reminder_kb(),
            )

            update_ui_state(
                user["id"],
                sent.message_id,
                "reminder",
            )

        except Exception as exc:
            logging.warning(
                "Reminder error for %s: %s",
                telegram_id,
                exc,
            )

        await asyncio.sleep(
            0.05
        )


async def reminder_scheduler(
    bot: Bot,
):
    while True:
        target = (
            next_reminder_datetime()
        )

        delay = (
            target
            - now_local()
        ).total_seconds()

        logging.info(
            "Next reminder at %s",
            target.isoformat(),
        )

        await asyncio.sleep(
            max(
                delay,
                1,
            )
        )

        await send_daily_reminders(
            bot
        )

        await asyncio.sleep(
            60
        )


# =========================================================
# АВТОВОЗВРАТ БАЗОВОГО СООБЩЕНИЯ ЧЕРЕЗ 2 ЧАСА
# =========================================================

async def reminder_expiration_scheduler(
    bot: Bot,
):
    while True:
        cutoff = (
            now_local()
            - timedelta(
                hours=REMINDER_TTL_HOURS
            )
        )

        cutoff_utc = (
            cutoff
            .astimezone(
                ZoneInfo("UTC")
            )
            .isoformat()
        )

        try:
            users = (
                supabase
                .table("bot_users")
                .select("*")
                .eq(
                    "is_active",
                    True,
                )
                .eq(
                    "ui_state",
                    "reminder",
                )
                .lt(
                    "ui_state_updated_at",
                    cutoff_utc,
                )
                .execute()
                .data
            )

            for user in users:
                try:
                    await delete_tracked_message(
                        bot,
                        user,
                    )

                    sent = await bot.send_message(
                        chat_id=user[
                            "telegram_id"
                        ],
                        text=base_menu_text(),
                        reply_markup=base_menu_kb(),
                    )

                    update_ui_state(
                        user["id"],
                        sent.message_id,
                        "menu",
                    )

                except Exception as exc:
                    logging.warning(
                        (
                            "Reminder expiration "
                            "error for %s: %s"
                        ),
                        user.get(
                            "telegram_id"
                        ),
                        exc,
                    )

                await asyncio.sleep(
                    0.05
                )

        except Exception as exc:
            logging.warning(
                (
                    "Reminder expiration "
                    "query error: %s"
                ),
                exc,
            )

        await asyncio.sleep(
            300
        )


# =========================================================
# УДАЛЕНИЕ СООБЩЕНИЙ ПОЛЬЗОВАТЕЛЯ
# =========================================================

@router.message()
async def cleanup_user_messages(
    message: Message,
):
    try:
        await message.delete()
    except Exception:
        pass


# =========================================================
# START
# =========================================================

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
    )

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    dispatcher = Dispatcher()

    dispatcher.include_router(
        router
    )

    reminder_task = asyncio.create_task(
        reminder_scheduler(
            bot
        )
    )

    expiration_task = asyncio.create_task(
        reminder_expiration_scheduler(
            bot
        )
    )

    try:
        await dispatcher.start_polling(
            bot
        )

    finally:
        reminder_task.cancel()
        expiration_task.cancel()

        await asyncio.gather(
            reminder_task,
            expiration_task,
            return_exceptions=True,
        )


if __name__ == "__main__":
    asyncio.run(
        main()
    )
