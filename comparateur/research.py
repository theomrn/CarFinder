"""Documents publics utilisés comme preuves, citations conservées avec leur URL."""
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import re

from ddgs import DDGS
from .domain import norm
from .sources import doc

DOMAINS = ("user-manual.renault.com","renault.fr","peugeot.fr","citroen.fr","dacia.fr","volkswagen.fr","toyota.fr",
           "rappel.conso.gouv.fr","caradisiac.com","largus.fr","auto-moto.com","quechoisir.org",
           "automobile-magazine.fr","bmw.fr","ford.fr","opel.fr","audi.fr")


def documents(q, cars):
    engines = list(dict.fromkeys(c.engine for c in cars if c.engine))[:4]
    searches = [f"{q.model} {q.fuel} motorisations équipements fiche technique",
                f"{q.model} {' '.join(engines[:2])} fiabilité problèmes années rappel"]
    urls = []
    errors = []
    for search in searches:
        try:
            for hit in DDGS(timeout=6).text(search, region="fr-fr", max_results=8, backend="duckduckgo,brave,yahoo"):
                u = hit.get("href","")
                host = urlparse(u).hostname or ""
                if u.startswith("https://") and any(host==d or host.endswith("."+d) for d in DOMAINS):
                    urls.append(u)
        except Exception as e:
            errors.append(f"Recherche Web indisponible ({type(e).__name__})")
    if norm(q.model) in ("clio 5","renault clio 5"):
        urls[:0] = ["https://www.user-manual.renault.com/fr/content/clio/technical-specifications/information-about-vehicle/identification-moteur",
                    "https://www.caradisiac.com/maxi-fiche-fiabilite-renault-clio-5-loin-d-etre-irreprochable-208286.htm"]
    return list(dict.fromkeys(urls))[:6], errors


def read_pages(urls, q):
    def read(url):
        try:
            s = doc(url)
            title = s.title.get_text(" ",strip=True) if s.title else ""
            title += " · " + " ".join(h.get_text(" ",strip=True) for h in s.select("h1")[:3])
            content = s.select_one("article") or s.select_one("main") or s
            terms = [w for w in norm(q.model).split() if len(w)>1]
            blocks = [" ".join(p.stripped_strings) for p in content.select("p, li, tr")]
            relevant = [p[:650] for p in blocks if 45<len(p)<1200 and
                        any(w in norm(title+" "+p).split() for w in terms)]
            rows = [" ".join(t.stripped_strings) for t in s.select("tr") if "TCe" in t.get_text()]
            period = re.search(r"\d{2}/\d{2}/\d{4} à \d{2}/\d{2}/\d{4}",s.get_text(" ",strip=True))
            if period:
                rows = [r+" (notice du "+period[0].replace(" à "," au ")+")" for r in rows]
            relevant = rows + relevant
            if relevant:
                return dict(url=url,title=title,excerpts=relevant[:10])
        except Exception:
            pass
    with ThreadPoolExecutor(max_workers=3) as pool:
        return [d for d in pool.map(read,urls) if d]
