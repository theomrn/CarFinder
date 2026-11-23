from pathlib import Path
from hashlib import sha256

import streamlit as st
import requests

from comparateur.agents import probe, run
from comparateur.selections import recent
from comparateur.vehicles import MODELS
from comparateur.domain import DEFAULT_WEIGHTS, Query, alternatives, model_match
from statistics import median

st.set_page_config(page_title="Carnet auto · Comparateur local", layout="wide")
st.html("""
<style>
[data-testid="stMainBlockContainer"] {max-width: 72rem; padding-top: 3.6rem;}
h1 {letter-spacing: -.055em; font-weight: 720;}
h2, h3 {letter-spacing: -.035em;}
[data-testid="stForm"], [class*="st-key-offre_"] {
    background: white; border-radius: 1rem; padding: clamp(1rem, 3vw, 2rem);
    border: 1px solid #d8e2de; box-shadow: 0 3px 16px #123c2e08;
}
[data-testid="stTabs"] [role="tablist"] {gap: clamp(.5rem, 3vw, 2rem);}
[data-testid="stMetricValue"] {font-variant-numeric: tabular-nums;}
@media (max-width: 640px) {
    [data-testid="stMainBlockContainer"] {padding: 3rem 1rem 2rem;}
    [data-testid="stTabs"] [role="tablist"] {overflow-x: auto;}
}
</style>
""")
st.title("Carnet auto")
st.write("Comparez les annonces d’occasion et préparez vos questions avant la visite.")

@st.cache_resource(ttl=900, show_spinner=False)
def check_model(name):
    probe(name)
    return True

recherche, carnet, architecture = st.tabs(["Recherche", "Carnet de visites", "Architecture"])

with st.sidebar:
    st.header("Réglages")
    mode = st.radio("Données", ["Catalogues en direct", "Soutenance locale", "Démonstration"])
    demo = mode == "Démonstration"
    names = ["llama3.1:latest","llama3.2:latest","ministral-3:3b"]
    rehearsal = mode == "Soutenance locale"
    if rehearsal:
        st.info("Les trois agents utilisent Ollama, sept fiches fictives et un extrait du manuel Renault enregistré sur ce Mac.")
    ready = demo
    if not demo:
        try:
            response = requests.get("http://127.0.0.1:11434/api/tags",timeout=3)
            response.raise_for_status()
            names = [x["name"] for x in response.json()["models"]]
            names.sort(key=lambda n:n!="llama3.1:latest")
        except requests.RequestException:
            st.warning("Ollama est inaccessible. Lancez l’application Ollama sur le Mac.")
    name = st.selectbox("Modèle Ollama",names or ["llama3.1:latest"],disabled=demo)
    if not demo:
        try:
            with st.spinner("Test de l’appel d’outil…"):
                ready = check_model(name)
            st.caption("Ollama local · appel d’outil vérifié")
        except Exception as exc:
            st.error(f"Diagnostic Ollama · {exc}")
            if st.button("Retester"):
                st.rerun()
    else:
        st.info("Sept annonces fictives de Clio V. La simulation fonctionne hors connexion.")

with recherche:
    st.subheader("Quel véhicule cherchez-vous ?")
    make_col, model_col = st.columns(2)
    local = demo or rehearsal
    brand = make_col.selectbox(
        "Marque", ["Renault"] if local else list(MODELS),
        index=0 if local else None, placeholder="Choisir une marque", key=f"marque_{local}",
    )
    models = ("Clio V",) if local else MODELS.get(brand, ())
    model = model_col.selectbox(
        "Modèle et génération", models, index=0 if local else None,
        placeholder="Choisir un modèle", disabled=brand is None, key=f"modele_{local}_{brand}",
    )

with recherche, st.form("search"):
    a,b = st.columns(2)
    budget = a.number_input("Budget maximal (€)",min_value=1,value=None,placeholder="Sans limite")
    km = b.number_input("Kilométrage maximal",min_value=0,value=None,placeholder="Sans limite")
    with st.expander("Affiner la recherche"):
        c,d = st.columns(2)
        first = c.number_input("Année minimale",min_value=1886,value=None,placeholder="Toutes")
        last = d.number_input("Année maximale",min_value=1886,value=None,placeholder="Toutes")
        a,b=st.columns(2)
        fuel=a.selectbox("Énergie",["Toutes","Essence","Diesel","Hybride","Électrique","GPL"])
        box=b.selectbox("Boîte",["Toutes","Manuelle","Automatique"])
        wants=st.text_input("Finition et équipements souhaités",placeholder="Ex. Zen, régulateur de vitesse")
    with st.expander("Personnaliser la notation"):
        st.caption("Augmentez le poids des critères qui comptent pour vous. Les poids sont ramenés à 100 % au lancement de la recherche. Un poids de 0 désactive le critère.")
        weights = {label: st.slider(label, 0, 100, default, step=5, key=f"poids_{label}")
                   for label, default in DEFAULT_WEIGHTS.items()}
    submit=st.form_submit_button("Rechercher et comparer",type="primary",disabled=not ready or model is None)
if submit:
    if not any(weights.values()):
        st.error("Donnez un poids positif à au moins un critère de notation.")
    elif not brand or not model or (first and last and first>last):
        st.error("Renseignez une marque et un modèle et vérifiez l’ordre des années.")
    else:
        q=Query(model.strip(),budget,km,first,last,fuel if fuel!="Toutes" else "",
                box if box!="Toutes" else "",tuple(dict.fromkeys(w.strip() for w in wants.split(",") if w.strip())), brand=brand.strip(), weights=weights)
        st.session_state.pop("last_report",None)
        with recherche, st.status("Recherche en cours…",expanded=True) as status:
            # LangGraph exécute les outils sur des threads. La file garde Streamlit sur le thread UI.
            from concurrent.futures import ThreadPoolExecutor
            from queue import Empty, Queue
            events=Queue()
            try:
                with ThreadPoolExecutor(max_workers=1) as worker:
                    job=worker.submit(run,q,name,demo,events.put,rehearsal=rehearsal)
                    while not job.done():
                        try:
                            status.write(events.get(timeout=0.25))
                        except Empty:
                            pass
                    report=job.result()
                while not events.empty():
                    status.write(events.get_nowait())
                st.session_state.last_report=(mode,q,report)
                status.update(label="Rapport disponible",state="complete",expanded=False)
            except Exception as e:
                status.update(label="Recherche interrompue",state="error")
                st.error(str(e))

def fmt(n):
    return f"{n:,.0f}".replace(","," ") if n is not None else "inconnu"

def link(c):
    if c.url.startswith("https://"):
        st.link_button("Voir l’annonce sur "+c.source,c.url)
    else:
        st.caption("Fiche fictive "+c.url.split(":")[-1])

with recherche:
    if "last_report" in st.session_state and st.session_state.last_report[0]==mode:
        _,q,r=st.session_state.last_report
        st.divider()
        st.header(f"Rapport d’achat · {q.vehicle}")
        if demo or rehearsal:
            st.info("Démonstration · données fictives du 15 janvier 2026.")
        if "Spoticar · accès au catalogue refusé (HTTP 403)" in r.logs:
            st.warning("Spoticar a refusé la consultation de son catalogue. Les résultats affichés proviennent des sources accessibles.")
        st.subheader("Fiche modèle")
        st.markdown("#### Motorisations disponibles")
        versions={}
        for car in r.cars:
            if model_match(car.model,q.vehicle) is True:
                versions.setdefault((car.model,car.engine,car.fuel,car.gearbox),car)
        for (model_name,engine,energy,gearbox),c in versions.items():
            label=" · ".join(filter(None,[model_name,engine or "Moteur à confirmer",energy,gearbox]))
            if c.url.startswith("https://"):
                st.markdown(f"{label} · [Fiche consultée]({c.url})")
            else:
                st.write(label)
        def display_facts(categories):
            facts = [(category, quote, url) for category, quote, url in r.facts if category in categories]
            for category, quote, url in facts:
                st.write(quote)
                st.link_button("Consulter la source", url)
            return bool(facts)

        documented = display_facts({"Motorisations"})
        if not versions and not documented:
            st.caption("Aucune motorisation confirmée dans les sources consultées.")
        st.markdown("#### Problèmes connus et rappels")
        if not display_facts({"Fiabilité", "Rappels"}):
            st.caption("Les sources consultées ne permettent pas de confirmer un problème pour cette recherche.")
        st.markdown("#### Points de vigilance avant achat")
        st.markdown(
            "- Vérifier l’historique d’entretien et les échéances propres à la motorisation.\n"
            "- Contrôler les campagnes de rappel avec le numéro de série auprès du constructeur.\n"
            "- Lors de l’essai, contrôler le démarrage à froid, les voyants et le fonctionnement de la boîte."
        )
        display_facts({"Équipements", "Vigilance"})
        st.divider()
        st.subheader("Rapport des annonces")
        if r.summary:
            st.write(r.summary)
        st.subheader("Estimation automatique du marché")
        market_prices, _ = alternatives(q, r.cars)
        if len(market_prices) >= 5:
            st.metric("Prix médian des annonces compatibles hors budget", f"{fmt(median(market_prices))} €")
            st.caption(f"Calculé sur {len(market_prices)} annonces vérifiées correspondant aux autres critères.")
        else:
            st.caption(f"{len(market_prices)} annonce(s) compatible(s) hors budget. Il en faut au moins cinq pour une estimation globale.")
        st.subheader("Prix observés")
        st.write("Comparaison par version, à deux années et 25 000 km près, sur les fiches vérifiées avant filtrage du budget.")
        if r.ranked:
            st.table([{"Véhicule":f"{i+1}. {v['car'].model} · {v['car'].engine}",
                       "Prix affiché":fmt(v["car"].price)+" €","Autres comparables":v["count"],
                       "Kilométrage":fmt(v["car"].km)+" km" if v["car"].km is not None else "Non renseigné",
                       "Consultation":v["car"].day} for i,v in enumerate(r.ranked)])
        st.subheader("Annonces classées")
        if not r.ranked:
            st.info("Aucune annonce vérifiée ne satisfait tous les critères." if r.cars or demo or any("0 annonce" in m for m in r.logs)
                    else "Collecte indisponible. La disponibilité des annonces reste inconnue.")
            prices, closest = alternatives(q, r.cars)
            if prices:
                st.metric("Budget minimum observé pour vos autres critères", f"{fmt(prices[0])} €")
                st.caption(f"{len(prices)} annonce(s) vérifiée(s) · médiane {fmt(median(prices))} €")
            else:
                st.caption("Budget indéterminé avec ces critères et les annonces vérifiées.")
            if closest:
                car, differences = closest
                with st.container(border=True):
                    st.markdown("#### Annonce la plus proche")
                    st.write(f"{car.model} · {fmt(car.price)} € · {fmt(car.km)} km · {car.year or 'Année inconnue'}")
                    st.caption(" · ".join(filter(None, [car.engine, car.fuel, car.gearbox, car.place])))
                    values = {"budget": f"{fmt(car.price - q.budget)} € au-dessus du budget" if q.budget is not None else "",
                              "kilométrage": f"{fmt(car.km - q.km)} km au-dessus du plafond" if q.km is not None and car.km is not None else "",
                              "année minimale": f"année {car.year}, minimum demandé {q.first}",
                              "année maximale": f"année {car.year}, maximum demandé {q.last}",
                              "énergie": f"{car.fuel} au lieu de {q.fuel}",
                              "boîte": f"{car.gearbox} au lieu de {q.gearbox}"}
                    st.write("Écarts avec la recherche · " + ", ".join(values[label] for label in differences))
                    link(car)
        for i,row in enumerate(r.ranked):
            c=row["car"]
            with st.container(border=True, key=f"offre_{i}"):
                st.subheader(f"{i+1}. {c.model} {c.trim}")
                price, score_col = st.columns(2)
                price.metric("Prix affiché", f"{fmt(c.price)} €")
                score_col.metric("Note", f"{row['score']:.1f}/10")
                st.write(f"{c.engine or 'Moteur à confirmer'} · {fmt(c.km)} km · {c.year or 'Millésime inconnu'} · {c.place}")
                st.write(" · ".join(filter(None,[c.fuel,c.gearbox,c.warranty,c.service])))
                fallback=f"À {fmt(c.price)} €, cette annonce indique {fmt(c.km)} km. Demandez les factures du dernier entretien."
                st.write(r.comments.get(i,fallback))
                with st.expander("Comprendre la note et vérifier les équipements"):
                    if row.get("reference"):
                        st.write(f"Référence de prix · {fmt(row['reference'])} € sur {row['reference_count']} autre(s) annonce(s).")
                    else:
                        st.caption("Prix relatif neutre · aucun comparable exploitable.")
                    st.write("Équipements reconnus · " + (", ".join(row.get("features", [])) or "aucun renseigné"))
                    if row.get("penalty"):
                        st.warning("Accident déclaré dans la fiche · −2,5 points sur la note finale.")
                    else:
                        st.caption("Historique accident · " + ("déclaré sans accident" if getattr(c, "accident", None) is False else "non renseigné"))
                    for label,(v,w) in row["parts"].items():
                        st.write(f"{label} · {v}/10 · poids {w:.1f} %")
                    st.write("Préférences confirmées · "+(", ".join(row["confirmed"]) or "aucune"))
                    st.write(c.equipment or "Équipements non renseignés")
                    st.caption("Consultation · "+c.day)
                link(c)
                if not (demo or rehearsal):
                    with st.expander("Comparer avec la cote L’Argus"):
                        st.link_button("Consulter le calculateur L’Argus", "https://www.largus.fr/cote/")
                        st.caption("Choisissez la version, l’année et le kilométrage de cette annonce dans le calculateur, puis reportez le montant ici.")
                        cote = st.number_input(
                            "Cote L’Argus relevée (€)", min_value=1, value=None, step=1,
                            key="argus_" + sha256(c.url.encode()).hexdigest(),
                        )
                        if cote is not None:
                            difference = c.price - cote
                            st.metric("Écart entre l’annonce et la cote", f"{difference:+,} €".replace(",", " "))
        if r.uncertain:
            with st.expander(f"À vérifier · {len(r.uncertain)} annonce(s)"):
                for c,missing in r.uncertain:
                    st.write(f"{c.model} · Information à confirmer : {', '.join(missing)}")
                    link(c)
        with st.expander("Délégations et sources consultées"):
            for msg in r.logs:
                st.text(msg)


with carnet:
    st.subheader("Carnet de visites")
    st.caption("Les 20 dernières sélections enregistrées par l’agent coordinateur sur ce Mac.")
    saved_selections = recent()
    if not saved_selections:
        st.info("Votre première sélection apparaîtra ici après une recherche en direct ou en mode soutenance locale.")
    for saved in saved_selections:
        records=saved["listings"]
        with st.expander(f"{saved['model']} · {saved['mode']} · {len(records)} annonce(s) · {saved['id'][:8]}"):
            criteria=saved["criteria"]
            st.caption(f"Enregistré le {saved['created']} UTC · Budget maximal : {fmt(criteria['budget'])} €")
            if not records:
                st.write("Aucune annonce ne répondait aux critères.")
            for item in records:
                c=item["car"]
                st.write(f"{c['model']} · {c['place']} · {fmt(c['price'])} € · {item['score']}/10")
                if c["url"].startswith("https://"):
                    st.markdown(f"[Ouvrir la fiche]({c['url']})")

with architecture:
    st.subheader("Architecture des trois agents")
    diagram = Path(__file__).resolve().parent / "docs" / "architecture.dot"
    st.graphviz_chart(diagram.read_text(), width="stretch")
    st.caption("Les trois agents partagent le modèle Ollama sélectionné. Le backend renvoie les événements et le rapport au navigateur.")
