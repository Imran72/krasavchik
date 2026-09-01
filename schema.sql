create extension if not exists pgcrypto;

create table if not exists public.bot_users (
  id uuid primary key default gen_random_uuid(),
  telegram_id bigint unique not null,
  telegram_username text,
  full_name text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.daily_norms (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.bot_users(id) on delete cascade,
  norm_date date not null,
  morning_sport boolean not null default false,
  night_sport boolean not null default false,
  breakfast boolean not null default false,
  dinner boolean not null default false,
  cooked_breakfast boolean not null default false,
  cooked_dinner boolean not null default false,
  story_speaker boolean not null default false,
  story_listener boolean not null default false,
  academic_hour boolean not null default false,
  points numeric(5,1) not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, norm_date)
);

create index if not exists idx_daily_norms_date on public.daily_norms(norm_date);
create index if not exists idx_daily_norms_user on public.daily_norms(user_id);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_bot_users_updated_at on public.bot_users;
create trigger trg_bot_users_updated_at
before update on public.bot_users
for each row execute function public.set_updated_at();

drop trigger if exists trg_daily_norms_updated_at on public.daily_norms;
create trigger trg_daily_norms_updated_at
before update on public.daily_norms
for each row execute function public.set_updated_at();
