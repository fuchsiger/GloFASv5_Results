"""
generate_map_glofas.py
----------------------
Reads GloFASv5_stations_metadata_calfunction_KGE_JSD_20March2026_final.csv
and generates a map.html with an interactive Leaflet map.

Run from the repo root or same folder as the CSV:
    python generate_map_glofas.py

Commit map.html to GitHub — it will be served by GitHub Pages alongside index.html.
"""

import pandas as pd
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
CSV_PATH    = Path("GloFASv5_stations_metadata_calfunction_KGE_JSD_20March2026_final.csv")
OUTPUT_PATH = Path("map.html")

LAT_COL  = "lat"
LON_COL  = "long"
KGE_COL  = "KGEmod"

# Fields shown in popup (label → column name)
POPUP_FIELDS = {
    "Station":        "name",
    "ID":             "ID",
    "Basin":          "basin",
    "River":          "river",
    "Region":         "Region",
    "Country (ISO)":  "iso",
    "Status":         "GlofasV5",
    "KGEmod":         "KGEmod",
    "JSD":            "JSD",
    "Function":       "Function",
    "Drainage Area":  "DrainageArea_LDD",
    "Obs Start":      "Obs_start",
    "Obs End":        "Obs_end",
}
# ──────────────────────────────────────────────────────────────────────────────


def kge_color(val):
    if pd.isna(val):
        return "#64748b", "#94a3b8"   # grey
    if val >= 0.75:
        return "#16a34a", "#22c55e"   # green
    if val >= 0.50:
        return "#65a30d", "#84cc16"   # lime
    if val >= 0.25:
        return "#ca8a04", "#eab308"   # yellow
    if val >= 0.00:
        return "#ea580c", "#f97316"   # orange
    return "#dc2626", "#ef4444"       # red


def build_popup(row):
    lines = []
    for label, col in POPUP_FIELDS.items():
        val = row.get(col, "")
        if pd.notna(val) and str(val).strip() not in ("", "nan"):
            # highlight KGE value
            if col == KGE_COL:
                try:
                    v = float(val)
                    _, fc = kge_color(v)
                    val_str = f"<b style='color:{fc}'>{v:.3f}</b>"
                except ValueError:
                    val_str = str(val)
            else:
                val_str = str(val).replace("'", "\\'")
            lines.append(f"<tr><td style='color:#94a3b8;padding:2px 10px 2px 0;font-size:12px'>{label}</td>"
                         f"<td style='font-size:12px'>{val_str}</td></tr>")
    table = ("<div style='font-family:monospace'>"
             "<table style='border-collapse:collapse'>"
             + "".join(lines) +
             "</table></div>")
    return table.replace("'", "&#39;").replace("\n", "")


def build_markers(df):
    markers = []
    skipped = 0
    for _, row in df.iterrows():
        try:
            lat = float(row[LAT_COL])
            lon = float(row[LON_COL])
        except (ValueError, KeyError):
            skipped += 1
            continue

        kge_val = row.get(KGE_COL, float("nan"))
        try:
            kge_val = float(kge_val)
        except (ValueError, TypeError):
            kge_val = float("nan")

        stroke, fill = kge_color(kge_val)
        popup_html   = build_popup(row)
        station      = str(row.get("name", "")).replace("'", " ")
        sid          = str(row.get("ID", ""))
        kge_str      = f"{kge_val:.3f}" if not pd.isna(kge_val) else "—"

        markers.append(
            f"L.circleMarker([{lat},{lon}],{{"
            f"radius:6,color:'{stroke}',fillColor:'{fill}',"
            f"fillOpacity:0.85,weight:1.5"
            f"}}).bindPopup("
            f"'<b>[{sid}] {station}</b><br>KGEmod: <b>{kge_str}</b><br>{popup_html}',"
            f"{{maxWidth:380,maxHeight:340}})"
            f".addTo(map);"
        )

    if skipped:
        print(f"  Skipped {skipped} rows with invalid coordinates.")
    return "\n    ".join(markers)


def build_legend():
    items = [
        ("#22c55e", "Excellent  ≥ 0.75"),
        ("#84cc16", "Good       0.50 – 0.75"),
        ("#eab308", "Fair       0.25 – 0.50"),
        ("#f97316", "Poor       0.00 – 0.25"),
        ("#ef4444", "Bad        < 0"),
        ("#94a3b8", "No data"),
    ]
    rows = "".join(
        f"<div style='display:flex;align-items:center;gap:7px;margin:3px 0'>"
        f"<div style='width:12px;height:12px;border-radius:50%;background:{c};flex-shrink:0'></div>"
        f"<span style='font-size:11px;color:#94a3b8;font-family:monospace'>{l}</span></div>"
        for c, l in items
    )
    return rows


def generate_html(markers_js, n_total, n_calib, legend_html):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>GloFASv5 · Station Map</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&display=swap');
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ background:#0b0e14; }}
    #map {{ height:100vh; width:100%; }}
    #panel {{
      position:absolute; top:12px; left:52px; z-index:1000;
      background:rgba(13,17,26,0.93); padding:12px 16px;
      border-radius:8px; box-shadow:0 2px 12px rgba(0,0,0,0.5);
      border:1px solid #1e2535; min-width:200px;
    }}
    #panel h2 {{
      font-family:'IBM Plex Mono',monospace; font-size:14px;
      font-weight:600; color:#fff; letter-spacing:-0.3px; margin-bottom:4px;
    }}
    #panel h2 span {{ color:#06b6d4; }}
    #panel .sub {{
      font-family:'IBM Plex Mono',monospace; font-size:10px;
      color:#64748b; margin-bottom:10px;
    }}
    #panel .stats {{
      display:flex; gap:16px; margin-bottom:10px;
      padding-bottom:10px; border-bottom:1px solid #1e2535;
    }}
    #panel .stat {{ text-align:center; }}
    #panel .stat-val {{ font-family:'IBM Plex Mono',monospace; font-size:16px; font-weight:600; color:#fff; }}
    #panel .stat-lbl {{ font-size:10px; color:#64748b; }}
    #back {{
      display:inline-block; margin-top:10px; padding-top:10px;
      border-top:1px solid #1e2535;
      font-family:'IBM Plex Mono',monospace; font-size:11px;
      color:#3b82f6; text-decoration:none;
    }}
    #back:hover {{ color:#60a5fa; }}
    .leaflet-popup-content-wrapper {{
      background:#131720; color:#e2e8f0;
      border:1px solid #1e2535; border-radius:6px;
    }}
    .leaflet-popup-tip {{ background:#131720; }}
    .leaflet-popup-content {{ margin:10px 14px; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <div id="panel">
    <h2>GloFAS<span>v5</span> · Stations</h2>
    <div class="sub">KGEmod (JSD-KGE) · click marker for details</div>
    <div class="stats">
      <div class="stat"><div class="stat-val">{n_total}</div><div class="stat-lbl">Total</div></div>
      <div class="stat"><div class="stat-val">{n_calib}</div><div class="stat-lbl">Calibrated</div></div>
    </div>
    {legend_html}
    <a href="index.html" id="back">← Back to Table</a>
  </div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    var map = L.map('map', {{zoomControl:true}}).setView([20, 10], 3);
    L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
      attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
      maxZoom: 19
    }}).addTo(map);
    {markers_js}
  </script>
</body>
</html>"""


def main():
    print(f"Reading {CSV_PATH} ...")
    df = pd.read_csv(CSV_PATH)
    print(f"  {len(df)} stations loaded.")

    n_calib = (df["GlofasV5"].str.lower() == "calibrated").sum() if "GlofasV5" in df.columns else "?"

    print("Building markers ...")
    markers_js  = build_markers(df)
    legend_html = build_legend()
    html        = generate_html(markers_js, n_total=len(df), n_calib=n_calib, legend_html=legend_html)

    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Saved → {OUTPUT_PATH}")
    print(f"Commit map.html to GitHub and it will be live at:")
    print(f"  https://<user>.github.io/<repo>/map.html")


if __name__ == "__main__":
    main()
