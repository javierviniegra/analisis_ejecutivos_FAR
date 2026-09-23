"""Grafico de barras: desglose de costo por categoria (cuenta 501, Odoo), agosto 2026, Puebla."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

BRAND_GREEN = "#10564E"
BRAND_GREEN_LIGHT = "#5C8A82"

df = pd.read_csv("odoo_cost_aug_only.csv")

# Solo categorias de producto (excluye Variaciones de Inventario y Merma, que van aparte)
product_codes = {
    "501.01.02",
    "501.01.03",
    "501.01.04",
    "501.01.05",
    "501.01.06",
    "501.01.09",
    "501.01.10",
    "501.01.11",
    "501.01.12",
    "501.01.13",
}
prod = df[df["code"].isin(product_codes)].sort_values("balance", ascending=True)

fig, ax = plt.subplots(figsize=(7.2, 3.4), dpi=200)
bars = ax.barh(prod["name"], prod["balance"], color=BRAND_GREEN, height=0.62)

ax.set_xlabel("Costo (MXN)", fontsize=9, color="#333333")
ax.tick_params(axis="y", labelsize=9.5, colors="#222222")
ax.tick_params(axis="x", labelsize=8, colors="#555555")
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x/1000:,.0f}k"))
for spine in ["top", "right"]:
    ax.spines[spine].set_visible(False)
for spine in ["left", "bottom"]:
    ax.spines[spine].set_color("#CCCCCC")

for bar, val in zip(bars, prod["balance"]):
    ax.text(
        bar.get_width() + 8000,
        bar.get_y() + bar.get_height() / 2,
        f"${val:,.0f}",
        va="center",
        ha="left",
        fontsize=8,
        color="#333333",
    )

ax.set_xlim(0, prod["balance"].max() * 1.28)
plt.title(
    "Costo por categoría — Cuenta 501 (Odoo) — Agosto 2026",
    fontsize=10.5,
    color=BRAND_GREEN,
    fontweight="bold",
    loc="left",
    pad=10,
)
plt.tight_layout()
plt.savefig("cost_breakdown_chart.png", dpi=200, transparent=True)
print("saved cost_breakdown_chart.png")
