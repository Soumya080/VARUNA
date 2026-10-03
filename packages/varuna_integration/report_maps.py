"""
VARUNA — incident-report static map rendering (Phase 8).

Matplotlib (Agg backend, no display needed — this runs server-side inside a
FastAPI request handler), plate-carree/flat lon-lat grid. Deliberately NOT a
tile basemap or satellite image: this repo's whole geospatial convention
(`varuna_geospatial.utils`) is honest flat-earth approximation over small
areas, never a fake-realism basemap, and a report claiming navigational
accuracy it doesn't have would be worse than an honestly plain plot.

Plots exactly the coordinate data `build_incident_report()` already renders
as text — the origin point (section 2) and predicted landfalls (section 7).
Nothing here is a new computation; it's the same numbers, drawn instead of
tabulated.
"""
from __future__ import annotations

import io
from typing import Any

from varuna_geospatial.utils import km_to_deg_lat, km_to_deg_lon


def render_case_map(operator_case: Any, *, width_in: float = 6.5, height_in: float = 4.2) -> bytes | None:
    """Returns PNG bytes, or None when there is no plottable geometry at all
    — the caller must then keep printing its existing NOT_AVAILABLE text,
    never a blank/misleading image."""
    origin = None
    sp = getattr(operator_case, "starting_point", None)
    pt = getattr(sp, "point", None) if sp else None
    if pt is not None:
        origin = (float(pt.lon), float(pt.lat))

    landfalls: list[tuple[float, float, str]] = []
    forecast_sec = getattr(operator_case, "forecast", None)
    fc = getattr(forecast_sec, "value", None) if forecast_sec else None
    for lf in (getattr(fc, "landfalls", None) or []):
        pos = getattr(lf, "position", None)
        if pos is not None:
            landfalls.append((float(pos.lon), float(pos.lat), getattr(lf, "location_name", "landfall")))

    if origin is None and not landfalls:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    points = ([origin] if origin else []) + [(lf[0], lf[1]) for lf in landfalls]
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    lon_span = max(lons) - min(lons) or 0.05
    lat_span = max(lats) - min(lats) or 0.05
    pad_lon, pad_lat = lon_span * 0.35 + 0.02, lat_span * 0.35 + 0.02
    min_lon, max_lon = min(lons) - pad_lon, max(lons) + pad_lon
    min_lat, max_lat = min(lats) - pad_lat, max(lats) + pad_lat

    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=150)
    ax.set_xlim(min_lon, max_lon)
    ax.set_ylim(min_lat, max_lat)
    ax.set_aspect(1.0 / max(0.2, abs(km_to_deg_lon(1.0, (min_lat + max_lat) / 2) / km_to_deg_lat(1.0))))
    ax.grid(True, linewidth=0.4, color="#c8ced8", alpha=0.7)
    ax.set_facecolor("#eef4f8")  # plain flat tint, not a fake satellite texture
    for spine in ax.spines.values():
        spine.set_color("#7a8494")

    if origin is not None:
        ax.scatter([origin[0]], [origin[1]], marker="*", s=180, color="#b3261e",
                   zorder=5, label="Spill origin", edgecolors="white", linewidths=0.6)
        ax.annotate("Origin", origin, textcoords="offset points", xytext=(6, 6), fontsize=8, color="#1a2440")

    for i, (lon, lat, name) in enumerate(landfalls):
        ax.scatter([lon], [lat], marker="^", s=90, color="#e8871a", zorder=4,
                   edgecolors="white", linewidths=0.5,
                   label="Predicted landfall" if i == 0 else None)
        ax.annotate(name, (lon, lat), textcoords="offset points", xytext=(6, -10), fontsize=7, color="#5b6472")

    # Scale bar (real distance, not a fabricated basemap scale)
    bar_km = 5.0 if lon_span < 0.5 else (25.0 if lon_span < 2.0 else 100.0)
    bar_deg = km_to_deg_lon(bar_km, (min_lat + max_lat) / 2)
    bar_x0 = min_lon + (max_lon - min_lon) * 0.06
    bar_y0 = min_lat + (max_lat - min_lat) * 0.07
    ax.plot([bar_x0, bar_x0 + bar_deg], [bar_y0, bar_y0], color="#1a2440", linewidth=2, solid_capstyle="butt")
    ax.text(bar_x0, bar_y0 + (max_lat - min_lat) * 0.015, f"{bar_km:g} km", fontsize=7, color="#1a2440")

    # North arrow
    nx = max_lon - (max_lon - min_lon) * 0.08
    ny0 = min_lat + (max_lat - min_lat) * 0.10
    ny1 = ny0 + (max_lat - min_lat) * 0.12
    ax.annotate("", xy=(nx, ny1), xytext=(nx, ny0),
                arrowprops=dict(arrowstyle="-|>", color="#1a2440", linewidth=1.4))
    ax.text(nx, ny1 + (max_lat - min_lat) * 0.02, "N", fontsize=8, color="#1a2440", ha="center")

    ax.set_xlabel("Longitude", fontsize=7, color="#5b6472")
    ax.set_ylabel("Latitude", fontsize=7, color="#5b6472")
    ax.tick_params(labelsize=6, colors="#5b6472")
    if origin is not None or landfalls:
        ax.legend(loc="upper right", fontsize=6, framealpha=0.85)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    return buf.getvalue()
