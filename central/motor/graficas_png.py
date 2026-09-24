"""Draw a `Grafica` as a PNG (matplotlib) for the PDF and Excel outputs.

Grouped columns: the period in Fonda green, the comparison period in a
light green-grey (a large lightness gap, so the pair stays distinct for
colour-blind readers and in greyscale print); a legend always names both.
Recessive hairline grid, y axis in pesos (k / M), no value on every bar.
"""

import io
import textwrap

import matplotlib

matplotlib.use("Agg")  # no display: server-side rendering
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from .graficas import Grafica  # noqa: E402

VERDE_FONDA = "#10564E"
VERDE_CLARO = "#A7C2BC"
TEXTO = "#333333"
TEXTO_SUAVE = "#6B6B6B"
REJILLA = "#E6E6E6"

ANCHO_PULG, ALTO_PULG, DPI = 3.7, 2.1, 200
MAX_ETIQUETAS = 16
CARACTERES_POR_RENGLON = 86  # note text at 5.3 pt across the figure width


def _pesos(v, _pos=None) -> str:
    if abs(v) >= 10_000_000:
        return f"${v / 1_000_000:,.0f}M"
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:,.1f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:,.0f}k"
    return f"${v:,.0f}"


def dibujar(g: Grafica) -> bytes:
    n = len(g.etiquetas)
    fig, ax = plt.subplots(figsize=(ANCHO_PULG, ALTO_PULG), dpi=DPI)
    hay_base = any(v is not None for v in g.base)
    ancho = 0.38 if hay_base else 0.55  # each bar; the rest of the slot is air
    xs = range(n)
    series = [(ancho / 2 if hay_base else 0, g.actual, VERDE_FONDA, g.nombre_actual)]
    if hay_base:  # a comparison with no data is not drawn nor listed in the legend
        series.append((-ancho / 2, g.base, VERDE_CLARO, g.nombre_base))
    for desplaz, valores, color, nombre in series:
        puntos = [(x + desplaz, float(v)) for x, v in zip(xs, valores) if v is not None]
        ax.bar([p[0] for p in puntos], [p[1] for p in puntos], width=ancho * 0.92,
               color=color, label=nombre, zorder=2)

    paso = max(1, -(-n // MAX_ETIQUETAS))  # ceil: at most MAX_ETIQUETAS labels
    ax.set_xticks([x for x in xs if x % paso == 0])
    ax.set_xticklabels([e for i, e in enumerate(g.etiquetas) if i % paso == 0], fontsize=6, color=TEXTO)
    if g.resaltar is not None and g.resaltar % paso == 0:  # the report's own bucket, in bold
        ax.get_xticklabels()[g.resaltar // paso].set_fontweight("bold")
    ax.yaxis.set_major_formatter(FuncFormatter(_pesos))
    ax.tick_params(axis="y", labelsize=6, colors=TEXTO_SUAVE, length=0)
    ax.tick_params(axis="x", length=0)
    ax.grid(axis="y", color=REJILLA, linewidth=0.6, zorder=0)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color("#BBBBBB")
    ax.spines["bottom"].set_linewidth(0.6)
    ax.set_xlim(-0.6, n - 0.4)

    columnas = 2 if not hay_base or len(g.nombre_actual) + len(g.nombre_base) <= 48 else 1
    renglones = len(series) if columnas == 1 else 1  # legend rows sit between the title and the plot
    ax.set_title(g.titulo, fontsize=7.5, color=TEXTO, loc="left", fontweight="bold", pad=4 + 9 * renglones)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=columnas, fontsize=5.8, frameon=False,
              handlelength=1, handleheight=0.8, borderaxespad=0.1, labelcolor=TEXTO)
    renglones_nota = 0
    if g.nota:
        nota = textwrap.fill(g.nota, CARACTERES_POR_RENGLON)
        renglones_nota = nota.count("\n") + 1
        fig.text(0.01, 0.01, nota, fontsize=5.3, color=TEXTO_SUAVE, ha="left", va="bottom", linespacing=1.3)

    fig.tight_layout(rect=(0, 0.045 * renglones_nota, 1, 1))
    salida = io.BytesIO()
    fig.savefig(salida, format="png", facecolor="white")
    plt.close(fig)
    return salida.getvalue()
