-- NyaySutra AI — lock and change log for edits made outside the app.
--
-- RLS does not bind the dashboard: the Table Editor and SQL Editor use the owner role `postgres`, which has BYPASSRLS.
-- * Lock: only sessions logged in as nyaya_app (the app and its scripts) may change public tables. Anything else is
--   refused before it runs. session_user, not current_user: SECURITY DEFINER functions and foreign-key cascades called
--   by the app run as postgres but keep the app's session. The condition sits in WHEN, so the app pays nothing.
-- * Planned maintenance: inside one transaction, `set local nyaya.maintenance = 'on';` lifts the lock for that
--   transaction only. There is no switch that can be left on by mistake.
-- * Change log: private.data_changes records every change that gets through, with who, when and which row and columns,
--   never the values (the same rule as the audit log). A refused edit is undone, log entry included, so it leaves no row.
-- * Schema changes that could weaken the lock (disabling or dropping a trigger) are logged too.
-- * Limit: the owner can remove all of this. It stops accidents and leaves a trail; it does not replace securing the
--   Supabase account. auth.users and Storage are outside it.
-- * A table added later is not covered until its migration runs `select private.guard_all_tables();`.
-- Idempotent.

create table if not exists private.data_changes (
    id bigint generated always as identity primary key,
    at timestamptz not null default now(),
    db_user text not null default session_user::text,
    via text default current_setting('application_name', true),
    client inet default inet_client_addr(),
    action text not null,
    table_name text,
    row_key text,
    columns text[],
    detail text
);
alter table private.data_changes enable row level security;
revoke all on private.data_changes from public, anon, authenticated, service_role, nyaya_app;

create or replace function private.keep_change_log() returns trigger
language plpgsql set search_path = '' as $$
begin
    raise exception 'The change log cannot be edited' using errcode = 'insufficient_privilege';
end
$$;
create or replace trigger keep_change_log before update or delete or truncate on private.data_changes
    for each statement execute function private.keep_change_log();

create or replace function private.refuse_direct_edit() returns trigger
language plpgsql set search_path = '' as $$
begin
    if current_setting('nyaya.maintenance', true) is distinct from 'on' then
        raise exception 'NyaySutra data is locked: % on % is refused. Make this change in the app.', tg_op, tg_table_name
            using errcode = 'insufficient_privilege';
    end if;
    return null;
end
$$;

-- Trigger arguments are the table's primary-key columns.
create or replace function private.log_direct_edit() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
    was jsonb := case when tg_level = 'ROW' and tg_op <> 'INSERT' then to_jsonb(old) end;
    now_is jsonb := case when tg_level = 'ROW' and tg_op <> 'DELETE' then to_jsonb(new) end;
    row_id text;
    changed text[];
begin
    if tg_level = 'ROW' then
        select string_agg(coalesce(now_is, was) ->> k, ' / ') into row_id from unnest(tg_argv) k;
        if tg_op = 'UPDATE' then
            select array_agg(k order by k) into changed from jsonb_object_keys(now_is) k
            where now_is -> k is distinct from was -> k;
        end if;
    end if;
    insert into private.data_changes(action, table_name, row_key, columns) values (tg_op, tg_table_name, row_id, changed);
    return null;
end
$$;

create or replace function private.guard_all_tables() returns integer
language plpgsql set search_path = '' as $$
declare
    t record;
    keys text;
    n integer := 0;
    outside constant text := 'when (session_user <> ''nyaya_app'')';
begin
    for t in select c.oid, c.relname from pg_catalog.pg_class c
             join pg_catalog.pg_namespace s on s.oid = c.relnamespace
             where s.nspname = 'public' and c.relkind = 'r' loop
        select string_agg(quote_literal(a.attname), ', ' order by a.attnum) into keys
        from pg_catalog.pg_index i join pg_catalog.pg_attribute a on a.attrelid = i.indrelid and a.attnum = any(i.indkey)
        where i.indrelid = t.oid and i.indisprimary;
        execute format('create or replace trigger guard_lock before insert or update or delete or truncate on public.%I '
                       'for each statement %s execute function private.refuse_direct_edit()', t.relname, outside);
        execute format('create or replace trigger guard_log after insert or update or delete on public.%I '
                       'for each row %s execute function private.log_direct_edit(%s)', t.relname, outside, keys);
        execute format('create or replace trigger guard_log_truncate after truncate on public.%I '
                       'for each statement %s execute function private.log_direct_edit()', t.relname, outside);
        n := n + 1;
    end loop;
    return n;
end
$$;

create or replace function private.log_schema_change() returns event_trigger
language plpgsql security definer set search_path = '' as $$
declare
    target text;
begin
    select string_agg(object_identity, ', ') into target from pg_catalog.pg_event_trigger_ddl_commands();
    insert into private.data_changes(action, table_name, detail) values (tg_tag, target, left(current_query(), 500));
exception when others then
    null;   -- logging must never get in the way of a schema change
end
$$;
drop event trigger if exists log_schema_change;
create event trigger log_schema_change on ddl_command_end
    when tag in ('ALTER TABLE', 'DROP TABLE', 'DROP TRIGGER', 'DROP FUNCTION')
    execute function private.log_schema_change();

revoke all on function private.keep_change_log(), private.refuse_direct_edit(), private.log_direct_edit(),
    private.guard_all_tables(), private.log_schema_change() from public, anon, authenticated, nyaya_app;

select private.guard_all_tables();
