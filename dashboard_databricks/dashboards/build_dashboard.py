"""Gera o JSON do dashboard Orçamento MXM (Receita x Despesa) para o Databricks AI/BI."""
import json
from pathlib import Path

HERE = Path(__file__).parent
DS = "ds_orcamento"

sql_lines = [line + "\n" for line in (HERE / "ds_orcamento.sql").read_text(encoding="utf-8").strip().splitlines()]

# Paleta corporativa
NAVY = "#1F3A5F"
RECEITA = "#2A9D8F"
DESPESA = "#E76F51"
EXECUTADO = "#3A7CA5"
DISPONIVEL = "#8AB17D"
SLATE = "#8D99AE"

BRL_COMPACT = {"type": "number-currency", "currencyCode": "BRL", "abbreviation": "compact",
               "decimalPlaces": {"type": "max", "places": 1}}
BRL_FULL = {"type": "number-currency", "currencyCode": "BRL", "decimalPlaces": {"type": "exact", "places": 2}}
PCT = {"type": "number-percent", "decimalPlaces": {"type": "exact", "places": 1}}

VL_BASE = {
    "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
    "data": {"name": "databricks_query"},
    "width": "container",
    "height": "container",
    "config": {"autosize": {"type": "fit", "contains": "padding"}, "view": {"stroke": None}},
}

# Expressão Vega para formatar moeda em pt-BR compacto: R$ 214,8 mi / R$ 1,25 bi
def brl_expr(field):
    v = f"datum.{field}"
    return (f"'R$ ' + replace(abs({v}) >= 1e9 ? format({v}/1e9, '.2f') + ' bi' : "
            f"abs({v}) >= 1e6 ? format({v}/1e6, '.1f') + ' mi' : format({v}/1e3, '.1f') + ' mil', '.', ',')")


def pct_expr(num, den):
    return (f"datum.{den} == 0 ? '—' : replace(format(datum.{num} / datum.{den} * 100, '.1f'), '.', ',') "
            f"+ '% do orçado'")


def text(name, lines, x, y, w, h):
    return {"widget": {"name": name, "multilineTextboxSpec": {"lines": lines}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def kpi_panel(name, title, prefix, accent, x, y):
    """Painel com 3 cards (Orçado / Executado / Disponível) em fonte de tamanho fixo."""
    fields = {"orc": f"{prefix}_orcado", "exe": f"{prefix}_executado", "disp": f"{prefix}_disponivel"}
    vl = dict(VL_BASE)
    vl["transform"] = [
        {"fold": ["orc", "exe", "disp"], "as": ["k", "v"]},
        {"calculate": "datum.k == 'orc' ? 0 : datum.k == 'exe' ? 1 : 2", "as": "ordem"},
        {"calculate": "datum.k == 'orc' ? 'ORÇADO' : datum.k == 'exe' ? 'EXECUTADO' : 'DISPONÍVEL'", "as": "rotulo"},
        {"calculate": brl_expr("v"), "as": "valor_fmt"},
        {"calculate": "datum.k == 'orc' ? 'Orçamento do período' : datum.k == 'exe' ? "
                      f"({pct_expr('exe', 'orc')}) : ({pct_expr('disp', 'orc')})", "as": "sub"},
        {"calculate": f"datum.k == 'orc' ? '{NAVY}' : datum.k == 'exe' ? '{accent}' : '{DISPONIVEL}'", "as": "cor"},
    ]
    x_enc = {"field": "ordem", "type": "ordinal", "axis": None, "scale": {"paddingInner": 0.06, "paddingOuter": 0}}
    y_dom = {"domain": [0, 1]}

    def yd(d):
        return {"datum": d, "type": "quantitative", "scale": y_dom, "axis": None}

    vl["layer"] = [
        {"mark": {"type": "rect", "cornerRadius": 6, "color": "#8D99AE", "opacity": 0.08},
         "encoding": {"x": x_enc, "y": yd(0.0), "y2": {"datum": 1.0}}},
        {"mark": {"type": "rect", "cornerRadius": 2},
         "encoding": {"x": x_enc, "y": yd(0.0), "y2": {"datum": 0.04},
                      "color": {"field": "cor", "type": "nominal", "scale": None, "legend": None}}},
        {"mark": {"type": "text", "fontSize": 11, "fontWeight": 600, "letterSpacing": 0.6, "opacity": 0.6,
                  "color": {"expr": "colors.textPrimary.default"}},
         "encoding": {"x": x_enc, "y": yd(0.80), "text": {"field": "rotulo"}}},
        {"mark": {"type": "text", "fontSize": 22, "fontWeight": 700,
                  "color": {"expr": "colors.textPrimary.default"}},
         "encoding": {"x": x_enc, "y": yd(0.50), "text": {"field": "valor_fmt"},
                      "tooltip": [{"field": "rotulo", "title": "Indicador"},
                                  {"field": "v", "type": "quantitative", "title": "Valor (R$)", "format": ",.2f"}]}},
        {"mark": {"type": "text", "fontSize": 11, "fontWeight": 500},
         "encoding": {"x": x_enc, "y": yd(0.22), "text": {"field": "sub"},
                      "color": {"field": "cor", "type": "nominal", "scale": None, "legend": None}}},
    ]
    return {
        "widget": {
            "name": name,
            "queries": [{"name": "main_query", "query": {
                "datasetName": DS,
                "fields": [{"name": k, "expression": f"SUM(`{c}`)"} for k, c in fields.items()],
                "disaggregated": False}}],
            "spec": {
                "version": 1,
                "widgetType": "custom-vega-viz",
                "data": {"queryName": "main_query"},
                "encodings": {"fields": [{"fieldName": k} for k in fields]},
                "jsonSpec": {"type": "vega-lite", "spec": json.dumps(vl, ensure_ascii=False)},
                "frame": {"showTitle": True, "title": title},
            },
        },
        "position": {"x": x, "y": y, "width": 6, "height": 3},
    }


def bullet_execucao(x, y, w, h):
    vl = dict(VL_BASE)
    vl["transform"] = [
        {"calculate": "datum.orc == 0 ? 0 : datum.exe / datum.orc", "as": "pct"},
        {"calculate": "replace(format(datum.pct * 100, '.1f'), '.', ',') + '%'", "as": "pct_fmt"},
    ]
    vl["encoding"] = {
        "y": {"field": "tipo", "type": "nominal", "title": None, "sort": ["Receita", "Despesa"],
              "axis": {"labelFontSize": 12, "labelFontWeight": 600, "ticks": False, "domain": False}},
        "x": {"type": "quantitative", "title": None, "scale": {"zero": True},
              "axis": {"labelExpr": "replace(format(datum.value / 1e6, ',.0f'), ',', '.') + ' mi'",
                       "tickCount": 5, "grid": True, "domain": False}},
        "tooltip": [
            {"field": "tipo", "title": "Tipo"},
            {"field": "orc", "type": "quantitative", "title": "Orçado (R$)", "format": ",.2f"},
            {"field": "exe", "type": "quantitative", "title": "Executado (R$)", "format": ",.2f"},
            {"field": "pct_fmt", "title": "% Executado"},
        ],
    }
    vl["layer"] = [
        {"mark": {"type": "bar", "size": 34, "color": SLATE, "opacity": 0.25, "cornerRadiusEnd": 3},
         "encoding": {"x": {"field": "orc"}}},
        {"mark": {"type": "bar", "size": 14, "cornerRadiusEnd": 3},
         "encoding": {"x": {"field": "exe"},
                      "color": {"field": "tipo", "type": "nominal", "legend": None,
                                "scale": {"domain": ["Receita", "Despesa"], "range": [RECEITA, DESPESA]}}}},
        {"mark": {"type": "tick", "thickness": 2, "size": 40, "color": {"expr": "colors.textPrimary.default"}},
         "encoding": {"x": {"field": "orc"}}},
        {"mark": {"type": "text", "align": "left", "dx": 6, "fontSize": 12, "fontWeight": 700,
                  "color": {"expr": "colors.textPrimary.default"}},
         "encoding": {"x": {"field": "exe"}, "text": {"field": "pct_fmt"}}},
    ]
    return {
        "widget": {
            "name": "execucao-orcamentaria",
            "queries": [{"name": "main_query", "query": {
                "datasetName": DS,
                "fields": [
                    {"name": "tipo", "expression": "`tipo`"},
                    {"name": "orc", "expression": "SUM(`vl_orcado`)"},
                    {"name": "exe", "expression": "SUM(`vl_executado`)"},
                ],
                "disaggregated": False}}],
            "spec": {
                "version": 1,
                "widgetType": "custom-vega-viz",
                "data": {"queryName": "main_query"},
                "encodings": {"fields": [{"fieldName": "tipo"}, {"fieldName": "orc"}, {"fieldName": "exe"}]},
                "jsonSpec": {"type": "vega-lite", "spec": json.dumps(vl, ensure_ascii=False)},
                "frame": {"showTitle": True, "title": "Execução orçamentária",
                          "showDescription": True,
                          "description": "Barra colorida = executado · faixa cinza e traço = orçado"},
            },
        },
        "position": {"x": x, "y": y, "width": w, "height": h},
    }


def filter_widget(name, wtype, field, title, x, y, w, selection=None):
    spec = {
        "version": 2,
        "widgetType": wtype,
        "encodings": {"fields": [{"fieldName": field, "displayName": title, "queryName": f"q_{name}"}]},
        "frame": {"showTitle": True, "title": title},
    }
    if selection:
        spec["selection"] = selection
    return {
        "widget": {
            "name": name,
            "queries": [{"name": f"q_{name}", "query": {
                "datasetName": DS, "fields": [{"name": field, "expression": f"`{field}`"}],
                "disaggregated": False}}],
            "spec": spec,
        },
        "position": {"x": x, "y": y, "width": w, "height": 2},
    }


executado_mensal = {
    "widget": {
        "name": "executado-mensal",
        "queries": [{"name": "main_query", "query": {
            "datasetName": DS,
            "fields": [
                {"name": "monthly(data)", "expression": "DATE_TRUNC(\"MONTH\", `data`)"},
                {"name": "sum(receita_executado)", "expression": "SUM(`receita_executado`)"},
                {"name": "sum(despesa_executado)", "expression": "SUM(`despesa_executado`)"},
            ],
            "disaggregated": False}}],
        "spec": {
            "version": 3,
            "widgetType": "bar",
            "encodings": {
                "x": {"fieldName": "monthly(data)", "scale": {"type": "temporal"}, "displayName": "Mês"},
                "y": {"scale": {"type": "quantitative"}, "format": BRL_COMPACT, "displayName": "Executado", "fields": [
                    {"fieldName": "sum(receita_executado)", "displayName": "Receita"},
                    {"fieldName": "sum(despesa_executado)", "displayName": "Despesa"},
                ]},
                "color": {"scale": {"type": "categorical", "mappings": [
                    {"value": "Receita", "color": RECEITA},
                    {"value": "Despesa", "color": DESPESA},
                ]}},
            },
            "mark": {"layout": "group"},
            "frame": {"showTitle": True, "title": "Executado mensal — Receita x Despesa"},
        },
    },
    "position": {"x": 5, "y": 6, "width": 7, "height": 6},
}

money_cols = [
    ("receita_orcado", "Receita · Orçado"), ("receita_executado", "Receita · Executado"),
    ("receita_disponivel", "Receita · Disponível"),
    ("despesa_orcado", "Despesa · Orçado"), ("despesa_executado", "Despesa · Executado"),
    ("despesa_disponivel", "Despesa · Disponível"),
]


def table_field(col):
    if col.startswith("%"):
        return {"name": f"measure({col})", "expression": f"MEASURE(`{col}`)"}
    return {"name": f"sum({col})", "expression": f"SUM(`{col}`)"}


def table_column(col, label):
    if col.startswith("%"):
        return {"fieldName": f"measure({col})", "displayName": label, "format": PCT}
    col_spec = {"fieldName": f"sum({col})", "displayName": label, "format": BRL_FULL}
    if col.endswith("disponivel"):
        col_spec["style"] = {"type": "basic", "rules": [{
            "condition": {"operand": {"type": "data-value", "value": "0"}, "operator": "<"},
            "backgroundColor": {"hex": "#FBE3DC"}}]}
    return col_spec


detalhe = {
    "widget": {
        "name": "detalhe-mensal",
        "queries": [{"name": "main_query", "query": {
            "datasetName": DS,
            "fields": [
                {"name": "ano_mes_texto", "expression": "`ano_mes_texto`"},
                {"name": "ano_mes", "expression": "`ano_mes`"},
                *[table_field(c) for c, _ in money_cols],
            ],
            "orders": [{"direction": "ASC", "expression": "`ano_mes`"}],
            "disaggregated": False}}],
        "spec": {
            "version": 2,
            "widgetType": "table",
            "encodings": {"columns": [
                {"fieldName": "ano_mes_texto", "displayName": "Mês/Ano"},
                *[table_column(c, label) for c, label in money_cols],
            ]},
            "frame": {"showTitle": True, "title": "Detalhamento mensal"},
        },
    },
    "position": {"x": 0, "y": 12, "width": 12, "height": 8},
}

layout = [
    text("titulo", [
        "## Execução Orçamentária — MXM\n",
        "\n",
        "Receita e despesa · orçado, executado e disponível",
    ], 0, 0, 6, 2),
    filter_widget("filtro-ano", "filter-multi-select", "ano", "Ano", 6, 0, 2,
                  {"defaultSelection": {"values": {"dataType": "STRING", "values": [{"value": "2026"}]}}}),
    filter_widget("filtro-mes", "filter-multi-select", "mes_nome", "Mês", 8, 0, 2),
    filter_widget("filtro-periodo", "filter-date-range-picker", "data", "Período", 10, 0, 2),
    kpi_panel("kpi-receita", "Receita", "receita", RECEITA, 0, 2),
    kpi_panel("kpi-despesa", "Despesa", "despesa", DESPESA, 6, 2),
    text("nota", [
        "*Orçado anual lançado em janeiro (com reformulação em julho). Ao filtrar meses isolados, "
        "o disponível considera apenas o orçado lançado nesses meses.*"
    ], 0, 5, 12, 1),
    bullet_execucao(0, 6, 5, 6),
    executado_mensal,
    detalhe,
]

dashboard = {
    "datasets": [{
        "name": DS,
        "displayName": "Orçamento MXM (receita + despesa)",
        "queryLines": sql_lines,
        "columns": [
            {"displayName": "% Execução Receita", "description": "Receita executada / receita orçada",
             "expression": "SUM(`receita_executado`) / NULLIF(SUM(`receita_orcado`), 0)"},
            {"displayName": "% Execução Despesa", "description": "Despesa executada / despesa orçada",
             "expression": "SUM(`despesa_executado`) / NULLIF(SUM(`despesa_orcado`), 0)"},
        ],
    }],
    "pages": [
        {"name": "visao-geral", "displayName": "Visão Geral", "pageType": "PAGE_TYPE_CANVAS",
         "layoutVersion": "GRID_V1", "layout": layout},
    ],
    "uiSettings": {"theme": {
        "canvasBackgroundColor": {"light": "#F3F5F8", "dark": "#141A21"},
        "widgetBackgroundColor": {"light": "#FFFFFF", "dark": "#1C242D"},
        "widgetBorderColor": {"light": "#E3E8EE", "dark": "#2A3440"},
        "fontColor": {"light": "#1B2A3A", "dark": "#E6EBF0"},
        "selectionColor": {"light": "#1F6FB2", "dark": "#7FB8F0"},
        "visualizationColors": [RECEITA, DESPESA, EXECUTADO, NAVY, DISPONIVEL, "#E9C46A", SLATE],
        "widgetHeaderAlignment": "LEFT",
        "fontFamily": "Inter",
        "widgetCornerRadius": 8,
    }},
}

out = HERE / "orcamento_mxm.lvdash.json"
out.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")

# Corpo para a API (ASCII-escapado: a CLI no Windows não lê UTF-8 corretamente)
body = {"serialized_dashboard": json.dumps(dashboard, ensure_ascii=True, separators=(",", ":")),
        "display_name": "Orçamento MXM - Receita x Despesa", "warehouse_id": "2725b5ef5aff55e5"}
(HERE / "update_body.json").write_text(json.dumps(body, ensure_ascii=True), encoding="ascii")
print("ok", len(body["serialized_dashboard"]))
