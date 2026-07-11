#!/usr/bin/env python3
"""
build_recap.py — Génère l'image du récap hebdomadaire Ziéclair (pour Facebook).

Contenu (dans l'ordre) :
  1. Marché : BRVM Composite (niveau + variation semaine) + mini-graphique de tendance
  2. Plus fortes hausses de la semaine
  3. Plus fortes baisses de la semaine
  4. Rubrique tournante (change chaque semaine) : Dividende à venir /
     Meilleur rendement / Valeur la plus échangée

Sortie : recaps/recap_AAAA-MM-JJ.png  +  recaps/latest.png  (1080x1350)
Dépendance : cairosvg (le workflow installe libcairo2 + fonts-liberation).
"""
from __future__ import annotations
import json, os, datetime as dt
import cairosvg

DATA_FILE = "data.json"
OUT_DIR = "recaps"

NAME = {
    'SNTS':'Sonatel SN','ORAC':'Orange CI','ECOC':'Ecobank CI','SIBC':'Sté Ivoirienne de Banque',
    'UNXC':'Uniwax CI','SGBC':'Société Générale CI','BICC':'BICI CI','SCRC':'Sucrivoire',
    'SICC':'Sicor CI','NTLC':'Nestlé CI','SMBC':'SMB CI','CABC':'Sicable CI','TTLS':'TotalEnergies SN',
    'TTLC':'TotalEnergies CI','BOAB':'Bank of Africa BN','BOABF':'Bank of Africa BF','BOAC':'Bank of Africa CI',
    'BOAM':'Bank of Africa ML','BOAN':'Bank of Africa NG','BOAS':'Bank of Africa SN','FTSC':'Filtisac CI',
    'CBIBF':'Coris Bank Intl','ETIT':'Ecobank Transnational','SDSC':'Africa Global Logistics','SPHC':'SAPH CI',
    'PALC':'Palm CI','STBC':'Sitab CI','SLBC':'Solibra CI','BICB':'BIIC BN','UNLC':'Unilever CI',
    'SIVC':'Erium CI','STAC':'Setao CI','ABJC':'Servair Abidjan','BNBC':'Bernabé CI','CFAC':'CFAO Motors CI',
    'NEIC':'NEI-CEDA CI','LNBB':'Loterie Nat. Bénin','PRSC':'Tractafric Motors','SAFC':'Safca CI',
    'SEMC':'Eviosys Packaging','SHEC':'Vivo Energy CI','SOGC':'SOGB CI','ONTBF':'Onatel BF',
    'CIEC':'CIE CI','SDCC':'Sodé CI','ORGT':'Oragroup Togo',
}
UP, DN, OR, TX, MU, CARD, BG = '#25c281', '#f0555c', '#F2811D', '#eef3f8', '#8593a1', '#151c24', '#0b0f14'
MONTHS = {1:'janvier',2:'février',3:'mars',4:'avril',5:'mai',6:'juin',7:'juillet',8:'août',
          9:'septembre',10:'octobre',11:'novembre',12:'décembre'}


def clean(sym, raw):
    if sym in NAME:
        return NAME[sym]
    return raw.title().replace("''", "'").replace(" (V)", "").replace(" (D)", "").strip()


def frdate(d): return f"{d.day} {MONTHS[d.month]}"
def frdate_y(d): return f"{d.day} {MONTHS[d.month]} {d.year}"
def f0(n): return f"{int(round(n)):,}".replace(",", " ")
def pct(w): return ('+' if w >= 0 else '') + f"{w:.2f} %"


def spark(vals, x, y, w, h, col):
    if len(vals) < 2:
        return ''
    mn, mx = min(vals), max(vals)
    rng = (mx - mn) or 1
    pts = [(x + i / (len(vals) - 1) * w, y + h - (v - mn) / rng * h) for i, v in enumerate(vals)]
    line = ' '.join(f'{px:.1f},{py:.1f}' for px, py in pts)
    area = f'{x:.1f},{y+h:.1f} ' + line + f' {x+w:.1f},{y+h:.1f}'
    lx, ly = pts[-1]
    return (f'<polygon points="{area}" fill="{col}22"/>'
            f'<polyline points="{line}" fill="none" stroke="{col}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="5.5" fill="{col}"/>')


def mover_cards(items, y0, col, ql):
    s = ''
    for i, (sym, w) in enumerate(items):
        y = y0 + i * 96
        cl = ql[sym]['close']
        s += f'<rect x="64" y="{y}" width="952" height="84" rx="16" fill="{CARD}"/>'
        s += f'<text x="96" y="{y+40}" font-family="Arial" font-size="29" font-weight="700" fill="{TX}">{sym}</text>'
        s += f'<text x="96" y="{y+70}" font-family="Arial" font-size="22" fill="{MU}">{clean(sym, ql[sym]["name"])}</text>'
        s += f'<text x="984" y="{y+40}" text-anchor="end" font-family="Arial" font-size="29" font-weight="700" fill="{TX}">{f0(cl)} F</text>'
        s += f'<text x="984" y="{y+72}" text-anchor="end" font-family="Arial" font-size="26" font-weight="700" fill="{col}">{pct(w)}</text>'
    return s


def rubric_dividende(ql, window, data, ref):
    best = None
    for s, q in ql.items():
        if not q.get('div_date') or q.get('yield_net_pct') is None:
            continue
        try:
            d = dt.date.fromisoformat(q['div_date'])
        except Exception:
            continue
        while d <= ref:
            try:
                d = d.replace(year=d.year + 1)
            except ValueError:
                d = d.replace(month=2, day=28, year=d.year + 1)
        if best is None or d < best[0]:
            best = (d, s, q['yield_net_pct'])
    if not best:
        return None
    d, s, y = best
    return ("Dividende à venir (estimé)", f"{clean(s, ql[s]['name'])} ({s})", f"≈ {frdate_y(d)} · {y:.2f} %")


def rubric_rendement(ql, window, data, ref):
    cand = [(q['yield_net_pct'], s) for s, q in ql.items() if q.get('yield_net_pct')]
    if not cand:
        return None
    y, s = max(cand)
    return ("Meilleur rendement du moment", f"{clean(s, ql[s]['name'])} ({s})", f"{y:.2f} %")


def rubric_volume(ql, window, data, ref):
    vol = {s: sum(x['volume'] or 0 for d in window for x in data[d]['quotes'] if x['symbol'] == s) for s in ql}
    s = max(vol, key=vol.get)
    return ("Valeur la plus échangée", f"{clean(s, ql[s]['name'])} ({s})", f"{f0(vol[s])} titres")


RUBRICS = [rubric_dividende, rubric_rendement, rubric_volume]


def build():
    with open(DATA_FILE, encoding='utf-8') as f:
        data = json.load(f)
    days = sorted(data)
    if len(days) < 2:
        print("Pas assez de séances.")
        return
    end = days[-1]
    end_d = dt.date.fromisoformat(end)
    lundi = end_d - dt.timedelta(days=end_d.weekday())
    window = [d for d in days if lundi <= dt.date.fromisoformat(d) <= end_d]
    if len(window) < 2:
        window = days[-2:]
    start = window[0]

    qf = {x['symbol']: x for x in data[start]['quotes']}
    ql = {x['symbol']: x for x in data[end]['quotes']}
    perf = [(s, (ql[s]['close'] - qf[s]['close']) / qf[s]['close'] * 100)
            for s in ql if s in qf and qf[s]['close'] and ql[s]['close']]
    perf.sort(key=lambda x: -x[1])
    gain, loss = perf[:3], sorted(perf, key=lambda x: x[1])[:3]
    up = sum(1 for _, w in perf if w > 0)
    dn = sum(1 for _, w in perf if w < 0)

    # Composite : série de la semaine (repli sur prestige si absent)
    key = 'composite'
    series = [data[d]['summary'].get('indices', {}).get('composite') for d in window]
    if any(v is None for v in series):
        series = [data[d]['summary'].get('indices', {}).get('prestige') for d in window]
        key = 'prestige'
    label = 'BRVM Composite' if key == 'composite' else 'BRVM Prestige'
    series = [v for v in series if v is not None]
    lvl = series[-1] if series else None
    iw = (lvl - series[0]) / series[0] * 100 if len(series) >= 2 else None
    iw_col = UP if (iw or 0) >= 0 else DN

    # Rubrique tournante (change chaque semaine ISO)
    ridx = end_d.isocalendar()[1] % len(RUBRICS)
    rub = None
    for k in range(len(RUBRICS)):
        rub = RUBRICS[(ridx + k) % len(RUBRICS)](ql, window, data, end_d)
        if rub:
            break

    rub_svg = ''
    if rub:
        rub_svg = (f'<rect x="64" y="1126" width="952" height="92" rx="16" fill="{CARD}"/>'
                   f'<text x="96" y="1166" font-family="Arial" font-size="25" fill="{MU}">{rub[0]}</text>'
                   f'<text x="96" y="1200" font-family="Arial" font-size="29" font-weight="700" fill="{TX}">{rub[1]}</text>'
                   f'<text x="984" y="1188" text-anchor="end" font-family="Arial" font-size="28" font-weight="700" fill="{OR}">{rub[2]}</text>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1350">
<rect width="1080" height="1350" fill="{BG}"/>
<rect x="64" y="52" width="96" height="96" rx="22" fill="{OR}"/>
<g transform="translate(64,52) scale(2)"><path d="M4 24 Q24 9 44 24 Q24 39 4 24 Z" fill="none" stroke="#fff" stroke-width="2.6"/><line x1="24" y1="14" x2="24" y2="34" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/><rect x="20.5" y="19.5" width="7" height="9" rx="1.6" fill="#fff"/></g>
<text x="184" y="104" font-family="Arial" font-size="56" font-weight="800" fill="{TX}">Zié<tspan fill="{OR}">clair</tspan></text>
<text x="186" y="142" font-family="Arial" font-size="25" fill="{MU}" letter-spacing="3">RÉCAP DE LA SEMAINE</text>
<text x="64" y="206" font-family="Arial" font-size="30" font-weight="700" fill="{OR}">Semaine du {frdate(dt.date.fromisoformat(start))} au {frdate(end_d)} {end[:4]}</text>
<rect x="64" y="228" width="952" height="150" rx="18" fill="{CARD}"/>
<text x="96" y="284" font-family="Arial" font-size="26" fill="{MU}">{label}</text>
<text x="96" y="344" font-family="Arial" font-size="50" font-weight="800" fill="{TX}">{lvl:.2f}</text>
<text x="984" y="318" text-anchor="end" font-family="Arial" font-size="44" font-weight="800" fill="{iw_col}">{pct(iw) if iw is not None else ''}</text>
<text x="984" y="352" text-anchor="end" font-family="Arial" font-size="22" fill="{MU}">{'sur la semaine' if iw is not None else ''}</text>
<text x="64" y="428" font-family="Arial" font-size="27" font-weight="700" fill="{TX}"><tspan fill="{UP}">{up} hausses</tspan>   ·   <tspan fill="{DN}">{dn} baisses</tspan></text>
<text x="64" y="486" font-family="Arial" font-size="29" font-weight="800" fill="{UP}">▲  PLUS FORTES HAUSSES</text>
{mover_cards(gain, 506, UP, ql)}
<text x="64" y="826" font-family="Arial" font-size="29" font-weight="800" fill="{DN}">▼  PLUS FORTES BAISSES</text>
{mover_cards(loss, 846, DN, ql)}
{rub_svg}
<text x="540" y="1276" text-anchor="middle" font-family="Arial" font-size="26" font-weight="700" fill="{TX}">La BRVM, en clair.</text>
<text x="540" y="1308" text-anchor="middle" font-family="Arial" font-size="19" fill="{MU}">Données : Bulletins Officiels de la Cote (BRVM). Information, pas un conseil en investissement.</text>
</svg>'''

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"recap_{end}.png")
    cairosvg.svg2png(bytestring=svg.encode('utf-8'), write_to=out, output_width=1080, output_height=1350)
    cairosvg.svg2png(bytestring=svg.encode('utf-8'), write_to=os.path.join(OUT_DIR, "latest.png"), output_width=1080, output_height=1350)
    print(f"Récap généré : {out}  (semaine {start} → {end}, rubrique : {rub[0] if rub else '—'})")


if __name__ == "__main__":
    build()
