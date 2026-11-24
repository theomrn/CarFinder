import unittest

from comparateur.intent import validated
from comparateur.vehicles import MODELS


class Interpretation(unittest.TestCase):
    def test_units_and_catalog(self):
        brand, model, fields, issues = validated(
            "Clio 5 à partir de 2020, 13k€ maximum et moins de 80 000 km",
            MODELS, {"first": 2020},
        )
        self.assertEqual((brand, model, fields.first, fields.budget, fields.km, issues),
                         ("Renault", "Clio V", 2020, 13000, 79999, []))

    def test_ambiguity_and_geographic_distance(self):
        self.assertTrue(validated("Clio ou Captur", MODELS, {})[-1])
        brand, model, fields, issues = validated("Toyota hybride dans un rayon de 30 km", MODELS,
                                                  {"fuel":"Hybride", "km":30})
        self.assertEqual((brand, model, fields.fuel, fields.km), ("Toyota", None, "Hybride", None))
        self.assertTrue(issues)

    def test_conflict_and_unknown(self):
        self.assertTrue(validated("Clio 5 à 10k€ maximum ou 12k€ maximum", MODELS, {})[-1])
        self.assertTrue(validated("Une Ferrari Roma", MODELS, {})[-1])

    def test_new_phrase_resets_filters_and_matches_manual_ranking(self):
        from comparateur.demo import cars
        from comparateur.domain import Query, rank
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            validated("une Clio", MODELS, {"fuel": "inconnu"})
        brand, model, fields, issues = validated(
            "Clio 5 essence manuelle, maximum 13000 euros et moins de 80 000 km avec régulateur",
            MODELS, {"fuel": "Essence", "gearbox": "Manuelle", "wants": ["régulateur"]},
        )
        self.assertFalse(issues)
        parsed = Query(model, fields.budget, fields.km, fuel=fields.fuel, gearbox=fields.gearbox,
                       wants=tuple(fields.wants), brand=brand)
        manual = Query("Clio V", 13000, 79999, fuel="Essence", gearbox="Manuelle",
                       wants=("régulateur",), brand="Renault")
        self.assertEqual(rank(parsed, cars()), rank(manual, cars()))
        _, _, second, _ = validated("Toyota Yaris peu kilométrée", MODELS, {})
        self.assertIsNone(second.km)
        self.assertIsNone(second.budget)

    def test_description_without_model_respects_brand_and_catalog(self):
        payload = {"candidates":[
            {"brand":"Toyota","model":"Yaris","reason":"Format citadin"},
            {"brand":"Honda","model":"Jazz","reason":"Compacte"},
            {"brand":"Toyota","model":"Fictive","reason":"Compacte"}]}
        brand, model, fields, issues = validated("Une petite Toyota pour la ville à 12 500 euros", MODELS, payload)
        self.assertEqual((brand, model, issues), ("Toyota", None, []))
        self.assertEqual([c.model for c in fields.candidates], ["Yaris"])
        self.assertEqual(fields.budget, 12500)
