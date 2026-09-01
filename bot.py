import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Europe/Moscow"))
COMPETITION_START = date.fromisoformat(os.getenv("COMPETITION_START", "2026-09-01"))

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
router = Router()

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


def today() -> date:
    return datetime.now(TIMEZONE).date()


def calc_points(row: dict) -> float:
    total = 0.0
    for key, _, points in NORM_FIELDS:
        if row.get(key):
            total += points
    return round(total, 1)


def fmt_points(value) -> str:
    value = float(value or 0)
    return str(int(value)) if value.is_integer() else f"{value:.1f}"


def menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Заполнить сегодня", callback_data="fill_today")],
        [InlineKeyboardButton(text="📅 Заполнить другой день", callback_data="choose_date")],
        [InlineKeyboardButton(text="🏆 Рейтинг", callback_data="rating")],
    ])


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")]
    ])


def get_user(telegram_id: int):
    rows = (
        supabase.table("bot_users")
        .select("*")
        .eq("telegram_id", telegram_id)
        .eq("is_active", True)
        .execute()
        .data
    )
    return rows[0] if rows else None


def get_or_create_day(user_id: str, norm_date: date) -> dict:
    rows = (
        supabase.table("daily_norms")
        .select("*")
        .eq("user_id", user_id)
        .eq("norm_date", norm_date.isoformat())
        .execute()
        .data
    )
    if rows:
        return rows[0]

    payload = {"user_id": user_id, "norm_date": norm_date.isoformat(), "points": 0}
    return supabase.table("daily_norms").insert(payload).execute().data[0]


def day_keyboard(row: dict, norm_date: date) -> InlineKeyboardMarkup:
    buttons = []
    for key, label, points in NORM_FIELDS:
        checked = "✅" if row.get(key) else "⬜"
        buttons.append([
            InlineKeyboardButton(
                text=f"{checked} {label} (+{fmt_points(points)})",
                callback_data=f"toggle:{norm_date.isoformat()}:{key}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🏁 Завершить", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def month_calendar_kb(year: int, month: int) -> InlineKeyboardMarkup:
    start = COMPETITION_START
    end = today()
    first = date(year, month, 1)
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    last = next_month - timedelta(days=1)

    rows = [[InlineKeyboardButton(text=f"{first.strftime('%B %Y')}", callback_data="noop")]]
    rows.append([InlineKeyboardButton(text=x, callback_data="noop") for x in ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]])

    offset = first.weekday()
    cells = [None] * offset + [date(year, month, d) for d in range(1, last.day + 1)]
    while len(cells) % 7:
        cells.append(None)

    for i in range(0, len(cells), 7):
        row = []
        for d in cells[i:i+7]:
            if not d or d < start or d > end:
                row.append(InlineKeyboardButton(text="·", callback_data="noop"))
            else:
                row.append(InlineKeyboardButton(text=str(d.day), callback_data=f"date:{d.isoformat()}"))
        rows.append(row)

    nav = []
    prev_month = first - timedelta(days=1)
    if date(prev_month.year, prev_month.month, 1) >= date(start.year, start.month, 1):
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"cal:{prev_month.year}-{prev_month.month:02d}"))
    nav.append(InlineKeyboardButton(text="⬅️ Меню", callback_data="menu"))
    if next_month <= date(end.year, end.month, 1):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"cal:{next_month.year}-{next_month.month:02d}"))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def safe_edit(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=reply_markup)


async def show_menu(callback: CallbackQuery):
    await safe_edit(callback, "🏠 <b>Конкурс общежития</b>\n\nВыберите действие:", menu_kb())


async def show_day(callback: CallbackQuery, norm_date: date):
    user = get_user(callback.from_user.id)
    if not user:
        await safe_edit(callback, "⛔ У вас нет доступа к боту.", None)
        return
    if norm_date < COMPETITION_START or norm_date > today():
        await callback.answer("Эту дату заполнять нельзя", show_alert=True)
        return
    row = get_or_create_day(user["id"], norm_date)
    text = (
        f"📅 <b>{norm_date.strftime('%d.%m.%Y')}</b>\n"
        f"Баллы за день: <b>{fmt_points(row.get('points'))}</b>\n\n"
        "Нажимайте на нормативы, чтобы включать или выключать их. Изменения сохраняются сразу."
    )
    await safe_edit(callback, text, day_keyboard(row, norm_date))


@router.message(CommandStart())
async def start(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("⛔ У вас нет доступа к боту. Обратитесь к администратору.")
        return
    await message.answer("🏠 <b>Конкурс общежития</b>\n\nВыберите действие:", reply_markup=menu_kb())
    try:
        await message.delete()
    except Exception:
        pass


@router.message(Command("admin"))
async def admin(message: Message):
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return
    users = supabase.table("bot_users").select("id", count="exact").eq("is_active", True).execute()
    norms = supabase.table("daily_norms").select("id", count="exact").execute()
    await message.answer(f"👑 Админ\nАктивных участников: {users.count or 0}\nЗаписей по дням: {norms.count or 0}")


@router.callback_query(F.data == "menu")
async def menu(callback: CallbackQuery):
    await callback.answer()
    await show_menu(callback)


@router.callback_query(F.data == "fill_today")
async def fill_today(callback: CallbackQuery):
    await callback.answer()
    await show_day(callback, today())


@router.callback_query(F.data == "choose_date")
async def choose_date(callback: CallbackQuery):
    await callback.answer()
    d = today()
    await safe_edit(callback, "📅 <b>Выберите дату</b>", month_calendar_kb(d.year, d.month))


@router.callback_query(F.data.startswith("cal:"))
async def calendar_nav(callback: CallbackQuery):
    await callback.answer()
    ym = callback.data.split(":", 1)[1]
    year, month = map(int, ym.split("-"))
    await safe_edit(callback, "📅 <b>Выберите дату</b>", month_calendar_kb(year, month))


@router.callback_query(F.data.startswith("date:"))
async def date_selected(callback: CallbackQuery):
    await callback.answer()
    d = date.fromisoformat(callback.data.split(":", 1)[1])
    await show_day(callback, d)


@router.callback_query(F.data.startswith("toggle:"))
async def toggle_norm(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Нет доступа", show_alert=True)
        return

    _, date_str, field = callback.data.split(":", 2)
    if field not in {x[0] for x in NORM_FIELDS}:
        await callback.answer("Неизвестный норматив", show_alert=True)
        return

    d = date.fromisoformat(date_str)
    row = get_or_create_day(user["id"], d)
    row[field] = not bool(row.get(field))
    points = calc_points(row)
    supabase.table("daily_norms").update({field: row[field], "points": points}).eq("id", row["id"]).execute()
    row["points"] = points
    await callback.answer("Сохранено")
    text = (
        f"📅 <b>{d.strftime('%d.%m.%Y')}</b>\n"
        f"Баллы за день: <b>{fmt_points(points)}</b>\n\n"
        "Нажимайте на нормативы, чтобы включать или выключать их. Изменения сохраняются сразу."
    )
    await safe_edit(callback, text, day_keyboard(row, d))


@router.callback_query(F.data == "rating")
async def rating(callback: CallbackQuery):
    await callback.answer()
    current_user = get_user(callback.from_user.id)
    if not current_user:
        await safe_edit(callback, "⛔ У вас нет доступа к боту.")
        return

    users = supabase.table("bot_users").select("id,telegram_id,full_name").eq("is_active", True).execute().data
    totals = supabase.table("daily_norms").select("user_id,points").gte("norm_date", COMPETITION_START.isoformat()).lte("norm_date", today().isoformat()).execute().data

    score_by_user = {u["id"]: 0.0 for u in users}
    for row in totals:
        score_by_user[row["user_id"]] = score_by_user.get(row["user_id"], 0.0) + float(row.get("points") or 0)

    ranked = sorted(users, key=lambda u: (-score_by_user.get(u["id"], 0.0), u["full_name"].lower()))
    lines = ["🏆 <b>Рейтинг на текущий момент</b>", ""]

    my_place = None
    my_score = score_by_user.get(current_user["id"], 0.0)
    for idx, u in enumerate(ranked, start=1):
        if u["id"] == current_user["id"]:
            my_place = idx
        if idx <= 10:
            shown_name = u["full_name"] if u["id"] == current_user["id"] else "Скрыто"
            prize = PRIZES.get(idx, 0)
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            lines.append(f"{medal} {shown_name} — <b>{fmt_points(score_by_user[u['id']])}</b> б. — {prize:,} ₽".replace(",", " "))

    lines.append("")
    lines.append(f"Ваше место: <b>{my_place} из {len(ranked)}</b>")
    lines.append(f"Ваши баллы: <b>{fmt_points(my_score)}</b>")
    if my_place and my_place > 10 and len(ranked) >= 10:
        gap = max(0.0, score_by_user[ranked[9]["id"]] - my_score)
        lines.append(f"До 10-го места: <b>{fmt_points(gap)}</b> б.")
    elif my_place and my_place > 1:
        above_score = score_by_user[ranked[my_place - 2]["id"]]
        gap = max(0.0, above_score - my_score)
        lines.append(f"До {my_place - 1}-го места: <b>{fmt_points(gap)}</b> б.")

    await safe_edit(callback, "\n".join(lines), back_kb())


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()


@router.message()
async def cleanup_user_messages(message: Message):
    # Стараемся не захламлять чат: пользовательские сообщения удаляются.
    try:
        await message.delete()
    except Exception:
        pass


async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(BOT_TOKEN, parse_mode="HTML")
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
