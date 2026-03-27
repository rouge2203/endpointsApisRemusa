#!/usr/bin/env python3
"""
Plate-to-Parts Pipeline: Costa Rica License Plate → Vehicle Info → TecDoc Parts Catalog

Flow:
  1. Enter a Costa Rica plate number
  2. Lookup vehicle info (make, model, year, VIN, owner, etc.)
  3. Match vehicle in TecDoc catalog (VIN decode or manual browse)
  4. Browse part categories for that vehicle
  5. View all compatible parts in a category
  6. Drill into any part for specs + compatible cars
"""

import requests
import json
import sys
import os
import re
import textwrap

# ── Config ──────────────────────────────────────────────────────────────────

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
TECDOC_BASE = "https://tecdoc-catalog.p.rapidapi.com"
TECDOC_HEADERS = {
    "x-rapidapi-host": "tecdoc-catalog.p.rapidapi.com",
    "x-rapidapi-key": RAPIDAPI_KEY,
}
PLATE_API = "https://www.regcheck.org.uk/api/reg.asmx/CheckCostaRica"
PLATE_USER = "jruiz2203"
LANG_ID = 8       # Español
COUNTRY_ID = 63   # Default country filter
TYPE_ID = 1       # Passenger Car

# ── Helpers ─────────────────────────────────────────────────────────────────

class Colors:
    BOLD = "\033[1m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    DIM = "\033[2m"
    RESET = "\033[0m"

C = Colors

def clear():
    os.system("clear" if os.name == "posix" else "cls")

def header(title):
    w = 60
    print(f"\n{C.CYAN}{'═' * w}")
    print(f"  {C.BOLD}{title}{C.RESET}{C.CYAN}")
    print(f"{'═' * w}{C.RESET}\n")

def subheader(title):
    print(f"\n{C.GREEN}── {title} {'─' * max(0, 50 - len(title))}{C.RESET}\n")

def info(label, value):
    print(f"  {C.BOLD}{label:.<30}{C.RESET} {value}")

def warn(msg):
    print(f"\n  {C.YELLOW}⚠  {msg}{C.RESET}")

def error(msg):
    print(f"\n  {C.RED}✖  {msg}{C.RESET}")

def success(msg):
    print(f"\n  {C.GREEN}✔  {msg}{C.RESET}")

class UserQuit(Exception):
    """Raised when user types 'q' to quit."""
    pass

class UserNewPlate(Exception):
    """Raised when user types 'c' to go back to plate search."""
    pass

def prompt(msg, allow_empty=False):
    while True:
        val = input(f"\n{C.BOLD}  » {msg}: {C.RESET}").strip()
        if val.lower() == "q":
            raise UserQuit()
        if val.lower() == "c":
            raise UserNewPlate()
        if val or allow_empty:
            return val

def pick(items, label_fn, prompt_text="Pick a number", allow_back=True):
    """Display numbered list and let user pick. Returns (index, item) or None."""
    if not items:
        warn("No items to display.")
        return None

    per_page = 20
    page = 0
    total_pages = (len(items) - 1) // per_page + 1

    while True:
        start = page * per_page
        end = min(start + per_page, len(items))
        page_items = items[start:end]

        for i, item in enumerate(page_items):
            idx = start + i + 1
            label = label_fn(item)
            print(f"  {C.DIM}{idx:>4}{C.RESET}  {label}")

        nav = []
        if page > 0:
            nav.append("[P]rev")
        if page < total_pages - 1:
            nav.append("[N]ext")
        if allow_back:
            nav.append("[B]ack")
        nav.append("[C] nueva placa")
        nav.append("[Q] salir")
        nav.append(f"Pag {page + 1}/{total_pages} ({len(items)} total)")

        print(f"\n  {C.DIM}{' | '.join(nav)}{C.RESET}")
        choice = prompt(prompt_text).lower()

        if choice == "n" and page < total_pages - 1:
            page += 1
            continue
        if choice == "p" and page > 0:
            page -= 1
            continue
        if choice == "b" and allow_back:
            return None

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                return (idx, items[idx])
        except ValueError:
            pass
        warn("Invalid choice. Try again.")


# ── API Calls ───────────────────────────────────────────────────────────────

def tecdoc_get(path, params=None):
    url = f"{TECDOC_BASE}{path}"
    resp = requests.get(url, headers=TECDOC_HEADERS, params=params, timeout=30)
    if resp.status_code != 200 or resp.headers.get("content-type", "").startswith("text/html"):
        return None
    return resp.json()

def tecdoc_post(path, payload):
    url = f"{TECDOC_BASE}{path}"
    resp = requests.post(url, headers={**TECDOC_HEADERS, "Content-Type": "application/json"},
                         json=payload, timeout=30)
    if resp.status_code != 200 or resp.headers.get("content-type", "").startswith("text/html"):
        return None
    return resp.json()


# ── Step 1: Plate Lookup ────────────────────────────────────────────────────

def lookup_plate(plate, retries=3):
    """Call Costa Rica plate API with retries, parse XML+JSON response."""
    import xml.etree.ElementTree as ET

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(PLATE_API, params={
                "RegistrationNumber": plate,
                "username": PLATE_USER,
            }, timeout=20)

            if resp.status_code != 200:
                error(f"Attempt {attempt}/{retries}: HTTP {resp.status_code}")
                continue

            text = resp.text
            m = re.search(r"<vehicleJson>\s*(\{.*?\})\s*</vehicleJson>", text, re.DOTALL)
            if not m:
                error(f"Attempt {attempt}/{retries}: No vehicle data in response")
                continue
            return json.loads(m.group(1))

        except requests.exceptions.Timeout:
            error(f"Attempt {attempt}/{retries}: Timeout — server took too long")
        except requests.exceptions.ConnectionError:
            error(f"Attempt {attempt}/{retries}: Connection error")
        except Exception as e:
            error(f"Attempt {attempt}/{retries}: {type(e).__name__}: {e}")

    return None


# ── Step 2: Match Vehicle in TecDoc ─────────────────────────────────────────

def vin_check(vin):
    """TecDoc VIN Check — returns TecDoc-native IDs (manufacturer, model, vehicles) or None."""
    data = tecdoc_get(f"/vin/tecdoc-vin-check/{vin}")
    if not data or not isinstance(data, dict):
        return None
    inner = data.get("data", data)

    def _extract(field):
        val = inner.get(field, {})
        if isinstance(val, dict):
            return val.get("array", [])
        if isinstance(val, list):
            return val
        return []

    manufacturers = _extract("matchingManufacturers")
    models = _extract("matchingModels")
    vehicles = _extract("matchingVehicles")
    if not manufacturers:
        return None
    return {
        "manufacturers": manufacturers,
        "models": models,
        "vehicles": vehicles,
    }

def get_vehicle_info(vehicle_id):
    """Fetch full vehicle details (engine, power, fuel, body, etc.)."""
    data = tecdoc_get(
        f"/types/type-id/{TYPE_ID}/vehicle-type-details/{vehicle_id}"
        f"/lang-id/{LANG_ID}/country-filter-id/{COUNTRY_ID}"
    )
    if not data:
        return {}
    return data.get("vehicleTypeDetails", {})

def show_vehicle_info(vinfo):
    """Print all available vehicle details."""
    fields = [
        ("Fabricante", "manufacturerName"),
        ("Modelo", "modelType"),
        ("Motor", "typeEngineName"),
        ("Desde", "constructionIntervalStart"),
        ("Hasta", "constructionIntervalEnd"),
        ("Potencia (kW)", "powerKw"),
        ("Potencia (PS)", "powerPs"),
        ("Cilindrada (L)", "capacityLt"),
        ("Cilindrada (cc)", "capacityTech"),
        ("Cilindros", "numberOfCylinders"),
        ("Valvulas", "numberOfValves"),
        ("Carroceria", "bodyType"),
        ("Tipo motor", "engineType"),
        ("Transmision", "gearType"),
        ("Traccion", "driveType"),
        ("Combustible", "fuelType"),
        ("Mezcla", "fuelMixture"),
        ("Catalizador", "catalysatorType"),
        ("Frenos", "brakeSystem"),
        ("Tipo freno", "brakeType"),
        ("ABS", "abs"),
        ("ASR", "asr"),
        ("Cod. motor", "engCodes"),
    ]
    for label, key in fields:
        val = vinfo.get(key)
        if val is not None and val != "" and val != 0:
            info(label, str(val))

def get_manufacturers():
    data = tecdoc_get(f"/manufacturers/list/type-id/{TYPE_ID}")
    if not data:
        return []
    return data.get("manufacturers", [])

def get_models(manufacturer_id):
    data = tecdoc_get(
        f"/models/list/type-id/{TYPE_ID}/manufacturer-id/{manufacturer_id}"
        f"/lang-id/{LANG_ID}/country-filter-id/{COUNTRY_ID}"
    )
    if not data:
        return []
    return data.get("models", [])

def get_vehicles_for_model(model_id):
    data = tecdoc_get(
        f"/types/type-id/{TYPE_ID}/list-vehicles-id/{model_id}"
        f"/lang-id/{LANG_ID}/country-filter-id/{COUNTRY_ID}"
    )
    if not data:
        return []
    # API returns under "modelTypes" key
    vehicles = (
        data.get("modelTypes")
        or data.get("vehicles")
        or data.get("vehicleIdList")
        or []
    )
    if isinstance(data, list):
        vehicles = data
    return vehicles


def search_manufacturer(make_name, manufacturers):
    """Fuzzy match a make name to manufacturer list."""
    make_upper = make_name.upper().strip()
    # Exact match first
    for m in manufacturers:
        if m["manufacturerName"].upper() == make_upper:
            return m
    # Partial match
    matches = [m for m in manufacturers if make_upper in m["manufacturerName"].upper()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        subheader(f"Multiple matches for '{make_name}'")
        result = pick(matches, lambda m: m["manufacturerName"], "Pick manufacturer")
        if result:
            return result[1]
    return None


def search_model(model_hint, year, models):
    """Try to auto-match model from plate info."""
    hint_upper = model_hint.upper().strip().split()[0]  # First word e.g. "TUCSON"
    year = int(year) if year else 0

    candidates = []
    for m in models:
        name_upper = m["modelName"].upper()
        yr_from = int(m.get("modelYearFrom", "0")[:4]) if m.get("modelYearFrom") else 0
        yr_to = int(m.get("modelYearTo", "9999")[:4]) if m.get("modelYearTo") else 9999

        if hint_upper in name_upper:
            if yr_from <= year <= yr_to:
                candidates.append(m)

    if len(candidates) == 1:
        return candidates[0]

    # Show all matching or all models
    show = candidates if candidates else models
    if candidates:
        subheader(f"Models matching '{hint_upper}' ({year})")
    else:
        subheader("All models — pick yours")

    result = pick(
        show,
        lambda m: (
            f"{m['modelName']:40s} "
            f"{C.DIM}({(m.get('modelYearFrom') or '?')[:7]} → {(m.get('modelYearTo') or 'present')[:7]}){C.RESET}"
        ),
        "Pick model"
    )
    if result:
        return result[1]
    return None


def pick_vehicle_variant(vehicles, title="Pick your vehicle variant"):
    """Let user pick a vehicle variant, then fetch and show full details."""
    result = pick(
        vehicles,
        lambda v: (
            f"{v.get('carName', v.get('vehicleTypeDescription', v.get('typeEngineName', '?'))):55s} "
            f"{C.DIM}ID:{v.get('vehicleId', '?')}{C.RESET}"
        ),
        title,
    )
    if not result:
        return None
    vehicle = result[1]
    vid = vehicle.get("vehicleId")
    if vid:
        subheader(f"Detalles del vehiculo (ID: {vid})")
        vinfo = get_vehicle_info(vid)
        if vinfo:
            show_vehicle_info(vinfo)
        else:
            warn("No se pudo cargar detalles del vehiculo")
    return vehicle


def match_vehicle_in_tecdoc(plate_data):
    """Try VIN Check (TecDoc-native) first, fall back to manual browse."""
    vin = plate_data.get("VIN", "")
    make = plate_data.get("CarMake", {}).get("CurrentTextValue", "")
    model = plate_data.get("CarModel", {}).get("CurrentTextValue", "")
    year = plate_data.get("RegistrationYear", "")

    # ── Try VIN Check (returns TecDoc IDs directly) ──
    if vin and len(vin) == 17:
        subheader(f"VIN Check: {vin}")
        vc = vin_check(vin)
        if vc:
            mfrs = vc["manufacturers"]
            models_vc = vc["models"]
            vehicles_vc = vc["vehicles"]

            mfr_names = ", ".join(m.get("manuName", "?") for m in mfrs)
            model_names = ", ".join(m.get("modelName", "?") for m in models_vc)
            success(f"VIN Check: {mfr_names} — {model_names}")
            print(f"  {C.DIM}  Vehiculos encontrados: {len(vehicles_vc)}{C.RESET}")

            if len(vehicles_vc) == 1:
                v = vehicles_vc[0]
                success(f"Match exacto: {v.get('carName', v.get('vehicleTypeDescription', '?'))}")
                # Show full details for the single match
                vid = v.get("vehicleId")
                if vid:
                    subheader(f"Detalles del vehiculo (ID: {vid})")
                    vinfo = get_vehicle_info(vid)
                    if vinfo:
                        show_vehicle_info(vinfo)
                return v

            elif len(vehicles_vc) > 1:
                subheader("VIN encontro multiples variantes — elige la tuya")
                return pick_vehicle_variant(vehicles_vc)

            elif models_vc:
                # VIN found manufacturer+model but no exact vehicle variants
                warn("VIN encontro modelo pero no variante exacta — cargando variantes...")
                mdl = models_vc[0]
                # Show matched model info
                subheader(f"Modelo encontrado por VIN")
                for m in models_vc:
                    info("Fabricante", m.get("manuName", "?"))
                    info("Modelo", m.get("modelName", "?"))
                    info("Model ID", str(m.get("modelId", "?")))

                vehicles = get_vehicles_for_model(mdl["modelId"])
                if vehicles:
                    subheader(f"Variantes para {mdl.get('modelName', '?')}")
                    return pick_vehicle_variant(vehicles, "Elige tu variante")
        else:
            warn("VIN Check no encontro datos — buscando manualmente")

    # ── Fallback: manual manufacturer/model browse ──
    subheader("Buscando en TecDoc por fabricante/modelo")
    manufacturers = get_manufacturers()
    if not manufacturers:
        error("No se pudo cargar fabricantes")
        return None

    mfr = search_manufacturer(make, manufacturers)
    if not mfr:
        subheader("Todos los fabricantes")
        result = pick(manufacturers, lambda m: m["manufacturerName"], "Elige fabricante")
        if not result:
            return None
        mfr = result[1]

    success(f"Fabricante: {mfr['manufacturerName']} (ID: {mfr['manufacturerId']})")

    all_models = get_models(mfr["manufacturerId"])
    if not all_models:
        error("No se encontraron modelos")
        return None

    mdl = search_model(model, year, all_models)
    if not mdl:
        return None

    success(f"Modelo: {mdl['modelName']} (ID: {mdl['modelId']})")

    # Get vehicle variants
    subheader("Cargando variantes...")
    vehicles = get_vehicles_for_model(mdl["modelId"])
    if not vehicles:
        error("No se encontraron variantes")
        return None

    return pick_vehicle_variant(vehicles)


# ── Step 3: Browse Categories ───────────────────────────────────────────────

def get_categories(vehicle_id):
    data = tecdoc_get(
        f"/category/type-id/{TYPE_ID}/products-groups-variant-3/{vehicle_id}/lang-id/{LANG_ID}"
    )
    if not data:
        return {}
    return data.get("categories", {})


def browse_categories(categories, breadcrumb=""):
    """Recursive category browser. Returns (category_id, category_name) or None."""
    items = []
    for cat_id, cat_data in categories.items():
        items.append({
            "id": cat_id,
            "name": cat_data.get("text", "?"),
            "children": cat_data.get("children", {}),
        })

    items.sort(key=lambda x: x["name"])

    prefix = f"{breadcrumb} > " if breadcrumb else ""

    result = pick(
        items,
        lambda c: (
            f"{c['name']:45s} "
            f"{C.DIM}({'→ subcategories' if c['children'] else 'PARTS'}){C.RESET}"
        ),
        f"Pick category ({prefix.rstrip(' > ') or 'root'})"
    )

    if not result:
        return None

    cat = result[1]

    if cat["children"]:
        # Has subcategories — ask: go deeper or show parts at this level?
        print(f"\n  {C.BOLD}[1]{C.RESET} Browse subcategories of {cat['name']}")
        print(f"  {C.BOLD}[2]{C.RESET} Show ALL parts in {cat['name']}")
        choice = prompt("Choice (1 or 2)")
        if choice == "1":
            sub = browse_categories(cat["children"], f"{prefix}{cat['name']}")
            if sub:
                return sub
            # If user went back from subcategories, show this level's parts
            return (cat["id"], cat["name"])
        else:
            return (cat["id"], cat["name"])
    else:
        return (cat["id"], cat["name"])


# ── Step 4: List Parts ──────────────────────────────────────────────────────

def get_parts(vehicle_id, category_id):
    data = tecdoc_get(
        f"/articles/list/type-id/{TYPE_ID}/vehicle-id/{vehicle_id}"
        f"/category-id/{category_id}/lang-id/{LANG_ID}"
    )
    if not data:
        return []
    articles = data.get("articles", [])
    if not articles:
        return []
    # Deduplicate by articleId
    seen = set()
    unique = []
    for a in articles:
        aid = a.get("articleId")
        if aid and aid not in seen:
            seen.add(aid)
            unique.append(a)
    return unique


# ── Step 5: Part Details + Compatible Cars ──────────────────────────────────

def get_part_details(article_id):
    data = tecdoc_get(
        f"/articles/article-complete-details/type-id/{TYPE_ID}",
        params={
            "articleId": article_id,
            "countryFilterId": COUNTRY_ID,
            "langId": LANG_ID,
        }
    )
    return data

def get_cross_references(article_id):
    data = tecdoc_get(
        f"/artlookup/select-article-cross-references/article-id/{article_id}/lang-id/{LANG_ID}"
    )
    return data

def show_part_detail(article, vehicle_id):
    """Show full details for a part and offer sub-actions."""
    article_id = article.get("articleId")
    article_no = article.get("articleNo", "?")
    supplier = article.get("supplierName", "?")
    product = article.get("articleProductName", "?")

    while True:
        header(f"{product} — {supplier} {article_no}")

        subheader("Loading full details...")
        details = get_part_details(article_id)

        if details and details.get("article"):
            art = details["article"]

            # Basic info
            subheader("Part Info")
            info("Article ID", str(article_id))
            info("Article No", art.get("articleNo", "?"))
            info("Product", art.get("articleProductName", "?"))
            info("Supplier", art.get("supplierName", "?"))

            # Image
            img = art.get("s3image")
            if img:
                info("Image", img)

            # Specs
            specs = art.get("allSpecifications", [])
            if specs:
                subheader("Technical Specifications")
                for s in specs:
                    info(s.get("criteriaName", "?"), s.get("criteriaValue", "?"))

            # OEM numbers
            oems = art.get("oemNo", [])
            if oems:
                subheader(f"OEM Numbers ({len(oems)})")
                for o in oems:
                    print(f"    {o.get('oemBrand', '?'):15s}  {o.get('oemDisplayNo', '?')}")

            # Compatible cars
            cars = art.get("compatibleCars", [])
            if cars:
                subheader(f"Compatible Vehicles ({len(cars)})")
                # Group by model
                by_model = {}
                for car in cars:
                    key = car.get("modelName", "?")
                    by_model.setdefault(key, []).append(car)

                for model_name, model_cars in sorted(by_model.items()):
                    print(f"\n  {C.BOLD}{model_name}{C.RESET}")
                    for car in sorted(model_cars, key=lambda c: c.get("constructionIntervalStart", "")):
                        yr_start = (car.get("constructionIntervalStart") or "?")[:7]
                        yr_end = (car.get("constructionIntervalEnd") or "present")[:7]
                        engine = car.get("typeEngineName", "?")
                        vid = car.get("vehicleId", "?")
                        print(f"    {C.DIM}ID:{vid:<8}{C.RESET} {engine:45s} {yr_start} → {yr_end}")
        else:
            warn("Could not load full details.")
            info("Article ID", str(article_id))
            info("Article No", article_no)
            info("Supplier", supplier)
            info("Product", product)
            if article.get("s3image"):
                info("Image", article["s3image"])

        # Sub-actions
        print(f"\n  {C.BOLD}[1]{C.RESET} View cross-references / equivalent parts")
        print(f"  {C.BOLD}[2]{C.RESET} Pick a compatible car → browse ITS parts")
        print(f"  {C.BOLD}[B]{C.RESET} Back to parts list")

        action = prompt("Action").lower()

        if action == "1":
            subheader("Loading cross-references...")
            xref = get_cross_references(article_id)
            if xref and xref.get("articles"):
                xref_arts = xref["articles"]
                # Deduplicate
                seen = set()
                unique_xref = []
                for x in xref_arts:
                    xid = x.get("articleId") or x.get("articleNo")
                    if xid not in seen:
                        seen.add(xid)
                        unique_xref.append(x)

                subheader(f"Cross-References ({len(unique_xref)})")
                for x in unique_xref:
                    xno = x.get("articleNo", "?")
                    xsup = x.get("supplierName", "?")
                    xprod = x.get("articleProductName", "?")
                    ximg = x.get("s3image") or ""
                    print(f"    {xsup:25s} {xno:20s} {xprod}")
            else:
                warn("No cross-references found.")
            prompt("Press Enter to continue", allow_empty=True)

        elif action == "2":
            if details and details.get("article", {}).get("compatibleCars"):
                cars = details["article"]["compatibleCars"]
                result = pick(
                    cars,
                    lambda c: (
                        f"{c.get('manufacturerName', '?'):12s} {c.get('modelName', '?'):30s} "
                        f"{c.get('typeEngineName', '?'):30s} "
                        f"{C.DIM}(ID:{c.get('vehicleId', '?')}){C.RESET}"
                    ),
                    "Pick a vehicle to browse its parts"
                )
                if result:
                    new_vehicle = result[1]
                    new_vid = new_vehicle.get("vehicleId")
                    if new_vid:
                        success(
                            f"Switching to: {new_vehicle.get('manufacturerName')} "
                            f"{new_vehicle.get('modelName')} {new_vehicle.get('typeEngineName')}"
                        )
                        return ("switch_vehicle", new_vid, new_vehicle)
            else:
                warn("No compatible cars data available.")

        elif action == "b":
            return None


# ── Main Loop ───────────────────────────────────────────────────────────────

def parts_browser(vehicle_id, vehicle_desc):
    """Browse categories → parts → details for a given vehicle."""
    while True:
        header(f"Parts Catalog: {vehicle_desc}")
        subheader("Loading categories...")
        categories = get_categories(vehicle_id)

        if not categories:
            error("No categories found for this vehicle.")
            return

        cat_result = browse_categories(categories)
        if not cat_result:
            return

        cat_id, cat_name = cat_result

        subheader(f"Loading parts: {cat_name}...")
        parts = get_parts(vehicle_id, cat_id)

        if not parts:
            warn(f"No parts found in '{cat_name}'.")
            prompt("Press Enter to go back", allow_empty=True)
            continue

        while True:
            subheader(f"{cat_name} — {len(parts)} parts")
            result = pick(
                parts,
                lambda p: (
                    f"{p.get('supplierName', '?'):25s} {p.get('articleNo', '?'):20s} "
                    f"{p.get('articleProductName', '?')}"
                ),
                "Pick a part for details"
            )

            if not result:
                break  # Back to categories

            part = result[1]
            detail_result = show_part_detail(part, vehicle_id)

            if detail_result and detail_result[0] == "switch_vehicle":
                _, new_vid, new_vehicle = detail_result
                new_desc = (
                    f"{new_vehicle.get('manufacturerName', '?')} "
                    f"{new_vehicle.get('modelName', '?')} "
                    f"{new_vehicle.get('typeEngineName', '?')}"
                )
                parts_browser(new_vid, new_desc)
                return


def main():
    if not RAPIDAPI_KEY:
        error("RAPIDAPI_KEY environment variable not set!")
        error("Export it: export RAPIDAPI_KEY=your_key_here")
        sys.exit(1)

    clear()
    header("PLATE → PARTS  |  Costa Rica Vehicle Lookup + TecDoc Catalog")
    print(f"  {C.DIM}En cualquier momento: [Q] salir  [C] nueva placa{C.RESET}")

    while True:
        try:
            plate = input(f"\n{C.BOLD}  » Numero de placa (o 'q' para salir): {C.RESET}").strip()
            if not plate:
                continue
            if plate.lower() == "q":
                print(f"\n{C.DIM}  Adios!{C.RESET}\n")
                break

            # ── Step 1: Plate lookup ──
            subheader(f"Buscando placa: {plate}")
            plate_data = lookup_plate(plate)

            if not plate_data:
                error("Placa no encontrada o error de API. Intenta de nuevo.")
                continue

            # Show plate info
            subheader("Registro Vehicular (Costa Rica)")
            desc = plate_data.get("Description", "?")
            make = plate_data.get("CarMake", {}).get("CurrentTextValue", "?")
            model = plate_data.get("CarModel", {}).get("CurrentTextValue", "?")
            year = plate_data.get("RegistrationYear", "?")

            info("Descripcion", desc)
            info("Marca", make)
            info("Modelo", model)
            info("Ano", year)
            info("Motor", plate_data.get("EngineSize", {}).get("CurrentTextValue", "?"))
            info("Carroceria", plate_data.get("Body", "?"))
            info("Combustible", plate_data.get("Fuel", "?"))
            info("Traccion", plate_data.get("WheelPlan", "?"))
            info("Color", plate_data.get("Colour", "?"))
            info("VIN", plate_data.get("VIN", "?"))
            info("Cod. Motor", plate_data.get("EngineCode", "?"))
            info("Propietario", plate_data.get("owner", "?"))

            img = plate_data.get("ImageUrl")
            if img:
                info("Imagen", img)

            # ── Step 2: Match in TecDoc ──
            subheader("Buscando vehiculo en catalogo TecDoc...")
            vehicle = match_vehicle_in_tecdoc(plate_data)

            if not vehicle:
                warn("No se pudo encontrar el vehiculo. Intenta otra placa.")
                continue

            vid = vehicle.get("vehicleId")
            vehicle_desc = (
                f"{vehicle.get('manufacturerName', make)} "
                f"{vehicle.get('modelName', model)} "
                f"{vehicle.get('typeEngineName', '')}"
            ).strip()

            success(f"Seleccionado: {vehicle_desc} (Vehicle ID: {vid})")

            # ── Steps 3-5: Browse parts ──
            parts_browser(vid, vehicle_desc)

        except UserNewPlate:
            print(f"\n  {C.DIM}Volviendo a busqueda de placa...{C.RESET}")
            continue
        except UserQuit:
            print(f"\n{C.DIM}  Adios!{C.RESET}\n")
            break
        except KeyboardInterrupt:
            print(f"\n{C.DIM}  Adios!{C.RESET}\n")
            break


if __name__ == "__main__":
    main()
