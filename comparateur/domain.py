"""Critères, observations et classement reproductible."""
from dataclasses import dataclass, field
from datetime import date
import re
from statistics import median
from unicodedata import normalize


def norm(value):
    plain = normalize("NFKD", str(value or "").lower()).encode("ascii", "ignore").decode()
    tokens = re.findall(r"[a-z0-9]+", plain)
    roman = dict(zip("i ii iii iv v vi vii viii ix x".split(), map(str, range(1,11))))
    return " ".join(roman.get(t,t) for t in tokens)


def contains(text, phrase):
    return f" {norm(phrase)} " in f" {norm(text)} "


@dataclass
class Query:
    model: str
    budget: int | None = None
    km: int | None = None
    first: int | None = None
    last: int | None = None
    fuel: str = ""
    gearbox: str = ""
    wants: tuple = ()


@dataclass
class Car:
    model: str
    url: str
    source: str
    price: int | None = None
    km: int | None = None
    year: int | None = None
    engine: str = ""
    gearbox: str = ""
    fuel: str = ""
    place: str = ""
    trim: str = ""
    equipment: str = ""
    warranty: str = ""
    service: str = ""
    identity: str = ""
    day: str = field(default_factory=lambda: date.today().isoformat())


def unique(cars):
    seen = set()
    result = []
    for c in cars:
        keys = {("url", c.url)}
        if c.identity:
            keys.add(("vehicle", norm(c.identity)))
        if keys.isdisjoint(seen):
            result.append(c)
        seen.update(keys)
    return result


def generation(model):
    match = re.search(r"\b(i{1,3}|iv|v|vi{1,3}|ix|x|[1-9])\b", norm(model))
    return match.group() if match else ""


def model_match(model, desired):
    if contains(model, desired):
        return True
    family = re.sub(r"\s+(?:i{1,3}|iv|v|vi{1,3}|ix|x|[1-9])$", "", norm(desired))
    if contains(model, family) and not generation(model):
        return None
    return False


def rank(q, cars):
    fleet = unique(cars)
    ranked, uncertain = [], []
    for c in fleet:
        checks = {"modèle": model_match(c.model, q.model)}
        for label, value, limit, lower in [
            ("budget", c.price, q.budget, False), ("kilométrage", c.km, q.km, False),
            ("année minimale", c.year, q.first, True), ("année maximale", c.year, q.last, False)
        ]:
            if limit is not None:
                checks[label] = None if value is None else (value >= limit if lower else value <= limit)
        for label, value, target in [("énergie", c.fuel, q.fuel), ("boîte", c.gearbox, q.gearbox)]:
            if target:
                checks[label] = contains(value, target) if value else None
        if False in checks.values():
            continue
        missing = [k for k, v in checks.items() if v is None]
        if missing or c.price is None:
            uncertain.append((c, missing or ["prix comptant"]))
            continue
        prices = [p.price for p in fleet if p is not c and p.price and generation(c.model)
                  and c.engine and c.gearbox and (norm(p.model), norm(p.engine), norm(p.gearbox))
                  == (norm(c.model), norm(c.engine), norm(c.gearbox))
                  and c.year and p.year and abs(c.year-p.year) <= 2
                  and c.km is not None and p.km is not None and abs(c.km-p.km) <= 25000]
        mid = median(prices) if len(prices) >= 5 else None
        parts = {}
        if mid:
            parts["Prix"] = (max(0, min(10, 5 + 25 * (1 - c.price / mid))), 50)
        confirmed = [w for w in q.wants if contains(c.trim + " " + c.equipment, w)]
        if q.wants:
            parts["Préférences confirmées"] = (10 * len(confirmed) / len(q.wants), 30)
        parts["Justificatifs annoncés"] = (5 * (bool(c.warranty) + bool(c.service)), 20)
        total = sum(w for _, w in parts.values())
        score = round(sum(v*w for v,w in parts.values()) / total, 1)
        ranked.append(dict(car=c, score=score, median=mid, count=len(prices), confirmed=confirmed,
                           parts={k:(round(v,1),round(100*w/total)) for k,(v,w) in parts.items()}))
    return sorted(ranked, key=lambda r:(-r["score"], r["car"].price))[:10], uncertain
