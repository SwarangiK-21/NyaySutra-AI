-- NyaySutra AI — Trash (recycle bin) for cases, case documents, drafts and calendar events.
--
-- Deleting in the app now moves the item to the Trash: it gets deleted_at / deleted_by and disappears everywhere
-- (lists, search, AI answers), but can be restored for 30 days. After that the daily retention job deletes it for
-- good, files included. An administrator can delete an item permanently at once (e.g. a client's erasure request).
--
-- * Cases: a trashed case is hidden by the access helpers below, so every policy built on them (case notes,
--   provisions, documents, passages, drafts, chats) hides its contents too. Trash, restore and purge run as
--   system work after the app has checked who may do it.
-- * Documents: status 'trashed' (search, the vector index and AI answers only use status 'ready').
-- * Drafts and calendar events: filtered by the app; reminders of a trashed event are withdrawn.
-- Idempotent. Planned maintenance: the direct-edit lock (migration 11) is lifted for this transaction only, for the
-- schema_version row; apply the file as one transaction.

set local nyaya.maintenance = 'on';

alter table public.cases add column if not exists deleted_at text;
alter table public.cases add column if not exists deleted_by text;
alter table public.documents add column if not exists deleted_at text;
alter table public.documents add column if not exists deleted_by text;
alter table public.drafts add column if not exists deleted_at text;
alter table public.drafts add column if not exists deleted_by text;
alter table public.calendar_events add column if not exists deleted_at text;
alter table public.calendar_events add column if not exists deleted_by text;

create index if not exists ix_cases_trash on public.cases(org_id, deleted_at) where deleted_at is not null;
create index if not exists ix_documents_trash on public.documents(deleted_at) where deleted_at is not null;
create index if not exists ix_drafts_trash on public.drafts(deleted_at) where deleted_at is not null;
create index if not exists ix_events_trash on public.calendar_events(owner_id, deleted_at) where deleted_at is not null;

alter table public.documents drop constraint if exists documents_status_check;
alter table public.documents add constraint documents_status_check
    check (status in ('processing', 'ready', 'failed', 'quarantined', 'cancelled', 'superseded', 'trashed'));

-- Same definitions as migration 07, plus: a case in the Trash gives nobody access.
create or replace function private.case_access(p_case text) returns text
language sql stable security definer set search_path = '' as $$
    select case when m.role in ('advocate', 'admin') then cm.access end
    from public.case_members cm
    join public.cases c on c.id = cm.case_id
    join public.memberships m on m.org_id = c.org_id and m.user_id = cm.user_id
    join public.profiles p on p.user_id = cm.user_id
    where cm.case_id = p_case and cm.user_id = auth.uid()::text and p.status = 'active' and c.deleted_at is null
$$;

create or replace function private.accessible_case_ids() returns setof text
language sql stable security definer set search_path = '' as $$
    select cm.case_id
    from public.case_members cm
    join public.cases c on c.id = cm.case_id
    join public.memberships m on m.org_id = c.org_id and m.user_id = cm.user_id
    join public.profiles p on p.user_id = cm.user_id
    where cm.user_id = auth.uid()::text and p.status = 'active' and m.role in ('advocate', 'admin')
      and c.deleted_at is null
$$;
revoke all on function private.case_access(text), private.accessible_case_ids() from public, anon, authenticated;

insert into public.meta(key, value) values ('schema_version', '8')
on conflict (key) do update set value = excluded.value;
