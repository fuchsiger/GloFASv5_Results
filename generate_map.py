"""
generate_map.py
---------------
Generates map.html (Leaflet.js station map) from glofas5_hydrobot.csv.

Usage:
    python generate_map.py --csv glofas5_hydrobot.csv --out map.html

The script reads the CSV (locally or via URL) and regenerates the full
map.html with one circleMarker per station, color-coded by KGEmod.
"""

import argparse
import math
import pandas as pd

# ── KGE colour scheme (matches index.html) ───────────────────────────────────
def kge_colors(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return '#dc2626', '#ef4444'          # bad
    if v >= 0.75: return '#16a34a', '#22c55e'   # excellent
    if v >= 0.50: return '#65a30d', '#84cc16'   # good
    if v >= 0.25: return '#ca8a04', '#eab308'   # fair
    if v >= 0.00: return '#ea580c', '#f97316'   # poor
    return '#dc2626', '#ef4444'                  # bad

def esc(s):
    """Escape single quotes for inline JS strings."""
    return str(s).replace("'", "\\'")

def fmt(v, decimals=4):
    try:
        f = float(v)
        return f'{f:.{decimals}f}' if not math.isnan(f) else '—'
    except (TypeError, ValueError):
        return '—'

def build_popup(row):
    kge = row.get('KGEmod', float('nan'))
    try:
        kge_f = float(kge)
    except (TypeError, ValueError):
        kge_f = float('nan')

    _, fill = kge_colors(kge_f)
    kge_str = f'{kge_f:.3f}' if not math.isnan(kge_f) else '—'

    def tr(label, value):
        return (
            f"<tr>"
            f"<td style='color:#94a3b8;padding:2px 10px 2px 0;font-size:12px'>{label}</td>"
            f"<td style='font-size:12px'>{value}</td>"
            f"</tr>"
        )

    rows_html = ''.join([
        tr('Station',       esc(row.get('name',   '—'))),
        tr('ID',            esc(row.get('ID',     '—'))),
        tr('Basin',         esc(row.get('basin',  '—'))),
        tr('River',         esc(row.get('river',  '—'))),
        tr('Region',        esc(row.get('Region', '—'))),
        tr('Country (ISO)', esc(row.get('iso',    '—'))),
        tr('Status',        esc(row.get('GlofasV5', '—'))),
        tr('KGEmod',        f"<b style='color:{fill}'>{kge_str}</b>"),
        tr('JSD',           fmt(row.get('JSD', '—'), 7)),
        tr('Function',      esc(row.get('Function', '—'))),
        tr('Drainage Area (prov km²)', fmt(row.get('DrainageArea_prov', '—'), 2)),
        tr('Drainage Area (LDD km²)',  fmt(row.get('DrainageArea_LDD',  '—'), 2)),
        tr('Elevation mean (m)',       fmt(row.get('elv_mean', '—'), 1)),
        tr('TP annual (mm/yr)',        fmt(row.get('tp_mean_annual', '—'), 1)),
        tr('ET0 annual (mm/yr)',       fmt(row.get('eT0_mean_annual', '—'), 1)),
        tr('Aridity Index',            fmt(row.get('aridity_index', '—'), 3)),
        tr('Temp mean (°C)',            fmt(row.get('ta_mean', '—'), 2)),
        tr('Forest frac',              fmt(row.get('fracforest_mean', '—'), 3)),
        tr('Glacier frac',             fmt(row.get('glacier_frac', '—'), 4)),
        tr('Obs Start',     esc(row.get('Obs_start', '—'))),
        tr('Obs End',       esc(row.get('Obs_end',   '—'))),
    ])

    station_id = esc(row.get('ID',   '—'))
    name       = esc(row.get('name', '—'))
    table_html = (
        f"<div style='font-family:monospace'>"
        f"<table style='border-collapse:collapse'>"
        f"{rows_html}"
        f"</table></div>"
    )
    popup = f"<b>[{station_id}] {name}</b><br>KGEmod: <b>{kge_str}</b><br>{table_html}"
    return popup.replace("'", "&#39;")


HTML_HEAD = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>GloFASv5 · Station Map</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&display=swap');
    * { margin:0; padding:0; box-sizing:border-box; }
    body { background:#0b0e14; font-family:'IBM Plex Mono',monospace; }
    #map { width:100vw; height:100vh; }

    .map-header {
      position:absolute; top:12px; left:50%; transform:translateX(-50%);
      z-index:1000; background:rgba(11,14,20,0.92);
      border:1px solid #1e2535; border-radius:8px;
      padding:10px 20px; display:flex; align-items:center; gap:20px;
      backdrop-filter:blur(6px);
    }
    .map-title { font-size:15px; font-weight:600; color:#fff; letter-spacing:-0.3px; }
    .map-title span { color:#06b6d4; }
    .map-back { font-size:12px; color:#06b6d4; text-decoration:none; }
    .map-back:hover { color:#38bdf8; }

    .legend {
      position:absolute; bottom:24px; right:12px; z-index:1000;
      background:rgba(11,14,20,0.92); border:1px solid #1e2535;
      border-radius:8px; padding:12px 16px;
      font-size:11px; color:#94a3b8;
      backdrop-filter:blur(6px);
    }
    .legend-title { color:#e2e8f0; font-weight:600; margin-bottom:8px; font-size:12px; }
    .legend-item { display:flex; align-items:center; gap:8px; margin-bottom:5px; }
    .legend-dot { width:11px; height:11px; border-radius:50%; flex-shrink:0; }

    .stat-bar {
      position:absolute; bottom:24px; left:12px; z-index:1000;
      background:rgba(11,14,20,0.92); border:1px solid #1e2535;
      border-radius:8px; padding:12px 16px;
      font-size:11px; color:#94a3b8;
      backdrop-filter:blur(6px);
    }
    .stat-bar-title { color:#e2e8f0; font-weight:600; margin-bottom:8px; font-size:12px; }
    .stat-row { display:flex; gap:20px; }
    .stat-item { text-align:center; }
    .stat-val { font-size:18px; font-weight:600; color:#fff; }
    .stat-lbl { font-size:10px; text-transform:uppercase; letter-spacing:0.5px; margin-top:2px; }

    .leaflet-popup-content-wrapper {
      background:#131720 !important; border:1px solid #1e2535 !important;
      color:#e2e8f0 !important; border-radius:8px !important;
      box-shadow:0 4px 24px rgba(0,0,0,0.5) !important;
    }
    .leaflet-popup-tip { background:#131720 !important; }
    .leaflet-popup-content { margin:12px 16px !important; }
  </style>
</head>
<body>
<div id="map"></div>

<div class="map-header">
  <div class="map-title">GloFAS<span>v5</span> · Station Map</div>
  <a class="map-back" href="index.html">← Table View</a>
</div>

<div class="legend">
  <div class="legend-title">KGEmod</div>
  <div class="legend-item"><div class="legend-dot" style="background:#22c55e"></div>Excellent ≥ 0.75</div>
  <div class="legend-item"><div class="legend-dot" style="background:#84cc16"></div>Good 0.5 – 0.75</div>
  <div class="legend-item"><div class="legend-dot" style="background:#eab308"></div>Fair 0.25 – 0.5</div>
  <div class="legend-item"><div class="legend-dot" style="background:#f97316"></div>Poor 0 – 0.25</div>
  <div class="legend-item"><div class="legend-dot" style="background:#ef4444"></div>Bad &lt; 0</div>
</div>

<div class="stat-bar" id="statBar">
  <div class="stat-bar-title">Overview</div>
  <div class="stat-row" id="statRow"></div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  const map = L.map('map', {
    center: [20, 10], zoom: 3,
    preferCanvas: true
  });

  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '© OpenStreetMap © CARTO',
    subdomains: 'abcd', maxZoom: 19
  }).addTo(map);
"""

HTML_STATS_JS = """\

  // Stats bar
  const _stats = {total:__TOTAL__, excellent:__EXCELLENT__, good:__GOOD__, fair:__FAIR__, poor:__POOR__, bad:__BAD__};
  const statRow = document.getElementById('statRow');
  [
    {val: _stats.total,     lbl: 'Total',           color: '#e2e8f0'},
    {val: _stats.excellent, lbl: 'Excellent ≥0.75', color: '#22c55e'},
    {val: _stats.good,      lbl: 'Good 0.5–0.75',   color: '#84cc16'},
    {val: _stats.fair,      lbl: 'Fair 0.25–0.5',   color: '#eab308'},
    {val: _stats.poor,      lbl: 'Poor 0–0.25',     color: '#f97316'},
    {val: _stats.bad,       lbl: 'Bad <0',           color: '#ef4444'},
  ].forEach(s => {
    statRow.innerHTML += `<div class="stat-item"><div class="stat-val" style="color:${s.color}">${s.val.toLocaleString()}</div><div class="stat-lbl">${s.lbl}</div></div>`;
  });
"""

HTML_TAIL = """\
</script>
</body>
</html>"""


def generate_map(csv_path, out_path):
    print(f"📥 Reading {csv_path}...")
    df = pd.read_csv(csv_path)
    print(f"   {len(df)} stations loaded")

    # Stats
    def kge_class(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return 'bad'
        if math.isnan(v): return 'bad'
        if v >= 0.75: return 'excellent'
        if v >= 0.50: return 'good'
        if v >= 0.25: return 'fair'
        if v >= 0.00: return 'poor'
        return 'bad'

    counts = {'excellent': 0, 'good': 0, 'fair': 0, 'poor': 0, 'bad': 0}
    for v in df['KGEmod']:
        counts[kge_class(v)] += 1

    print("📊 Stats:", counts)

    # Build markers
    marker_lines = []
    skipped = 0
    for _, row in df.iterrows():
        try:
            lat = float(row['lat'])
            lon = float(row['lon'])
        except (TypeError, ValueError):
            skipped += 1
            continue
        if math.isnan(lat) or math.isnan(lon):
            skipped += 1
            continue

        try:
            kge = float(row['KGEmod'])
        except (TypeError, ValueError):
            kge = float('nan')

        border, fill = kge_colors(kge)
        kge_str = f'{kge:.3f}' if not math.isnan(kge) else '—'
        popup = build_popup(row)
        station_id = esc(row.get('ID',   '—'))
        name       = esc(row.get('name', '—'))

        line = (
            f"    L.circleMarker([{lat},{lon}],"
            f"{{radius:6,color:'{border}',fillColor:'{fill}',fillOpacity:0.85,weight:1.5}})"
            f".bindPopup('{popup}',"
            f"{{maxWidth:420,maxHeight:400}})"
            f".addTo(map);"
        )
        marker_lines.append(line)

    if skipped:
        print(f"⚠️  Skipped {skipped} rows with invalid lat/lon")

    stats_js = HTML_STATS_JS \
        .replace('__TOTAL__',     str(len(df) - skipped)) \
        .replace('__EXCELLENT__', str(counts['excellent'])) \
        .replace('__GOOD__',      str(counts['good'])) \
        .replace('__FAIR__',      str(counts['fair'])) \
        .replace('__POOR__',      str(counts['poor'])) \
        .replace('__BAD__',       str(counts['bad']))

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(HTML_HEAD)
        f.write('\n')
        f.write('\n'.join(marker_lines))
        f.write(stats_js)
        f.write(HTML_TAIL)

    size_mb = len(open(out_path, 'rb').read()) / 1024 / 1024
    print(f"✅ Written → {out_path}  ({size_mb:.1f} MB, {len(marker_lines)} markers)")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', default='glofas5_hydrobot.csv')
    parser.add_argument('--out', default='map.html')
    args = parser.parse_args()
    generate_map(args.csv, args.out)
