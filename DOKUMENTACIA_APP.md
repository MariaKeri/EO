# Justice.cz Explorer — Dokumentácia

## Čo to je

Interaktívny Streamlit dashboard na exploratórnu analýzu dát z verejných registrov Českej republiky (justice.cz). Umožňuje prehliadať ~871 000 subjektov a ~7,6 milióna záznamov o angažovaných osobách bez nutnosti písať SQL alebo Python kód.

## Dátový zdroj

Dáta pochádzajú z bulkového XML exportu Ministerstva spravodlivosti ČR (https://dataor.justice.cz). Stiahnutie a konverziu do CSV robí skript `main.py` z repozitára [kokes/od](https://github.com/kokes/od/tree/main/data/justice). Appka číta priamo z výstupných CSV priečinkov — nepotrebuje žiadne medzisúbory ani databázu.

Použité tabuľky:

| Priečinok | Obsah | Riadkov |
|-----------|-------|---------|
| `subjekty/` | Základné údaje o subjektoch (IČO, názov, dátumy zápisu/výmazu) | ~871 000 |
| `angazovane_osoby/` | Osoby vo funkciách (meno, dátum narodenia, funkcia, adresa, IČO firmy) | ~7 600 000 |
| `sidlo/` | Sídla subjektov (ulica, obec, PSČ, číslo popisné) | ~1 500 000 |

## Spustenie

```bash
cd data/justice            # adresár s priečinkami subjekty/, angazovane_osoby/, sidlo/
pip install -r requirements.txt
streamlit run app.py
```

Otvorí sa prehliadač na `http://localhost:8501`. V sidebar je možné zvoliť vzorku osôb (10–100 %) pre rýchlejšie načítanie.

## Stránky aplikácie

### 📊 Prehľad

Základné štatistiky datasetu — počet subjektov, osôb, sídiel, unikátnych mien. Donut chart rozdelenia na sektory (komerčné / neziskové / ostatné). Tabuľka top 15 právnych foriem podľa početnosti. Bar chart počtu nových registrácií podľa rokov (od 1990).

### 🔍 Kvalita dát

Analýza kvality kľúčových polí. Distribúcia dĺžok IČO (štandardné 8-ciferné vs. neštandardné). Vyplnenosť mien a dátumov narodenia u fyzických osôb. Bar chart vyplnenosti adresných polí (štát, obec, ulica, PSČ…). Validácia PSČ na 5-ciferný formát. Klasifikácia chýb do 4 typov: chýbajúci dátum narodenia, starý záznam (pred 2000), zahraničná osoba, právnická osoba v dátach fyzických osôb.

### 👤 Hľadanie osôb

Fulltextové vyhľadávanie osoby podľa mena (napr. „Michal Tkac"). Výsledky zoskupené podľa mena + dátumu narodenia — vidno koľko rôznych osôb s rovnakým menom existuje. Pre každú osobu sa zobrazí: vygenerované person_id (PID-XXXXXXXX), role vo firmách, IČO a názvy prepojených firiem. Slúži na riešenie problému „je Michal Tkáč ten istý ako ten druhý Michal Tkáč".

### 🔗 Prepojenia firiem

Po zadaní IČO firmy zobrazí všetky ostatné firmy prepojené cez spoločné osoby (konateľov, spoločníkov, členov predstavenstva…). Pre každé prepojenie ukazuje meno spájajúcej osoby a jej roly v oboch firmách. Bez zadania IČO zobrazí rebríček najprepojenejších osôb v datasete. Bar chart rozdelenia prepojení podľa typu roly.

### 🧮 Pravidlá identifikácie

Vysvetlenie a simulácia 4 sekvenčných pravidiel na riešenie chýbajúcich dátumov narodenia:

- **Pravidlo 1** — meno + adresa: ak sa rovnaká osoba vyskytuje inde s dátumom narodenia, prevezme sa
- **Pravidlo 2** — len adresa: zoskupenie podľa adresy
- **Pravidlo 3** — meno + firma: osoba sa presťahovala, ale zostala v rovnakej firme
- **Pravidlo 4** — krstné meno + firma + adresa: zmena priezviska (napr. po sobáši)

Stránka spustí pravidlá 1 a 3 na reálnych dátach a zobrazí koľko záznamov by sa podarilo doplniť (pie chart).

## Technické detaily

- **Framework:** Streamlit + Plotly
- **Dáta:** raw CSV, načítané cez `pd.read_csv` s `@st.cache_data`
- **Normalizácia mien:** lowercase, odstránenie diakritiky, špeciálnych znakov
- **Person ID:** deterministický MD5 hash z normalizovaného mena + dátumu narodenia
- **Pamäťové nároky:** ~2–4 GB RAM pri plnom datasete, ~500 MB pri 10% vzorke
