"""Sources embarquées pour présenter le projet sans Internet."""
import json
from pathlib import Path

from .domain import Car, model_match

DATA = Path(__file__).resolve().parent.parent / "donnees"
NOTICE = DATA / "notice-clio.json"


def cars():
    return [Car(**row) for row in json.loads((DATA / "annonces.json").read_text())]


def notices(query):
    return [NOTICE] if model_match("Renault Clio V", query.model) is True else []
