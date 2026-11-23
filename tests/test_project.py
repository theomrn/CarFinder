from dataclasses import replace
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup
from streamlit.testing.v1 import AppTest
from comparateur import demo
from comparateur.agents import run
from comparateur.domain import Query, rank, model_match
from comparateur.sources import renew_detail, spot_detail


class Ranking(unittest.TestCase):
    def test_market_before_budget_and_dedup(self):
        fleet=demo.cars()
        ranked,_=rank(Query("Clio V",12000,wants=("Radar de recul",)),fleet+[fleet[1]])
        r=ranked[0]
        self.assertEqual((len(ranked),r["count"],r["median"]),(1,6,13300))
        self.assertEqual(r["confirmed"],["Radar de recul"])
        self.assertEqual(sum(w for _,w in r["parts"].values()),100)

    def test_missing_and_wrong_generation(self):
        c=demo.cars()[0]
        ranked,unchecked=rank(Query("Clio V",13000,80000,gearbox="manuelle"),
            [replace(c,gearbox=""),replace(c,url="demo:x",model="Renault Clio IV")])
        self.assertFalse(ranked)
        self.assertEqual(unchecked[0][1],["boîte"])
        self.assertIsNone(model_match("Renault Clio","Clio V"))
        self.assertFalse(model_match("Clio 4","Clio V"))

    def test_unknown_engine_and_small_sample(self):
        fleet=demo.cars()
        r,_=rank(Query("Clio V"),[replace(fleet[0],engine=""),*fleet[1:4]])
        self.assertTrue(all(x["median"] is None for x in r))
        self.assertEqual([x["count"] for x in r if not x["car"].engine],[0])

    def test_no_match(self):
        report=run(Query("Clio V",budget=100),offline=True)
        self.assertFalse(report.ranked)
        self.assertEqual(len(report.cars),7)


class Parsing(unittest.TestCase):
    def test_monthly_only(self):
        s=BeautifulSoup('<h1><b class="UCIMarqueModel__title">Clio V</b></h1>'
                        '<span>109 € / mois</span>',"html.parser")
        self.assertIsNone(renew_detail(s,"test").price)

    def test_expired(self):
        s=BeautifulSoup('<script type="application/ld+json">{"@type":"Car","model":"Clio",'
                        '"offers":{"availability":"https://schema.org/SoldOut"}}</script>',"html.parser")
        with self.assertRaises(ValueError):
            spot_detail(s,"test")
        with self.assertRaises(ValueError):
            renew_detail(BeautifulSoup("<h1>Annonce expirée</h1>","html.parser"),"test")

    def test_vehicle_schema(self):
        s=BeautifulSoup('<script type="application/ld+json">{"@type":"Car","model":"Clio V",'
                        '"offers":{"price":12000,"priceCurrency":"EUR"}}</script>',"html.parser")
        self.assertEqual(spot_detail(s,"test").price,12000)


class Interface(unittest.TestCase):
    def test_demo(self):
        with patch("comparateur.agents.probe"), patch("requests.get",side_effect=__import__("requests").ConnectionError):
            app=AppTest.from_file("../app.py",default_timeout=45).run()
            app.radio[0].set_value("Démonstration").run()
            app.number_input[0].set_value(13000)
            app.number_input[1].set_value(80000)
            app.button[0].click().run()
            self.assertFalse(list(app.exception))
            self.assertEqual(len(app.session_state.last_report[2].ranked),3)

class Documentation(unittest.TestCase):
    def test_problem_specific_to_engine_and_generation(self):
        from comparateur.agents import problem_applies
        page={"title":"Renault Clio 5"}
        q=Query("Clio V",fuel="Essence")
        self.assertFalse(problem_applies(page,"Clio IV 1.0 TCe 90 en 2021",q,demo.cars()))
        self.assertFalse(problem_applies(page,"Clio V 1.5 dCi en 2021",q,demo.cars()))
        self.assertTrue(problem_applies(page,"Clio V 1.0 TCe 90 en 2021",q,demo.cars()))

class Carnet(unittest.TestCase):
    def test_sauvegarde_relue_et_idempotente(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from comparateur.selections import recent, save
        with TemporaryDirectory() as directory:
            db=Path(directory)/"carnet.sqlite"
            query=Query("Clio V",budget=13000)
            ranked,_=rank(query,demo.cars())
            for _ in range(2):
                save("une-recherche","Soutenance locale",query,ranked,db)
            rows=recent(db)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["criteria"]["budget"],13000)
            self.assertEqual([x["car"]["place"] for x in rows[0]["listings"]],["Tours","Lille","Lyon"])
            save("recherche-vide","Soutenance locale",Query("Clio V",budget=100),[],db)
            self.assertEqual(recent(db)[0]["listings"],[])

class Marques(unittest.TestCase):
    def test_marque_libre_et_modele_homonyme(self):
        q = Query("Model 3", brand="Tesla")
        car = replace(demo.cars()[0], model="Tesla Model 3")
        other = replace(car, model="Autre Model 3", url="demo:autre")
        ranked, _ = rank(q, [other, car])
        self.assertEqual([row["car"] for row in ranked], [car])

    def test_chemins_catalogues_marque_composee(self):
        from comparateur.sources import catalog
        page = BeautifulSoup("<p>Aucun véhicule</p>", "html.parser")
        with patch("comparateur.sources.doc", return_value=page):
            _, _, url = catalog("Spoticar", "Discovery Sport", "Land Rover")
            self.assertTrue(url.endswith("/land-rover/discovery-sport"))
            _, _, url = catalog("renew", "Discovery Sport", "Land Rover")
            self.assertIn("brand.label.raw=LAND+ROVER", url)
            self.assertIn("model.label.raw=DISCOVERY+SPORT", url)

class Alternatives(unittest.TestCase):
    def test_budget_avec_meme_vehicule_et_memes_criteres(self):
        from comparateur.domain import alternatives
        fleet = demo.cars()
        prices, closest = alternatives(Query("Clio V", budget=11000, km=80000), fleet)
        self.assertEqual(prices[0], 11900)
        self.assertEqual(closest[1], ["budget"])

    def test_budget_indetermine_et_ecart_de_kilometrage(self):
        from comparateur.domain import alternatives
        fleet = demo.cars()
        prices, closest = alternatives(Query("Clio V", budget=15000, km=45000), fleet)
        self.assertFalse(prices)
        self.assertEqual(closest, (fleet[0], ["kilométrage"]))
        self.assertEqual(alternatives(Query("Yaris", brand="Toyota"), fleet), ([], None))

class Scoring(unittest.TestCase):
    def test_each_signal_changes_score(self):
        base = replace(demo.cars()[0], price=12000, km=60000, equipment="", warranty="", service="")
        peers = [replace(base, url=f"peer:{i}") for i in range(5)]

        def score(**changes):
            target = replace(base, **changes)
            rows, _ = rank(Query("Clio V"), [target, *peers])
            return next(r["score"] for r in rows if r["car"] is target)

        for changes in ({"price":10500}, {"km":40000}, {"service":"Carnet présenté"},
                        {"equipment":"Caméra, navigation, Bluetooth, radar de recul"}):
            self.assertGreater(score(**changes), score())
        self.assertLess(score(price=14000), score())
        self.assertLess(score(km=80000), score())
        self.assertAlmostEqual(score()-score(accident=True), 2.5)
