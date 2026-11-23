"""Lecture des catalogues et de leurs fiches publiques."""
import json
import re
from urllib.parse import urlencode, urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup
import requests

from .domain import Car, contains, norm

RENEW = "https://fr.renew.auto"
SPOT = "https://www.spoticar.fr"
BRANDS = "renault peugeot citroen dacia opel fiat ford bmw audi toyota volkswagen mercedes seat skoda hyundai kia nissan volvo mini".split()
FAMILIES = {"clio":"renault", "megane":"renault", "captur":"renault", "208":"peugeot",
            "308":"peugeot", "3008":"peugeot", "c3":"citroen", "sandero":"dacia", "golf":"volkswagen"}


def doc(url):
    response = requests.get(url, timeout=(4, 10))
    response.raise_for_status()
    return BeautifulSoup(response.content, "html.parser", from_encoding=response.encoding if response.encoding != "ISO-8859-1" else None)


def txt(s, selector):
    node = s.select_one(selector)
    return node.get_text(" ", strip=True) if node else ""


def number(s):
    value = re.fullmatch(r"\s*([\d\s.,]+)\s*(?:€|km)?\s*", str(s), re.I)
    if value:
        try:
            return int(float("".join(value[1].split()).replace(",", ".")))
        except ValueError:
            pass


def renew_detail(s, url):
    model = txt(s, "h1 .UCIMarqueModel__title")
    if not model or re.search(r"(?:ce véhicule|cette annonce) (?:est vendu|a été vendu|a été retirée|n.est plus disponible)",s.get_text(" ",strip=True),re.I):
        raise ValueError("fiche retirée ou format inconnu")
    fields = {}
    for node in s.select(".UCICharacteristics__label"):
        if node.strong:
            fields[norm(node.find(string=True, recursive=False))] = node.strong.get_text(strip=True)
    year = re.search(r"\d{4}$", fields.get("date de 1ere immatriculation",""))
    title = s.title.get_text(strip=True) if s.title else ""
    return Car(model, url, "renew", number(txt(s,".UCIVehicleDetailsCard__header .UCIVehicleCardPrice__taxLabel")
                                           or txt(s,".UCIVehicleCardPrice__taxLabel")),
               number(fields.get("kilometrage")), int(year[0]) if year else None,
               fields.get("modele",""), fields.get("type de boite",""), fields.get("energie",""),
               title.split("d'occasion à ")[-1] if "d'occasion à " in title else "",
               txt(s,"h1 .UCIMarqueModel__subTitle").split(" - ")[0],
               ", ".join(x.get_text(strip=True) for x in s.select(".UCIEquipments__listItem")),
               txt(s,".UCIVehicleDetailsCard__warranty .UCIWarranty__duration"),
               identity=txt(s,".UCIVehicleDetailsCard__registrationNumber"))


def spot_detail(s, url):
    def walk(data):
        if isinstance(data, list):
            for item in data:
                yield from walk(item)
        if isinstance(data, dict):
            yield data
            if "@graph" in data:
                yield from walk(data["@graph"])
    for script in s.select('script[type="application/ld+json"]'):
        try:
            nodes = list(walk(json.loads(script.get_text())))
        except ValueError:
            continue
        for node in nodes:
            if node.get("@type") not in ("Car","Vehicle","Product"):
                continue
            offers = node.get("offers", {})
            if isinstance(offers,list):
                offers = next(iter(offers),{})
            if not isinstance(offers,dict) or any(k in str(offers.get("availability")) for k in ("SoldOut","OutOfStock","Discontinued")):
                raise ValueError("fiche retirée")
            def label(key):
                v = node.get(key,"")
                return str(v.get("name","")) if isinstance(v,dict) else str(v)
            name = label("model") or label("name")
            if not name:
                continue
            km = node.get("mileageFromOdometer", {})
            year = re.match(r"\d{4}",label("dateVehicleFirstRegistered") or label("vehicleModelDate"))
            return Car(name,url,"Spoticar",number(offers.get("price")) if offers.get("priceCurrency")=="EUR"
                       and not offers.get("priceSpecification") else None,
                       number(km.get("value")) if isinstance(km,dict) and km.get("unitCode")=="KMT" else None,
                       int(year[0]) if year else None,label("vehicleEngine"),label("vehicleTransmission"),
                       label("fuelType"),trim=label("vehicleConfiguration"),identity=label("vehicleIdentificationNumber"))
    raise ValueError("format de fiche non reconnu")


def catalog(source, model):
    words = norm(model).split()
    brand = words.pop(0) if words[0] in BRANDS else FAMILIES.get(words[0], "")
    family = " ".join(words)
    if not family:
        raise ValueError("préciser le modèle")
    if source == "renew":
        catalog_model = family.upper()
        if catalog_model.startswith("CLIO "):
            numerals = dict(zip("123456", "I II III IV V VI".split()))
            catalog_model = "CLIO " + numerals.get(catalog_model[5:],catalog_model[5:])
        url = RENEW + "/achat-vehicules-occasions.html?" + urlencode({"model.label.raw":catalog_model})
        selector = 'a[href*="details.html?productId="]'
        parser = renew_detail
    else:
        if not brand:
            raise ValueError("marque nécessaire pour ce catalogue")
        slug = re.sub(r"\s+(?:i{1,3}|iv|v|vi{1,3}|[1-9])$", "",family).replace(" ","-")
        url = f"{SPOT}/voitures-occasion/{brand}/{slug}"
        selector = 'a[href*="/voitures-occasion/"][href]'
        parser = spot_detail
    page = doc(url)
    pages = [page]
    if source=="renew":
        variants = [x.get("name","") for x in page.select('input[id^="model.label.raw_terms-"]')
                    if contains(x.get("name"),family) and norm(x.get("name"))!=norm(family)]
        for variant in variants[:3]:
            variant_url = RENEW+"/achat-vehicules-occasions.html?"+urlencode({"model.label.raw":variant})
            pages.append(doc(variant_url))
    # Alterner les générations pour les demandes portant sur toute une famille.
    from itertools import zip_longest
    groups = [[urljoin(url,a["href"]) for a in p.select(selector)] for p in pages]
    links = list(dict.fromkeys(u for row in zip_longest(*groups) for u in row if u))
    links = [u for u in links if urlparse(u).netloc == urlparse(url).netloc and
             (source=="renew" or re.search(r"\d{6,}/?$",urlparse(u).path))]
    if not links:
        if re.search(r"(?:0 véhicule|aucun véhicule|aucun résultat)",page.get_text(" ",strip=True),re.I):
            return [], "0 annonce", url
        raise ValueError("aucune fiche identifiable dans le catalogue")
    def read(link):
        try:
            return parser(doc(link),link)
        except (requests.RequestException,ValueError):
            return None
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(read, links[:24]))
    cars = [c for c in results if c]
    if not cars:
        raise ValueError("aucune fiche individuelle vérifiable")
    return cars, f"{len(cars)} fiches vérifiées sur {len(results)} consultées", url
