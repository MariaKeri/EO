import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import glob
import os
import re
import hashlib
from collections import defaultdict, Counter
from unicodedata import normalize as unicode_normalize, category

st.set_page_config(
    page_title="Justice.cz Analýza",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

    .stApp { font-family: 'IBM Plex Sans', sans-serif; }
    
    .metric-card {
        background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        color: white;
        margin-bottom: 0.5rem;
    }
    .metric-card .label {
        font-size: 0.75rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #94a3b8;
        margin-bottom: 0.25rem;
    }
    .metric-card .value {
        font-size: 1.8rem;
        font-weight: 600;
        font-family: 'IBM Plex Mono', monospace;
        line-height: 1.1;
    }
    .metric-card .detail {
        font-size: 0.7rem;
        color: #64748b;
        margin-top: 0.3rem;
    }

    .section-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #1e293b;
        border-bottom: 2px solid #3b82f6;
        padding-bottom: 0.4rem;
        margin: 1.5rem 0 1rem 0;
    }

    .flag-badge {
        display: inline-block;
        padding: 0.15rem 0.5rem;
        border-radius: 4px;
        font-size: 0.7rem;
        font-weight: 500;
        font-family: 'IBM Plex Mono', monospace;
    }
    .flag-old    { background: #dbeafe; color: #1e40af; }
    .flag-foreign { background: #fef3c7; color: #92400e; }
    .flag-legal  { background: #dcfce7; color: #166534; }
    .flag-missing { background: #fce7f3; color: #9d174d; }
</style>
""", unsafe_allow_html=True)

def strip_accents(s):
    if not isinstance(s, str):
        return ""
    return "".join(
        c for c in unicode_normalize("NFD", s) if category(c) != "Mn"
    )


def normalize_name(s):
    if not isinstance(s, str) or not s.strip():
        return ""
    s = strip_accents(s).lower().strip()
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def make_person_id(name, birth_date):
    raw = f"{normalize_name(str(name))}|{str(birth_date)}"
    return "PID-" + hashlib.md5(raw.encode()).hexdigest()[:8].upper()


def classify_entity(filename):
    """Classify entity type from filename prefix"""
    prefix = os.path.basename(filename).split("-full-")[0] if "-full-" in filename else ""
    mapping = {
        "sro": "s.r.o.", "as": "a.s.", "vos": "v.o.s.", "ks": "k.s.",
        "dr": "Družstvo", "evrspol": "Europ. spol. (SE)",
        "spolek": "Spolek", "pobspolek": "Pobočný spolek",
        "odbororg": "Odborová org.", "ops": "O.p.s.", "ustav": "Ústav",
        "nad": "Nadácia", "nadf": "Nadačný fond",
        "svj": "SVJ", "sf": "Svěřenský fond",
        "pfot": "FO podnikateľ", "zahrfos": "Zahraničná FO",
        "prisp": "Príspevková org.", "oszpo": "Odšt. závod zahr. PO",
        "komora_ha": "Komora", "nevlad_org": "Nevládna org.",
        "orgzam": "Org. zamestnávateľov",
    }
    return mapping.get(prefix, prefix or "Ostatné")


def classify_sector(entity_type):
    commercial = {"s.r.o.", "a.s.", "v.o.s.", "k.s.", "Družstvo", "Europ. spol. (SE)", "FO podnikateľ"}
    ngo = {"Spolek", "Pobočný spolek", "Odborová org.", "O.p.s.", "Ústav", "Nadácia", "Nadačný fond", "Nevládna org."}
    if entity_type in commercial:
        return "Komerčné"
    elif entity_type in ngo:
        return "Neziskové (NGO)"
    else:
        return "Ostatné"


ROLE_MAP = {
    "jednatel": "Konateľ", "člen představenstva": "Člen predstavenstva",
    "předseda představenstva": "Predseda predstavenstva",
    "společník": "Spoločník", "člen dozorčí rady": "Člen dozornej rady",
    "prokurista": "Prokurista", "likvidátor": "Likvidátor",
    "předseda": "Predseda", "místopředseda": "Podpredseda",
    "člen": "Člen", "zakladatel": "Zakladateľ",
}


def canonical_role(raw):
    if not isinstance(raw, str):
        return "Neuvedené"
    return ROLE_MAP.get(raw.lower().strip(), raw.strip().title() if raw.strip() else "Neuvedené")


@st.cache_data(show_spinner="Načítavam subjekty…")
def load_subjekty(data_dir):
    files = sorted(glob.glob(os.path.join(data_dir, "subjekty", "*.csv")))
    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f, dtype=str, keep_default_na=False)
            df["_entity_type"] = classify_entity(f)
            dfs.append(df)
        except:
            pass
    out = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    out = out.drop_duplicates(subset=["ico"], keep="last")
    return out


@st.cache_data(show_spinner="Načítavam osoby…")
def load_osoby(data_dir, sample_frac=1.0):
    files = sorted(glob.glob(os.path.join(data_dir, "angazovane_osoby", "*.csv")))
    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f, dtype=str, keep_default_na=False)
            if sample_frac < 1.0:
                df = df.sample(frac=sample_frac, random_state=42)
            dfs.append(df)
        except:
            pass
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


@st.cache_data(show_spinner="Načítavam sídla…")
def load_sidla(data_dir):
    files = sorted(glob.glob(os.path.join(data_dir, "sidlo", "*.csv")))
    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f, dtype=str, keep_default_na=False)
            dfs.append(df)
        except:
            pass
    out = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    return out


@st.cache_data(show_spinner="Načítavam právne formy…")
def load_pravni_formy(data_dir):
    files = sorted(glob.glob(os.path.join(data_dir, "pravni_forma", "*.csv")))
    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f, dtype=str, keep_default_na=False)
            dfs.append(df)
        except:
            pass
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def metric(label, value, detail=""):
    detail_html = f'<div class="detail">{detail}</div>' if detail else ""
    st.markdown(f"""
    <div class="metric-card">
        <div class="label">{label}</div>
        <div class="value">{value}</div>
        {detail_html}
    </div>
    """, unsafe_allow_html=True)


def page_overview(subj, osoby, sidla):
    st.markdown("## Prehľad datasetu")

    n_subj = len(subj)
    n_osoby = len(osoby)
    n_sidla = len(sidla)
    n_active = (subj["datum_vymaz"] == "").sum()
    n_deleted = n_subj - n_active

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric("Subjekty", f"{n_subj:,}".replace(",", " "), f"{n_active:,} aktívnych · {n_deleted:,} zaniklých".replace(",", " "))
    with c2:
        metric("Angažované osoby", f"{n_osoby:,}".replace(",", " "), "záznamy osôb vo funkciách")
    with c3:
        metric("Sídla", f"{n_sidla:,}".replace(",", " "), "historické + aktuálne adresy")
    with c4:
        fo_mask = osoby["jmeno_prijmeni"] != ""
        n_unique = osoby.loc[fo_mask, "jmeno_prijmeni"].nunique()
        metric("Unikátne mená FO", f"{n_unique:,}".replace(",", " "), "fyzické osoby podľa mena")

    st.markdown('<div class="section-header">Distribúcia podľa sektoru</div>', unsafe_allow_html=True)

    subj["_sector"] = subj["_entity_type"].apply(classify_sector)
    sector_counts = subj["_sector"].value_counts()

    col_chart, col_table = st.columns([2, 1])

    with col_chart:
        colors = {"Komerčné": "#3b82f6", "Neziskové (NGO)": "#10b981", "Ostatné": "#8b5cf6"}
        fig = px.pie(
            values=sector_counts.values, names=sector_counts.index,
            color=sector_counts.index, color_discrete_map=colors,
            hole=0.45,
        )
        fig.update_traces(textinfo="label+percent", textfont_size=13)
        fig.update_layout(
            margin=dict(t=10, b=10, l=10, r=10), height=320,
            legend=dict(orientation="h", y=-0.05),
            font=dict(family="IBM Plex Sans"),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_table:
        type_counts = subj["_entity_type"].value_counts().head(15)
        st.dataframe(
            pd.DataFrame({"Právna forma": type_counts.index, "Počet": type_counts.values}),
            hide_index=True, height=320,
        )

    st.markdown('<div class="section-header">Registrácie v čase</div>', unsafe_allow_html=True)

    subj["_year"] = pd.to_datetime(subj["datum_zapis"], errors="coerce").dt.year
    year_counts = subj["_year"].dropna().astype(int).value_counts().sort_index()
    year_counts = year_counts[year_counts.index >= 1990]

    fig2 = px.bar(
        x=year_counts.index, y=year_counts.values,
        labels={"x": "Rok registrácie", "y": "Počet nových subjektov"},
    )
    fig2.update_traces(marker_color="#3b82f6")
    fig2.update_layout(
        margin=dict(t=10, b=40, l=60, r=10), height=280,
        font=dict(family="IBM Plex Sans"),
    )
    st.plotly_chart(fig2, use_container_width=True)


def page_quality(subj, osoby, sidla):
    st.markdown("## Kvalita dát")

    #ICO
    st.markdown('<div class="section-header">IČO</div>', unsafe_allow_html=True)

    ico_lens = subj["ico"].str.len()
    ico_8 = (ico_lens == 8).sum()
    ico_other = (ico_lens != 8).sum()
    c1, c2, c3 = st.columns(3)
    with c1:
        metric("Štandardné (8 cifier)", f"{ico_8:,}".replace(",", " "), f"{100*ico_8/len(subj):.1f} %")
    with c2:
        metric("Neštandardné", f"{ico_other:,}".replace(",", " "), "6–7 cifier alebo zahraničné")
    with c3:
        metric("Duplicitné IČO", f"{subj['ico'].duplicated().sum()}", "po deduplikácii = 0")

    len_dist = ico_lens.value_counts().sort_index()
    fig = px.bar(x=len_dist.index.astype(str), y=len_dist.values, labels={"x": "Dĺžka IČO", "y": "Počet"})
    fig.update_traces(marker_color="#f59e0b")
    fig.update_layout(margin=dict(t=10, b=40), height=220, font=dict(family="IBM Plex Sans"))
    st.plotly_chart(fig, use_container_width=True)

    #Osoby
    st.markdown('<div class="section-header">Mená a dátumy narodenia</div>', unsafe_allow_html=True)

    has_name = (osoby["jmeno_prijmeni"] != "").sum()
    has_nazev = (osoby.get("nazev", pd.Series(dtype=str)) != "").sum() if "nazev" in osoby.columns else 0
    has_bday = (osoby.get("datum_narozeni", pd.Series(dtype=str)) != "").sum() if "datum_narozeni" in osoby.columns else 0

    fo_total = has_name
    bday_of_fo = osoby[(osoby["jmeno_prijmeni"] != "") & (osoby.get("datum_narozeni", pd.Series(dtype=str)) != "")].shape[0] if "datum_narozeni" in osoby.columns else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric("Meno (FO)", f"{has_name:,}".replace(",", " "), f"{100*has_name/len(osoby):.1f} %")
    with c2:
        metric("Názov (PO)", f"{has_nazev:,}".replace(",", " "), f"{100*has_nazev/len(osoby):.1f} %")
    with c3:
        metric("Dátum narodenia", f"{has_bday:,}".replace(",", " "), f"{100*has_bday/len(osoby):.1f} % všetkých")
    with c4:
        pct_fo_bday = 100 * bday_of_fo / fo_total if fo_total > 0 else 0
        metric("Dát. nar. u FO", f"{pct_fo_bday:.1f} %", f"{bday_of_fo:,} z {fo_total:,}".replace(",", " "))

    #Adresy
    st.markdown('<div class="section-header">Adresy (sídla)</div>', unsafe_allow_html=True)

    fields = ["stat", "obec", "ulice", "psc", "cislo_po", "cast_obce", "okres"]
    quality_data = []
    for f in fields:
        if f in sidla.columns:
            filled = (sidla[f] != "").sum()
            quality_data.append({"Pole": f, "Vyplnené": filled, "Percento": 100 * filled / len(sidla) if len(sidla) > 0 else 0})

    qdf = pd.DataFrame(quality_data)
    fig = px.bar(qdf, x="Pole", y="Percento", text="Percento",
                 labels={"Percento": "Vyplnenosť (%)"})
    fig.update_traces(marker_color="#10b981", texttemplate="%{text:.1f}%", textposition="outside")
    fig.update_layout(margin=dict(t=10, b=40), height=280, yaxis_range=[0, 110], font=dict(family="IBM Plex Sans"))
    st.plotly_chart(fig, use_container_width=True)

    # PSC validation
    if "psc" in sidla.columns:
        pscs = sidla[sidla["psc"] != ""]["psc"]
        valid_psc = pscs.str.match(r"^\d{5}$").sum()
        st.info(f"**PSČ validácia:** {valid_psc:,} / {len(pscs):,} ({100*valid_psc/len(pscs):.1f} %) má správny 5-ciferný formát.".replace(",", " "))

    #Error flag
    st.markdown('<div class="section-header">Klasifikácia chýb (flagy)</div>', unsafe_allow_html=True)

    fo = osoby[osoby["jmeno_prijmeni"] != ""].copy()
    flags = {}

    # Old record
    if "datum_zapis" in fo.columns:
        fo["_year"] = pd.to_datetime(fo["datum_zapis"], errors="coerce").dt.year
        flags["old_record"] = (fo["_year"] < 2000).sum()
    else:
        flags["old_record"] = 0

    # No birth date
    if "datum_narozeni" in fo.columns:
        flags["no_birth_date"] = (fo["datum_narozeni"] == "").sum()
    else:
        flags["no_birth_date"] = len(fo)

    # Foreign person
    if "adresa_stat" in fo.columns:
        foreign_mask = (fo["adresa_stat"] != "") & (~fo["adresa_stat"].str.contains("Česk", case=False, na=True))
        flags["foreign_person"] = foreign_mask.sum()
    else:
        flags["foreign_person"] = 0

    # Legal entity in FO data
    if "nazev" in fo.columns:
        le_patterns = r"s\.r\.o|a\.s\.|spol\.|v\.o\.s|k\.s\.|družstvo|nadace|spolek"
        flags["legal_entity_in_fo"] = fo["jmeno_prijmeni"].str.contains(le_patterns, case=False, na=False).sum()
    else:
        flags["legal_entity_in_fo"] = 0

    flag_df = pd.DataFrame([
        {"Flag": "Bez dátumu narodenia", "Počet": flags["no_birth_date"], "Typ": "Dátová medzera"},
        {"Flag": "Starý záznam (pred 2000)", "Počet": flags["old_record"], "Typ": "Historický"},
        {"Flag": "Zahraničná osoba", "Počet": flags["foreign_person"], "Typ": "Zahraničný"},
        {"Flag": "PO v dátach FO", "Počet": flags["legal_entity_in_fo"], "Typ": "Misklasifikácia"},
    ])

    colors_flag = {"Dátová medzera": "#ef4444", "Historický": "#3b82f6", "Zahraničný": "#f59e0b", "Misklasifikácia": "#10b981"}
    fig = px.bar(flag_df, x="Flag", y="Počet", color="Typ", color_discrete_map=colors_flag,
                 text="Počet")
    fig.update_traces(texttemplate="%{text:,}", textposition="outside")
    fig.update_layout(margin=dict(t=10, b=40), height=300, font=dict(family="IBM Plex Sans"),
                      legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, use_container_width=True)


def page_person_search(osoby, subj):
    st.markdown("## Hľadanie a identifikácia osôb")
    st.caption("Zadaj meno a nájdi všetky výskyty v registri. Uvidíš, v koľkých firmách sa osoba vyskytuje, s akými dátumami narodenia a adresami.")

    query = st.text_input("Meno osoby", placeholder="napr. Jan Novak, Michal Tkac…")

    if not query or len(query) < 3:
        st.info("Zadaj aspoň 3 znaky mena.")
        return

    norm_q = normalize_name(query)
    parts = norm_q.split()

    osoby_search = osoby[osoby["jmeno_prijmeni"] != ""].copy()
    osoby_search["_norm"] = osoby_search["jmeno_prijmeni"].apply(normalize_name)

    mask = osoby_search["_norm"].notna()
    for p in parts:
        mask = mask & osoby_search["_norm"].str.contains(p, na=False)

    matches = osoby_search[mask].copy()

    if matches.empty:
        st.warning(f'Ziadne vysledky pre: {query}')
        return

    st.success(f"Nájdených **{len(matches):,}** záznamov.".replace(",", " "))

    # Group by name + birth date
    bday_col = "datum_narozeni" if "datum_narozeni" in matches.columns else None
    group_cols = ["jmeno_prijmeni"]
    if bday_col:
        group_cols.append(bday_col)

    grouped = matches.groupby(group_cols).agg(
        pocet_zaznamov=("ico", "size"),
        pocet_firiem=("ico", "nunique"),
        firmy_ico=("ico", lambda x: ", ".join(x.unique()[:8])),
        role=("funkce", lambda x: ", ".join(x.dropna().unique()[:5])) if "funkce" in matches.columns else ("ico", lambda x: ""),
    ).reset_index().sort_values("pocet_firiem", ascending=False)

    # Add person_id
    if bday_col:
        grouped["person_id"] = grouped.apply(lambda r: make_person_id(r["jmeno_prijmeni"], r[bday_col]), axis=1)
    else:
        grouped["person_id"] = grouped.apply(lambda r: make_person_id(r["jmeno_prijmeni"], ""), axis=1)

    # Display
    for _, row in grouped.head(20).iterrows():
        bday_str = row.get(bday_col, "—") if bday_col else "—"
        if not bday_str or bday_str == "":
            bday_str = "⚠️ chýba"

        with st.expander(f"**{row['jmeno_prijmeni']}** — nar. {bday_str} — {row['pocet_firiem']} firiem — {row['pocet_zaznamov']} záznamov"):
            st.code(f"Person ID: {row['person_id']}")
            st.write(f"**Role:** {row['role']}")
            st.write(f"**IČO firiem:** {row['firmy_ico']}")

            # Show matching company names
            icos = [i.strip() for i in row["firmy_ico"].split(",")]
            company_names = subj[subj["ico"].isin(icos)][["ico", "nazev"]].drop_duplicates()
            if not company_names.empty:
                st.dataframe(company_names.rename(columns={"ico": "IČO", "nazev": "Názov"}), hide_index=True)

    if len(grouped) > 20:
        st.caption(f"Zobrazených prvých 20 z {len(grouped)} unikátnych osôb.")


def page_connections(osoby, subj):
    st.markdown("## Prepojenia firiem")
    st.caption("Hľadá firmy prepojené cez spoločné osoby (konateľov, spoločníkov, členov predstavenstva…)")

    # Build person → companies map
    fo = osoby[(osoby["jmeno_prijmeni"] != "")].copy()
    bday_col = "datum_narozeni" if "datum_narozeni" in fo.columns else None

    if bday_col:
        fo["_pkey"] = fo["jmeno_prijmeni"].apply(normalize_name) + "|" + fo[bday_col].fillna("")
    else:
        fo["_pkey"] = fo["jmeno_prijmeni"].apply(normalize_name)

    # Let user pick a company by ICO
    target_ico = st.text_input("IČO firmy", placeholder="napr. 60827441")

    if not target_ico:
        st.info("Zadaj IČO firmy pre zobrazenie prepojení.")

        # Show top connected persons
        st.markdown('<div class="section-header">Najviac prepojené osoby (ukážka z prvých 500k záznamov)</div>', unsafe_allow_html=True)

        sample = fo.head(500_000)
        person_ico_count = sample.groupby("_pkey")["ico"].nunique()
        top_connected = person_ico_count[person_ico_count > 3].sort_values(ascending=False).head(15)

        if not top_connected.empty:
            results = []
            for pkey, n_companies in top_connected.items():
                name_part = pkey.split("|")[0] if "|" in pkey else pkey
                # find original name
                orig = sample[sample["_pkey"] == pkey]["jmeno_prijmeni"].iloc[0] if (sample["_pkey"] == pkey).any() else name_part
                results.append({"Osoba": orig, "Počet firiem": n_companies})

            st.dataframe(pd.DataFrame(results), hide_index=True)
        return

    target_ico = target_ico.strip()
    company_name = subj[subj["ico"] == target_ico]["nazev"].values
    if len(company_name) > 0:
        st.markdown(f"**{company_name[0]}** (IČO: {target_ico})")
    else:
        st.warning(f"IČO {target_ico} sa nenašlo medzi subjektami.")
        return

    # Find all persons in this company
    persons_in_target = fo[fo["ico"] == target_ico].copy()
    if persons_in_target.empty:
        st.info("Pre túto firmu neboli nájdené žiadne angažované osoby.")
        return

    pkeys_in_target = set(persons_in_target["_pkey"].unique())

    st.markdown(f"Osôb v tejto firme: **{len(pkeys_in_target)}**")

    # Find other companies where these persons appear
    other_companies = fo[fo["_pkey"].isin(pkeys_in_target) & (fo["ico"] != target_ico)]

    if other_companies.empty:
        st.info("Osoby tejto firmy sa nenachádzajú v žiadnych iných firmách.")
        return

    # Build edge list
    edges = []
    for pkey in pkeys_in_target:
        person_records = fo[fo["_pkey"] == pkey]
        other_icos = person_records[person_records["ico"] != target_ico]["ico"].unique()
        if len(other_icos) > 0:
            orig_name = person_records["jmeno_prijmeni"].iloc[0]
            role_in_target = persons_in_target[persons_in_target["_pkey"] == pkey]["funkce"].iloc[0] if "funkce" in persons_in_target.columns else ""
            for other_ico in other_icos:
                role_in_other = person_records[person_records["ico"] == other_ico]["funkce"].iloc[0] if "funkce" in person_records.columns else ""
                other_name = subj[subj["ico"] == other_ico]["nazev"].values
                edges.append({
                    "Prepojená firma": other_name[0] if len(other_name) > 0 else f"IČO {other_ico}",
                    "IČO": other_ico,
                    "Cez osobu": orig_name,
                    "Rola (zdrojová)": canonical_role(role_in_target),
                    "Rola (cieľová)": canonical_role(role_in_other),
                    "Typ": "Priame",
                })

    if edges:
        edges_df = pd.DataFrame(edges)

        c1, c2 = st.columns(2)
        with c1:
            metric("Priame prepojenia", str(len(edges_df)))
        with c2:
            metric("Prepojených firiem", str(edges_df["IČO"].nunique()))

        st.dataframe(edges_df.head(50), hide_index=True, use_container_width=True)

        # Role breakdown chart
        role_counts = edges_df["Rola (zdrojová)"].value_counts()
        fig = px.bar(x=role_counts.index, y=role_counts.values,
                     labels={"x": "Rola", "y": "Počet prepojení"})
        fig.update_traces(marker_color="#8b5cf6")
        fig.update_layout(margin=dict(t=10, b=40), height=250, font=dict(family="IBM Plex Sans"))
        st.plotly_chart(fig, use_container_width=True)


def page_identification_rules(osoby):
    st.markdown("## Pravidlá identifikácie osôb")
    st.caption("4 sekvenčné pravidlá na riešenie chýbajúcich dátumov narodenia — podľa zadania.")

    st.markdown("""
| # | Pravidlo | Logika | Kedy sa použije |
|---|---------|--------|-----------------|
| 1 | **Meno + adresa** | Rovnaké norm. meno + rovnaká adresa → prevziať dátum narodenia z iného záznamu | Najčastejší prípad |
| 2 | **Len adresa** | Bez nájdeného mena → zoskupiť podľa adresy | Chýba meno alebo znehodnotené |
| 3 | **Meno + firma** | Rovnaké meno + rovnaké IČO, ale iná adresa (presťahovanie) | Osoba zmenila bydlisko |
| 4 | **Krstné meno + firma + adresa** | Zmenené priezvisko (sobáš), ale rovnaké krstné meno + IČO + adresa | Zmena priezviska |
""")

    st.markdown('<div class="section-header">Simulácia pravidiel na reálnych dátach</div>', unsafe_allow_html=True)

    fo = osoby[osoby["jmeno_prijmeni"] != ""].copy()
    bday_col = "datum_narozeni" if "datum_narozeni" in fo.columns else None

    if not bday_col:
        st.warning("Stĺpec datum_narozeni chýba.")
        return

    total = len(fo)
    has_bday = (fo[bday_col] != "").sum()
    missing_bday = total - has_bday

    st.write(f"**Celkom FO záznamov:** {total:,}".replace(",", " "))
    st.write(f"**Má dátum narodenia:** {has_bday:,} ({100*has_bday/total:.1f} %)".replace(",", " "))
    st.write(f"**Chýba dátum narodenia:** {missing_bday:,} ({100*missing_bday/total:.1f} %)".replace(",", " "))

    # Quick simulation on sample
    st.markdown("**Simulácia pravidla 1** (meno + adresa → doplnenie dátumu narodenia):")

    addr_col = "adresa_obec" if "adresa_obec" in fo.columns else None
    if addr_col:
        fo["_norm_name"] = fo["jmeno_prijmeni"].apply(normalize_name)
        fo["_key1"] = fo["_norm_name"] + "|" + fo[addr_col].fillna("")

        missing = fo[fo[bday_col] == ""]
        has = fo[fo[bday_col] != ""]

        # Find keys that have birth date somewhere
        keys_with_bday = set(has["_key1"].unique())
        resolvable_r1 = missing[missing["_key1"].isin(keys_with_bday)]

        st.success(f"Pravidlo 1 by doplnilo dátum narodenia pre **{len(resolvable_r1):,}** z {len(missing):,} záznamov ({100*len(resolvable_r1)/max(len(missing),1):.1f} %).".replace(",", " "))

        # Rule 3: name + company
        still_missing = missing[~missing["_key1"].isin(keys_with_bday)]
        fo["_key3"] = fo["_norm_name"] + "|" + fo["ico"].fillna("")
        keys_with_bday_3 = set(has["_key3"].unique())
        resolvable_r3 = still_missing[still_missing["_key3"].isin(keys_with_bday_3)]

        st.success(f"Pravidlo 3 (meno + firma) by doplnilo ďalších **{len(resolvable_r3):,}** záznamov.".replace(",", " "))

        remaining = len(missing) - len(resolvable_r1) - len(resolvable_r3)
        st.info(f"Po pravidlách 1 + 3 zostáva **{remaining:,}** záznamov bez dátumu narodenia ({100*remaining/max(len(missing),1):.1f} %).".replace(",", " "))

        # Pie of resolution
        fig = px.pie(
            values=[has_bday, len(resolvable_r1), len(resolvable_r3), remaining],
            names=["Má dát. nar.", "Pravidlo 1", "Pravidlo 3", "Nevyriešené"],
            color_discrete_sequence=["#10b981", "#3b82f6", "#8b5cf6", "#ef4444"],
            hole=0.4,
        )
        fig.update_layout(margin=dict(t=10, b=10), height=300, font=dict(family="IBM Plex Sans"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Adresné stĺpce nie sú k dispozícii.")


# ═══════════════════════════════════════════════════════════════════════
# SIDEBAR + MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    st.sidebar.markdown("#  Justice Analytics")
    st.sidebar.markdown("---")

    data_dir = st.sidebar.text_input("Cesta k dátam", value=".", help="Adresár kde sú priečinky subjekty/, angazovane_osoby/, sidlo/…")

    # Check data exists
    subj_files = glob.glob(os.path.join(data_dir, "subjekty", "*.csv"))
    if not subj_files:
        st.error(f"V adresári `{data_dir}/subjekty/` neboli nájdené žiadne CSV. Skontroluj cestu k dátam.")
        st.info("Dáta stiahneš skriptom `main.py` z repozitára [kokes/od](https://github.com/kokes/od/tree/main/data/justice).")
        return

    # Sampling option for large datasets
    sample_option = st.sidebar.selectbox(
        "Vzorka osôb",
        ["100 %", "50 %", "25 %", "10 %"],
        index=0,
        help="Pre rýchlejšie načítanie zvoľ menšiu vzorku",
    )
    sample_frac = {"100 %": 1.0, "50 %": 0.5, "25 %": 0.25, "10 %": 0.1}[sample_option]

    # Load data
    subj = load_subjekty(data_dir)
    osoby = load_osoby(data_dir, sample_frac=sample_frac)
    sidla = load_sidla(data_dir)

    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Načítané:** {len(subj):,} subj · {len(osoby):,} osôb".replace(",", " "))

    page = st.sidebar.radio(
        "Navigácia",
        ["📊 Prehľad", "🔍 Kvalita dát", "👤 Hľadanie osôb", "🔗 Prepojenia firiem", "🧮 Pravidlá identifikácie"],
    )

    if page.startswith("📊"):
        page_overview(subj, osoby, sidla)
    elif page.startswith("🔍"):
        page_quality(subj, osoby, sidla)
    elif page.startswith("👤"):
        page_person_search(osoby, subj)
    elif page.startswith("🔗"):
        page_connections(osoby, subj)
    elif page.startswith("🧮"):
        page_identification_rules(osoby)


if __name__ == "__main__":
    main()
