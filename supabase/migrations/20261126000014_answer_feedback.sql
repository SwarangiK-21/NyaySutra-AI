-- NyaySutra AI — answer feedback (👍 / 👎 with an optional reason) on research answers.
--
-- One row per (answer, person). Only the person who gave feedback can read or change it; administrators see counts
-- for their organisation through the app (system query restricted to their org). The text of answers is never copied
-- here, and feedback is not used as evaluation data automatically (evaluation sets stay synthetic).
-- Planned maintenance: the direct-edit lock (migration 11) is lifted for this transaction only, for schema_version.
-- Idempotent.

set local nyaya.maintenance = 'on';

create table if not exists public.answer_feedback (
    message_id bigint not null references public.messages(id) on delete cascade,
    user_id    text not null,
    org_id     text,
    rating     smallint not null check (rating in (-1, 1)),
    reason     text not null default '' check (reason in ('', 'wrong_law', 'wrong_citation', 'incomplete',
                                                          'not_relevant', 'language', 'other')),
    comment    text not null default '' check (char_length(comment) <= 500),
    created_at text not null,
    updated_at text not null,
    primary key (message_id, user_id)
);
create index if not exists ix_feedback_org on public.answer_feedback(org_id, created_at);

grant select, insert, update, delete on public.answer_feedback to nyaya_app;
revoke all on public.answer_feedback from anon, authenticated;
alter table public.answer_feedback enable row level security;

drop policy if exists sys_all on public.answer_feedback;
drop policy if exists app_read on public.answer_feedback;
drop policy if exists app_insert on public.answer_feedback;
drop policy if exists app_update on public.answer_feedback;
drop policy if exists app_delete on public.answer_feedback;
create policy sys_all on public.answer_feedback for all to nyaya_app
    using ((select private.is_system())) with check ((select private.is_system()));
create policy app_read on public.answer_feedback for select to nyaya_app using (user_id = (select private.uid()));
-- The answer must be in a chat the caller can read (the messages policy decides that).
create policy app_insert on public.answer_feedback for insert to nyaya_app
    with check (user_id = (select private.uid()) and message_id in (select m.id from public.messages m));
create policy app_update on public.answer_feedback for update to nyaya_app
    using (user_id = (select private.uid())) with check (user_id = (select private.uid()));
create policy app_delete on public.answer_feedback for delete to nyaya_app using (user_id = (select private.uid()));

-- Bring the new table under the direct-edit lock and change log (migration 11).
select private.guard_all_tables();

insert into public.meta(key, value) values ('schema_version', '9')
on conflict (key) do update set value = excluded.value;
