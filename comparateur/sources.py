"""Lecture des catalogues et de leurs fiches publiques."""
import json
import re
from urllib.parse import urlencode, urljoin, urlparse
from unicodedata import normalize
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup
import requests

from .domain import Car, contains, norm

RENEW = "https://fr.renew.auto"
SCOUT = "https://www.autoscout24.fr"
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
            make = label("brand") or label("manufacturer")
            if make and not contains(name, make):
                name = f"{make} {name}"
            km = node.get("mileageFromOdometer", {})
            year = re.match(r"\d{4}",label("dateVehicleFirstRegistered") or label("vehicleModelDate"))
            return Car(name,url,"Spoticar",number(offers.get("price")) if offers.get("priceCurrency")=="EUR"
                       and not offers.get("priceSpecification") else None,
                       number(km.get("value")) if isinstance(km,dict) and km.get("unitCode")=="KMT" else None,
                       int(year[0]) if year else None,label("vehicleEngine"),label("vehicleTransmission"),
                       label("fuelType"),trim=label("vehicleConfiguration"),identity=label("vehicleIdentificationNumber"))
    raise ValueError("format de fiche non reconnu")


def slug(text):
    plain = normalize("NFKD", text.casefold()).encode("ascii", "ignore").decode()
    return "-".join(re.findall(r"[a-z0-9]+", plain))


def scout_props(page):
    data = page.select_one("#__NEXT_DATA__")
    return json.loads(data.get_text())["props"]["pageProps"] if data else {}


def scout_detail(page, url):
    detail = scout_props(page).get("listingDetails", {})
    vehicle = detail.get("vehicle", {})
    location = detail.get("location", {})
    if not vehicle.get("make") or not vehicle.get("model") or location.get("countryCode") != "FR":
        raise ValueError("fiche française indisponible")
    if detail.get("price", {}).get("isConditionalPrice"):
        raise ValueError("prix soumis à condition")
    for script in page.select('script[type="application/ld+json"]'):
        try:
            offer = json.loads(script.get_text()).get("offers", {})
        except (ValueError, AttributeError):
            continue
        if (offer.get("priceCurrency") == "EUR" and str(offer.get("availability", "")).endswith("InStock")
                and urlparse(offer.get("url", "")).path == urlparse(url).path):
            registration = re.match(r"\d{4}", vehicle.get("firstRegistrationDateRaw") or "")
            return Car(
                model=f"{vehicle['make']} {vehicle['model']}", url=url, source="AutoScout24",
                price=number(offer.get("price")), km=number(vehicle.get("mileageInKmRaw")),
                year=int(registration[0]) if registration else None,
                engine=vehicle.get("modelVersionInput") or "",
                gearbox=vehicle.get("transmissionType") or "",
                fuel=next((engine.get("fuelType", "") for engine in offer.get("itemOffered", {}).get("vehicleEngine", [])), ""),
                equipment=", ".join(item["id"]["formatted"] for item in
                    vehicle.get("rawData", {}).get("equipment", {}).get("as24", [])
                    if item.get("id", {}).get("formatted")),
                service="Historique d’entretien complet déclaré" if vehicle.get("hasFullServiceHistory") is True else "",
                accident=vehicle.get("hadAccident"),
                place=location.get("city") or "", identity=vehicle.get("licensePlate") or "",
            )
    raise ValueError("prix comptant ou disponibilité non confirmé")


def catalog(source, model, brand=""):
    family = model.strip()
    if brand:
        # Le formulaire accepte aussi le nom complet collé dans le champ modèle.
        prefix = re.match(re.escape(brand) + r"\s+", family, re.I)
        if prefix:
            family = family[prefix.end():]
    else:
        words = family.split()
        if words and norm(words[0]) in BRANDS:
            brand = words.pop(0)
            family = " ".join(words)
        elif words:
            brand = FAMILIES.get(norm(words[0]), "")
    filters = {"brand.label.raw": brand.upper()} if brand else {}
    if not family:
        raise ValueError("préciser le modèle")
    if source == "renew":
        catalog_model = family.upper()
        if catalog_model.startswith("CLIO "):
            numerals = dict(zip("123456", "I II III IV V VI".split()))
            catalog_model = "CLIO " + numerals.get(catalog_model[5:],catalog_model[5:])
        url = RENEW + "/achat-vehicules-occasions.html?" + urlencode({**filters, "model.label.raw":catalog_model})
        selector = 'a[href*="details.html?productId="]'
        parser = renew_detail
    elif source == "AutoScout24":
        if not brand:
            raise ValueError("marque nécessaire pour ce catalogue")
        family_slug = re.sub(r"\s+(?:ii|iii|iv|v|vi|vii|viii)$", "", family, flags=re.I)
        url = f"{SCOUT}/lst/{slug(brand)}/{slug(family_slug)}?cy=F&atype=C&ustate=U"
        selector = 'a[href^="/offres/"]'
        parser = scout_detail
    else:
        if not brand:
            raise ValueError("marque nécessaire pour ce catalogue")
        family_slug = re.sub(r"\s+(?:ii|iii|iv|v|vi|vii|viii)$", "", family, flags=re.I)
        url = f"{SPOT}/voitures-occasion/{slug(brand)}/{slug(family_slug)}"
        selector = 'a[href*="/voitures-occasion/"], a[href*="/acheter-voiture-occasion/"]'
        parser = spot_detail
    page = doc(url)
    pages = [page]
    if source=="renew":
        variants = [x.get("name","") for x in page.select('input[id^="model.label.raw_terms-"]')
                    if contains(x.get("name"),family) and norm(x.get("name"))!=norm(family)]
        for variant in variants[:3]:
            variant_url = RENEW+"/achat-vehicules-occasions.html?"+urlencode({**filters, "model.label.raw":variant})
            pages.append(doc(variant_url))
    # Alterner les générations pour les demandes portant sur toute une famille.
    from itertools import zip_longest
    groups = [[urljoin(url,a["href"]) for a in p.select(selector)] for p in pages]
    links = list(dict.fromkeys(u for row in zip_longest(*groups) for u in row if u))
    if source == "AutoScout24":
        props = scout_props(page)
        if props.get("numberOfResults") == 0:
            return [], "0 annonce", url
        links.extend(urljoin(url, row.get("url", "")) for row in props.get("listings", []))
    links = [u for u in dict.fromkeys(links) if urlparse(u).netloc == urlparse(url).netloc and
             (source=="renew" or (source=="AutoScout24" and urlparse(u).path.startswith("/offres/"))
              or (source=="Spoticar" and re.search(r"\d{6,}/?$",urlparse(u).path)))]
    if not links:
        if re.search(r"(?:0 véhicule|aucun véhicule|aucun résultat)",page.get_text(" ",strip=True),re.I):
            return [], "0 annonce", url
        raise ValueError("aucune fiche identifiable dans le catalogue")
    def read(link):
        try:
            return parser(doc(link),link)
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
            return None
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(read, links[:24]))
    cars = [c for c in results if c]
    if not cars:
        raise ValueError("aucune fiche individuelle vérifiable")
    return cars, f"{len(cars)} fiches vérifiées sur {len(results)} consultées", url
