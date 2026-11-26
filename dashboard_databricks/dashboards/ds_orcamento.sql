WITH fatos AS (
  SELECT 'Receita' AS tipo, sk_calendario, vl_orcado, vl_executado, vl_disponivel FROM mxm_fato_receita_executada
  UNION ALL
  SELECT 'Despesa' AS tipo, sk_calendario, vl_orcado, vl_executado, vl_disponivel FROM mxm_fato_despesa_executada
)
SELECT
  c.data,
  CAST(c.ano AS STRING) AS ano,
  c.mes,
  CONCAT(LPAD(CAST(c.mes AS STRING), 2, '0'), ' - ', c.mes_nome_completo) AS mes_nome,
  c.ano_mes,
  c.ano_mes_texto,
  f.tipo,
  SUM(f.vl_orcado) AS vl_orcado,
  SUM(f.vl_executado) AS vl_executado,
  SUM(f.vl_disponivel) AS vl_disponivel,
  SUM(CASE WHEN f.tipo = 'Receita' THEN f.vl_orcado ELSE 0 END) AS receita_orcado,
  SUM(CASE WHEN f.tipo = 'Receita' THEN f.vl_executado ELSE 0 END) AS receita_executado,
  SUM(CASE WHEN f.tipo = 'Receita' THEN f.vl_disponivel ELSE 0 END) AS receita_disponivel,
  SUM(CASE WHEN f.tipo = 'Despesa' THEN f.vl_orcado ELSE 0 END) AS despesa_orcado,
  SUM(CASE WHEN f.tipo = 'Despesa' THEN f.vl_executado ELSE 0 END) AS despesa_executado,
  SUM(CASE WHEN f.tipo = 'Despesa' THEN f.vl_disponivel ELSE 0 END) AS despesa_disponivel
FROM fatos f
JOIN temporal.dim_calendario c ON f.sk_calendario = c.sk_calendario
GROUP BY c.data, c.ano, c.mes, c.mes_nome_completo, c.ano_mes, c.ano_mes_texto, f.tipo
ORDER BY c.data
