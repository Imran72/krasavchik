-- =========================================================
-- ОДНО АКТУАЛЬНОЕ СООБЩЕНИЕ БОТА НА ПОЛЬЗОВАТЕЛЯ
-- Выполнить один раз в Supabase SQL Editor
-- =========================================================

alter table public.bot_users
add column if not exists last_ui_message_id bigint;

-- Если таблица напоминаний уже есть, ничего больше делать не надо.
-- Если её ещё нет, создаём с UUID user_id, т.к. bot_users.id = uuid.

create table if not exists public.reminder_messages (
    id uuid primary key default gen_random_uuid(),

    user_id uuid not null
        references public.bot_users(id)
        on delete cascade,

    telegram_id bigint not null,
    message_id bigint not null unique,

    sent_at timestamptz not null default now()
);

create index if not exists idx_reminder_messages_sent_at
    on public.reminder_messages (sent_at);

create index if not exists idx_reminder_messages_user_id
    on public.reminder_messages (user_id);

create index if not exists idx_reminder_messages_telegram_id
    on public.reminder_messages (telegram_id);

alter table public.reminder_messages
enable row level security;
