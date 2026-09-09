import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
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

ADMIN_TELEGRAM_ID = int(
    os.getenv("ADMIN_TELEGRAM_ID") or "0"
)

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


MONTH_NAMES = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}


# =========================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================================================

def now_local() -> datetime:
    return datetime.now(
        TIMEZONE
    )


def today() -> date:
    return now_local().date()


def calc_points(
    row: dict,
) -> float:

    total = 0.0

    for key, _, points in NORM_FIELDS:
        if bool(
            row.get(key)
        ):
            total += points

    return round(
        total,
        1,
    )


def fmt_points(
    value,
) -> str:

    value = float(
        value or 0
    )

    if value.is_integer():
        return str(
            int(value)
        )

    return f"{value:.1f}"


def telegram_full_name(
    tg_user,
) -> str:

    first_name = (
        tg_user.first_name
        or ""
    ).strip()

    last_name = (
        tg_user.last_name
        or ""
    ).strip()

    full_name = (
        f"{first_name} {last_name}"
    ).strip()

    if full_name:
        return full_name

    if tg_user.username:
        return tg_user.username

    return f"Участник {tg_user.id}"


def place_label(
    place: int,
) -> str:

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
        target += timedelta(
            days=1
        )

    return target


# =========================================================
# КЛАВИАТУРЫ
# =========================================================

def menu_kb() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚔️ Выполнить нормативы сегодня",
                    callback_data="fill_today",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 Заполнить другой день",
                    callback_data="choose_date",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏆 Рейтинг кайфариков",
                    callback_data="rating",
                )
            ],
        ]
    )


def back_kb() -> InlineKeyboardMarkup:

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
                    text="✅ Заполнить нормативы",
                    callback_data="open_today_from_reminder",
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

        checked = (
            "✅"
            if row.get(key)
            else "⬜"
        )

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


def month_calendar_kb(
    year: int,
    month: int,
) -> InlineKeyboardMarkup:

    start = COMPETITION_START
    end = today()

    first = date(
        year,
        month,
        1,
    )

    if month == 12:
        next_month = date(
            year + 1,
            1,
            1,
        )
    else:
        next_month = date(
            year,
            month + 1,
            1,
        )

    last = (
        next_month
        - timedelta(days=1)
    )

    rows = [
        [
            InlineKeyboardButton(
                text=(
                    f"{MONTH_NAMES[month]} "
                    f"{year}"
                ),
                callback_data="noop",
            )
        ]
    ]

    rows.append(
        [
            InlineKeyboardButton(
                text=weekday,
                callback_data="noop",
            )
            for weekday in [
                "Пн",
                "Вт",
                "Ср",
                "Чт",
                "Пт",
                "Сб",
                "Вс",
            ]
        ]
    )

    offset = first.weekday()
    cells = [None] * offset

    cells += [
        date(
            year,
            month,
            day,
        )
        for day in range(
            1,
            last.day + 1,
        )
    ]

    while len(cells) % 7:
        cells.append(
            None
        )

    for i in range(
        0,
        len(cells),
        7,
    ):

        keyboard_row = []

        for day_value in cells[
            i:i + 7
        ]:

            if (
                day_value is None
                or day_value < start
                or day_value > end
            ):

                keyboard_row.append(
                    InlineKeyboardButton(
                        text="·",
                        callback_data="noop",
                    )
                )

            else:

                keyboard_row.append(
                    InlineKeyboardButton(
                        text=str(
                            day_value.day
                        ),
                        callback_data=(
                            f"date:"
                            f"{day_value.isoformat()}"
                        ),
                    )
                )

        rows.append(
            keyboard_row
        )

    nav = []

    prev_month_last_day = (
        first
        - timedelta(days=1)
    )

    prev_month_first_day = date(
        prev_month_last_day.year,
        prev_month_last_day.month,
        1,
    )

    competition_start_month = date(
        start.year,
        start.month,
        1,
    )

    competition_end_month = date(
        end.year,
        end.month,
        1,
    )

    if (
        prev_month_first_day
        >= competition_start_month
    ):

        nav.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=(
                    f"cal:"
                    f"{prev_month_first_day.year}-"
                    f"{prev_month_first_day.month:02d}"
                ),
            )
        )

    nav.append(
        InlineKeyboardButton(
            text="⬅️ В меню",
            callback_data="menu",
        )
    )

    if (
        next_month
        <= competition_end_month
    ):

        nav.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=(
                    f"cal:"
                    f"{next_month.year}-"
                    f"{next_month.month:02d}"
                ),
            )
        )

    rows.append(
        nav
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# БАЗА — ПОЛЬЗОВАТЕЛИ
# =========================================================

def get_user(
    telegram_id: int,
):

    rows = (
        supabase
        .table("bot_users")
        .select("*")
        .eq(
            "telegram_id",
            telegram_id,
        )
        .execute()
        .data
    )

    if not rows:
        return None

    return rows[0]


def set_last_ui_message(
    user_id,
    message_id: int | None,
):

    (
        supabase
        .table("bot_users")
        .update(
            {
                "last_ui_message_id": message_id,
            }
        )
        .eq(
            "id",
            user_id,
        )
        .execute()
    )


def get_or_create_user(
    tg_user,
) -> dict:

    existing = get_user(
        tg_user.id
    )

    username = (
        tg_user.username
        if tg_user.username
        else None
    )

    full_name = telegram_full_name(
        tg_user
    )

    if existing:

        updates = {}

        if (
            existing.get(
                "telegram_username"
            )
            != username
        ):
            updates[
                "telegram_username"
            ] = username

        if (
            existing.get(
                "full_name"
            )
            != full_name
        ):
            updates[
                "full_name"
            ] = full_name

        if not existing.get(
            "is_active",
            True,
        ):
            updates[
                "is_active"
            ] = True

        if updates:

            updated = (
                supabase
                .table("bot_users")
                .update(
                    updates
                )
                .eq(
                    "id",
                    existing["id"],
                )
                .execute()
                .data
            )

            if updated:
                return updated[0]

        return existing

    payload = {
        "telegram_id": tg_user.id,
        "telegram_username": username,
        "full_name": full_name,
        "is_active": True,
        "is_admin": (
            tg_user.id
            == ADMIN_TELEGRAM_ID
        ),
        "last_ui_message_id": None,
    }

    created = (
        supabase
        .table("bot_users")
        .insert(
            payload
        )
        .execute()
        .data
    )

    return created[0]


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
        .eq(
            "user_id",
            user_id,
        )
        .eq(
            "norm_date",
            norm_date.isoformat(),
        )
        .execute()
        .data
    )

    if rows:
        return rows[0]

    payload = {
        "user_id": user_id,
        "norm_date": (
            norm_date.isoformat()
        ),
    }

    created = (
        supabase
        .table("daily_norms")
        .insert(
            payload
        )
        .execute()
        .data
    )

    return created[0]


# =========================================================
# БАЗА — НАПОМИНАНИЯ
# =========================================================

def save_reminder(
    user_id,
    telegram_id: int,
    message_id: int,
):

    payload = {
        "user_id": user_id,
        "telegram_id": telegram_id,
        "message_id": message_id,
        "sent_at": (
            now_local()
            .astimezone(
                ZoneInfo("UTC")
            )
            .isoformat()
        ),
    }

    (
        supabase
        .table("reminder_messages")
        .insert(
            payload
        )
        .execute()
    )


def delete_reminder_row(
    message_id: int,
):

    (
        supabase
        .table("reminder_messages")
        .delete()
        .eq(
            "message_id",
            message_id,
        )
        .execute()
    )


# =========================================================
# УПРАВЛЕНИЕ ОДНИМ СООБЩЕНИЕМ
# =========================================================

async def delete_previous_ui(
    bot: Bot,
    user: dict,
):

    old_message_id = user.get(
        "last_ui_message_id"
    )

    if not old_message_id:
        return

    try:

        await bot.delete_message(
            chat_id=user[
                "telegram_id"
            ],
            message_id=old_message_id,
        )

    except Exception:
        pass

    try:

        set_last_ui_message(
            user["id"],
            None,
        )

    except Exception:
        pass


async def send_single_ui(
    bot: Bot,
    user: dict,
    text: str,
    reply_markup=None,
):

    await delete_previous_ui(
        bot,
        user,
    )

    sent = await bot.send_message(
        chat_id=user[
            "telegram_id"
        ],
        text=text,
        reply_markup=reply_markup,
    )

    set_last_ui_message(
        user["id"],
        sent.message_id,
    )

    return sent


async def safe_edit(
    callback: CallbackQuery,
    text: str,
    reply_markup=None,
):

    if callback.message is None:
        return

    user = get_or_create_user(
        callback.from_user
    )

    try:

        await (
            callback.message
            .edit_text(
                text,
                reply_markup=reply_markup,
            )
        )

        set_last_ui_message(
            user["id"],
            callback.message.message_id,
        )

        return

    except Exception:
        pass

    try:

        await callback.message.delete()

    except Exception:
        pass

    sent = await (
        callback.message
        .answer(
            text,
            reply_markup=reply_markup,
        )
    )

    set_last_ui_message(
        user["id"],
        sent.message_id,
    )


# =========================================================
# ЭКРАНЫ
# =========================================================

async def show_menu(
    callback: CallbackQuery,
):

    await safe_edit(
        callback,
        (
            "⚔️ <b>ЛИГА КРАСАВЧИКОВ</b>\n\n"
            "Выбирай свой следующий ход:"
        ),
        menu_kb(),
    )


async def show_day(
    callback: CallbackQuery,
    norm_date: date,
):

    user = get_or_create_user(
        callback.from_user
    )

    if (
        norm_date
        < COMPETITION_START
        or norm_date
        > today()
    ):

        await callback.answer(
            "Эту дату заполнять нельзя",
            show_alert=True,
        )

        return

    row = get_or_create_day(
        user["id"],
        norm_date,
    )

    points = calc_points(
        row
    )

    text = (
        f"⚔️ <b>День "
        f"{norm_date.strftime('%d.%m.%Y')}</b>\n\n"
        f"Набрано баллов: "
        f"<b>{fmt_points(points)}</b>\n\n"
        "Отмечай выполненные нормативы.\n"
        "Каждое изменение сохраняется сразу."
    )

    await safe_edit(
        callback,
        text,
        day_keyboard(
            row,
            norm_date,
        ),
    )


# =========================================================
# /START
# =========================================================

@router.message(
    CommandStart()
)
async def start(
    message: Message,
):

    user = get_or_create_user(
        message.from_user
    )

    greeting = (
        "⚔️ <b>ВОУ! ПРИВЕТСТВУЮ ТЕБЯ "
        "В ЛИГЕ КРАСАВЧИКОВ.</b>\n\n"
        "Здесь собираются те, кто не ищет "
        "лёгких путей.\n\n"
        "Каждый день — новый поход.\n"
        "Каждый выполненный норматив — "
        "балл в твою копилку.\n"
        "А в конце лучшие воины дружины "
        "заберут свою добычу 💰\n\n"
        "🛡 <b>Держи строй.</b>\n"
        "⚔️ <b>Выполняй нормативы.</b>\n"
        "🏆 <b>Поднимайся в рейтинге.</b>\n\n"
        f"Добро пожаловать, "
        f"<b>{user['full_name']}</b>.\n\n"
        "Да начнётся битва!"
    )

    await send_single_ui(
        message.bot,
        user,
        greeting,
        menu_kb(),
    )

    try:

        await message.delete()

    except Exception:
        pass


# =========================================================
# КНОПКА ИЗ РАССЫЛКИ ПРАВИЛ
# =========================================================

@router.callback_query(
    F.data == "ack_rules_update"
)
async def acknowledge_rules_update(
    callback: CallbackQuery,
):

    await callback.answer(
        "Погнали 🤝"
    )

    user = get_or_create_user(
        callback.from_user
    )

    old_message_id = (
        callback.message.message_id
        if callback.message
        else None
    )

    try:

        await callback.message.delete()

    except Exception:
        pass

    if old_message_id:
        try:
            set_last_ui_message(
                user["id"],
                None,
            )
        except Exception:
            pass

    norm_date = today()

    row = get_or_create_day(
        user["id"],
        norm_date,
    )

    points = calc_points(
        row
    )

    text = (
        f"⚔️ <b>День "
        f"{norm_date.strftime('%d.%m.%Y')}</b>\n\n"
        f"Набрано баллов: "
        f"<b>{fmt_points(points)}</b>\n\n"
        "Отмечай выполненные нормативы.\n"
        "Каждое изменение сохраняется сразу."
    )

    await send_single_ui(
        callback.bot,
        user,
        text,
        day_keyboard(
            row,
            norm_date,
        ),
    )


# =========================================================
# КНОПКА ИЗ ЕЖЕДНЕВНОГО НАПОМИНАНИЯ
# =========================================================

@router.callback_query(
    F.data == "open_today_from_reminder"
)
async def open_today_from_reminder(
    callback: CallbackQuery,
):

    await callback.answer(
        "Погнали ⚔️"
    )

    user = get_or_create_user(
        callback.from_user
    )

    message_id = (
        callback.message.message_id
        if callback.message
        else None
    )

    try:

        await callback.message.delete()

    except Exception:
        pass

    if message_id:

        try:

            delete_reminder_row(
                message_id
            )

        except Exception:
            pass

    try:

        set_last_ui_message(
            user["id"],
            None,
        )

    except Exception:
        pass

    norm_date = today()

    row = get_or_create_day(
        user["id"],
        norm_date,
    )

    points = calc_points(
        row
    )

    text = (
        f"⚔️ <b>День "
        f"{norm_date.strftime('%d.%m.%Y')}</b>\n\n"
        f"Набрано баллов: "
        f"<b>{fmt_points(points)}</b>\n\n"
        "Отмечай выполненные нормативы.\n"
        "Каждое изменение сохраняется сразу."
    )

    await send_single_ui(
        callback.bot,
        user,
        text,
        day_keyboard(
            row,
            norm_date,
        ),
    )


# =========================================================
# /ADMIN
# =========================================================

@router.message(
    Command("admin")
)
async def admin(
    message: Message,
):

    if (
        message.from_user.id
        != ADMIN_TELEGRAM_ID
    ):

        try:

            await message.delete()

        except Exception:
            pass

        return

    users = (
        supabase
        .table("bot_users")
        .select(
            "id",
            count="exact",
        )
        .eq(
            "is_active",
            True,
        )
        .execute()
    )

    norms = (
        supabase
        .table("daily_norms")
        .select(
            "id",
            count="exact",
        )
        .execute()
    )

    user = get_or_create_user(
        message.from_user
    )

    text = (
        "👑 <b>Админка</b>"
        "\n\n"
        "Участников: "
        f"<b>{users.count or 0}</b>"
        "\n"
        "Заполненных дней: "
        f"<b>{norms.count or 0}</b>"
    )

    await send_single_ui(
        message.bot,
        user,
        text,
        menu_kb(),
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
async def menu(
    callback: CallbackQuery,
):

    get_or_create_user(
        callback.from_user
    )

    await callback.answer()

    await show_menu(
        callback
    )


# =========================================================
# СЕГОДНЯ
# =========================================================

@router.callback_query(
    F.data == "fill_today"
)
async def fill_today(
    callback: CallbackQuery,
):

    await callback.answer()

    await show_day(
        callback,
        today(),
    )


# =========================================================
# ВЫБОР ДАТЫ
# =========================================================

@router.callback_query(
    F.data == "choose_date"
)
async def choose_date(
    callback: CallbackQuery,
):

    get_or_create_user(
        callback.from_user
    )

    await callback.answer()

    current_day = today()

    await safe_edit(
        callback,
        "📜 <b>Выбери день</b>",
        month_calendar_kb(
            current_day.year,
            current_day.month,
        ),
    )


# =========================================================
# НАВИГАЦИЯ КАЛЕНДАРЯ
# =========================================================

@router.callback_query(
    F.data.startswith("cal:")
)
async def calendar_nav(
    callback: CallbackQuery,
):

    await callback.answer()

    ym = callback.data.split(
        ":",
        1,
    )[1]

    year, month = map(
        int,
        ym.split("-"),
    )

    requested_month = date(
        year,
        month,
        1,
    )

    min_month = date(
        COMPETITION_START.year,
        COMPETITION_START.month,
        1,
    )

    current_day = today()

    max_month = date(
        current_day.year,
        current_day.month,
        1,
    )

    if (
        requested_month
        < min_month
        or requested_month
        > max_month
    ):
        return

    await safe_edit(
        callback,
        "📜 <b>Выбери день</b>",
        month_calendar_kb(
            year,
            month,
        ),
    )


# =========================================================
# ВЫБОР КОНКРЕТНОЙ ДАТЫ
# =========================================================

@router.callback_query(
    F.data.startswith("date:")
)
async def date_selected(
    callback: CallbackQuery,
):

    await callback.answer()

    selected_date = (
        date.fromisoformat(
            callback.data.split(
                ":",
                1,
            )[1]
        )
    )

    await show_day(
        callback,
        selected_date,
    )


# =========================================================
# ПЕРЕКЛЮЧЕНИЕ НОРМАТИВА
# =========================================================

@router.callback_query(
    F.data.startswith("toggle:")
)
async def toggle_norm(
    callback: CallbackQuery,
):

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

    if (
        norm_date
        < COMPETITION_START
        or norm_date
        > today()
    ):

        await callback.answer(
            "Эту дату заполнять нельзя",
            show_alert=True,
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

    points = calc_points(
        row
    )

    await callback.answer(
        "✅ Сохранено"
    )

    text = (
        f"⚔️ <b>День "
        f"{norm_date.strftime('%d.%m.%Y')}</b>"
        "\n\n"
        "Набрано баллов: "
        f"<b>{fmt_points(points)}</b>"
        "\n\n"
        "Отмечай выполненные нормативы.\n"
        "Каждое изменение сохраняется сразу."
    )

    await safe_edit(
        callback,
        text,
        day_keyboard(
            row,
            norm_date,
        ),
    )


# =========================================================
# РЕЙТИНГ
# =========================================================

@router.callback_query(
    F.data == "rating"
)
async def rating(
    callback: CallbackQuery,
):

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

        user_id = row["user_id"]

        score_by_user[user_id] = (
            score_by_user.get(
                user_id,
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

        prize = PRIZES[
            place
        ]

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

            score = score_by_user.get(
                user["id"],
                0.0,
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

                shown_name = "Скрыто"

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
            (
                "Место: "
                f"<b>{my_place}</b>"
            )
        )

        lines.append(
            (
                "Баллы: "
                f"<b>{fmt_points(my_score)}</b>"
            )
        )

    await safe_edit(
        callback,
        "\n".join(
            lines
        ),
        back_kb(),
    )


# =========================================================
# ПУСТЫЕ КНОПКИ КАЛЕНДАРЯ
# =========================================================

@router.callback_query(
    F.data == "noop"
)
async def noop(
    callback: CallbackQuery,
):

    await callback.answer()


# =========================================================
# УДАЛЕНИЕ ЛИШНИХ СООБЩЕНИЙ ПОЛЬЗОВАТЕЛЯ
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
# ЕЖЕДНЕВНЫЕ НАПОМИНАНИЯ
# =========================================================

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

            # Перед напоминанием удаляем старый экран бота.
            await delete_previous_ui(
                bot,
                user,
            )

            sent = await bot.send_message(
                chat_id=telegram_id,
                text=(
                    "⏰ <b>Время заполнить нормативы</b>\n\n"
                    "День почти закончился — "
                    "отметь, что успел сделать сегодня ⚔️"
                ),
                reply_markup=reminder_kb(),
            )

            set_last_ui_message(
                user["id"],
                sent.message_id,
            )

            save_reminder(
                user_id=user["id"],
                telegram_id=telegram_id,
                message_id=sent.message_id,
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

        target = next_reminder_datetime()

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


async def cleanup_old_reminders(
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

            old_rows = (
                supabase
                .table("reminder_messages")
                .select(
                    "id,"
                    "user_id,"
                    "telegram_id,"
                    "message_id"
                )
                .lt(
                    "sent_at",
                    cutoff_utc,
                )
                .execute()
                .data
            )

            for row in old_rows:

                try:

                    await bot.delete_message(
                        chat_id=row[
                            "telegram_id"
                        ],
                        message_id=row[
                            "message_id"
                        ],
                    )

                except Exception:
                    pass

                try:

                    current_user_rows = (
                        supabase
                        .table("bot_users")
                        .select(
                            "last_ui_message_id"
                        )
                        .eq(
                            "id",
                            row["user_id"],
                        )
                        .execute()
                        .data
                    )

                    if current_user_rows:

                        current_last = (
                            current_user_rows[0]
                            .get(
                                "last_ui_message_id"
                            )
                        )

                        if (
                            current_last
                            == row["message_id"]
                        ):

                            set_last_ui_message(
                                row["user_id"],
                                None,
                            )

                except Exception:
                    pass

                try:

                    (
                        supabase
                        .table(
                            "reminder_messages"
                        )
                        .delete()
                        .eq(
                            "id",
                            row["id"],
                        )
                        .execute()
                    )

                except Exception:
                    pass

        except Exception as exc:

            logging.warning(
                "Reminder cleanup error: %s",
                exc,
            )

        await asyncio.sleep(
            300
        )


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

    logging.info(
        "Bot started"
    )

    reminder_task = asyncio.create_task(
        reminder_scheduler(
            bot
        )
    )

    cleanup_task = asyncio.create_task(
        cleanup_old_reminders(
            bot
        )
    )

    try:

        await dispatcher.start_polling(
            bot
        )

    finally:

        reminder_task.cancel()
        cleanup_task.cancel()

        await asyncio.gather(
            reminder_task,
            cleanup_task,
            return_exceptions=True,
        )


if __name__ == "__main__":

    asyncio.run(
        main()
    )
