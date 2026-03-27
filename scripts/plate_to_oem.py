#!/usr/bin/env python3
"""
Plate-to-OEM Pipeline: Costa Rica License Plate → OEM Parts Catalog (Parts-Catalogs API)

Flow:
  1. Enter a Costa Rica plate number
  2. Lookup vehicle info (make, model, year, VIN, owner, etc.)
  3. VIN lookup in Parts-Catalogs → exact car with criteria, options, engine info
  4. Browse part groups (with diagram images)
  5. View OEM parts in a group (with positions on diagram)
  6. Search parts by name within a catalog

Advantages over TecDoc:
  - OEM part numbers (original manufacturer)
  - Diagram images with part positions
  - Factory option codes from VIN
  - Rich car description (engine code, transmission, production date)
"""

import requests
import json
import sys
import os
import re

# ── Config ──────────────────────────────────────────────────────────────────

PC_BASE = "https://api.parts-catalogs.com/v1"
PC_KEY = os.environ.get("AUTOPARTSCATALOG_KEY", "")
PC_HEADERS = {
    "Authorization": PC_KEY,
    "Accept": "application/json",
    "Accept-Language": "es",  # Translates part names/descriptions on some catalogs (e.g. Mercedes). Group/category names always come in English from OEM data — API limitation.
}
PLATE_API = "https://www.regcheck.org.uk/api/reg.asmx/CheckCostaRica"
PLATE_USER = "jruiz2203"

# ── Helpers ─────────────────────────────────────────────────────────────────

class Colors:
    BOLD = "\033[1m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    DIM = "\033[2m"
    MAGENTA = "\033[95m"
    RESET = "\033[0m"

C = Colors


def clear():
    os.system("clear" if os.name == "posix" else "cls")


def header(title):
    w = 70
    print(f"\n{C.CYAN}{'═' * w}")
    print(f"  {C.BOLD}{title}{C.RESET}{C.CYAN}")
    print(f"{'═' * w}{C.RESET}\n")


def subheader(title):
    print(f"\n{C.GREEN}── {title} {'─' * max(0, 55 - len(title))}{C.RESET}\n")


def info(label, value):
    if value and str(value).strip() and str(value).strip() != "?":
        print(f"  {C.BOLD}{label:.<30}{C.RESET} {value}")


def warn(msg):
    print(f"\n  {C.YELLOW}⚠  {msg}{C.RESET}")


def error(msg):
    print(f"\n  {C.RED}✖  {msg}{C.RESET}")


def success(msg):
    print(f"\n  {C.GREEN}✔  {msg}{C.RESET}")


class UserQuit(Exception):
    pass


class UserNewPlate(Exception):
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


def pick(items, label_fn, prompt_text="Elige un numero", allow_back=True):
    """Display numbered list with pagination. Returns (index, item) or None."""
    if not items:
        warn("No hay elementos.")
        return None

    per_page = 20
    page = 0
    total_pages = (len(items) - 1) // per_page + 1

    while True:
        start = page * per_page
        end = min(start + per_page, len(items))

        for i, item in enumerate(items[start:end]):
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
        warn("Opcion invalida.")


# ── API Calls ───────────────────────────────────────────────────────────────

def pc_get(path, params=None):
    """GET request to Parts-Catalogs API."""
    url = f"{PC_BASE}{path}"
    try:
        resp = requests.get(url, headers=PC_HEADERS, params=params, timeout=30)
        if resp.status_code == 404:
            return None
        if resp.status_code == 403:
            error(f"Acceso denegado (403) — verifica API key y IP")
            return None
        if resp.status_code != 200:
            error(f"HTTP {resp.status_code}: {resp.text[:100]}")
            return None
        return resp.json()
    except requests.exceptions.Timeout:
        error("Timeout — servidor tardo demasiado")
        return None
    except Exception as e:
        error(f"{type(e).__name__}: {e}")
        return None


# ── Step 1: Plate Lookup ────────────────────────────────────────────────────

def lookup_plate(plate, retries=3):
    """Call Costa Rica plate API with retries."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(PLATE_API, params={
                "RegistrationNumber": plate,
                "username": PLATE_USER,
            }, timeout=20)

            if resp.status_code != 200:
                error(f"Intento {attempt}/{retries}: HTTP {resp.status_code}")
                continue

            text = resp.text
            m = re.search(r"<vehicleJson>\s*(\{.*?\})\s*</vehicleJson>", text, re.DOTALL)
            if not m:
                error(f"Intento {attempt}/{retries}: Sin datos del vehiculo")
                continue
            return json.loads(m.group(1))

        except requests.exceptions.Timeout:
            error(f"Intento {attempt}/{retries}: Timeout")
        except requests.exceptions.ConnectionError:
            error(f"Intento {attempt}/{retries}: Error de conexion")
        except Exception as e:
            error(f"Intento {attempt}/{retries}: {type(e).__name__}: {e}")

    return None


# ── Step 2: VIN Lookup in Parts-Catalogs ────────────────────────────────────

def vin_lookup(vin, catalogs=None):
    """Search car by VIN. Returns list of CarInfo matches."""
    params = {"q": vin}
    if catalogs:
        params["catalogs"] = catalogs
    data = pc_get("/car/info", params=params)
    if not data or not isinstance(data, list):
        return []
    return data


def show_car_info(car):
    """Display full car info from VIN lookup."""
    info("Titulo", car.get("title"))
    info("Catalogo", f"{car.get('brand', '?')} ({car.get('catalogId', '?')})")
    info("Modelo", car.get("modelName"))

    # Parse description for rich details
    desc = car.get("description", "")
    if desc:
        for line in desc.split("\n"):
            line = line.strip().rstrip(";")
            if ":" in line:
                k, v = line.split(":", 1)
                info(k.strip(), v.strip())
            elif line:
                info("Info", line)

    # Show parameters
    params = car.get("parameters", [])
    if params:
        for p in sorted(params, key=lambda x: x.get("sortOrder", 999)):
            key = p.get("name") or p.get("key", "?")
            val = p.get("value", "?")
            if val and val != "Not specified":
                info(key, val)

    info("VIN", car.get("vin"))
    info("Frame", car.get("frame"))
    info("Criteria", car.get("criteria", "")[:60] + "..." if len(car.get("criteria", "")) > 60 else car.get("criteria"))

    # Option codes summary
    opts = car.get("optionCodes", [])
    if opts:
        print(f"\n  {C.DIM}  Codigos de fabrica: {len(opts)} opciones{C.RESET}")


def show_option_codes(car):
    """Display factory option codes.
    API only returns 'code' and 'description' per option — no extra fields available."""
    opts = car.get("optionCodes", [])
    if not opts:
        warn("Sin codigos de opciones de fabrica.")
        return
    subheader(f"Codigos de Fabrica ({len(opts)})")
    for o in opts:
        code = o.get("code", "?")
        desc = o.get("description", "?")
        print(f"    {C.BOLD}{code:12s}{C.RESET} {desc}")


# ── Step 3: Match Vehicle ───────────────────────────────────────────────────

def get_catalogs():
    """Get all available catalogs."""
    data = pc_get("/catalogs/")
    if not data or not isinstance(data, list):
        return []
    return data


def get_models(catalog_id):
    """Get models for a catalog."""
    data = pc_get(f"/catalogs/{catalog_id}/models/")
    if not data or not isinstance(data, list):
        return []
    return data


def get_cars(catalog_id, model_id, page=0):
    """Get car list for a model."""
    data = pc_get(f"/catalogs/{catalog_id}/cars2/", params={
        "modelId": model_id,
        "page": page,
    })
    if not data or not isinstance(data, list):
        return []
    return data


def match_vehicle(plate_data):
    """Try VIN lookup first, fall back to manual catalog browse."""
    vin = plate_data.get("VIN", "")
    make = plate_data.get("CarMake", {}).get("CurrentTextValue", "").upper()

    # ── Try VIN lookup ──
    if vin and len(vin) == 17:
        subheader(f"VIN Lookup: {vin}")

        # Try with specific catalog hint first
        catalog_hint = None
        brand_map = {
            "HYUNDAI": "hyundai", "KIA": "kia", "TOYOTA": "toyota",
            "NISSAN": "nissan", "MERCEDES": "mercedes", "MERCEDES BENZ": "mercedes",
            "BMW": "bmw", "CHEVROLET": "chevrolet", "FORD": "ford",
            "MITSUBISHI": "mitsubishi", "HONDA": "honda", "MAZDA": "mazda",
            "SUZUKI": "suzuki", "SUBARU": "subaru", "VOLKSWAGEN": "vw",
            "VW": "vw", "AUDI": "audi", "FIAT": "fiat", "JEEP": "jeep",
            "DODGE": "dodge", "CHRYSLER": "chrysler", "PEUGEOT": "peugeot",
            "RENAULT": "renault", "VOLVO": "volvo", "LEXUS": "lexus",
            "INFINITI": "infiniti", "ACURA": "acura", "CADILLAC": "cadillac",
            "GMC": "gmc", "PONTIAC": "pontiac", "PORSCHE": "porsche",
            "LAND ROVER": "land-rover", "JAGUAR": "jaguar",
        }
        for brand_key, cat_id in brand_map.items():
            if brand_key in make:
                catalog_hint = cat_id
                break

        matches = vin_lookup(vin, catalogs=catalog_hint)

        if not matches and catalog_hint:
            # Try without catalog filter
            matches = vin_lookup(vin)

        if len(matches) == 1:
            car = matches[0]
            success(f"Match exacto: {car.get('title', car.get('modelName', '?'))}")
            subheader("Detalles del Vehiculo")
            show_car_info(car)
            return car

        elif len(matches) > 1:
            subheader(f"VIN encontro {len(matches)} resultados — elige el tuyo")
            # Show detailed info for each match so user can make informed choice
            for i, m in enumerate(matches, 1):
                print(f"\n  {C.BOLD}--- Opcion {i} ---{C.RESET}")
                print(f"    {C.BOLD}Marca:{C.RESET} {m.get('brand', '?')}  {C.BOLD}Catalogo:{C.RESET} {m.get('catalogId', '?')}")
                print(f"    {C.BOLD}Modelo:{C.RESET} {m.get('modelName', '?')}  {C.BOLD}Titulo:{C.RESET} {m.get('title', '?')}")
                desc = m.get("description", "")
                if desc:
                    for line in desc.strip().split("\n")[:5]:
                        line = line.strip().rstrip(";")
                        if line:
                            print(f"    {C.DIM}{line}{C.RESET}")
                params = m.get("parameters", [])
                if params:
                    param_strs = [f"{p.get('name','?')}={p.get('value','?')}" for p in params[:8] if p.get('value') and p.get('value') != 'Not specified']
                    if param_strs:
                        print(f"    {C.DIM}{' | '.join(param_strs)}{C.RESET}")
                opts = m.get("optionCodes", [])
                if opts:
                    print(f"    {C.DIM}Opciones de fabrica: {len(opts)}{C.RESET}")

            print()
            result = pick(
                matches,
                lambda c: (
                    f"{c.get('brand', '?'):12s} "
                    f"{c.get('title', c.get('modelName', '?')):45s} "
                    f"{C.DIM}catalog={c.get('catalogId', '?')}{C.RESET}"
                ),
                "Elige tu vehiculo (numero)",
                allow_back=False,
            )
            if result:
                car = result[1]
                subheader("Detalles del Vehiculo")
                show_car_info(car)
                return car

        else:
            warn("VIN no encontrado en Parts-Catalogs")

    # ── Fallback: manual catalog/model/car browse ──
    subheader("Busqueda manual por catalogo")
    catalogs = get_catalogs()
    if not catalogs:
        error("No se pudieron cargar catalogos")
        return None

    # Try to auto-match catalog by make
    matched_cat = None
    for cat in catalogs:
        if make and (make.lower() in cat["name"].lower() or make.lower() in cat["id"].lower()):
            matched_cat = cat
            break

    if matched_cat:
        success(f"Catalogo: {matched_cat['name']} ({matched_cat['id']})")
    else:
        catalogs.sort(key=lambda c: c["name"])
        result = pick(
            catalogs,
            lambda c: f"{c['name']:25s} {C.DIM}({c['id']}) {c.get('modelsCount', '?')} modelos — actualizado: {c.get('actuality', '?')}{C.RESET}",
            "Elige catalogo"
        )
        if not result:
            return None
        matched_cat = result[1]

    catalog_id = matched_cat["id"]

    # Get models
    subheader(f"Modelos de {matched_cat['name']}")
    models = get_models(catalog_id)
    if not models:
        error("No se encontraron modelos")
        return None

    # Try to auto-match model by plate model name
    plate_model = plate_data.get("CarModel", {}).get("CurrentTextValue", "").upper()
    model_candidates = []
    if plate_model:
        first_word = plate_model.split()[0]
        model_candidates = [m for m in models if first_word in m["name"].upper()]

    show_models = model_candidates if model_candidates else models
    if model_candidates:
        subheader(f"Modelos que coinciden con '{plate_model}'")
    result = pick(
        show_models,
        lambda m: f"{m['name']:40s} {C.DIM}id={m['id'][:30]}{C.RESET}",
        "Elige modelo"
    )
    if not result:
        return None
    model = result[1]

    # Get cars for model
    subheader(f"Vehiculos de {model['name']}")
    cars = get_cars(catalog_id, model["id"])
    if not cars:
        error("No se encontraron vehiculos")
        return None

    # Show detailed info for each car so user can make informed choice
    for i, c in enumerate(cars, 1):
        name = c.get("name", "?")
        desc = c.get("description", "")
        params = c.get("parameters", [])
        print(f"\n  {C.BOLD}{i:>4}. {name}{C.RESET}")
        if desc:
            for line in desc.strip().split("\n")[:4]:
                line = line.strip().rstrip(";")
                if line:
                    print(f"       {C.DIM}{line}{C.RESET}")
        if params:
            param_strs = [f"{p.get('name','?')}={p.get('value','?')}" for p in params[:8] if p.get('value') and p.get('value') != 'Not specified']
            if param_strs:
                print(f"       {C.DIM}{' | '.join(param_strs)}{C.RESET}")
        vin = c.get("vin") or c.get("frame") or ""
        if vin:
            print(f"       {C.DIM}VIN/Frame: {vin}{C.RESET}")

    print()
    result = pick(
        cars,
        lambda c: (
            f"{c.get('name', '?'):50s} "
            f"{C.DIM}{(c.get('description') or '')[:60]}{C.RESET}"
        ),
        "Elige vehiculo (numero)"
    )
    if not result:
        return None
    car = result[1]

    # Build a CarInfo-like dict for consistency
    return {
        "catalogId": catalog_id,
        "carId": car["id"],
        "criteria": car.get("criteria", ""),
        "modelId": car.get("modelId", model["id"]),
        "modelName": car.get("modelName", model["name"]),
        "brand": matched_cat["name"],
        "title": car.get("name", "?"),
        "description": car.get("description", ""),
        "vin": car.get("vin", ""),
        "parameters": car.get("parameters", []),
    }


# ── Step 4: Browse Groups ──────────────────────────────────────────────────

def get_groups(catalog_id, car_id, group_id=None, criteria=None):
    """Get groups/subgroups for a car."""
    params = {"carId": car_id}
    if group_id:
        params["groupId"] = group_id
    if criteria:
        params["criteria"] = criteria
    data = pc_get(f"/catalogs/{catalog_id}/groups2/", params=params)
    if not data or not isinstance(data, list):
        return []
    return data


def get_groups_tree(catalog_id, car_id, criteria=None):
    """Get full groups tree in one call."""
    params = {"carId": car_id, "cached": "true"}
    if criteria:
        params["criteria"] = criteria
    data = pc_get(f"/catalogs/{catalog_id}/groups-tree", params=params)
    if not data or not isinstance(data, list):
        return []
    return data


def browse_groups(catalog_id, car_id, criteria=None, breadcrumb=""):
    """Recursive group browser. Returns group dict with hasParts=true, or None."""
    groups = get_groups(catalog_id, car_id, criteria=criteria)
    if not groups:
        groups = get_groups(catalog_id, car_id)

    if not groups:
        warn("No se encontraron grupos.")
        return None

    prefix = f"{breadcrumb} > " if breadcrumb else ""

    result = pick(
        groups,
        lambda g: (
            f"{g.get('name', '?'):50s} "
            f"{C.MAGENTA}{'PARTES' if g.get('hasParts') else '→ subcategorias' if g.get('hasSubgroups') else ''}{C.RESET}"
        ),
        f"Elige grupo ({prefix.rstrip(' > ') or 'raiz'})"
    )

    if not result:
        return None

    group = result[1]

    if group.get("hasParts"):
        return group

    if group.get("hasSubgroups"):
        # Has subcategories — ask: go deeper or show parts if also hasParts
        subheader(f"Subcategorias de {group.get('name', '?')}")
        sub_groups = get_groups(catalog_id, car_id, group_id=group["id"], criteria=criteria)
        if not sub_groups:
            sub_groups = get_groups(catalog_id, car_id, group_id=group["id"])

        if not sub_groups:
            warn("No se encontraron subcategorias.")
            return None

        sub_result = pick(
            sub_groups,
            lambda g: (
                f"{g.get('name', '?'):50s} "
                f"{C.MAGENTA}{'PARTES' if g.get('hasParts') else '→ subcategorias' if g.get('hasSubgroups') else ''}{C.RESET}"
            ),
            f"Elige subcategoria ({group.get('name', '?')})"
        )

        if not sub_result:
            return None

        sub_group = sub_result[1]

        if sub_group.get("hasParts"):
            return sub_group

        if sub_group.get("hasSubgroups"):
            # Go one more level deep
            subheader(f"Subcategorias de {sub_group.get('name', '?')}")
            deep_groups = get_groups(catalog_id, car_id, group_id=sub_group["id"], criteria=criteria)
            if not deep_groups:
                deep_groups = get_groups(catalog_id, car_id, group_id=sub_group["id"])

            if not deep_groups:
                warn("No se encontraron subcategorias.")
                return None

            deep_result = pick(
                deep_groups,
                lambda g: (
                    f"{g.get('name', '?'):50s} "
                    f"{C.MAGENTA}{'PARTES' if g.get('hasParts') else '→' if g.get('hasSubgroups') else ''}{C.RESET}"
                ),
                f"Elige subcategoria"
            )

            if deep_result and deep_result[1].get("hasParts"):
                return deep_result[1]
            elif deep_result and deep_result[1].get("hasSubgroups"):
                # Even deeper — get groups again
                deeper = get_groups(catalog_id, car_id, group_id=deep_result[1]["id"], criteria=criteria)
                if deeper:
                    dr = pick(
                        deeper,
                        lambda g: (
                            f"{g.get('name', '?'):50s} "
                            f"{C.MAGENTA}{'PARTES' if g.get('hasParts') else ''}{C.RESET}"
                        ),
                        "Elige grupo"
                    )
                    if dr and dr[1].get("hasParts"):
                        return dr[1]
            return None

    return None


# ── Step 5: View Parts ──────────────────────────────────────────────────────

def get_parts(catalog_id, car_id, group_id, criteria=None):
    """Get OEM parts for a group."""
    params = {"carId": car_id, "groupId": group_id}
    if criteria:
        params["criteria"] = criteria
    data = pc_get(f"/catalogs/{catalog_id}/parts2", params=params)
    return data


def show_parts(parts_data, catalog_id):
    """Display parts from a group with diagram info."""
    if not parts_data:
        warn("No se encontraron partes.")
        return

    img = parts_data.get("img")
    if img:
        if img.startswith("//"):
            img = "https:" + img
        print(f"  {C.CYAN}Diagrama: {img}{C.RESET}")

    part_groups = parts_data.get("partGroups", [])
    if not part_groups:
        warn("Sin grupos de partes.")
        return

    # Flatten all parts with their group context
    all_parts = []
    for pg in part_groups:
        pg_name = pg.get("name") or ""
        pg_desc = pg.get("description") or ""
        pg_number = pg.get("number") or ""
        pg_pos = pg.get("positionNumber") or ""
        for part in pg.get("parts", []):
            part["_group_name"] = pg_name
            part["_group_desc"] = pg_desc
            part["_group_number"] = pg_number
            part["_group_positionNumber"] = pg_pos
            all_parts.append(part)

    if not all_parts:
        warn("Sin partes en este grupo.")
        return

    while True:
        subheader(f"Partes OEM ({len(all_parts)} piezas)")
        if img:
            print(f"  {C.DIM}Diagrama: {img}{C.RESET}\n")

        result = pick(
            all_parts,
            lambda p: (
                f"{C.BOLD}{p.get('number', '?'):22s}{C.RESET} "
                f"{p.get('name', '?'):30s} "
                f"{C.DIM}pos:{p.get('positionNumber', '-'):4s}{C.RESET} "
                f"{C.DIM}{(p.get('notice') or '')[:35]}{C.RESET}"
            ),
            "Elige parte para ver detalle"
        )

        if not result:
            return

        part = result[1]
        show_part_detail(part, catalog_id)


def show_part_detail(part, catalog_id):
    """Show full details for a single OEM part."""
    header(f"Parte OEM: {part.get('number', '?')}")

    info("Numero OEM", part.get("number"))
    info("ID interno", part.get("id"))
    info("Name ID", part.get("nameId"))
    info("Nombre", part.get("name"))
    info("Posicion en diagrama", part.get("positionNumber"))
    info("Catalogo", catalog_id)

    notice = part.get("notice", "")
    if notice:
        info("Nota", notice)

    # Group context
    gname = part.get("_group_name")
    gdesc = part.get("_group_desc")
    g_number = part.get("_group_number")
    g_pos = part.get("_group_positionNumber")
    if gname:
        info("Grupo", gname)
    if gdesc:
        info("Desc. grupo", gdesc)
    if g_number:
        info("Numero grupo", g_number)
    if g_pos:
        info("Posicion grupo", g_pos)

    desc = part.get("description", "")
    if desc:
        subheader("Descripcion / Aplicabilidad")
        # Show FULL description — split by newlines
        for line in desc.split("\n"):
            line = line.strip()
            if line:
                if line.startswith("-") or line.startswith("Cantidad"):
                    print(f"    {C.DIM}{line}{C.RESET}")
                elif line.startswith("ó") or line.startswith("o\n"):
                    print(f"    {C.YELLOW}— o —{C.RESET}")
                else:
                    print(f"    {line}")

    url = part.get("url")
    if url:
        info("URL", url)

    # Show any remaining fields not already displayed
    known_keys = {"id", "nameId", "number", "name", "positionNumber", "notice",
                  "description", "url", "_group_name", "_group_desc",
                  "_group_number", "_group_positionNumber"}
    extra = {k: v for k, v in part.items() if k not in known_keys and v}
    if extra:
        subheader("Campos adicionales")
        for k, v in extra.items():
            info(k, str(v)[:200])

    prompt("Enter para volver", allow_empty=True)


# ── Step 6: Search Parts by Name ────────────────────────────────────────────

def search_suggest(catalog_id, query):
    """Search for part groups by name."""
    data = pc_get(f"/catalogs/{catalog_id}/groups-suggest", params={"q": query})
    if not data or not isinstance(data, list):
        return []
    return data


# ── Step 7: Schemas (Diagrams) ──────────────────────────────────────────────

def get_schemas(catalog_id, car_id, criteria=None, page=0, branch_id=None, part_name=None):
    """Get diagram schemas for a car."""
    params = {"carId": car_id, "page": page}
    if criteria:
        params["criteria"] = criteria
    if branch_id:
        params["branchId"] = branch_id
    if part_name:
        params["partName"] = part_name
    data = pc_get(f"/catalogs/{catalog_id}/schemas", params=params)
    return data


def browse_schemas(catalog_id, car_id, criteria=None):
    """Browse diagram schemas and pick one to view parts."""
    page = 0
    while True:
        data = get_schemas(catalog_id, car_id, criteria=criteria, page=page)
        if not data:
            warn("No se encontraron diagramas.")
            return None

        schemas = data.get("list", [])
        if not schemas:
            warn("No hay diagramas en esta pagina.")
            return None

        subheader(f"Diagramas (pagina {page + 1})")

        result = pick(
            schemas,
            lambda s: (
                f"{s.get('name', '?'):55s} "
                f"{C.DIM}{', '.join(p['name'] for p in s.get('partNames', [])[:3])}{C.RESET}"
            ),
            "Elige diagrama"
        )

        if not result:
            return None

        schema = result[1]
        return schema


# ── Main Loop ───────────────────────────────────────────────────────────────

def parts_browser(car):
    """Main parts browsing loop for a matched car."""
    catalog_id = car.get("catalogId", "")
    car_id = car.get("carId", "")
    criteria = car.get("criteria", "")
    car_title = car.get("title", car.get("modelName", "?"))

    while True:
        header(f"Catalogo OEM: {car.get('brand', '')} {car_title}")
        print(f"  {C.BOLD}[1]{C.RESET} Navegar por grupos (categorias)")
        print(f"  {C.BOLD}[2]{C.RESET} Ver diagramas")
        print(f"  {C.BOLD}[3]{C.RESET} Buscar parte por nombre")
        print(f"  {C.BOLD}[4]{C.RESET} Ver codigos de fabrica (opciones VIN)")
        print(f"  {C.BOLD}[B]{C.RESET} Volver a busqueda de placa")

        choice = prompt("Opcion").lower()

        if choice == "1":
            # Browse groups
            group = browse_groups(catalog_id, car_id, criteria)
            if group:
                subheader(f"Cargando partes: {group.get('name', '?')}")
                parts_data = get_parts(catalog_id, car_id, group["id"], criteria)
                if not parts_data:
                    # Try without criteria
                    parts_data = get_parts(catalog_id, car_id, group["id"])
                show_parts(parts_data, catalog_id)

        elif choice == "2":
            # Browse schemas/diagrams
            schema = browse_schemas(catalog_id, car_id, criteria)
            if schema:
                group_id = schema.get("groupId")
                if group_id:
                    subheader(f"Partes de: {schema.get('name', '?')}")
                    img = schema.get("img")
                    if img:
                        if img.startswith("//"):
                            img = "https:" + img
                        print(f"  {C.CYAN}Diagrama: {img}{C.RESET}\n")
                    parts_data = get_parts(catalog_id, car_id, group_id, criteria)
                    if not parts_data:
                        parts_data = get_parts(catalog_id, car_id, group_id)
                    show_parts(parts_data, catalog_id)

        elif choice == "3":
            # Search by part name
            query = prompt("Nombre de la parte (ej: brake, filter, oil)")
            suggestions = search_suggest(catalog_id, query)
            if not suggestions:
                warn(f"Sin resultados para '{query}'")
                continue
            subheader(f"Resultados de busqueda: '{query}'")
            result = pick(
                suggestions,
                lambda s: f"{s.get('name', '?')}",
                "Elige grupo de partes"
            )
            if result:
                # Use the suggestion to find schemas or groups
                suggestion = result[1]
                part_name = suggestion.get("name", "")
                schema_data = get_schemas(catalog_id, car_id, criteria=criteria, part_name=part_name)
                if schema_data and schema_data.get("list"):
                    schemas = schema_data["list"]
                    subheader(f"Diagramas para '{part_name}'")
                    s_result = pick(
                        schemas,
                        lambda s: (
                            f"{s.get('name', '?'):55s} "
                            f"{C.DIM}{', '.join(p['name'] for p in s.get('partNames', [])[:3])}{C.RESET}"
                        ),
                        "Elige diagrama"
                    )
                    if s_result:
                        group_id = s_result[1].get("groupId")
                        if group_id:
                            parts_data = get_parts(catalog_id, car_id, group_id, criteria)
                            if not parts_data:
                                parts_data = get_parts(catalog_id, car_id, group_id)
                            show_parts(parts_data, catalog_id)
                else:
                    warn(f"Sin diagramas para '{part_name}'")

        elif choice == "4":
            # Show option codes
            show_option_codes(car)
            prompt("Enter para volver", allow_empty=True)

        elif choice == "b":
            return


def main():
    if not PC_KEY:
        error("AUTOPARTSCATALOG_KEY no esta configurada!")
        error("Ejecuta: export AUTOPARTSCATALOG_KEY=tu_clave")
        sys.exit(1)

    clear()
    header("PLACA → OEM  |  Costa Rica → Catalogo de Partes Originales")
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
            info("Descripcion", plate_data.get("Description"))
            info("Marca", plate_data.get("CarMake", {}).get("CurrentTextValue"))
            info("Modelo", plate_data.get("CarModel", {}).get("CurrentTextValue"))
            info("Ano", plate_data.get("RegistrationYear"))
            info("Motor", plate_data.get("EngineSize", {}).get("CurrentTextValue"))
            info("Carroceria", plate_data.get("Body"))
            info("Combustible", plate_data.get("Fuel"))
            info("Traccion", plate_data.get("WheelPlan"))
            info("Color", plate_data.get("Colour"))
            info("VIN", plate_data.get("VIN"))
            info("Cod. Motor", plate_data.get("EngineCode"))
            info("Propietario", plate_data.get("owner"))

            img = plate_data.get("ImageUrl")
            if img:
                info("Imagen", img)

            # ── Step 2: Match in Parts-Catalogs ──
            subheader("Buscando vehiculo en catalogo OEM...")
            car = match_vehicle(plate_data)

            if not car:
                warn("No se pudo encontrar el vehiculo.")
                continue

            car_title = car.get("title", car.get("modelName", "?"))
            success(f"Seleccionado: {car.get('brand', '')} {car_title}")

            # ── Steps 3+: Browse parts ──
            parts_browser(car)

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
