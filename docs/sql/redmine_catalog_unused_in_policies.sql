-- Снимок: строки справочников Redmine, на которые ни одна активная routing_policy не ссылается по осям.
-- Только диагностика; удалять вручную после проверки FK и прод-политики.
-- Postgres.

WITH policy_status AS (
    SELECT DISTINCT rps.status_id AS id FROM routing_policy_statuses rps
    JOIN routing_policies rp ON rp.id = rps.policy_id AND rp.enabled = true
),
policy_version AS (
    SELECT DISTINCT rpv.version_id AS id FROM routing_policy_versions rpv
    JOIN routing_policies rp ON rp.id = rpv.policy_id AND rp.enabled = true
),
policy_priority AS (
    SELECT DISTINCT rpp.priority_id AS id FROM routing_policy_priorities rpp
    JOIN routing_policies rp ON rp.id = rpp.policy_id AND rp.enabled = true
)
SELECT 'redmine_statuses' AS tbl, rs.id AS redmine_id, rs.name
FROM redmine_statuses rs
WHERE rs.id NOT IN (SELECT id FROM policy_status)
ORDER BY rs.id;

-- Версии / приоритеты — по аналогии (раскомментировать при нужде):
-- SELECT 'redmine_versions' ...
-- SELECT 'redmine_priorities' ...
