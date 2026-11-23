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


DEFAULT_WEIGHTS = {"Prix relatif": 40, "Kilométrage": 25, "Équipements annoncés": 15,
                   "Entretien documenté": 15, "Garantie annoncée": 5}


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
    brand: str = ""
    weights: dict = field(default_factory=lambda: DEFAULT_WEIGHTS.copy())

    @property
    def vehicle(self):
        if not self.brand or contains(self.model, self.brand):
            return self.model
        return f"{self.brand} {self.model}"


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
    accident: bool | None = None


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


def criteria(q, c):
    checks = {"modèle": model_match(c.model, q.vehicle)}
    for label, value, limit, lower in [
        ("budget", c.price, q.budget, False), ("kilométrage", c.km, q.km, False),
        ("année minimale", c.year, q.first, True), ("année maximale", c.year, q.last, False)
    ]:
        if limit is not None:
            checks[label] = None if value is None else (value >= limit if lower else value <= limit)
    for label, value, target in [("énergie", c.fuel, q.fuel), ("boîte", c.gearbox, q.gearbox)]:
        if target:
            checks[label] = contains(value, target) if value else None
    return checks


def alternatives(q, cars):
    """Budget observé à critères constants et annonce vérifiée la plus proche."""
    candidates = []
    for car in unique(cars):
        checks = criteria(q, car)
        if checks.pop("modèle") is not True or car.price is None or None in checks.values():
            continue
        differences = [label for label, matches in checks.items() if not matches]
        candidates.append((car, differences))

    exact = sorted(car.price for car, differences in candidates
                   if all(label == "budget" for label in differences))
    close = min(candidates, key=lambda item: (
        len([label for label in item[1] if label != "budget"]),
        len(item[1]),
        max(0, item[0].km - q.km) if q.km is not None else 0,
        max(0, (q.first or 0) - (item[0].year or 0),
            (item[0].year or 0) - (q.last or item[0].year or 0)),
        item[0].price,
    ), default=None)
    return exact, close


FEATURES = {
    "Climatisation": r"climatisation|climatiseur", "Régulateur": r"regulateur|cruise control",
    "Stationnement assisté": r"radar de recul|aide au (?:parking|stationnement)|park assist",
    "Caméra": r"camera", "Navigation": r"navigation|gps", "Bluetooth": r"bluetooth",
    "Intégration smartphone": r"carplay|android auto", "Sièges chauffants": r"sieges? chauffant",
    "Toit ouvrant ou panoramique": r"toit (?:ouvrant|panoramique)",
    "Accès sans clé": r"sans cle|keyless", "Éclairage LED": r"phares? led|full led",
    "Surveillance des angles morts": r"angle[s]? mort",
}


def clamp(value):
    return max(0, min(10, value))


def rank(q, cars):
    fleet = unique(cars)
    ranked, uncertain = [], []
    for c in fleet:
        checks = criteria(q, c)
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
        peers = [p for p in fleet if p is not c and norm(p.model) == norm(c.model)
                 and c.year and p.year and abs(c.year-p.year) <= 2
                 and c.fuel and norm(p.fuel) == norm(c.fuel)
                 and c.gearbox and norm(p.gearbox).removeprefix("boite ") == norm(c.gearbox).removeprefix("boite ")]
        peer_prices = [p.price for p in peers if p.price and c.km is not None
                       and p.km is not None and abs(c.km-p.km) <= 40000]
        reference = mid or (median(peer_prices) if peer_prices else None)
        price_score = clamp(5 + 20 * (1 - c.price/reference)) if reference else 5
        distances = [p.km for p in peers if p.km is not None]
        km_score = 5
        if c.km is not None:
            km_score = clamp(10 - c.km/22000)
            if distances:
                km_score = (km_score + clamp(5 + (median(distances)-c.km)/8000))/2
        equipment = norm(c.equipment)
        features = [name for name, pattern in FEATURES.items() if re.search(pattern, equipment)]
        equipment_score = min(10, 2 + 1.2*len(features)) if equipment else 4
        confirmed = [w for w in q.wants if contains(c.trim + " " + c.equipment, w)]
        values = {"Prix relatif": price_score, "Kilométrage": km_score,
                  "Équipements annoncés": equipment_score, "Entretien documenté": 10 if c.service else 4,
                  "Garantie annoncée": 10 if c.warranty else 4}
        weights = q.weights.copy()
        if q.wants:
            preference_weight = weights["Équipements annoncés"] * 2 / 3
            weights["Équipements annoncés"] -= preference_weight
            weights["Préférences confirmées"] = preference_weight
            values["Préférences confirmées"] = 10 * len(confirmed) / len(q.wants)
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("Choisissez au moins un critère de notation.")
        parts = {label: (value, 100 * weights[label] / total) for label, value in values.items()}
        penalty = 2.5 if c.accident is True else 0
        score = round(clamp(sum(value*weight for value,weight in parts.values())/100 - penalty), 1)
        ranked.append(dict(car=c, score=score, median=mid, count=len(prices), confirmed=confirmed,
                           reference=reference, reference_count=len(prices) if mid else len(peer_prices),
                           features=features, penalty=penalty,
                           parts={k:(round(v,1),w) for k,(v,w) in parts.items()}))
    return sorted(ranked, key=lambda r:(-r["score"], r["car"].price))[:10], uncertain
