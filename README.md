# BRVM Live — site de consultation auto-alimenté

Front office public de suivi des actions BRVM, hébergé gratuitement, mis à jour
tout seul chaque soir. Aucun serveur, aucune base de données.

## Comment ça marche

```
   GitHub Actions (robot planifié)            GitHub Pages (site public)
   ┌─────────────────────────────┐            ┌──────────────────────────┐
   │ chaque soir :               │            │ index.html               │
   │  1. télécharge le BOC du jour│   écrit    │   ↓ lit                  │
   │  2. le parse (brvm_parser)  │ ─────────▶ │ data.json  ──▶ visiteurs │
   │  3. met à jour data.json    │  (commit)  │                          │
   └─────────────────────────────┘            └──────────────────────────┘
```

- **`index.html`** — le site. Charge `data.json` et affiche marché + fiches.
- **`data.json`** — les données (une entrée par séance). Généré par le robot.
- **`build_data.py`** — le robot : télécharge, parse, met à jour `data.json`.
- **`brvm_parser.py`** — le moteur d'extraction du bulletin (validé).
- **`.github/workflows/update.yml`** — la planification (cron quotidien + backfill manuel).

## Déploiement — de zéro à site en ligne

### 1. Créer le dépôt
1. Crée un compte sur [github.com](https://github.com) (gratuit).
2. Nouveau dépôt **public** (ex. `brvm-live`).
3. Téléverse tout le contenu de ce dossier (glisser-déposer via « Add file → Upload files », en conservant le dossier `.github/workflows/`).

### 2. Activer le site (GitHub Pages)
1. Dépôt → **Settings → Pages**.
2. *Source* : **Deploy from a branch**, branche `main`, dossier `/ (root)`.
3. Au bout d'une minute, ton site est en ligne à l'adresse indiquée
   (`https://TON-COMPTE.github.io/brvm-live/`).

### 3. Charger l'historique (une seule fois)
1. Dépôt → onglet **Actions** → workflow **« Mise à jour des données BRVM »**.
2. Bouton **Run workflow** → dans *backfill*, saisis `2026-01-02` → **Run**.
3. Le robot télécharge et parse toute l'année, puis met à jour `data.json`.
   (Le site fonctionne déjà avant, avec les 4 séances de démonstration fournies.)

### 4. C'est automatique ensuite
Chaque soir (19h UTC, jours ouvrés), le robot ajoute la séance du jour. Rien à faire.

## Nom de domaine (optionnel, ~10 €/an)
Achète un domaine, puis Settings → Pages → *Custom domain*. Une adresse comme
`brvmlive.com` remplace l'URL github.io.

## Notes
- **Téléchargement depuis le cloud** : le robot télécharge depuis les serveurs GitHub.
  Si la BRVM venait à bloquer ces adresses, bascule le robot sur un petit serveur
  (VPS ~5 €/mois) avec la même commande en cron — le reste ne change pas.
- **Droits sur la donnée** : la rediffusion publique du BOC relève des conditions de
  réutilisation de la BRVM. À vérifier / sécuriser avant ouverture au public.
- **Le score** est un indicateur d'information à règles transparentes, pas un conseil
  en investissement personnalisé (voir la méthodologie dans le front office).

## Lancer le robot en local (optionnel, pour tester)
```bash
pip install -r requirements.txt
python build_data.py --from 2026-06-01     # backfill
python build_data.py --update              # séances manquantes
# puis ouvrir index.html via un petit serveur local :
python -m http.server 8000                 # http://localhost:8000
```
> Ouvrir `index.html` en double-clic ne suffit pas : le navigateur bloque `fetch`
> sur `file://`. Utilise un petit serveur local (commande ci-dessus) ou le site en ligne.
