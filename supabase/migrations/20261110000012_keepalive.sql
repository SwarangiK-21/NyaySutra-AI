-- NyaySutra AI — keep-alive check for the free Supabase plan.
--
-- Supabase pauses free projects after about 7 days without activity. While the app runs, its sync worker touches the
-- database every minute; when the laptop or server is off for a week, nothing does. The scheduled GitHub Actions
-- workflow .github/workflows/supabase-keepalive.yml calls this function through the REST API every few days with the
-- publishable key, so the project sees a real database query even when the app is down.
--
-- The function reads and returns nothing about the data: no table access, no arguments, the same answer for everyone.
-- Idempotent.

create or replace function public.keepalive() returns boolean
language sql stable security invoker set search_path = '' as $$
    select true
$$;

comment on function public.keepalive() is 'Keep-alive ping for the scheduled GitHub Actions workflow. Touches no data.';

revoke all on function public.keepalive() from public;
grant execute on function public.keepalive() to anon, authenticated;
