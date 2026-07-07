"""
brvm_parser.py — Extraction structurée du Bulletin Officiel de la Cote (BOC) de la BRVM.

Convertit un PDF BOC en données exploitables :
  - en-tête (date de séance, numéro de bulletin)
  - indices de référence (Composite, 30, Prestige)
  - statistiques de marché (actions & obligations)
  - indices sectoriels
  - cote détaillée des valeurs (une ligne par action)

Robuste au layout : les colonnes sont reconstruites par position horizontale (x)
des mots, ce qui gère les nombres à séparateur d'espace et les cellules vides.

Dépendance : pdfplumber  (pip install pdfplumber)
"""
from __future__ import annotations
import re
import datetime as dt
from dataclasses import dataclass, asdict, field
from typing import Optional
import pdfplumber

# ---------------------------------------------------------------------------
# Bandes de colonnes de la cote détaillée (bornes x0, en points PDF).
# Calibrées sur le gabarit BOC A4 standard. Les valeurs sont alignées à droite ;
# les nombres à séparateur d'espace ("16 490") sont recollés par bande.
# ---------------------------------------------------------------------------
COLS = [
    ("sect",  15,  30),   # code secteur (ligne sous le symbole)
    ("symbol", 30, 63),
    ("name",  63, 150),
    ("prev_close", 150, 195),
    ("open",  195, 224),
    ("close", 224, 248),
    ("var_day", 248, 288),
    ("volume", 288, 320),
    ("value", 320, 360),
    ("ref_price", 360, 398),
    ("var_ytd", 398, 448),
    ("div_amount", 448, 490),
    ("div_date", 490, 522),
    ("yield_net", 522, 560),
    ("per", 560, 600),
]

SECTORS = {
    "CB": "Consommation de base",
    "CD": "Consommation discrétionnaire",
    "FIN": "Services financiers",
    "IND": "Industriels",
    "ENE": "Énergie",
    "TEL": "Télécommunications",
    "SPU": "Services publics",
}
_SECT_CODES = set(SECTORS)
_SYMBOL_RE = re.compile(r"^\(?([A-Z]{2,6})\)?$")
_MONTHS = {
    "janv": 1, "févr": 2, "fevr": 2, "mars": 3, "avr": 4, "mai": 5, "juin": 6,
    "juil": 7, "août": 8, "aout": 8, "sept": 9, "oct": 10, "nov": 11, "déc": 12, "dec": 12,
}


def _num(s: Optional[str]) -> Optional[float]:
    """Convertit un nombre BOC ('16 490', '-5,10', ',92') en float. '' -> None."""
    if not s:
        return None
    s = s.replace("%", "").replace(" ", "").replace("\xa0", "").replace(" ", "").strip()
    if not s or s in ("-", "—"):
        return None
    if s.startswith(","):
        s = "0" + s
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_fr_date(s: Optional[str]) -> Optional[str]:
    """'18-août-25' -> '2025-08-18' (ISO). Retourne None si non parsable."""
    if not s:
        return None
    m = re.match(r"(\d{1,2})[-\s]([A-Za-zéûôàè.]+)[-\s](\d{2,4})", s.strip())
    if not m:
        return None
    day = int(m.group(1))
    mon_raw = m.group(2).lower().strip(".")
    mon = None
    for k, v in _MONTHS.items():
        if mon_raw.startswith(k):
            mon = v
            break
    if mon is None:
        return None
    year = int(m.group(3))
    if year < 100:
        year += 2000
    try:
        return dt.date(year, mon, day).isoformat()
    except ValueError:
        return None


@dataclass
class Quote:
    session_date: str
    symbol: str
    name: str
    sector: str
    sector_code: str
    compartment: str
    prev_close: Optional[float]
    open: Optional[float]
    close: Optional[float]
    var_day_pct: Optional[float]
    volume: Optional[float]
    value_fcfa: Optional[float]
    ref_price: Optional[float]
    var_ytd_pct: Optional[float]
    div_amount_net: Optional[float]
    div_date: Optional[str]
    yield_net_pct: Optional[float]
    per: Optional[float]


def _assign(word, x0):
    for name, lo, hi in COLS:
        if lo <= x0 < hi:
            return name
    return None


def _cluster_rows(page, tol=2.2):
    """Regroupe les mots d'une page en lignes par coordonnée verticale."""
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    rows = []
    for w in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
        placed = False
        for r in rows:
            if abs(r["top"] - w["top"]) <= tol:
                r["words"].append(w)
                r["top"] = (r["top"] * r["n"] + w["top"]) / (r["n"] + 1)
                r["n"] += 1
                placed = True
                break
        if not placed:
            rows.append({"top": w["top"], "n": 1, "words": [w]})
    return sorted(rows, key=lambda r: r["top"])


def _row_cells(row):
    cells: dict[str, list] = {name: [] for name, _, _ in COLS}
    for w in sorted(row["words"], key=lambda w: w["x0"]):
        col = _assign(w, w["x0"])
        if col:
            cells[col].append(w["text"])
    return {k: " ".join(v).strip() for k, v in cells.items()}


def parse_cote(pdf, session_date: str) -> list[Quote]:
    """Extrait uniquement le marché des ACTIONS (compartiments Prestige + Principal).
    Les obligations et OPCVM sont ignorés."""
    quotes: list[Quote] = []
    compartment = ""
    in_equities = False   # devient True au compartiment Prestige, False au TOTAL Principal
    current: Optional[Quote] = None
    for page in pdf.pages:
        txt = page.extract_text() or ""
        if "COMPARTIMENT" not in txt and not any(c in txt for c in _SECT_CODES):
            continue
        for row in _cluster_rows(page):
            cells = _row_cells(row)
            joined = " ".join(w["text"] for w in row["words"])
            up = joined.upper()
            if "COMPARTIMENT PRESTIGE" in up:
                compartment = "Prestige"; in_equities = True; current = None; continue
            if "COMPARTIMENT PRINCIPAL" in up:
                compartment = "Principal"; in_equities = True; current = None; continue
            if up.startswith("TOTAL"):
                if compartment == "Principal":
                    in_equities = False   # fin du marché actions
                current = None; continue
            if not in_equities:
                continue
            if "CODE" in cells.get("sect", "").upper():
                current = None; continue

            sym_cell = cells.get("symbol", "")
            m = _SYMBOL_RE.match(sym_cell.split()[0]) if sym_cell.split() else None
            has_price = bool(cells.get("close")) or bool(cells.get("var_day"))

            if m and has_price:
                # nouvelle ligne de valeur
                current = Quote(
                    session_date=session_date,
                    symbol=m.group(1),
                    name=cells.get("name", ""),
                    sector="", sector_code="", compartment=compartment,
                    prev_close=_num(cells.get("prev_close")),
                    open=_num(cells.get("open")),
                    close=_num(cells.get("close")),
                    var_day_pct=_num(cells.get("var_day")),
                    volume=_num(cells.get("volume")),
                    value_fcfa=_num(cells.get("value")),
                    ref_price=_num(cells.get("ref_price")),
                    var_ytd_pct=_num(cells.get("var_ytd")),
                    div_amount_net=_num(cells.get("div_amount")),
                    div_date=_parse_fr_date(cells.get("div_date")),
                    yield_net_pct=_num(cells.get("yield_net")),
                    per=_num(cells.get("per")),
                )
                quotes.append(current)
            elif current is not None:
                # ligne de continuation : code secteur et/ou suite du nom
                sect_tok = cells.get("sect", "").strip().strip("()")
                if sect_tok in _SECT_CODES and not current.sector_code:
                    current.sector_code = sect_tok
                    current.sector = SECTORS[sect_tok]
                extra = cells.get("name", "").strip()
                if extra and not any(ch.isdigit() for ch in extra):
                    current.name = (current.name + " " + extra).strip()
    return quotes


def parse_summary(pdf) -> dict:
    """Extrait date, n° bulletin, indices, stats marché et indices sectoriels (page 1)."""
    p0 = pdf.pages[0]
    text = p0.extract_text() or ""
    out: dict = {}

    # Date + numéro
    dm = re.search(r"(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+(\d{1,2})\s+"
                   r"(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})",
                   text, re.I)
    fr_mon = {"janvier":1,"février":2,"mars":3,"avril":4,"mai":5,"juin":6,"juillet":7,
              "août":8,"septembre":9,"octobre":10,"novembre":11,"décembre":12}
    if dm:
        out["session_date"] = dt.date(int(dm.group(4)), fr_mon[dm.group(3).lower()], int(dm.group(2))).isoformat()
    nm = re.search(r"N[°º]\s*(\d+)", text)
    out["bulletin_no"] = int(nm.group(1)) if nm else None

    # Indices de référence
    out["indices"] = {}
    for key, label in [("BRVM COMPOSITE", "composite"), ("BRVM 30", "brvm30"), ("BRVM PRESTIGE", "prestige")]:
        rx = re.search(re.escape(key) + r"\s+([\d\s,]+)", text)
        if rx:
            out["indices"][label] = _num(rx.group(1).split("\n")[0])
    return out


def parse_boc(path: str) -> dict:
    """Point d'entrée : parse un PDF BOC -> dict {summary, quotes}."""
    with pdfplumber.open(path) as pdf:
        summary = parse_summary(pdf)
        session_date = summary.get("session_date") or _date_from_filename(path)
        quotes = parse_cote(pdf, session_date)
    return {"summary": summary, "quotes": [asdict(q) for q in quotes]}


def _date_from_filename(path: str) -> str:
    m = re.search(r"(\d{4})(\d{2})(\d{2})", path)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return dt.date.today().isoformat()


if __name__ == "__main__":
    import sys, json
    res = parse_boc(sys.argv[1])
    print(json.dumps(res["summary"], ensure_ascii=False, indent=2))
    print(f"\n{len(res['quotes'])} valeurs extraites")
    for q in res["quotes"]:
        print(f"  {q['symbol']:6} {q['name'][:32]:32} {q['sector_code']:4} "
              f"clot={q['close']} varj={q['var_day_pct']} vol={q['volume']} "
              f"val={q['value_fcfa']} per={q['per']} rdt={q['yield_net_pct']}")
