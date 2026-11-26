"""Gráficas de Plotly para la web. Cada función recibe una tabla de estadisticas.py.

Colores: siempre los mismos para lo mismo.
- Kills  = azul, Muertes = naranja (en todas las gráficas).
- Mapa de calor = un solo color, de claro (pocas kills) a oscuro (muchas).
Son colores de una paleta comprobada para daltonismo; no cambiarlos sin volver a comprobarla.
"""

import plotly.graph_objects as go

KILLS = "#2a78d6"
MUERTES = "#eb6834"
# El 0 es casi el color del fondo, para que las horas sin kills no parezcan "con datos".
AZULES = ["#f3f2ef", "#b7d3f6", "#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]

TEXTO = "#0b0b0b"
TEXTO_SUAVE = "#52514e"
REJILLA = "#e8e7e3"
FONDO = "#ffffff"


def _estilo(fig, alto=320, leyenda=True):
    """Aspecto común: fondo blanco, rejilla suave, barras con esquinas redondeadas."""
    fig.update_layout(
        height=alto,
        margin=dict(l=10, r=10, t=36 if leyenda else 12, b=10),
        paper_bgcolor=FONDO,
        plot_bgcolor=FONDO,
        font=dict(color=TEXTO, size=13),
        showlegend=leyenda,
        legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom", title=None,
                    font=dict(color=TEXTO_SUAVE)),
        barcornerradius=4,
        bargap=0.35,
        bargroupgap=0.08,
        hoverlabel=dict(bgcolor=FONDO, font_color=TEXTO, bordercolor=REJILLA),
    )
    # automargin: deja sitio a las etiquetas de los ejes para que no se corten.
    fig.update_xaxes(showgrid=False, linecolor=REJILLA, tickfont=dict(color=TEXTO_SUAVE),
                     automargin=True)
    fig.update_yaxes(gridcolor=REJILLA, zeroline=False, tickfont=dict(color=TEXTO_SUAVE),
                     rangemode="tozero", automargin=True)
    return fig


def _barras_kills_muertes(x, kills, muertes, formato_x="%{x}", horizontal=False):
    """Dos series de barras (kills y muertes) una al lado de la otra."""
    fig = go.Figure()
    for nombre, valores, color in (("Kills", kills, KILLS), ("Muertes", muertes, MUERTES)):
        if horizontal:
            fig.add_bar(y=x, x=valores, name=nombre, marker_color=color, orientation="h",
                        hovertemplate=f"%{{y}}: %{{x}} {nombre.lower()}<extra></extra>")
        else:
            fig.add_bar(x=x, y=valores, name=nombre, marker_color=color,
                        hovertemplate=f"{formato_x}: %{{y}} {nombre.lower()}<extra></extra>")
    fig.update_layout(barmode="group", hovermode="x unified" if not horizontal else "y unified")
    return fig


def por_dia(tabla):
    fig = _barras_kills_muertes(tabla.index, tabla["kills"], tabla["muertes"],
                                formato_x="%{x|%d/%m}")
    fig.update_xaxes(tickformat="%d/%m", dtick=86400000)  # una marca por día
    return _estilo(fig, alto=280)


def armas(tabla, cuantas=8):
    tabla = tabla.head(cuantas)
    fig = _barras_kills_muertes(tabla.index, tabla["kills"], tabla["muertes"], horizontal=True)
    fig.update_yaxes(autorange="reversed", showgrid=False)  # la mejor arma arriba
    fig.update_xaxes(showgrid=True, gridcolor=REJILLA, rangemode="tozero")
    return _estilo(fig, alto=max(240, 44 * len(tabla) + 60))


def por_hora(tabla):
    fig = _barras_kills_muertes([f"{h:02d}h" for h in tabla.index], tabla["kills"],
                                tabla["muertes"])
    return _estilo(fig, alto=280)


def mapa_calor(tabla, que="kills"):
    """Tabla día x hora (de estadisticas.mapa_calor)."""
    fig = go.Figure(go.Heatmap(
        z=tabla.values,
        x=[f"{h:02d}h" for h in tabla.columns],
        y=list(tabla.index),
        colorscale=[[i / (len(AZULES) - 1), c] for i, c in enumerate(AZULES)],
        xgap=2, ygap=2,  # separación entre celdas
        hovertemplate=f"%{{y}} a las %{{x}}: %{{z}} {que}<extra></extra>",
        colorbar=dict(title=dict(text=que, font=dict(color=TEXTO_SUAVE)), thickness=12,
                      tickfont=dict(color=TEXTO_SUAVE)),
    ))
    fig.update_yaxes(autorange="reversed", showgrid=False)  # lunes arriba
    fig = _estilo(fig, alto=300, leyenda=False)
    fig.update_xaxes(showgrid=False, dtick=3, tickangle=0)  # una etiqueta cada 3 horas, en horizontal
    return fig


def una_serie(etiquetas, valores, color, unidad):
    """Barras de una sola serie (no necesita leyenda: el título dice qué es)."""
    fig = go.Figure(go.Bar(x=list(etiquetas), y=list(valores), marker_color=color,
                           hovertemplate=f"%{{x}}: %{{y}} {unidad}<extra></extra>"))
    return _estilo(fig, alto=260, leyenda=False)


def comparar_kills_muertes(tabla):
    fig = _barras_kills_muertes(list(tabla.index), tabla["kills"], tabla["muertes"])
    return _estilo(fig, alto=300)
