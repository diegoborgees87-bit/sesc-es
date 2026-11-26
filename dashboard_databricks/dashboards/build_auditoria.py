"""Gera o JSON do dashboard de Auditoria de Acessos (system.access.audit + system.query.history).

Os nomes dos dashboards são lidos via `databricks lakeview list` no momento do build
(rode de novo este script para incluir dashboards criados depois).
"""
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
DS = "ds_auditoria"
PROFILE = "dbck-workspace-bigdata-dev"
WAREHOUSE_ID = "2725b5ef5aff55e5"

NAVY = "#1F3A5F"
TEAL = "#2A9D8F"
BLUE = "#3A7CA5"
CORAL = "#E76F51"
AMBER = "#E9C46A"
GREEN = "#8AB17D"
SLATE = "#8D99AE"


def sql_str(v):
    return "'" + v.replace("'", "''") + "'"


def dashboard_names():
    out = subprocess.run(["databricks", "lakeview", "list", "-p", PROFILE, "-o", "json"],
                         capture_output=True, check=True).stdout.decode("utf-8")
    data = json.loads(out)
    items = data if isinstance(data, list) else data.get("dashboards", [])
    return [(d["dashboard_id"], d["display_name"]) for d in items]


rows = ",\n    ".join(f"({sql_str(i)}, {sql_str(n)})" for i, n in dashboard_names())
sql = (HERE / "ds_auditoria.sql").read_text(encoding="utf-8").replace("__DASHBOARDS__", rows)
sql_lines = [line + "\n" for line in sql.strip().splitlines()]

VL_BASE = {
    "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
    "data": {"name": "databricks_query"},
    "width": "container",
    "height": "container",
    "config": {"autosize": {"type": "fit", "contains": "padding"}, "view": {"stroke": None}},
}


def num_br(v):
    """Expressão Vega: número compacto pt-BR (1,2 mi / 15,3 mil / 842)."""
    return (f"replace(abs({v}) >= 1e9 ? format({v}/1e9, '.1f') + ' bi' : abs({v}) >= 1e6 ? "
            f"format({v}/1e6, '.1f') + ' mi' : abs({v}) >= 1e4 ? format({v}/1e3, '.1f') + ' mil' : "
            f"format({v}, '.0f'), '.', ',')")


def text(name, lines, x, y, w, h):
    return {"widget": {"name": name, "multilineTextboxSpec": {"lines": lines}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def kpi_panel(x, y, w, h):
    cards = [  # (campo, expressão, rótulo, formatação, subtítulo, cor)
        ("usuarios", "COUNT(DISTINCT `email`)", "USUÁRIOS", num_br("datum.v"), "'pessoas distintas'", NAVY),
        ("sessoes", "COUNT(`email`)", "SESSÕES", num_br("datum.v"), "'acessos a dashboards'", TEAL),
        ("consultas", "SUM(`consultas`)", "CONSULTAS", num_br("datum.v"), "'executadas no warehouse'", BLUE),
        ("linhas", "SUM(`linhas_lidas`)", "LINHAS LIDAS", num_br("datum.v"), "'volume processado'", AMBER),
        ("duracao", "AVG(`duracao_sessao_min`)", "DURAÇÃO MÉDIA",
         "replace(format(datum.v, '.1f'), '.', ',') + ' min'", "'por sessão'", CORAL),
    ]
    keys = [c[0] for c in cards]

    def case(idx):
        expr = "''"
        for c in reversed(cards):
            expr = f"datum.k == '{c[0]}' ? {c[idx]} : {expr}"
        return expr

    vl = dict(VL_BASE)
    rotulo = "''"
    cor = "''"
    for c in reversed(cards):
        rotulo = f"datum.k == '{c[0]}' ? '{c[2]}' : {rotulo}"
        cor = f"datum.k == '{c[0]}' ? '{c[5]}' : {cor}"
    vl["transform"] = [
        {"fold": keys, "as": ["k", "v"]},
        {"calculate": "indexof(" + json.dumps(keys) + ", datum.k)", "as": "ordem"},
        {"calculate": rotulo, "as": "rotulo"},
        {"calculate": case(3), "as": "valor_fmt"},
        {"calculate": case(4), "as": "sub"},
        {"calculate": cor, "as": "cor"},
    ]
    x_enc = {"field": "ordem", "type": "ordinal", "axis": None, "scale": {"paddingInner": 0.06, "paddingOuter": 0}}

    def yd(d):
        return {"datum": d, "type": "quantitative", "scale": {"domain": [0, 1]}, "axis": None}

    vl["layer"] = [
        {"mark": {"type": "rect", "cornerRadius": 6, "color": SLATE, "opacity": 0.08},
         "encoding": {"x": x_enc, "y": yd(0.0), "y2": {"datum": 1.0}}},
        {"mark": {"type": "rect", "cornerRadius": 2},
         "encoding": {"x": x_enc, "y": yd(0.0), "y2": {"datum": 0.04},
                      "color": {"field": "cor", "type": "nominal", "scale": None, "legend": None}}},
        {"mark": {"type": "text", "fontSize": 11, "fontWeight": 600, "letterSpacing": 0.6, "opacity": 0.6,
                  "color": {"expr": "colors.textPrimary.default"}},
         "encoding": {"x": x_enc, "y": yd(0.80), "text": {"field": "rotulo"}}},
        {"mark": {"type": "text", "fontSize": 22, "fontWeight": 700, "color": {"expr": "colors.textPrimary.default"}},
         "encoding": {"x": x_enc, "y": yd(0.50), "text": {"field": "valor_fmt"},
                      "tooltip": [{"field": "rotulo", "title": "Indicador"},
                                  {"field": "v", "type": "quantitative", "title": "Valor", "format": ",.2f"}]}},
        {"mark": {"type": "text", "fontSize": 11, "fontWeight": 500, "opacity": 0.7,
                  "color": {"expr": "colors.textPrimary.default"}},
         "encoding": {"x": x_enc, "y": yd(0.22), "text": {"field": "sub"}}},
    ]
    return {
        "widget": {
            "name": "kpis",
            "queries": [{"name": "main_query", "query": {
                "datasetName": DS,
                "fields": [{"name": c[0], "expression": c[1]} for c in cards],
                "disaggregated": False}}],
            "spec": {
                "version": 1,
                "widgetType": "custom-vega-viz",
                "data": {"queryName": "main_query"},
                "encodings": {"fields": [{"fieldName": k} for k in keys]},
                "jsonSpec": {"type": "vega-lite", "spec": json.dumps(vl, ensure_ascii=False)},
                "frame": {"showTitle": False},
            },
        },
        "position": {"x": x, "y": y, "width": w, "height": h},
    }


def filter_widget(name, wtype, field, title, x, y, w):
    return {
        "widget": {
            "name": name,
            "queries": [{"name": f"q_{name}", "query": {
                "datasetName": DS, "fields": [{"name": field, "expression": f"`{field}`"}],
                "disaggregated": False}}],
            "spec": {
                "version": 2,
                "widgetType": wtype,
                "encodings": {"fields": [{"fieldName": field, "displayName": title, "queryName": f"q_{name}"}]},
                "frame": {"showTitle": True, "title": title},
            },
        },
        "position": {"x": x, "y": y, "width": w, "height": 2},
    }


def chart(name, title, wtype, fields, encodings, x, y, w, h, mark=None, description=None):
    spec = {"version": 3, "widgetType": wtype, "encodings": encodings,
            "frame": {"showTitle": True, "title": title}}
    if mark:
        spec["mark"] = mark
    if description:
        spec["frame"].update({"showDescription": True, "description": description})
    return {
        "widget": {
            "name": name,
            "queries": [{"name": "main_query", "query": {"datasetName": DS, "fields": fields, "disaggregated": False}}],
            "spec": spec,
        },
        "position": {"x": x, "y": y, "width": w, "height": h},
    }


COMPACT = {"type": "number", "abbreviation": "compact", "decimalPlaces": {"type": "max", "places": 1}}

sessoes_dia = chart(
    "sessoes-por-dia", "Sessões por dia", "bar",
    [{"name": "daily(data)", "expression": "DATE_TRUNC(\"DAY\", `data`)"},
     {"name": "count(email)", "expression": "COUNT(`email`)"},
     {"name": "dashboard", "expression": "`dashboard`"}],
    {"x": {"fieldName": "daily(data)", "scale": {"type": "temporal"}, "displayName": "Dia"},
     "y": {"fieldName": "count(email)", "scale": {"type": "quantitative"}, "displayName": "Sessões"},
     "color": {"fieldName": "dashboard", "scale": {"type": "categorical"}, "displayName": "Dashboard"}},
    0, 5, 7, 6)

linhas_usuario = chart(
    "linhas-por-usuario", "Linhas lidas por usuário", "bar",
    [{"name": "nome", "expression": "`nome`"},
     {"name": "sum(linhas_lidas)", "expression": "SUM(`linhas_lidas`)"}],
    {"x": {"fieldName": "sum(linhas_lidas)", "scale": {"type": "quantitative"}, "displayName": "Linhas lidas",
           "format": COMPACT},
     "y": {"fieldName": "nome", "scale": {"type": "categorical"}, "displayName": "Usuário"},
     "label": {"show": True}},
    7, 5, 5, 6)

uso_warehouse = chart(
    "uso-por-warehouse", "Consultas por warehouse", "bar",
    [{"name": "warehouse", "expression": "`warehouse`"},
     {"name": "sum(consultas)", "expression": "SUM(`consultas`)"}],
    {"x": {"fieldName": "sum(consultas)", "scale": {"type": "quantitative"}, "displayName": "Consultas"},
     "y": {"fieldName": "warehouse", "scale": {"type": "categorical"}, "displayName": "Warehouse"},
     "label": {"show": True}},
    0, 11, 5, 5)

acessos_dashboard = chart(
    "acessos-por-dashboard", "Acessos por dashboard", "bar",
    [{"name": "dashboard", "expression": "`dashboard`"},
     {"name": "count(email)", "expression": "COUNT(`email`)"},
     {"name": "countdistinct(email)", "expression": "COUNT(DISTINCT `email`)"}],
    {"x": {"scale": {"type": "quantitative"}, "fields": [
        {"fieldName": "count(email)", "displayName": "Sessões"},
        {"fieldName": "countdistinct(email)", "displayName": "Usuários"}]},
     "y": {"fieldName": "dashboard", "scale": {"type": "categorical"}, "displayName": "Dashboard"},
     "color": {"scale": {"type": "categorical", "mappings": [
         {"value": "Sessões", "color": TEAL}, {"value": "Usuários", "color": NAVY}]}},
     "label": {"show": True}},
    5, 11, 7, 5, mark={"layout": "group"})

det_cols = [
    ("nome", "Nome", None), ("email", "E-mail", None), ("dashboard", "Dashboard", None),
    ("tipo_acesso", "Tipo", None), ("warehouse", "Warehouse", None),
    ("inicio_sessao", "Início", None), ("fim_sessao", "Fim", None),
    ("duracao_sessao_min", "Duração (min)", {"type": "number", "decimalPlaces": {"type": "exact", "places": 1}}),
    ("aberturas", "Aberturas", {"type": "number", "decimalPlaces": {"type": "exact", "places": 0}}),
    ("consultas", "Consultas", {"type": "number", "decimalPlaces": {"type": "exact", "places": 0}}),
    ("servido_do_cache", "Só cache", None),
    ("credencial_incorporada", "Cred. incorporada", None),
    ("linhas_lidas", "Linhas lidas", {"type": "number", "decimalPlaces": {"type": "exact", "places": 0}}),
    ("tempo_processamento_s", "Processamento (s)", {"type": "number", "decimalPlaces": {"type": "exact", "places": 1}}),
]


def det_column(f, label, fmt):
    c = {"fieldName": f, "displayName": label}
    if fmt:
        c["format"] = fmt
    return c


detalhe = {
    "widget": {
        "name": "detalhe-sessoes",
        "queries": [{"name": "main_query", "query": {
            "datasetName": DS,
            "fields": [{"name": f, "expression": f"`{f}`"} for f, _, _ in det_cols],
            "disaggregated": True}}],
        "spec": {
            "version": 2,
            "widgetType": "table",
            "encodings": {"columns": [det_column(*c) for c in det_cols]},
            "frame": {"showTitle": True, "title": "Sessões de acesso (detalhe)",
                      "showDescription": True,
                      "description": "Sessão = aberturas e consultas do mesmo usuário no mesmo dashboard com intervalo de até 30 min. \"Só cache\" = resultados entregues pelo cache do dashboard, sem consulta ao warehouse (0 linhas lidas). \"Cred. incorporada\" = consultas executadas com a credencial de quem publicou, atribuídas ao último usuário que abriu o dashboard. Horários de Brasília."},
        },
    },
    "position": {"x": 0, "y": 16, "width": 12, "height": 8},
}

layout = [
    text("titulo", ["## Auditoria de Acessos aos Dashboards\n", "\n",
                    "Quem acessou, por quanto tempo, quanto foi lido e em qual warehouse · últimos 6 meses"], 0, 0, 6, 2),
    filter_widget("filtro-periodo", "filter-date-range-picker", "data", "Período", 6, 0, 2),
    filter_widget("filtro-usuario", "filter-multi-select", "nome", "Usuário", 8, 0, 2),
    filter_widget("filtro-dashboard", "filter-multi-select", "dashboard", "Dashboard", 10, 0, 2),
    kpi_panel(0, 2, 12, 3),
    sessoes_dia,
    linhas_usuario,
    uso_warehouse,
    acessos_dashboard,
    detalhe,
]

dashboard = {
    "datasets": [{"name": DS, "displayName": "Sessões de acesso a dashboards", "queryLines": sql_lines}],
    "pages": [{"name": "auditoria", "displayName": "Auditoria", "pageType": "PAGE_TYPE_CANVAS",
               "layoutVersion": "GRID_V1", "layout": layout}],
    "uiSettings": {"theme": {
        "canvasBackgroundColor": {"light": "#F3F5F8", "dark": "#141A21"},
        "widgetBackgroundColor": {"light": "#FFFFFF", "dark": "#1C242D"},
        "widgetBorderColor": {"light": "#E3E8EE", "dark": "#2A3440"},
        "fontColor": {"light": "#1B2A3A", "dark": "#E6EBF0"},
        "selectionColor": {"light": "#1F6FB2", "dark": "#7FB8F0"},
        "visualizationColors": [TEAL, NAVY, BLUE, AMBER, CORAL, GREEN, SLATE],
        "widgetHeaderAlignment": "LEFT",
        "fontFamily": "Inter",
        "widgetCornerRadius": 8,
    }},
}

(HERE / "auditoria_acessos.lvdash.json").write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")
(HERE / "_auditoria_query.sql").write_text(sql, encoding="utf-8")
body = {"serialized_dashboard": json.dumps(dashboard, ensure_ascii=True, separators=(",", ":")),
        "display_name": "Auditoria de Acessos aos Dashboards", "warehouse_id": WAREHOUSE_ID,
        "parent_path": "/Workspace/Users/diego.costa@es.sesc.com.br/dashboards"}
(HERE / "auditoria_body.json").write_text(json.dumps(body, ensure_ascii=True), encoding="ascii")
print("ok", len(body["serialized_dashboard"]))
