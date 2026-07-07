#!/usr/bin/env python3
"""
build_data.py — Robot d'alimentation du front office BRVM Live.

Télécharge les Bulletins Officiels de la Cote (BOC) de la BRVM, les parse
(via brvm_parser.py) et maintient le fichier data.json que lit le site.

Exécuté automatiquement par GitHub Actions :
  - backfill (une fois)  :  python build_data.py --from 2026-01-02
  - mise à jour quotidienne :  python build_data.py --update

data.json a la forme : { "2026-07-03": { "summary": {...}, "quotes": [...] }, ... }
"""
from __future__ import annotations
import argparse, datetime as dt, json, os, sys, tempfile, time
import requests
from brvm_parser import parse_boc

DATA_FILE = "data.json"
URLS = [
    "https://bfin.brvm.org/boc/BOC_JOUR/BOC_{ymd}.pdf",
    "https://www.brvm.org/sites/default/files/boc_{ymd}_2.pdf",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; brvm-live/1.0)"}


def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_data(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def download(date: dt.date, tmp: str) -> str | None:
    ymd = date.strftime("%Y%m%d")
    for u in URLS:
        url = u.format(ymd=ymd)
        try:
            r = requests.get(url, timeout=45, headers=HEADERS)
        except Exception:
            continue
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            path = os.path.join(tmp, f"BOC_{ymd}.pdf")
            with open(path, "wb") as f:
                f.write(r.content)
            return path
    return None  # week-end / jour férié / bulletin absent


def business_days(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def run(start: dt.date, end: dt.date, data: dict) -> int:
    added = 0
    with tempfile.TemporaryDirectory() as tmp:
        for d in business_days(start, end):
            iso = d.isoformat()
            if iso in data:
                continue
            path = download(d, tmp)
            if not path:
                continue
            try:
                res = parse_boc(path)
                sd = res["summary"].get("session_date") or iso
                if len(res["quotes"]) < 40:
                    print(f"  ! {sd} ignoré ({len(res['quotes'])} valeurs, extraction douteuse)")
                    continue
                data[sd] = {"summary": res["summary"], "quotes": res["quotes"]}
                added += 1
                print(f"  OK {sd} : {len(res['quotes'])} valeurs")
            except Exception as e:
                print(f"  ! {iso} parsing échoué : {e}")
            time.sleep(1)
    return added


def main():
    ap = argparse.ArgumentParser(description="Alimente data.json depuis les bulletins BRVM.")
    ap.add_argument("--from", dest="frm", help="Date de début AAAA-MM-JJ (backfill)")
    ap.add_argument("--to", help="Date de fin AAAA-MM-JJ (défaut : aujourd'hui)")
    ap.add_argument("--update", action="store_true", help="Récupère les séances manquantes jusqu'à aujourd'hui")
    a = ap.parse_args()

    data = load_data()
    today = dt.date.today()

    if a.frm and not a.update:
        start = dt.date.fromisoformat(a.frm)
        end = dt.date.fromisoformat(a.to) if a.to else today
    else:
        if data:
            last = max(dt.date.fromisoformat(k) for k in data)
            start = last + dt.timedelta(days=1)
        else:
            start = today - dt.timedelta(days=10)
        end = today

    if start > end:
        print("Déjà à jour, rien à faire.")
        return

    print(f"Alimentation du {start} au {end}…")
    n = run(start, end, data)
    save_data(data)
    print(f"Terminé : {n} séance(s) ajoutée(s). Total en base : {len(data)} séances.")


if __name__ == "__main__":
    main()
