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
    (
        "morning_sport",
        "Утренний совместный спорт",
        1.0,
    ),
    (
        "night_sport",
        "Ночной совместный спорт",
        1.0,
    ),
    (
        "breakfast",
        "Совместный завтрак",
        1.0,
    ),
    (
        "dinner",
        "Совместный ужин",
        1.0,
    ),
    (
        "cooked_breakfast",
        "Приготовил завтрак",
        0.5,
    ),
    (
        "cooked_dinner",
        "Приготовил ужин",
        0.5,
    ),
    (
        "story_speaker",
        "Проведение рассказа",
        1.0,
    ),
    (
        "story_listener",
        "Прослушивание рассказа",
        1.0,
    ),
    (
        "academic_hour",
        "Академический час",
        1.0,
    ),
]

NORM_KEYS = {
    item[0]
    for item in NORM_FIELDS
}


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

def today() -> date:
    return datetime.now(
        TIMEZONE
    ).date()


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
                    text="🏆 Рейтинг дружины",
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
                    text="⬅️ Вернуться в лагерь",
                    callback_data="menu",
                )
            ]
        ]
    )


def day_keyboard(
    row: dict,
    norm_date: date,
) -> InlineKeyboardMarkup:

    buttons = []

    for (
        key,
        label,
        points,
    ) in NORM_FIELDS:

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
                text="🛡 Завершить поход",
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

    cells = (
        [None] * offset
    )

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
            text="🏕 В лагерь",
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
    user_id: int,
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
# РЕДАКТИРОВАНИЕ СООБЩЕНИЙ
# =========================================================

async def safe_edit(
    callback: CallbackQuery,
    text: str,
    reply_markup: (
        InlineKeyboardMarkup
        | None
    ) = None,
):

    if callback.message is None:
        return

    try:

        await (
            callback.message
            .edit_text(
                text,
                reply_markup=reply_markup,
            )
        )

        return

    except Exception:
        pass

    try:

        await callback.message.delete()

    except Exception:
        pass

    await (
        callback.message
        .answer(
            text,
            reply_markup=reply_markup,
        )
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
            "Дружина в сборе.\n\n"
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
        f"⚔️ <b>Поход за "
        f"{norm_date.strftime('%d.%m.%Y')}</b>\n\n"
        f"Добыто баллов: "
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
        f"Добро пожаловать в дружину, "
        f"<b>{user['full_name']}</b>.\n\n"
        "Да начнётся битва!"
    )

    await message.answer(
        greeting,
        reply_markup=menu_kb(),
    )

    try:

        await message.delete()

    except Exception:
        pass


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

    await message.answer(
        (
            "👑 <b>Ярл дружины</b>"
            "\n\n"
            "Воинов в Лиге: "
            f"<b>{users.count or 0}</b>"
            "\n"
            "Заполненных дней: "
            f"<b>{norms.count or 0}</b>"
        )
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
        "📜 <b>Выбери день прошлого похода</b>",
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
        "📜 <b>Выбери день прошлого похода</b>",
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
        "⚔️ Записано в летопись"
    )

    text = (
        f"⚔️ <b>Поход за "
        f"{norm_date.strftime('%d.%m.%Y')}</b>"
        "\n\n"
        "Добыто баллов: "
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

    lines = [
        "🏆 <b>РЕЙТИНГ ДРУЖИНЫ</b>",
        "",
    ]

    my_place = None

    my_score = score_by_user.get(
        current_user["id"],
        0.0,
    )

    for (
        index,
        user,
    ) in enumerate(
        ranked,
        start=1,
    ):

        if (
            user["id"]
            == current_user["id"]
        ):

            my_place = index

        if index > 10:
            continue

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

        prize = PRIZES.get(
            index,
            0,
        )

        if index == 1:

            place_label = "🥇"

        elif index == 2:

            place_label = "🥈"

        elif index == 3:

            place_label = "🥉"

        else:

            place_label = (
                f"{index}."
            )

        prize_text = (
            f"{prize:,}"
            .replace(
                ",",
                " ",
            )
        )

        score_text = fmt_points(
            score_by_user[
                user["id"]
            ]
        )

        lines.append(
            (
                f"{place_label} "
                f"{shown_name} — "
                f"<b>{score_text}</b> б. — "
                f"💰 {prize_text} ₽"
            )
        )

    if not ranked:

        lines.append(
            "Пока дружина пуста."
        )

    lines.append("")

    if my_place is not None:

        lines.append(
            "⚔️ <b>ТВОЯ ПОЗИЦИЯ</b>"
        )

        lines.append(
            (
                "Место: "
                f"<b>{my_place} "
                f"из {len(ranked)}</b>"
            )
        )

        lines.append(
            (
                "Баллы: "
                f"<b>{fmt_points(my_score)}</b>"
            )
        )

        if (
            my_place > 10
            and len(ranked) >= 10
        ):

            tenth_score = (
                score_by_user[
                    ranked[9]["id"]
                ]
            )

            gap = max(
                0.0,
                tenth_score
                - my_score,
            )

            lines.append(
                (
                    "До попадания в десятку: "
                    f"<b>{fmt_points(gap)}</b> б."
                )
            )

        elif my_place > 1:

            previous_score = (
                score_by_user[
                    ranked[
                        my_place - 2
                    ]["id"]
                ]
            )

            gap = max(
                0.0,
                previous_score
                - my_score,
            )

            lines.append(
                (
                    f"До {my_place - 1}-го места: "
                    f"<b>{fmt_points(gap)}</b> б."
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
# УДАЛЕНИЕ ЛИШНИХ СООБЩЕНИЙ
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

    logging.info(
        "Bot started"
    )

    await dispatcher.start_polling(
        bot
    )


if __name__ == "__main__":

    asyncio.run(
        main()
    )