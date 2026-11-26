WITH aberturas AS (
  -- Aberturas do dashboard (publicado ou rascunho): a auditoria registra o usuário real
  SELECT
    a.event_time,
    a.action_name,
    a.user_identity.email AS email,
    a.request_params.dashboard_id AS dashboard_id
  FROM system.access.audit a
  WHERE a.service_name = 'dashboards'
    AND a.action_name IN ('getPublishedDashboard', 'getDashboard')
    AND a.workspace_id = '7405604893278287'
    AND a.event_date >= add_months(current_date(), -6)
    AND a.request_params.dashboard_id IS NOT NULL
    AND a.user_identity.email IS NOT NULL
),
publicacoes AS (
  -- Warehouse da última publicação de cada dashboard (para aberturas sem consulta)
  SELECT request_params.dashboard_id AS dashboard_id, request_params.warehouse_id AS warehouse_id
  FROM system.access.audit
  WHERE service_name = 'dashboards'
    AND action_name = 'publishDashboard'
    AND workspace_id = '7405604893278287'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY request_params.dashboard_id ORDER BY event_time DESC) = 1
),
historico AS (
  -- Consultas disparadas por dashboards. Com credenciais incorporadas o executor
  -- aparece como 'Unknown' (a consulta roda com a identidade de quem publicou).
  SELECT
    h.statement_id,
    h.query_source.dashboard_id AS dashboard_id,
    h.executed_by,
    h.start_time,
    COALESCE(h.end_time, h.start_time) AS end_time,
    h.compute.warehouse_id AS warehouse_id,
    h.from_result_cache,
    COALESCE(h.total_duration_ms, 0) AS duracao_ms,
    COALESCE(h.read_rows, 0) AS linhas_lidas,
    COALESCE(h.read_bytes, 0) AS bytes_lidos
  FROM system.query.history h
  WHERE h.workspace_id = '7405604893278287'
    AND h.start_time >= add_months(current_date(), -6)
    AND h.query_source.dashboard_id IS NOT NULL
    AND h.query_source.dashboard_id <> ''
),
consultas AS (
  -- Atribui consultas sem usuário identificado ao último visualizador que abriu
  -- o dashboard publicado nos 30 minutos anteriores
  SELECT
    COALESCE(
      CASE WHEN h.executed_by LIKE '%@%' THEN h.executed_by END,
      ab.email,
      'nao.identificado@desconhecido'
    ) AS email,
    h.dashboard_id,
    h.start_time AS inicio,
    h.end_time AS fim,
    h.warehouse_id,
    0 AS abertura_publicado,
    0 AS abertura_rascunho,
    1 AS consulta,
    CASE WHEN h.executed_by LIKE '%@%' THEN 0 ELSE 1 END AS atribuida,
    h.duracao_ms,
    h.linhas_lidas,
    h.bytes_lidos
  FROM historico h
  LEFT JOIN aberturas ab
    ON h.executed_by NOT LIKE '%@%'
   AND ab.action_name = 'getPublishedDashboard'
   AND ab.dashboard_id = h.dashboard_id
   AND ab.event_time <= h.start_time + make_interval(0, 0, 0, 0, 0, 0, 5)
   AND ab.event_time >= h.start_time - make_interval(0, 0, 0, 0, 0, 30, 0)
  QUALIFY ROW_NUMBER() OVER (PARTITION BY h.statement_id ORDER BY ab.event_time DESC NULLS LAST) = 1
),
atividades AS (
  SELECT
    ab.email,
    ab.dashboard_id,
    ab.event_time AS inicio,
    ab.event_time AS fim,
    p.warehouse_id,
    CASE WHEN ab.action_name = 'getPublishedDashboard' THEN 1 ELSE 0 END AS abertura_publicado,
    CASE WHEN ab.action_name = 'getDashboard' THEN 1 ELSE 0 END AS abertura_rascunho,
    0 AS consulta,
    0 AS atribuida,
    0 AS duracao_ms,
    0 AS linhas_lidas,
    0 AS bytes_lidos
  FROM aberturas ab
  LEFT JOIN publicacoes p ON ab.dashboard_id = p.dashboard_id
  UNION ALL
  SELECT * FROM consultas
),
marcadas AS (
  SELECT *,
    CASE WHEN LAG(inicio) OVER (PARTITION BY email, dashboard_id ORDER BY inicio) IS NULL
           OR inicio > MAX(fim) OVER (PARTITION BY email, dashboard_id ORDER BY inicio
                                      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) + make_interval(0, 0, 0, 0, 0, 30, 0)
         THEN 1 ELSE 0 END AS nova_sessao
  FROM atividades
),
sessoes AS (
  SELECT *, SUM(nova_sessao) OVER (PARTITION BY email, dashboard_id ORDER BY inicio ROWS UNBOUNDED PRECEDING) AS sessao_n
  FROM marcadas
),
warehouses AS (
  SELECT warehouse_id, warehouse_name
  FROM system.compute.warehouses
  WHERE workspace_id = '7405604893278287'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY warehouse_id ORDER BY change_time DESC) = 1
),
dashboards AS (
  SELECT * FROM VALUES
    __DASHBOARDS__
  AS t(dashboard_id, dashboard_nome)
)
SELECT
  CAST(from_utc_timestamp(MIN(s.inicio), 'America/Sao_Paulo') AS DATE) AS data,
  INITCAP(REPLACE(SPLIT(s.email, '@')[0], '.', ' ')) AS nome,
  s.email,
  COALESCE(d.dashboard_nome, s.dashboard_id) AS dashboard,
  CASE WHEN SUM(s.abertura_publicado) > 0 THEN 'Publicado'
       WHEN SUM(s.abertura_rascunho) > 0 THEN 'Rascunho (edição)'
       ELSE 'Consulta' END AS tipo_acesso,
  COALESCE(MAX(w.warehouse_name), MAX(s.warehouse_id), 'Não identificado') AS warehouse,
  date_format(from_utc_timestamp(MIN(s.inicio), 'America/Sao_Paulo'), 'dd/MM/yyyy HH:mm') AS inicio_sessao,
  date_format(from_utc_timestamp(MAX(s.fim), 'America/Sao_Paulo'), 'dd/MM/yyyy HH:mm') AS fim_sessao,
  (unix_millis(MAX(s.fim)) - unix_millis(MIN(s.inicio))) / 60000.0 AS duracao_sessao_min,
  SUM(s.abertura_publicado + s.abertura_rascunho) AS aberturas,
  SUM(s.consulta) AS consultas,
  CASE WHEN SUM(s.consulta) = 0 THEN 'Sim' ELSE 'Não' END AS servido_do_cache,
  CASE WHEN SUM(s.atribuida) > 0 THEN 'Sim' ELSE 'Não' END AS credencial_incorporada,
  SUM(s.duracao_ms) / 1000.0 AS tempo_processamento_s,
  SUM(s.linhas_lidas) AS linhas_lidas,
  SUM(s.bytes_lidos) AS bytes_lidos
FROM sessoes s
LEFT JOIN warehouses w ON s.warehouse_id = w.warehouse_id
LEFT JOIN dashboards d ON s.dashboard_id = d.dashboard_id
GROUP BY s.email, s.dashboard_id, s.sessao_n, d.dashboard_nome
ORDER BY MIN(s.inicio) DESC
