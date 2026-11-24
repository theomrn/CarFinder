"""Conversion d'une demande française en filtres du formulaire."""
import json
import re
import unicodedata

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from .agents import itinerary, local_model
from .domain import contains
from .vehicles import MODELS


class Candidate(BaseModel):
    brand: str
    model: str
    reason: str = Field(min_length=1)


class Shortlist(BaseModel):
    candidates: list[Candidate] = Field(max_length=3)


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    budget: int | None = Field(default=None, ge=1, strict=True)
    km: int | None = Field(default=None, ge=0, strict=True)
    first: int | None = Field(default=None, ge=1886, strict=True)
    last: int | None = Field(default=None, ge=1886, strict=True)
    fuel: Literal["Essence", "Diesel", "Hybride", "Électrique", "GPL"] | None = None
    gearbox: Literal["Manuelle", "Automatique"] | None = None
    wants: list[str] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


def vehicles_in(phrase, catalog):
    # Un montant ou un millésime isolé peut aussi être un nom de modèle (500, 2008).
    phrase = re.sub(r"\b\d+(?:[ .\u202f]\d{3})*(?:,\d+)?\s*k?\s*(?:€|euros?\b|km\b|kilomètres?\b)", " ", phrase, flags=re.I)
    phrase = re.sub(r"\b(?:depuis|après|avant|à partir de|de l’année)\s+(?:19|20)\d{2}\b", " ", phrase, flags=re.I)
    brands = [b for b in catalog if contains(phrase, b)]
    matches = [(b, m) for b in brands or catalog for m in catalog[b] if contains(phrase, m)]
    return brands, [(b, m) for b, m in matches if not any(
        b == other and m != longer and contains(longer, m) for other, longer in matches)]


def validated(phrase, catalog, payload):
    fields = Filters.model_validate(payload)
    brands, matches = vehicles_in(phrase, catalog)
    issues = list(fields.issues)
    brand = brands[0] if len(brands) == 1 else None
    model = None
    if len(matches) == 1 and len(brands) <= 1:
        brand, model = matches[0]
        fields.candidates = []
    elif not matches and fields.candidates and len(brands) <= 1:
        allowed = {(b.casefold(), m.casefold()): (b, m) for b in catalog for m in catalog[b]
                   if not brand or b == brand}
        selected = {}
        for candidate in fields.candidates:
            pair = allowed.get((candidate.brand.casefold(), candidate.model.casefold()))
            if pair:
                selected[pair] = Candidate(brand=pair[0], model=pair[1], reason=candidate.reason)
        fields.candidates = list(selected.values())[:3]
        if not fields.candidates:
            issues.append("Aucun modèle proposé ne figure dans le catalogue disponible.")
    else:
        issues.append("Sélectionnez un seul modèle disponible dans le catalogue.")
    plain = unicodedata.normalize("NFKD", phrase.casefold().replace("€", " euros ")).encode("ascii", "ignore").decode()
    geographic = bool(re.search(r"\b(?:rayon|autour de|a proximite|pres de)\b|km de [a-z]", plain))
    if geographic:
        issues.append("La recherche géographique n’est pas disponible. Vérifiez les filtres.")
    for key, unit in [("budget", r"euros?\b|eur\b"), ("km", r"km\b|kilometres?\b")]:
        if key == "km" and geographic:
            fields.km = None
            continue
        limits = []
        for match in re.finditer(r"(\d+(?:[ .]\d{3})*(?:,\d+)?)[ ]*(k)?[ ]*(?:"+unit+r")", plain):
            raw = match[1].replace(" ", "").replace(".", "").replace(",", ".")
            amount = int(float(raw) * (1000 if match[2] else 1))
            prefix = plain[:match.start()].rstrip()
            if re.search(r"(plus de|au moins|a partir de)$", prefix):
                issues.append("Le formulaire accepte uniquement un plafond pour le budget et le kilométrage.")
                continue
            limits.append(amount - int(bool(re.search(r"(moins de|inferieur a|<)$", prefix))))
        if len(set(limits)) > 1:
            issues.append("Précisez un seul plafond pour " + key + ".")
        elif limits:
            setattr(fields, key, limits[0])
        elif getattr(fields, key) is not None:
            if re.search(r"budget" if key == "budget" else r"kilom[eé]trage", phrase, re.I) and re.search(r"\d", phrase):
                issues.append("Confirmez la limite de " + ("budget en euros." if key == "budget" else "kilométrage en km."))
            setattr(fields, key, None)
    years = set(re.findall(r"\b(?:19|20)\d{2}\b", plain))
    for key in ("first", "last"):
        year = getattr(fields, key)
        if year is not None and str(year) not in years:
            setattr(fields, key, None)
            if years:
                issues.append("Précisez les années souhaitées.")
    if (fields.first and fields.last and fields.first > fields.last) or (
        fields.budget is not None and fields.budget < 1) or (fields.km is not None and fields.km < 0):
        raise ValueError("Les limites indiquées sont incompatibles.")
    return brand, model, fields, issues


def understand(phrase, name, rehearsal=False):
    catalog = {"Renault": ("Clio V",)} if rehearsal else MODELS
    context = []
    def prompt():
        return (
            "Extrais les critères explicites de cette phrase française. Retourne uniquement un objet JSON "
            "avec budget, km (plafonds entiers), first, last (années), fuel (Essence, Diesel, Hybride, "
            "Électrique ou GPL), gearbox (Manuelle ou Automatique), wants (liste des équipements), "
            "issues (liste des contradictions ou exigences impossibles à représenter, comme un rayon géographique). "
            "Omettre les champs absents. Ne pas inventer de seuil pour une préférence vague. "
            "Ignore les questions de choix de modèle : elles sont traitées séparément. "
            "N’ajoute aucun carburant, boîte ou équipement par défaut. "
            f"Résultat du catalogue : {context}. Demande : {phrase}"
        )

    # Conserver le résultat de l’outil dans le contexte de rédaction du dernier tour.
    @tool
    def catalogue() -> str:
        """Consulte les véhicules disponibles pour cette demande."""
        brands, matches = vehicles_in(phrase, catalog)
        result = json.dumps({"marques": brands, "modeles": matches}, ensure_ascii=False)
        context.append(result)
        return result

    parser_model = local_model(name).model_copy(update={"format": Filters.model_json_schema()})
    agent = create_agent(parser_model, tools=[catalogue],
                         middleware=[itinerary([("catalogue", {})], prompt)])
    result = agent.invoke({"messages":[HumanMessage(phrase)]}, {"recursion_limit": 6})
    payload = json.loads(result["messages"][-1].content)
    brands, matches = vehicles_in(phrase, catalog)
    if not matches and len(brands) <= 1:
        choices = {b: catalog[b] for b in brands or catalog}
        selector = local_model(name).model_copy(update={"format": Shortlist.model_json_schema()})
        answer = selector.invoke(
            "Tu conseilles un acheteur automobile. Choisis jusqu’à trois modèles adaptés à son usage "
            "dans le catalogue suivant, en variant les marques si possible. Fournis pour chaque "
            "choix brand et model EXACTEMENT comme dans le catalogue et reason en français. "
            "Si la demande désigne explicitement une voiture absente du catalogue, retourne une liste vide. "
            "Ne promets aucun équipement ni prix. Catalogue : " + json.dumps(choices, ensure_ascii=False)
            + "\nDemande : " + phrase
        )
        payload["candidates"] = json.loads(answer.content)["candidates"]
        if payload["candidates"]:
            payload["issues"] = [issue for issue in payload.get("issues", [])
                                 if not re.search(r"modèle|marque", issue, re.I)]
    else:
        payload["candidates"] = []
    if not re.search(r"essence|diesel|gazole|hybride|[ée]lectri|gpl", phrase, re.I):
        payload["fuel"] = None
    if not re.search(r"manuel|automatique|bo[iî]te auto|bva|bvm", phrase, re.I):
        payload["gearbox"] = None
    return validated(phrase, catalog, payload)
