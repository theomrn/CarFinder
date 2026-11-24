"""Recherche d'annonces par usage dans une sélection bornée de modèles."""
from dataclasses import dataclass, replace
from uuid import uuid4

from . import demo, selections, sources
from .domain import rank


@dataclass
class Suggestions:
    ranked: list
    notices: list
    receipt: str


def discover(query, candidates, rehearsal=False, progress=lambda msg: None, database=selections.DATABASE):
    rows, notices = [], []
    for candidate in candidates:
        q = replace(query, model=candidate.model, brand=candidate.brand)
        progress(f"Recherche · {q.vehicle}")
        cars = []
        if rehearsal:
            cars = demo.cars()
        else:
            for source in ("renew", "AutoScout24", "Spoticar"):
                try:
                    found, status, _ = sources.catalog(source, q.model, q.brand)
                    cars.extend(found)
                    progress(f"{q.vehicle} · {source} · {status}")
                except Exception as error:
                    notices.append(f"{q.vehicle} · {source} indisponible ({type(error).__name__})")
        ranked, _ = rank(q, cars)
        # Réserver de la place aux autres modèles dans la sélection finale.
        rows.extend(dict(row, reason=candidate.reason) for row in ranked[:3])
    rows.sort(key=lambda row: (-row["score"], row["car"].price))
    seen = set()
    distinct = []
    for row in rows:
        car = row["car"]
        if car.url not in seen and (not car.identity or car.identity not in seen):
            distinct.append(row)
            seen.update((car.url, car.identity))
    receipt = uuid4().hex
    selections.save(receipt, "Soutenance locale" if rehearsal else "Catalogues en direct",
                    query, distinct, database)
    return Suggestions(distinct, notices, receipt[:8])
