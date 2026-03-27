#!/usr/bin/env python3
"""
Plate-to-17VIN Pipeline: Costa Rica License Plate → 17VIN EPC Catalog

Flow:
  1. Enter a Costa Rica plate number
  2. Lookup vehicle info (make, model, year, VIN, owner, etc.)
  3. VIN decode via 17VIN → EPC match, model list, factory option codes
  4. Browse OEM EPC categories (hierarchical: L1 → L2 → L3)
  5. View OEM parts with exploded-view diagrams + hotspot coordinates
  6. Search parts by OE number within the vehicle's catalog
  7. Cross-reference any OE number → OEM interchange + aftermarket equivalents
  8. Get 4S dealer pricing for parts
  9. Dump all OE part numbers for the vehicle

Unique 17VIN capabilities vs TecDoc/Parts-Catalogs:
  - Combined OEM + aftermarket cross-references in one call
  - Full factory option codes (87-150+ per VIN)
  - 4S dealer pricing (Chinese market)
  - All OE numbers dump (2500-3000 per vehicle)
  - VIN OCR (photo → VIN)
"""

import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request

import pymssql

# ── .env loader ────────────────────────────────────────────────────────────

def _load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

_load_dotenv()

# ── Config ──────────────────────────────────────────────────────────────────

API_BASE = "http://api.17vin.com:8080"
USERNAME = "international_lobsterlabs"
PASSWORD = "e0ikkf8"
MD5_USER = hashlib.md5(USERNAME.encode()).hexdigest()
MD5_PASS = hashlib.md5(PASSWORD.encode()).hexdigest()

PLATE_API = "https://www.regcheck.org.uk/api/reg.asmx/CheckCostaRica"

# ── REMUSA DB Config ───────────────────────────────────────────────────────

DB_HOST = "192.168.100.14"
DB_PORT = 1433
DB_USER = "RemusaxLobster"
DB_PASS = os.environ.get("DB2_PASSWORD", "")
DB_NAME = "SOFTLAND"

_db_conn = None

def get_db_conn():
    global _db_conn
    if _db_conn is None:
        _db_conn = pymssql.connect(
            server=DB_HOST, port=DB_PORT,
            user=DB_USER, password=DB_PASS,
            database=DB_NAME, timeout=15, login_timeout=10
        )
    return _db_conn
PLATE_USER = "jruiz2203"

# ── TecDoc (RapidAPI) Config ───────────────────────────────────────────────

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
TECDOC_BASE = "https://tecdoc-catalog.p.rapidapi.com"
TECDOC_HEADERS = {
    "x-rapidapi-host": "tecdoc-catalog.p.rapidapi.com",
    "x-rapidapi-key": RAPIDAPI_KEY,
}
TECDOC_LANG = 8       # Español
TECDOC_TYPE = 1       # Passenger Car
TECDOC_COUNTRY = 63


def tecdoc_get(path, params=None):
    """GET request to TecDoc RapidAPI. Returns parsed JSON or None."""
    if not RAPIDAPI_KEY:
        return None
    import requests
    url = f"{TECDOC_BASE}{path}"
    try:
        resp = requests.get(url, headers=TECDOC_HEADERS, params=params, timeout=30)
        if resp.status_code == 200 and not resp.headers.get("content-type", "").startswith("text/html"):
            return resp.json()
    except Exception:
        pass
    return None

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
    if value and str(value).strip() and str(value).strip() not in ("?", "None"):
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


# ── 17VIN API Client ────────────────────────────────────────────────────────


def make_token(url_params):
    return hashlib.md5((MD5_USER + MD5_PASS + url_params).encode()).hexdigest()


def api_get(url_params, timeout=30):
    tok = make_token(url_params)
    sep = "&" if "?" in url_params else "?"
    full_url = f"{API_BASE}{url_params}{sep}user={USERNAME}&token={tok}"
    try:
        req = urllib.request.Request(full_url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error(f"HTTP {e.code}: {e.reason}")
        return None
    except urllib.error.URLError as e:
        error(f"Connection error: {e.reason}")
        return None
    except Exception as e:
        error(f"{type(e).__name__}: {e}")
        return None


# ── Step 0: Account Balance (API 1002) ──────────────────────────────────────


def check_balance():
    r = api_get("/?action=myapicount")
    if r and r.get("code") == 1:
        for d in r.get("data", []):
            raw = d.get("Count", "")
            remark = d.get("Remark", "")
            amt = re.search(r"[\d.]+", raw)
            balance = amt.group() if amt else raw
            expiry = re.search(r"\d{4}-\d{2}-\d{2}", remark)
            return balance, expiry.group() if expiry else remark
    return "?", "?"


# ── Step 1: Plate Lookup ────────────────────────────────────────────────────


def lookup_plate(plate, retries=3):
    import urllib.request as ur

    for attempt in range(1, retries + 1):
        try:
            params = urllib.parse.urlencode({
                "RegistrationNumber": plate,
                "username": PLATE_USER,
            })
            url = f"{PLATE_API}?{params}"
            req = ur.Request(url)
            with ur.urlopen(req, timeout=20) as resp:
                text = resp.read().decode()

            m = re.search(r"<vehicleJson>\s*(\{.*?\})\s*</vehicleJson>", text, re.DOTALL)
            if not m:
                error(f"Intento {attempt}/{retries}: Sin datos del vehiculo")
                continue
            return json.loads(m.group(1))

        except Exception as e:
            error(f"Intento {attempt}/{retries}: {type(e).__name__}: {e}")

    return None


# ── Step 2: VIN Decode (API 3001) ───────────────────────────────────────────


def vin_decode(vin):
    url_params = f"/?vin={vin}"
    return api_get(url_params)


def show_decode_result(data):
    d = data.get("data", {})

    info("Ano (VIN)", d.get("model_year_from_vin"))
    info("EPC", d.get("epc"))
    info("EPC ID", d.get("epc_id"))
    info("Marca", d.get("brand"))
    info("Match", d.get("matching_mode"))
    info("Fecha fabricacion", d.get("build_date"))
    info("Pais fabricacion", d.get("made_in_en") or d.get("made_in_cn"))

    model_list = d.get("model_list") or []
    if model_list:
        subheader(f"Modelos estandar ({len(model_list)})")
        for i, m in enumerate(model_list[:5]):
            en = m.get("Model_detial_en") or m.get("Model_detail", "?")
            print(f"  {C.DIM}{i + 1:>3}{C.RESET}  {en}")
            brand_en = m.get("Brand_en") or m.get("Brand", "")
            model_en = m.get("Model_en") or m.get("Model", "")
            cc = m.get("Cc", "")
            engine = m.get("Engine_no_en") or m.get("Engine_no", "")
            trans = m.get("Transmission_detail_en") or m.get("Transmission_detail", "")
            drive = m.get("Driving_mode_en") or m.get("Driving_mode", "")
            year = m.get("Model_year", "")
            series = m.get("Series_en") or m.get("Series", "")
            factory = m.get("Factory_en") or m.get("Factory", "")
            price = m.get("Price", "")
            begin = m.get("Date_begin", "")
            end = m.get("Date_end", "")
            details = []
            if brand_en:
                details.append(f"Marca={brand_en}")
            if model_en:
                details.append(f"Modelo={model_en}")
            if series and series != model_en:
                details.append(f"Serie={series}")
            if cc:
                details.append(f"CC={cc}")
            if engine:
                details.append(f"Motor={engine}")
            if trans:
                details.append(f"Trans={trans}")
            if drive:
                details.append(f"Traccion={drive}")
            if year:
                details.append(f"Ano={year}")
            if factory:
                details.append(f"Fabrica={factory}")
            if price:
                details.append(f"Precio={price} CNY")
            if begin:
                details.append(f"Desde={begin}")
            if end:
                details.append(f"Hasta={end}")
            if details:
                print(f"       {C.DIM}{' | '.join(details)}{C.RESET}")
        if len(model_list) > 5:
            print(f"       {C.DIM}... +{len(model_list) - 5} modelos mas{C.RESET}")

    oepc_list = d.get("model_original_epc_list") or []
    if oepc_list:
        subheader(f"Datos originales EPC ({len(oepc_list)} registros)")
        for ep in oepc_list[:2]:
            attrs = ep.get("CarAttributes", [])
            en_attrs = [(a["Col_name"], a["Col_value"]) for a in attrs if a.get("Language") == "en"]
            major = [(n, v) for n, v in en_attrs if any(
                k in n.lower() for k in ("model", "engine", "transmission", "grade", "body", "paint", "interior", "release", "delivery")
            )]
            minor = [(n, v) for n, v in en_attrs if (n, v) not in major]

            if major:
                for name, val in major:
                    info(name, val)
            if minor:
                opt_count = len(minor)
                shown = minor[:8]
                for name, val in shown:
                    print(f"    {C.DIM}{name}: {val}{C.RESET}")
                if opt_count > 8:
                    print(f"    {C.DIM}... +{opt_count - 8} opciones de fabrica mas{C.RESET}")

    imp_list = d.get("model_import_list") or []
    if imp_list:
        subheader("Datos de importacion")
        for m in imp_list[:3]:
            info("Marca", m.get("Make_en"))
            info("Modelo", m.get("Model_en"))
            info("Motor", m.get("Engine_en"))
            info("CC", m.get("Cc_en"))
            info("Traccion", m.get("Driveline_en"))
            info("Carroceria", m.get("Body_style_en"))

    return d


# ── Step 3: EPC Category Navigation (API 5101/5102/5103) ───────────────────


def get_categories(epc, vin, level, parent_code=None, epc_id=None):
    if level == 1:
        url = f"/{epc}?action=cata1&vin={vin}"
    elif level == 2:
        url = f"/{epc}?action=cata2&vin={vin}&cata1_code={parent_code}"
    elif level == 3:
        url = f"/{epc}?action=cata3&vin={vin}&cata2_code={parent_code}"
    else:
        return []

    if epc_id:
        url += f"&epc_id={epc_id}"

    r = api_get(url)
    if not r or r.get("code") != 1:
        return []
    return r.get("data", {}).get("catalist") or []


def browse_categories(epc, vin, epc_id=None, level=1, parent_code=None, breadcrumb=""):
    cats = get_categories(epc, vin, level, parent_code, epc_id)
    if not cats:
        if level == 1:
            warn("No se encontraron categorias EPC para este VIN.")
        return None

    prefix = f"{breadcrumb} > " if breadcrumb else ""
    fit_cats = [c for c in cats if c.get("Is_fit_for_this_vin", c.get("is_fit_for_this_vin", 1)) == 1]
    show_cats = fit_cats if fit_cats else cats

    def cat_label(c):
        name = (c.get('name_en') or c.get('name_zh') or '?')[:55]
        kind = 'PARTES' if c.get('is_last') == 1 else '→ subcategorias'
        img = c.get('illustration_img_address', '')
        img_part = f" {C.DIM}http://resource.17vin.com/img/{epc}/{img}{C.RESET}" if img else ""
        return f"{name:55s} {C.MAGENTA}{kind}{C.RESET}{img_part}"

    result = pick(
        show_cats,
        cat_label,
        f"Elige categoria ({prefix.rstrip(' > ') or 'raiz'})"
    )

    if not result:
        return None

    cat = result[1]
    cat_name = cat.get("name_en") or cat.get("name_zh") or "?"

    if cat.get("is_last") == 1:
        return {
            "cata_code": cat["cata_code"],
            "level": level,
            "name": cat_name,
            "img": cat.get("illustration_img_address", ""),
        }

    next_level = level + 1
    if next_level > 3:
        return {
            "cata_code": cat["cata_code"],
            "level": level,
            "name": cat_name,
            "img": cat.get("illustration_img_address", ""),
        }

    subheader(f"Subcategorias de: {cat_name}")
    sub = browse_categories(epc, vin, epc_id, next_level, cat["cata_code"], f"{prefix}{cat_name}")
    if sub:
        return sub

    if cat.get("is_last") == 1:
        return {
            "cata_code": cat["cata_code"],
            "level": level,
            "name": cat_name,
            "img": cat.get("illustration_img_address", ""),
        }
    return None


# ── Step 4: Parts List (API 5105) ───────────────────────────────────────────


def get_parts(epc, vin, cata_code, level, epc_id=None):
    url = f"/{epc}?action=part&vin={vin}&last_cata_code={cata_code}&last_cata_code_level={level}"
    if epc_id:
        url += f"&epc_id={epc_id}"
    return api_get(url)


def _check_parts_remusa(partlist):
    """Check a list of EPC parts against REMUSA. Returns dict of pn -> remusa_info."""
    try:
        art_dict, alias_dict, alt_dict = _load_remusa_lookup()
    except Exception:
        return {}

    remusa_map = {}
    for p in partlist:
        pn = p.get("partnumber", "")
        if not pn:
            continue
        norm = _normalize_pn(pn)
        if norm in art_dict:
            orig, art_code, desc = art_dict[norm]
            remusa_map[pn] = {"articulo": art_code, "desc": desc, "source": "OE", "aftermarket": []}
        elif norm in alias_dict:
            orig, art_code, desc = alias_dict[norm]
            remusa_map[pn] = {"articulo": art_code, "desc": desc, "source": "ALIAS", "aftermarket": []}
        elif norm in alt_dict:
            orig, art_code, desc = alt_dict[norm]
            remusa_map[pn] = {"articulo": art_code, "desc": desc, "source": "ALTERNO", "aftermarket": []}

    return remusa_map


def show_parts(parts_data, epc):
    if not parts_data or parts_data.get("code") != 1:
        warn("No se encontraron partes.")
        return None

    d = parts_data.get("data", {})
    partlist = d.get("partlist") or []
    img = d.get("imgaddress", "")

    if img:
        full_img = f"http://resource.17vin.com/img/{epc}/{img}"
        print(f"  {C.CYAN}Diagrama: {full_img}{C.RESET}")

    hotspots = d.get("all_img_hotspots") or []
    if hotspots:
        hs = hotspots[0].get("img_hotspots", {})
        hs_count = len(hs.get("hotspots", []))
        print(f"  {C.DIM}Imagen: {hs.get('img_width', '?')}x{hs.get('img_height', '?')} | {hs_count} hotspots{C.RESET}")

    if not partlist:
        warn("Sin partes en esta categoria.")
        return None

    fit_parts = [p for p in partlist if p.get("is_fit_for_this_vin", 1) == 1]
    show_list = fit_parts if fit_parts else partlist

    # REMUSA matching (instant — checks ARTICULO, ALIAS_PRODUCCION, ARTICULO_ALTERNO in memory)
    print(f"  {C.DIM}Buscando matches en REMUSA...{C.RESET}")
    remusa_map = _check_parts_remusa(show_list)

    matched_count = len(remusa_map)
    if matched_count:
        print(f"  {C.GREEN}✔ {matched_count} partes encontradas en REMUSA{C.RESET}")
        matched_parts = [p for p in show_list if p.get("partnumber") in remusa_map]
        unmatched_parts = [p for p in show_list if p.get("partnumber") not in remusa_map]
        show_list = matched_parts + unmatched_parts
    else:
        print(f"  {C.DIM}Ninguna parte de esta categoria esta en REMUSA.{C.RESET}")

    while True:
        filter_info = f", {len(partlist) - len(fit_parts)} filtradas" if len(fit_parts) < len(partlist) else ""
        remusa_info = f" | {C.GREEN}{matched_count} en REMUSA{C.RESET}" if matched_count else ""
        subheader(f"Partes OEM ({len(show_list)} piezas{filter_info}{remusa_info})")

        def label_fn(p):
            pn = p.get("partnumber", "?")
            name = (p.get("name_en") or p.get("name_zh") or "?")[:35]
            qty = p.get("qty", "?")
            remark = p.get("remark_en") or p.get("remark_zh") or ""

            if pn in remusa_map:
                rm = remusa_map[pn]
                return (
                    f"{C.GREEN}★{C.RESET} {C.BOLD}{pn:18s}{C.RESET} "
                    f"{name:35s} "
                    f"{C.GREEN}REMUSA: {rm['articulo']} ({rm['source']}){C.RESET}"
                )
            else:
                return (
                    f"  {pn:18s} "
                    f"{name:35s} "
                    f"qty={qty:3s} "
                    f"{C.DIM}{remark}{C.RESET}"
                )

        result = pick(show_list, label_fn, "Elige parte para detalle")

        if not result:
            return None

        part = result[1]
        pn = part.get("partnumber", "")

        if pn in remusa_map:
            _show_part_with_remusa(part, epc, remusa_map[pn])
        else:
            show_part_detail(part, epc)


def _show_part_with_remusa(part, epc, remusa_info, _aft_list=None):
    """Show part detail — OE number directly matched in REMUSA. Shows full REMUSA detail automatically."""
    pn = part.get("partnumber", "?")
    header(f"Parte OEM: {pn}  {C.GREEN}★ EN REMUSA{C.RESET}")

    info("Numero OEM", pn)
    info("Nombre (EN)", part.get("name_en"))
    info("Nombre (ZH)", part.get("name_zh"))
    info("Cantidad", part.get("qty"))
    info("Compatible VIN", "Si" if part.get("is_fit_for_this_vin") == 1 else "No")
    info("Match via", remusa_info["source"])

    art_code = remusa_info["articulo"]
    show_remusa_detail(art_code, oe_code=pn)

    while True:
        print(f"\n  {C.BOLD}[T]{C.RESET} Buscar en TecDoc (specs, imagen, autos compatibles)")
        print(f"  {C.BOLD}[1]{C.RESET} Buscar reemplazos / equivalencias (API 4004)")
        print(f"  {C.BOLD}[2]{C.RESET} Ver modelos compatibles (detallado por version/trim)")
        print(f"  {C.BOLD}[3]{C.RESET} Ver modelos compatibles (agrupado por motor)")
        print(f"  {C.BOLD}[4]{C.RESET} Consultar precio 4S (API 4006)")
        print(f"  {C.BOLD}[5]{C.RESET} Buscar ilustracion EPC (API 4002 + 4005)")
        print(f"  {C.BOLD}[B]{C.RESET} Volver a lista de partes")

        choice = prompt("Accion").lower()

        if choice == "t":
            fallback = [pn, art_code]
            tecdoc_part_lookup(pn, fallback_codes=fallback)
        elif choice == "1":
            part_interchange(pn)
        elif choice == "2":
            part_vehicles(pn)
        elif choice == "3":
            part_vehicles_aftermarket(pn)
        elif choice == "4":
            part_price(pn)
        elif choice == "5":
            part_illustration(pn, epc)
        elif choice == "b":
            return


def show_part_detail(part, epc):
    pn = part.get("partnumber", "?")
    header(f"Parte OEM: {pn}")

    info("Numero OEM", pn)
    info("Numero original", part.get("partnumber_original"))
    info("Nombre (EN)", part.get("name_en"))
    info("Nombre (ZH)", part.get("name_zh"))
    info("Nombre estandar (EN)", part.get("std_name_en"))
    info("Nombre estandar (ZH)", part.get("std_name_zh"))
    info("Cantidad", part.get("qty"))
    info("Callout (diagrama)", part.get("callout"))
    info("Fecha inicio", part.get("begin_date"))
    info("Fecha fin", part.get("end_date"))
    info("Reemplazo", part.get("replacement"))
    info("Nota (EN)", part.get("remark_en"))
    info("Nota (ZH)", part.get("remark_zh"))
    info("Compatible VIN", "Si" if part.get("is_fit_for_this_vin") == 1 else "No")

    img = part.get("illustration_img_address", "")
    if img:
        info("Diagrama", f"http://resource.17vin.com/img/{epc}/{img}")

    while True:
        print(f"\n  {C.BOLD}[T]{C.RESET} Buscar en TecDoc (specs, imagen, autos compatibles)")
        print(f"  {C.BOLD}[1]{C.RESET} Buscar info de esta parte (API 4001)")
        print(f"  {C.BOLD}[2]{C.RESET} Buscar reemplazos / equivalencias (API 4004)")
        print(f"  {C.BOLD}[3]{C.RESET} Ver modelos compatibles (detallado por version/trim)")
        print(f"  {C.BOLD}[4]{C.RESET} Ver modelos compatibles (agrupado por motor)")
        print(f"  {C.BOLD}[5]{C.RESET} Consultar precio 4S (API 4006)")
        print(f"  {C.BOLD}[6]{C.RESET} Buscar ilustracion EPC (API 4002 + 4005)")
        print(f"  {C.BOLD}[B]{C.RESET} Volver a lista de partes")

        choice = prompt("Accion").lower()

        if choice == "t":
            tecdoc_part_lookup(pn)
        elif choice == "1":
            part_search(pn)
        elif choice == "2":
            part_interchange(pn)
        elif choice == "3":
            part_vehicles(pn)
        elif choice == "4":
            part_vehicles_aftermarket(pn)
        elif choice == "5":
            part_price(pn)
        elif choice == "6":
            part_illustration(pn, epc)
        elif choice == "b":
            return


# ── TecDoc Lookup ───────────────────────────────────────────────────────────


def tecdoc_part_lookup(pn, fallback_codes=None):
    """Search TecDoc for aftermarket analogues, specs, images, and compatible vehicles.
    If primary pn fails and fallback_codes is provided, tries each one until a match is found."""
    if not RAPIDAPI_KEY:
        warn("RAPIDAPI_KEY no configurada. Ejecuta: export RAPIDAPI_KEY=tu_clave")
        prompt("Enter para volver", allow_empty=True)
        return

    codes_to_try = [pn]
    if fallback_codes:
        for c in fallback_codes:
            if c and c not in codes_to_try:
                codes_to_try.append(c)

    articles = []
    matched_code = pn

    for code in codes_to_try:
        clean = re.sub(r"[^A-Za-z0-9]", "", code)
        if not clean:
            continue
        print(f"\r  {C.DIM}Buscando en TecDoc: {code}...{C.RESET}", end="", flush=True)

        data = tecdoc_get(
            f"/artlookup/search-for-analogue-of-spare-parts-by-oem-number"
            f"/oem-number/{clean}/lang-id/{TECDOC_LANG}/type-id/{TECDOC_TYPE}"
        )

        if data:
            found = data if isinstance(data, list) else data.get("articles", data.get("data", []))
            if found:
                articles = found
                matched_code = code
                break

    print("\r" + " " * 60 + "\r", end="", flush=True)

    if not articles:
        tried = ", ".join(codes_to_try[:5])
        extra = f" +{len(codes_to_try) - 5} mas" if len(codes_to_try) > 5 else ""
        warn(f"Sin resultados en TecDoc (intentados: {tried}{extra})")
        prompt("Enter para volver", allow_empty=True)
        return

    if matched_code != pn:
        print(f"  {C.GREEN}✔ Encontrado via codigo: {matched_code}{C.RESET}")

    # Deduplicate by articleId
    seen = set()
    unique = []
    for a in articles:
        aid = a.get("articleId")
        if aid and aid not in seen:
            seen.add(aid)
            unique.append(a)

    subheader(f"TecDoc: {len(unique)} aftermarket equivalentes para {matched_code}")

    # Show summary list
    for i, art in enumerate(unique[:30], 1):
        supplier = art.get("supplierName", "?")
        art_no = art.get("articleNo", "?")
        product = art.get("articleProductName", "")
        img_tag = " [IMG]" if art.get("s3image") else ""
        print(
            f"  {C.BOLD}[{i:2d}]{C.RESET} {supplier:25s} {art_no:22s} "
            f"{product[:30]}{C.DIM}{img_tag}{C.RESET}"
        )

    if len(unique) > 30:
        print(f"  {C.DIM}... y {len(unique) - 30} mas{C.RESET}")

    while True:
        sel = prompt("Selecciona articulo para detalle (numero) o [B] volver", allow_empty=True)
        if not sel or sel.lower() == "b":
            return

        try:
            idx = int(sel) - 1
            if 0 <= idx < len(unique):
                _show_tecdoc_article_detail(unique[idx])
            else:
                warn("Numero fuera de rango.")
        except ValueError:
            warn("Entrada invalida.")


def _show_tecdoc_article_detail(article):
    """Show full details for a TecDoc article, fetching complete info if needed."""
    article_id = article.get("articleId")
    art_no = article.get("articleNo", "?")
    supplier = article.get("supplierName", "?")
    product = article.get("articleProductName", "?")

    header(f"TecDoc: {supplier} {art_no}")

    # Try to get full details via article-complete-details
    full = None
    if article_id:
        print(f"  {C.DIM}Cargando especificaciones completas...{C.RESET}")
        full = tecdoc_get(
            f"/articles/article-complete-details/type-id/{TECDOC_TYPE}",
            params={
                "articleId": article_id,
                "countryFilterId": TECDOC_COUNTRY,
                "langId": TECDOC_LANG,
            }
        )

    art_data = (full or {}).get("article", article)

    # Basic info
    subheader("Info del Articulo")
    info("Article ID", str(article_id or "?"))
    info("Numero", art_data.get("articleNo", art_no))
    info("Producto", art_data.get("articleProductName", product))
    info("Proveedor", art_data.get("supplierName", supplier))

    # Image
    img = art_data.get("s3image")
    if img:
        info("Imagen", img)

    # Specs
    specs = art_data.get("allSpecifications", [])
    if specs:
        subheader(f"Especificaciones Tecnicas ({len(specs)})")
        for s in specs:
            info(s.get("criteriaName", "?"), s.get("criteriaValue", "?"))

    # OEM numbers
    oems = art_data.get("oemNo", article.get("oemNumbers", []))
    if oems:
        subheader(f"Numeros OEM equivalentes ({len(oems)})")
        for o in oems:
            brand = o.get("oemBrand", o.get("mfrName", "?"))
            number = o.get("oemDisplayNo", o.get("oemNumber", "?"))
            print(f"    {brand:15s}  {C.BOLD}{number}{C.RESET}")

    # Compatible vehicles
    cars = art_data.get("compatibleCars", [])
    if cars:
        by_model = {}
        for car in cars:
            key = car.get("modelName", "?")
            by_model.setdefault(key, []).append(car)

        subheader(f"Vehiculos Compatibles ({len(cars)} en {len(by_model)} modelos)")
        for model_name, model_cars in sorted(by_model.items()):
            print(f"\n  {C.BOLD}{model_name}{C.RESET}")
            sorted_cars = sorted(model_cars, key=lambda c: c.get("constructionIntervalStart", ""))
            for car in sorted_cars[:10]:
                yr_start = (car.get("constructionIntervalStart") or "?")[:7]
                yr_end = (car.get("constructionIntervalEnd") or "actual")[:7]
                engine = car.get("typeEngineName", "?")
                mfr = car.get("manufacturerName", "")
                print(
                    f"    {C.DIM}{mfr:12s}{C.RESET} {engine:45s} "
                    f"{yr_start} → {yr_end}"
                )
            if len(model_cars) > 10:
                print(f"    {C.DIM}... +{len(model_cars) - 10} mas{C.RESET}")
    elif not cars and full:
        print(f"\n  {C.DIM}Sin informacion de vehiculos compatibles.{C.RESET}")

    prompt("Enter para volver", allow_empty=True)


# ── Part Detail Sub-actions ─────────────────────────────────────────────────


def part_search(pn):
    """API 4001: Search part info across EPCs."""
    subheader(f"Buscando parte: {pn}")
    clean = re.sub(r"[^A-Za-z0-9]", "", pn)
    url = f"/?action=search_epc&query_part_number={clean}&query_match_type=exact"
    r = api_get(url)
    if not r or r.get("code") != 1:
        warn(f"Sin resultados para '{pn}' (code={r.get('code') if r else '?'})")
        prompt("Enter para volver", allow_empty=True)
        return

    results = r.get("data", [])
    if not results:
        warn("Sin resultados.")
        prompt("Enter para volver", allow_empty=True)
        return

    subheader(f"Resultados para {pn} ({len(results)} fuentes)")
    for d in results:
        epc_name = d.get("Epc") or "(aftermarket)"
        brand = d.get("Brand_name_en") or d.get("Brand_name_zh") or "?"
        part_name = d.get("Part_name_en") or d.get("Part_name_zh") or ""
        group_id = d.get("Group_id", "")
        epc_id = d.get("Epc_id", "")
        part_img = d.get("Part_img", "")

        print(f"  {C.BOLD}{d.get('Partnumber', '?')}{C.RESET}")
        print(f"    EPC: {epc_name}  |  Marcas: {brand}")
        if part_name:
            print(f"    Nombre: {part_name}")
        if group_id:
            print(f"    Group ID: {group_id}  |  EPC ID: {epc_id}")
        if part_img:
            print(f"    {C.DIM}Imagen: http://resource.17vin.com/img/{part_img}{C.RESET}")
        print()

    prompt("Enter para volver", allow_empty=True)


def part_interchange(pn):
    """API 4004: Get interchange/replacement numbers."""
    clean = re.sub(r"[^A-Za-z0-9]", "", pn)

    subheader(f"Buscando grupo para {pn}...")
    search = api_get(f"/?action=search_epc&query_part_number={clean}&query_match_type=exact")
    if not search or search.get("code") != 1 or not search.get("data"):
        warn("No se encontro la parte en ningún EPC.")
        prompt("Enter para volver", allow_empty=True)
        return

    oem_hits = [d for d in search["data"] if d.get("Epc")]
    if not oem_hits:
        warn("Parte encontrada solo como aftermarket — sin cross-ref OEM disponible.")
        prompt("Enter para volver", allow_empty=True)
        return

    hit = oem_hits[0]
    group_id = hit.get("Group_id", "")

    subheader(f"Cross-reference: {pn} (group={group_id})")
    url = f"/?action=get_interchange_from_part_number_and_group_id_plus_zh&part_number={clean}&group_id={group_id}"
    r = api_get(url)
    if not r or r.get("code") != 1:
        warn(f"Sin resultados de interchange (code={r.get('code') if r else '?'})")
        prompt("Enter para volver", allow_empty=True)
        return

    data = r.get("data", {})
    pi = data.get("PartInfo", {})
    ii = data.get("InterchangeInfo", {})

    info("Parte", pi.get("Part_number"))
    info("Nombre", pi.get("Part_name_en") or pi.get("Part_name_zh"))
    info("Marcas", pi.get("Brand_name_en"))

    total = ii.get("TotalRecords", 0)
    oe_count = ii.get("OeInterchangeRecords", 0)
    fac_count = ii.get("FactoryInterchangeRecords", 0)

    print(f"\n  {C.BOLD}Total intercambios: {total}{C.RESET}  (OE: {oe_count} | Aftermarket: {fac_count})")

    oe_list = ii.get("OeInterchange") or []
    if oe_list:
        subheader(f"Intercambio OEM ({len(oe_list)})")
        for o in oe_list:
            sim = o.get("Similarity_degree", "")
            dist = o.get("Distance", "")
            name = o.get("Part_name_en") or o.get("Part_name_zh") or ""
            brand = o.get("Brand_name_en") or ""
            print(
                f"  {C.BOLD}{o.get('Part_number', '?'):20s}{C.RESET} "
                f"{brand:20s} {name:30s} "
                f"{C.DIM}sim={sim} dist={dist}{C.RESET}"
            )

    fac_list = ii.get("FactoryInterchange") or []
    if fac_list:
        subheader(f"Aftermarket equivalentes ({len(fac_list)})")
        for f in fac_list[:30]:
            name = f.get("Part_name_en") or f.get("Part_name_zh") or ""
            brand = f.get("Brand_name_en") or ""
            sim = f.get("Similarity_degree", "")
            print(
                f"  {C.BOLD}{f.get('Part_number', '?'):20s}{C.RESET} "
                f"{brand:20s} {name:30s} "
                f"{C.DIM}sim={sim}{C.RESET}"
            )
        if len(fac_list) > 30:
            print(f"  {C.DIM}... +{len(fac_list) - 30} mas{C.RESET}")

    prompt("Enter para volver", allow_empty=True)


def part_vehicles(pn):
    """API 40031: Applicable vehicle models (standard)."""
    clean = re.sub(r"[^A-Za-z0-9]", "", pn)

    search = api_get(f"/?action=search_epc&query_part_number={clean}&query_match_type=exact")
    if not search or search.get("code") != 1 or not search.get("data"):
        warn("Parte no encontrada.")
        prompt("Enter para volver", allow_empty=True)
        return

    oem_hits = [d for d in search["data"] if d.get("Epc")]
    if not oem_hits:
        warn("No hay datos OEM para esta parte.")
        prompt("Enter para volver", allow_empty=True)
        return

    hit = oem_hits[0]
    group_id = hit.get("Group_id", "")

    subheader(f"Vehiculos compatibles con {pn}")
    url = f"/?action=get_modellist_from_part_number_and_group_id&part_number={clean}&group_id={group_id}"
    r = api_get(url)
    if not r or r.get("code") != 1:
        warn("Sin resultados.")
        prompt("Enter para volver", allow_empty=True)
        return

    data = r.get("data", {})
    total = data.get("TotalModelListStdRecords", 0)
    ml = data.get("ModelListStd") or []

    print(f"  {C.BOLD}Total modelos/variantes compatibles: {total}{C.RESET}")
    print(f"  {C.DIM}(Cada variante = combinacion unica de marca/modelo/version/motor/traccion){C.RESET}")
    print(f"  {C.DIM}(MSRP = precio de venta del vehiculo, NO de la parte){C.RESET}\n")

    seen = set()
    unique_models = []
    for m in ml:
        brand = m.get("Brand", "?")
        model = m.get("Model", "?")
        version = m.get("Sales_version", "")
        cc = m.get("CC") or m.get("Cc", "")
        engine = m.get("Engine_no", "")
        year = m.get("Model_year", "?")
        fuel = m.get("Fuel_type", "")
        driven = m.get("Driven_model", "")
        body = m.get("Body_type", "")
        trans = m.get("Transmission_detail", "")
        price = m.get("Price", "")
        begin = m.get("Date_begin", "")
        end = m.get("Date_end", "")

        key = f"{brand}|{model}|{version}|{cc}|{engine}|{year}"
        if key in seen:
            continue
        seen.add(key)

        desc = f"{brand} {model}"
        if version:
            desc += f" — {version}"

        line2_parts = []
        if year:
            line2_parts.append(f"Ano: {year}")
        if cc:
            line2_parts.append(f"Motor: {cc} {engine}".strip())
        if fuel:
            line2_parts.append(fuel)
        if driven:
            line2_parts.append(driven)
        if body:
            line2_parts.append(body)

        line3_parts = []
        if trans:
            line3_parts.append(f"Trans: {trans}")
        if begin:
            line3_parts.append(f"Periodo: {begin} → {end or '?'}")
        if price:
            line3_parts.append(f"MSRP: ¥{int(price):,}" if price.isdigit() else f"MSRP: {price} CNY")

        unique_models.append((desc, line2_parts, line3_parts))

    for desc, line2, line3 in unique_models[:30]:
        print(f"  {C.BOLD}{desc}{C.RESET}")
        if line2:
            print(f"    {' | '.join(line2)}")
        if line3:
            print(f"    {C.DIM}{' | '.join(line3)}{C.RESET}")
        print()

    if len(unique_models) > 30:
        print(f"  {C.DIM}... +{len(unique_models) - 30} variantes mas{C.RESET}")

    print(f"  {C.DIM}({len(unique_models)} variantes unicas de {total} registros totales){C.RESET}")
    prompt("Enter para volver", allow_empty=True)


def part_vehicles_aftermarket(pn):
    """API 40032: Aftermarket aggregated models."""
    clean = re.sub(r"[^A-Za-z0-9]", "", pn)

    search = api_get(f"/?action=search_epc&query_part_number={clean}&query_match_type=exact")
    if not search or search.get("code") != 1 or not search.get("data"):
        warn("Parte no encontrada.")
        prompt("Enter para volver", allow_empty=True)
        return

    oem_hits = [d for d in search["data"] if d.get("Epc")]
    if not oem_hits:
        warn("No hay datos OEM.")
        prompt("Enter para volver", allow_empty=True)
        return

    hit = oem_hits[0]
    group_id = hit.get("Group_id", "")

    subheader(f"Modelos aftermarket para {pn}")
    url = (
        f"/?action=get_modellist_from_part_number_and_group_id_for_aftermarket"
        f"&part_number={clean}&group_id={group_id}&based_on=engine"
    )
    r = api_get(url)
    if not r or r.get("code") != 1:
        warn("Sin resultados.")
        prompt("Enter para volver", allow_empty=True)
        return

    data = r.get("data", {})
    ml = data.get("ModelListStd_aftermarket_by_engine") or []

    if not ml:
        warn("Sin modelos aftermarket agrupados.")
        prompt("Enter para volver", allow_empty=True)
        return

    print(f"  {C.BOLD}Grupos de modelos (agrupados por motor): {len(ml)}{C.RESET}\n")
    for m in ml:
        brand = m.get("brand", "?")
        series = m.get("series", "?")
        model = m.get("model", "")
        cc = m.get("cc", "")
        years = m.get("model_years", "?")
        engines = m.get("engine_nos", "")
        factory = m.get("factory", "")

        print(f"  {C.BOLD}{brand} {series}{' (' + model + ')' if model and model != series else ''}{C.RESET} {cc}")
        details = []
        if years:
            details.append(f"Anos: {years}")
        if engines:
            details.append(f"Motores: {engines}")
        if factory:
            details.append(f"Fabrica: {factory}")
        if details:
            print(f"    {C.DIM}{' | '.join(details)}{C.RESET}")

    prompt("Enter para volver", allow_empty=True)


def part_price(pn):
    """API 4006: 4S dealer pricing."""
    clean = re.sub(r"[^A-Za-z0-9]", "", pn)
    subheader(f"Precio 4S para: {pn}")
    url = f"/?action=price&partnumber={clean}"
    r = api_get(url)

    if not r or r.get("code") != 1:
        warn(f"Sin precio disponible. (Los precios cubren principalmente el mercado chino)")
        prompt("Enter para volver", allow_empty=True)
        return

    prices = r.get("data") or []
    if not prices:
        warn("Sin datos de precio.")
        prompt("Enter para volver", allow_empty=True)
        return

    print(f"  {'Marca':<25s} {'Precio (CNY)':>15s}  PN")
    print(f"  {'─' * 60}")
    for p in prices:
        brand = p.get("Brand") or p.get("Factory") or "?"
        price = p.get("Price", "?")
        part_no = p.get("Partnumber_Original") or p.get("Partnumber", "")
        print(f"  {brand:<25s} {price:>15s}  {part_no}")

    prompt("Enter para volver", allow_empty=True)


def part_illustration(pn, epc):
    """API 4002 + 4005: Find illustration and show all parts in it."""
    clean = re.sub(r"[^A-Za-z0-9]", "", pn)
    subheader(f"Buscando ilustracion EPC para: {pn}")
    url = f"/{epc}?action=search_illustration&query_part_number={clean}"
    r = api_get(url)

    if not r or r.get("code") != 1:
        warn("Sin ilustracion encontrada para esta parte en este EPC.")
        prompt("Enter para volver", allow_empty=True)
        return

    sl = r.get("data", {}).get("searchlist") or []
    if not sl:
        warn("Sin resultados de ilustracion.")
        prompt("Enter para volver", allow_empty=True)
        return

    subheader(f"Ilustraciones encontradas ({len(sl)})")
    result = pick(
        sl,
        lambda s: (
            f"{(s.get('cata_name_en') or s.get('cata_name_zh') or '?'):40s} "
            f"{C.DIM}img={s.get('illustration_img_address', '?'):20s} "
            f"callout={s.get('callout', '?')}{C.RESET}"
        ),
        "Elige ilustracion"
    )

    if not result:
        return

    ill = result[1]
    cata_code = ill.get("cata_code", "")
    img_addr = ill.get("illustration_img_address", "")

    if img_addr:
        print(f"\n  {C.CYAN}Diagrama: http://resource.17vin.com/img/{epc}/{img_addr}{C.RESET}")

    subheader("Cargando partes de la ilustracion (API 4005)...")
    url2 = f"/{epc}?action=illustration&cata_code={cata_code}"
    r2 = api_get(url2)

    if not r2 or r2.get("code") != 1:
        warn("No se pudieron cargar las partes.")
        prompt("Enter para volver", allow_empty=True)
        return

    parts = r2.get("data", {}).get("partlist") or []
    hs_data = r2.get("data", {}).get("all_img_hotspots") or []

    if hs_data:
        hs = hs_data[0].get("img_hotspots", {})
        print(f"  {C.DIM}Imagen: {hs.get('img_width', '?')}x{hs.get('img_height', '?')} | {len(hs.get('hotspots', []))} hotspots{C.RESET}")

    subheader(f"Partes en ilustracion ({len(parts)})")
    for p in parts:
        callout = p.get("callout", "")
        part_no = p.get("partnumber", "?")
        name = p.get("name_en") or p.get("name_zh") or "?"
        qty = p.get("qty", "?")
        highlight = C.BOLD + C.GREEN if clean.upper() in part_no.upper() else ""
        reset = C.RESET if highlight else ""
        print(
            f"  {C.DIM}{callout:>8s}{C.RESET}  "
            f"{highlight}{part_no:18s}{reset} "
            f"{name[:40]:40s} "
            f"qty={qty}"
        )

    prompt("Enter para volver", allow_empty=True)


# ── Step 5: Search Part Number via VIN (API 5106) ──────────────────────────


def search_part_in_catalog(epc, vin, epc_id=None):
    pn = prompt("Numero OEM a buscar (ej: 091140G010)")
    subheader(f"Buscando {pn} en catalogo {epc}...")

    url = f"/{epc}?action=search_part_number&vin={vin}&query_match_type=exact&query_part_number={pn}"
    if epc_id:
        url += f"&epc_id={epc_id}"
    r = api_get(url)

    if not r or r.get("code") != 1:
        warn(f"Sin resultados para '{pn}'")
        return

    sl = r.get("data", {}).get("searchlist") or []
    if not sl:
        warn("Sin resultados en el catalogo de este vehiculo.")
        return

    subheader(f"Resultados ({len(sl)})")
    for s in sl:
        print(f"  {C.BOLD}{s.get('partnumber', '?')}{C.RESET}")
        print(f"    Categoria: {s.get('cata_name_en') or s.get('cata_name_zh', '?')}")
        print(f"    Nombre: {s.get('name_en') or s.get('name_zh', '?')}")
        print(f"    Callout: {s.get('callout', '?')}  |  Qty: {s.get('qty', '?')}")
        print(f"    Fechas: {s.get('begin_date', '?')} → {s.get('end_date', '?')}")
        if s.get("illustration_img_address"):
            print(f"    {C.DIM}Diagrama: http://resource.17vin.com/img/{epc}/{s['illustration_img_address']}{C.RESET}")
        print()

    prompt("Enter para volver", allow_empty=True)


# ── Step 6: All OE Numbers (API 5109) ──────────────────────────────────────


def _lookup_part_name(pn):
    """Quick API 4001 lookup to resolve a part number to its name."""
    clean = re.sub(r"[^A-Za-z0-9]", "", pn)
    r = api_get(f"/?action=search_epc&query_part_number={clean}&query_match_type=exact")
    if r and r.get("code") == 1 and r.get("data"):
        hit = r["data"][0]
        return hit.get("Part_name_en") or hit.get("Part_name_zh") or ""
    return ""


def _oe_part_detail_menu(pn, epc):
    """Detail menu for a selected OE part number — lookup + all sub-actions."""
    clean = re.sub(r"[^A-Za-z0-9]", "", pn)
    subheader(f"Buscando info de: {pn}")
    r = api_get(f"/?action=search_epc&query_part_number={clean}&query_match_type=exact")

    if not r or r.get("code") != 1 or not r.get("data"):
        warn(f"No se encontro '{pn}' en la base de datos.")
        prompt("Enter para volver", allow_empty=True)
        return

    results = r["data"]
    hit = results[0]
    part_name = hit.get("Part_name_en") or hit.get("Part_name_zh") or "?"
    brand = hit.get("Brand_name_en") or hit.get("Brand_name_zh") or "?"
    hit_epc = hit.get("Epc") or epc

    header(f"Parte: {pn}")
    info("Numero", pn)
    info("Nombre", part_name)
    info("Marcas", brand)
    info("EPC", hit_epc)
    if hit.get("Group_id"):
        info("Group ID", hit["Group_id"])
    if len(results) > 1:
        print(f"  {C.DIM}(tambien encontrada en {len(results) - 1} fuente(s) mas){C.RESET}")

    while True:
        print(f"\n  {C.BOLD}[1]{C.RESET} Buscar reemplazos / equivalencias (API 4004)")
        print(f"  {C.BOLD}[2]{C.RESET} Ver modelos compatibles (detallado por version/trim)")
        print(f"  {C.BOLD}[3]{C.RESET} Ver modelos compatibles (agrupado por motor)")
        print(f"  {C.BOLD}[4]{C.RESET} Consultar precio 4S (API 4006)")
        print(f"  {C.BOLD}[5]{C.RESET} Buscar ilustracion EPC (API 4002 + 4005)")
        print(f"  {C.BOLD}[B]{C.RESET} Volver a lista OE")

        action = prompt("Accion").lower()
        if action == "1":
            part_interchange(pn)
        elif action == "2":
            part_vehicles(pn)
        elif action == "3":
            part_vehicles_aftermarket(pn)
        elif action == "4":
            part_price(pn)
        elif action == "5":
            part_illustration(pn, hit_epc)
        elif action == "b":
            return


def dump_all_oe(epc, vin):
    subheader(f"Obteniendo TODOS los numeros OE ({epc})...")
    url = f"/{epc}?action=all_part_number&vin={vin}"
    r = api_get(url, timeout=60)

    if not r or r.get("code") != 1:
        warn("No se pudieron obtener los numeros OE.")
        return

    raw = r.get("data", "")
    if not isinstance(raw, str) or not raw.strip():
        warn("Sin numeros OE.")
        return

    parts = [p.strip() for p in raw.split("@") if p.strip()]
    subheader(f"Total numeros OE: {len(parts)}")

    per_page = 40
    page = 0
    total_pages = (len(parts) - 1) // per_page + 1

    while True:
        start = page * per_page
        end = min(start + per_page, len(parts))
        batch = parts[start:end]

        cols = 4
        for i in range(0, len(batch), cols):
            row = batch[i:i + cols]
            print("  " + "  ".join(f"{p:18s}" for p in row))

        nav_parts = []
        if page > 0:
            nav_parts.append("[P]rev")
        if page < total_pages - 1:
            nav_parts.append("[N]ext")
        nav_parts.append("[S] buscar en lista")
        nav_parts.append("[#] numero para ver detalle")
        nav_parts.append("[B]ack")
        nav_parts.append(f"Pag {page + 1}/{total_pages} ({len(parts)} total)")

        print(f"\n  {C.DIM}{' | '.join(nav_parts)}{C.RESET}")
        choice = prompt("Opcion")
        lc = choice.lower()

        if lc == "n" and page < total_pages - 1:
            page += 1
        elif lc == "p" and page > 0:
            page -= 1
        elif lc == "s":
            term = prompt("Buscar (parcial)")
            matches = [p for p in parts if term.upper() in p.upper()]
            if matches:
                subheader(f"Coincidencias: {len(matches)}")
                for idx, m in enumerate(matches[:40], 1):
                    print(f"    {C.BOLD}[{idx:>2}]{C.RESET} {m}")
                if len(matches) > 40:
                    print(f"    {C.DIM}... +{len(matches) - 40} mas (mostrando primeros 40){C.RESET}")

                sel = prompt("Numero para ver detalle (o Enter para volver)", allow_empty=True)
                if sel.isdigit():
                    idx = int(sel) - 1
                    if 0 <= idx < min(len(matches), 40):
                        _oe_part_detail_menu(matches[idx], epc)
            else:
                warn("Sin coincidencias.")
                prompt("Enter para continuar", allow_empty=True)
        elif lc == "b":
            return
        else:
            clean_input = re.sub(r"[^A-Za-z0-9 \-]", "", choice).strip()
            if clean_input:
                exact = [p for p in parts if re.sub(r"[^A-Za-z0-9]", "", p).upper() == re.sub(r"[^A-Za-z0-9]", "", clean_input).upper()]
                if exact:
                    _oe_part_detail_menu(exact[0], epc)
                else:
                    fuzzy = [p for p in parts if clean_input.upper() in p.upper()]
                    if len(fuzzy) == 1:
                        _oe_part_detail_menu(fuzzy[0], epc)
                    elif fuzzy:
                        subheader(f"Coincidencias: {len(fuzzy)}")
                        for idx, m in enumerate(fuzzy[:20], 1):
                            print(f"    {C.BOLD}[{idx:>2}]{C.RESET} {m}")
                        sel = prompt("Numero para ver detalle (o Enter para volver)", allow_empty=True)
                        if sel.isdigit():
                            idx = int(sel) - 1
                            if 0 <= idx < min(len(fuzzy), 20):
                                _oe_part_detail_menu(fuzzy[idx], epc)
                    else:
                        warn(f"'{clean_input}' no coincide con ningun numero OE en la lista.")


# ── Step 7: Factory Option Codes ────────────────────────────────────────────


def show_option_codes(decode_data):
    oepc_list = decode_data.get("model_original_epc_list") or []
    if not oepc_list:
        warn("Sin datos de opciones de fabrica.")
        prompt("Enter para volver", allow_empty=True)
        return

    for ep in oepc_list:
        attrs = ep.get("CarAttributes", [])
        en_attrs = [(a["Col_name"], a["Col_value"]) for a in attrs if a.get("Language") == "en"]

        if not en_attrs:
            en_attrs = [(a["Col_name"], a["Col_value"]) for a in attrs if a.get("Language") == "zh"]

        if not en_attrs:
            warn("Sin atributos disponibles.")
            continue

        subheader(f"Opciones de fabrica / atributos EPC ({len(en_attrs)} campos)")
        for name, val in en_attrs:
            is_major = any(k in name.lower() for k in (
                "model", "engine", "transmission", "grade", "body", "paint",
                "interior", "release", "delivery", "nation", "drive", "fuel", "year"
            ))
            if is_major:
                info(name, val)
            else:
                print(f"    {C.DIM}{name:45s}{C.RESET} {val}")

    prompt("Enter para volver", allow_empty=True)


# ── Step 8: Direct Part Number Lookup (no VIN context) ──────────────────────


def standalone_part_lookup():
    pn = prompt("Numero OEM o aftermarket a buscar")
    clean = re.sub(r"[^A-Za-z0-9]", "", pn)

    subheader(f"Buscando: {pn}")

    url = f"/?action=search_epc&query_part_number={clean}&query_match_type=smart"
    r = api_get(url)
    if not r or r.get("code") != 1 or not r.get("data"):
        warn("Sin resultados.")
        return

    results = r.get("data", [])
    subheader(f"Encontrado en {len(results)} fuente(s)")

    for d in results:
        epc_val = d.get("Epc") or "(aftermarket)"
        brand = d.get("Brand_name_en") or d.get("Brand_name_zh") or "?"
        part_name = d.get("Part_name_en") or d.get("Part_name_zh") or ""
        group_id = d.get("Group_id", "")

        print(f"  {C.BOLD}{d.get('Partnumber', '?')}{C.RESET}")
        print(f"    EPC: {epc_val}  |  Marcas: {brand}")
        if part_name:
            print(f"    Nombre: {part_name}")
        if group_id:
            print(f"    Group ID: {group_id}")
        print()

    oem_hits = [d for d in results if d.get("Epc")]
    if oem_hits:
        print(f"  {C.BOLD}[1]{C.RESET} Ver reemplazos / equivalencias (API 4004)")
        print(f"  {C.BOLD}[2]{C.RESET} Ver vehiculos compatibles (API 40031)")
        print(f"  {C.BOLD}[3]{C.RESET} Consultar precio 4S (API 4006)")
        print(f"  {C.BOLD}[B]{C.RESET} Volver")

        choice = prompt("Accion").lower()
        if choice == "1":
            part_interchange(pn)
        elif choice == "2":
            part_vehicles(pn)
        elif choice == "3":
            part_price(pn)
    else:
        prompt("Enter para volver", allow_empty=True)


# ── Main Loop ───────────────────────────────────────────────────────────────


def limited_browser(epc, vin, decode_data):
    """Fallback browser when VIN decode failed (code=0) but EPC was detected.
    EPC category navigation won't work, but part-level APIs do."""
    while True:
        header(f"Modo limitado: {epc.upper()} | VIN: {vin}")
        print(f"  {C.DIM}(VIN no decodificado — navegacion de categorias no disponible){C.RESET}")
        print(f"  {C.DIM}(Busca partes por numero OEM para acceder a cross-ref, precios, diagramas){C.RESET}\n")

        print(f"  {C.BOLD}[1]{C.RESET} Buscar parte por numero OEM (API 4001 + cross-ref)")
        print(f"  {C.BOLD}[2]{C.RESET} Buscar parte por numero con busqueda difusa")
        print(f"  {C.BOLD}[3]{C.RESET} Consultar precio 4S por numero OEM")
        print(f"  {C.BOLD}[B]{C.RESET} Volver a busqueda de placa")

        choice = prompt("Opcion").lower()

        if choice == "1":
            standalone_part_lookup()
        elif choice == "2":
            fuzzy_part_search(epc)
        elif choice == "3":
            pn = prompt("Numero OEM para precio")
            part_price(pn)
        elif choice == "b":
            return


def fuzzy_part_search(epc):
    """Search parts by partial OE number (inexact/fuzzy)."""
    pn = prompt("Numero parcial (min 5 caracteres, ej: 58101D3)")
    clean = re.sub(r"[^A-Za-z0-9]", "", pn)
    if len(clean) < 3:
        warn("Ingresa al menos 3 caracteres.")
        return

    subheader(f"Busqueda difusa: {pn}")
    url = f"/?action=search_epc&query_part_number={clean}&query_match_type=inexact"
    r = api_get(url)

    if not r or r.get("code") != 1 or not r.get("data"):
        warn("Sin resultados.")
        return

    results = r.get("data", [])
    subheader(f"Resultados ({len(results)})")

    items = []
    for d in results:
        epc_name = d.get("Epc") or "(aftermarket)"
        brand = d.get("Brand_name_en") or d.get("Brand_name_zh") or "?"
        part_name = d.get("Part_name_en") or d.get("Part_name_zh") or ""
        items.append(d)

    result = pick(
        items,
        lambda d: (
            f"{C.BOLD}{d.get('Partnumber', '?'):20s}{C.RESET} "
            f"{(d.get('Part_name_en') or d.get('Part_name_zh') or ''):30s} "
            f"{C.DIM}EPC={d.get('Epc') or 'aftermarket'} | {d.get('Brand_name_en') or ''}{C.RESET}"
        ),
        "Elige parte para mas opciones"
    )

    if not result:
        return

    selected = result[1]
    sel_pn = selected.get("Partnumber", "")
    sel_epc = selected.get("Epc") or epc

    while True:
        header(f"Parte: {sel_pn}")
        info("Numero", sel_pn)
        info("EPC", sel_epc)
        info("Marcas", selected.get("Brand_name_en"))
        info("Nombre", selected.get("Part_name_en") or selected.get("Part_name_zh"))

        print(f"\n  {C.BOLD}[1]{C.RESET} Buscar reemplazos / equivalencias (API 4004)")
        print(f"  {C.BOLD}[2]{C.RESET} Ver modelos compatibles (detallado por version/trim)")
        print(f"  {C.BOLD}[3]{C.RESET} Buscar ilustracion EPC (API 4002 + 4005)")
        print(f"  {C.BOLD}[4]{C.RESET} Consultar precio 4S (API 4006)")
        print(f"  {C.BOLD}[B]{C.RESET} Volver")

        action = prompt("Accion").lower()
        if action == "1":
            part_interchange(sel_pn)
        elif action == "2":
            part_vehicles(sel_pn)
        elif action == "3":
            part_illustration(sel_pn, sel_epc)
        elif action == "4":
            part_price(sel_pn)
        elif action == "b":
            return


# ── REMUSA Integration ──────────────────────────────────────────────────────


def _normalize_pn(pn):
    """Strip all non-alphanumeric chars and uppercase for comparison."""
    return re.sub(r"[^A-Za-z0-9]", "", pn).upper()


_remusa_cache = None

def _load_remusa_lookup():
    """Load REMUSA article codes, aliases, and alternos into normalized dicts.
    Returns (art_dict, alias_dict, alt_dict) where each maps normalized_code -> (original_code, articulo, descripcion).
    Results are cached for the session."""
    global _remusa_cache  # noqa: PLW0603
    if _remusa_cache is not None:
        return _remusa_cache
    conn = get_db_conn()
    cursor = conn.cursor()

    art_dict = {}
    cursor.execute("SELECT ARTICULO, DESCRIPCION FROM REMUSA.ARTICULO")
    for art, desc in cursor.fetchall():
        norm = _normalize_pn(art)
        if norm:
            art_dict[norm] = (art, art, desc or "")

    alias_dict = {}
    cursor.execute("SELECT ALIAS_PRODUCCION, ARTICULO, DESCRIPCION FROM REMUSA.ALIAS_PRODUCCION")
    for alias, art, desc in cursor.fetchall():
        norm = _normalize_pn(alias)
        if norm and norm not in art_dict:
            alias_dict[norm] = (alias, art, desc or "")

    alt_dict = {}
    cursor.execute("SELECT ARTICULO, ALTERNO FROM REMUSA.ARTICULO_ALTERNO")
    for art, alt in cursor.fetchall():
        norm = _normalize_pn(alt)
        if norm and norm not in art_dict and norm not in alias_dict:
            cursor2 = conn.cursor()
            cursor2.execute("SELECT DESCRIPCION FROM REMUSA.ARTICULO WHERE ARTICULO = %s", (art,))
            row = cursor2.fetchone()
            alt_dict[norm] = (alt, art, row[0] if row else "")

    _remusa_cache = (art_dict, alias_dict, alt_dict)
    return _remusa_cache


def show_remusa_detail(articulo_code, oe_code=None):
    """Display full REMUSA article info: costs, aliases, alternos, inventory.
    If oe_code is provided, also fetches 17VIN part info (name, diagram, etc.)."""
    conn = get_db_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT ARTICULO, DESCRIPCION, ACTIVO, MANUFACTURADOR, PROVEEDOR,
               ARTICULO_DEL_PROV, CLASIFICACION_1, CLASIFICACION_2,
               COSTO_ULT_LOC, COSTO_ULT_DOL, COSTO_PROM_LOC, COSTO_PROM_DOL,
               PRECIO_BASE_LOCAL, PRECIO_BASE_DOLAR,
               UNIDAD_ALMACEN, UNIDAD_VENTA,
               U_DIAMETRO, U_PASO, U_LARGO, U_GRADO, U_INFO_TECNICA
        FROM REMUSA.ARTICULO WHERE ARTICULO = %s
    """, (articulo_code,))
    row = cursor.fetchone()

    if not row:
        warn(f"Articulo '{articulo_code}' no encontrado en REMUSA.")
        prompt("Enter para volver", allow_empty=True)
        return

    (art, desc, activo, manuf, prov, art_prov, c1, c2,
     cult_l, cult_d, cprom_l, cprom_d, prc_l, prc_d,
     u_alm, u_ven, diam, paso, largo, grado, info_tec) = row

    # Classification descriptions
    c1_desc = c2_desc = ""
    if c1:
        cursor.execute("SELECT DESCRIPCION FROM REMUSA.CLASIFICACION WHERE CLASIFICACION = %s AND AGRUPACION = 1", (c1,))
        r = cursor.fetchone()
        c1_desc = r[0] if r else ""
    if c2:
        cursor.execute("SELECT DESCRIPCION FROM REMUSA.CLASIFICACION WHERE CLASIFICACION = %s AND AGRUPACION = 2", (c2,))
        r = cursor.fetchone()
        c2_desc = r[0] if r else ""

    # Show 17VIN OE part info if available
    search_pn = oe_code or articulo_code
    if oe_code:
        clean = re.sub(r"[^A-Za-z0-9]", "", oe_code)
        oe_data = api_get(f"/?action=search_epc&query_part_number={clean}&query_match_type=exact")
        if oe_data and oe_data.get("code") == 1 and oe_data.get("data"):
            hits = oe_data["data"]
            oem_hits = [d for d in hits if d.get("Epc")]
            best = oem_hits[0] if oem_hits else hits[0]
            subheader(f"Info OE (17VIN): {oe_code}")
            info("Numero OE", best.get("Partnumber") or oe_code)
            info("Nombre (EN)", best.get("Part_name_en"))
            info("Nombre (ZH)", best.get("Part_name_zh"))
            info("Marcas", best.get("Brand_name_en"))
            info("EPC", best.get("Epc"))
            img = best.get("Part_img")
            if img:
                info("Imagen", f"http://resource.17vin.com/img/{img}")

    header(f"REMUSA: {art}")
    info("Codigo", art)
    info("Descripcion", desc)
    info("Activo", "Si" if activo == "S" else "No")
    info("Familia", f"{c1} — {c1_desc}" if c1_desc else c1)
    info("Sub-familia", f"{c2} — {c2_desc}" if c2_desc else c2)
    info("Manufacturador", manuf)
    info("Proveedor", prov)
    info("Art. del Proveedor", art_prov)
    info("Unidad Almacen/Venta", f"{u_alm} / {u_ven}")

    if any([diam, paso, largo, grado]):
        subheader("Especificaciones")
        info("Diametro", diam)
        info("Paso", paso)
        info("Largo", largo)
        info("Grado", grado)
    if info_tec:
        info("Info Tecnica", info_tec[:120])

    subheader("Costos y Precios")
    print(f"  {'Concepto':<25} {'Colones (₡)':>15}   {'Dolares ($)':>12}")
    print(f"  {'─'*25} {'─'*15}   {'─'*12}")
    print(f"  {'Costo Ultimo':<25} ₡{cult_l:>13,.2f}   ${cult_d:>10,.2f}")
    print(f"  {'Costo Promedio':<25} ₡{cprom_l:>13,.2f}   ${cprom_d:>10,.2f}")
    print(f"  {'Precio Base':<25} ₡{prc_l:>13,.2f}   ${prc_d:>10,.2f}")

    # Aliases
    cursor.execute("""
        SELECT ALIAS_PRODUCCION, DESCRIPCION
        FROM REMUSA.ALIAS_PRODUCCION WHERE ARTICULO = %s
        ORDER BY ALIAS_PRODUCCION
    """, (articulo_code,))
    aliases = cursor.fetchall()
    diff_aliases = [(a, d) for a, d in aliases if a != articulo_code]
    if diff_aliases:
        subheader(f"Alias de Produccion ({len(diff_aliases)} diferentes)")
        for alias, alias_desc in diff_aliases:
            print(f"    {C.BOLD}{alias}{C.RESET}  {alias_desc or ''}")
    elif aliases:
        print(f"\n  {C.DIM}Alias: solo el mismo codigo ({len(aliases)} registro){C.RESET}")

    # Alternos
    cursor.execute("SELECT ALTERNO, PRIORIDAD FROM REMUSA.ARTICULO_ALTERNO WHERE ARTICULO = %s ORDER BY PRIORIDAD", (articulo_code,))
    alternos = cursor.fetchall()
    cursor.execute("SELECT ARTICULO, PRIORIDAD FROM REMUSA.ARTICULO_ALTERNO WHERE ALTERNO = %s ORDER BY PRIORIDAD", (articulo_code,))
    rev_alternos = cursor.fetchall()

    if alternos or rev_alternos:
        subheader("Articulos Alternos (Cross-Ref)")
        if alternos:
            for alt, prio in alternos:
                cursor.execute("SELECT DESCRIPCION FROM REMUSA.ARTICULO WHERE ARTICULO = %s", (alt,))
                r = cursor.fetchone()
                print(f"    → {C.BOLD}{alt}{C.RESET} (prio {prio}) {r[0] if r else ''}")
        if rev_alternos:
            for orig, prio in rev_alternos:
                cursor.execute("SELECT DESCRIPCION FROM REMUSA.ARTICULO WHERE ARTICULO = %s", (orig,))
                r = cursor.fetchone()
                print(f"    ← {C.BOLD}{orig}{C.RESET} (prio {prio}) {r[0] if r else ''}")

    # Inventory by bodega
    cursor.execute("""
        SELECT eb.BODEGA, b.NOMBRE,
               eb.CANT_DISPONIBLE, eb.CANT_RESERVADA, eb.CANT_TRANSITO,
               eb.CANT_PEDIDA, eb.CANT_VENCIDA, eb.CANT_NO_APROBADA,
               eb.COSTO_UNT_PROMEDIO_LOC
        FROM REMUSA.EXISTENCIA_BODEGA eb
        JOIN REMUSA.BODEGA b ON eb.BODEGA = b.BODEGA
        WHERE eb.ARTICULO = %s
          AND (eb.CANT_DISPONIBLE != 0 OR eb.CANT_RESERVADA != 0
               OR eb.CANT_TRANSITO != 0 OR eb.CANT_PEDIDA != 0
               OR eb.CANT_VENCIDA != 0 OR eb.CANT_NO_APROBADA != 0)
        ORDER BY eb.CANT_DISPONIBLE DESC
    """, (articulo_code,))
    bodegas = cursor.fetchall()

    subheader("Inventario por Bodega")
    if bodegas:
        print(f"  {'Bod':<5} {'Nombre':<30} {'Disp':>6} {'Reserv':>6} {'Trans':>6} {'Pedida':>6} {'Venc':>5} {'CostProm':>12}")
        print(f"  {'─'*5} {'─'*30} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*5} {'─'*12}")
        tot = [0, 0, 0, 0, 0]
        for bod, nombre, disp, res, trans, ped, venc, noapr, cprom in bodegas:
            print(f"  {bod:<5} {nombre:<30} {disp:>6,.0f} {res:>6,.0f} {trans:>6,.0f} {ped:>6,.0f} {venc:>5,.0f} ₡{cprom:>10,.2f}")
            tot[0] += disp; tot[1] += res; tot[2] += trans; tot[3] += ped; tot[4] += venc
        print(f"  {'─'*5} {'─'*30} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*5}")
        print(f"  {'':5} {'TOTAL':<30} {tot[0]:>6,.0f} {tot[1]:>6,.0f} {tot[2]:>6,.0f} {tot[3]:>6,.0f} {tot[4]:>5,.0f}")
    else:
        warn("Sin existencia en ninguna bodega.")

    # Collect all searchable codes for TecDoc fallback
    all_codes = [search_pn]
    if articulo_code != search_pn:
        all_codes.append(articulo_code)
    if diff_aliases:
        for alias, _ in diff_aliases:
            all_codes.append(alias)
    if alternos:
        for alt, _ in alternos:
            all_codes.append(alt)
    if rev_alternos:
        for orig, _ in rev_alternos:
            all_codes.append(orig)

    while True:
        print(f"\n  {C.BOLD}[T]{C.RESET} Buscar en TecDoc (specs, imagen, autos compatibles)")
        print(f"  {C.BOLD}[1]{C.RESET} Ver vehiculos compatibles (detallado por version/trim)")
        print(f"  {C.BOLD}[2]{C.RESET} Ver vehiculos compatibles (agrupado por motor)")
        print(f"  {C.BOLD}[3]{C.RESET} Buscar reemplazos / equivalencias (API 4004)")
        print(f"  {C.BOLD}[B]{C.RESET} Volver")

        choice = prompt("Accion").lower()

        if choice == "t":
            tecdoc_part_lookup(search_pn, fallback_codes=all_codes)
        elif choice == "1":
            part_vehicles(search_pn)
        elif choice == "2":
            part_vehicles_aftermarket(search_pn)
        elif choice == "3":
            part_interchange(search_pn)
        elif choice == "b" or choice == "":
            return


def remusa_match_oe(epc, vin):
    """Cross-reference all OE part numbers from 17VIN against REMUSA inventory."""
    subheader(f"Obteniendo TODOS los numeros OE ({epc})...")
    url = f"/{epc}?action=all_part_number&vin={vin}"
    r = api_get(url, timeout=60)

    if not r or r.get("code") != 1:
        warn("No se pudieron obtener los numeros OE del vehiculo.")
        prompt("Enter para volver", allow_empty=True)
        return

    raw = r.get("data", "")
    if not isinstance(raw, str) or not raw.strip():
        warn("Sin numeros OE.")
        return

    oe_parts = [p.strip() for p in raw.split("@") if p.strip()]
    total_oe = len(oe_parts)
    subheader(f"Total numeros OE del vehiculo: {total_oe}")

    print(f"  {C.DIM}Conectando a REMUSA (SOFTLAND)...{C.RESET}")
    try:
        art_dict, alias_dict, alt_dict = _load_remusa_lookup()
    except Exception as e:
        error(f"Error conectando a REMUSA DB: {e}")
        prompt("Enter para volver", allow_empty=True)
        return

    total_remusa = len(art_dict) + len(alias_dict) + len(alt_dict)
    print(f"  {C.DIM}REMUSA cargado: {len(art_dict):,} articulos + {len(alias_dict):,} aliases + {len(alt_dict):,} alternos{C.RESET}")

    print(f"  {C.DIM}Buscando coincidencias...{C.RESET}")
    matches = []
    for oe in oe_parts:
        norm = _normalize_pn(oe)
        if not norm:
            continue
        if norm in art_dict:
            orig, art_code, desc = art_dict[norm]
            matches.append((oe, art_code, "ARTICULO", desc))
        elif norm in alias_dict:
            orig, art_code, desc = alias_dict[norm]
            matches.append((oe, art_code, "ALIAS", desc))
        elif norm in alt_dict:
            orig, art_code, desc = alt_dict[norm]
            matches.append((oe, art_code, "ALTERNO", desc))

    if not matches:
        warn(f"Ninguna de las {total_oe} partes OE coincide con articulos en REMUSA.")
        prompt("Enter para volver", allow_empty=True)
        return

    pct = len(matches) * 100 / total_oe
    success(f"Encontradas {len(matches)} coincidencias de {total_oe} partes OE ({pct:.1f}%)")

    match_source_color = {"ARTICULO": C.GREEN, "ALIAS": C.CYAN, "ALTERNO": C.YELLOW}

    while True:
        result = pick(
            matches,
            lambda m: (
                f"{C.BOLD}{m[0]:22s}{C.RESET} → "
                f"{match_source_color.get(m[2], '')}{m[2]:8s}{C.RESET} "
                f"{C.BOLD}{m[1]:22s}{C.RESET}  {m[3]}"
            ),
            f"Elige parte para ver detalle REMUSA ({len(matches)} matches)"
        )

        if not result:
            return

        _, selected = result
        oe_code = selected[0]
        art_code = selected[1]
        show_remusa_detail(art_code, oe_code=oe_code)


def catalog_browser(epc, vin, epc_id, decode_data):
    while True:
        header(f"Catalogo EPC: {epc.upper()} | VIN: {vin}")

        print(f"  {C.BOLD}[1]{C.RESET} Navegar categorias EPC (diagramas + partes)")
        print(f"  {C.BOLD}[2]{C.RESET} Buscar parte por numero OEM (en este vehiculo)")
        print(f"  {C.BOLD}[3]{C.RESET} Ver TODOS los numeros OE del vehiculo ({C.CYAN}2500-3000 partes{C.RESET})")
        print(f"  {C.BOLD}[4]{C.RESET} Ver opciones de fabrica / atributos EPC")
        print(f"  {C.BOLD}[5]{C.RESET} Buscar parte por numero (sin contexto VIN)")
        print(f"  {C.BOLD}[6]{C.RESET} Consultar precio 4S por numero OEM")
        print(f"  {C.BOLD}[7]{C.RESET} Matches con REMUSA ({C.GREEN}cross-ref inventario local{C.RESET})")
        print(f"  {C.BOLD}[B]{C.RESET} Volver a busqueda de placa")

        choice = prompt("Opcion").lower()

        if choice == "1":
            cat = browse_categories(epc, vin, epc_id)
            if cat:
                subheader(f"Cargando partes: {cat['name']}")
                parts_data = get_parts(epc, vin, cat["cata_code"], cat["level"], epc_id)
                show_parts(parts_data, epc)

        elif choice == "2":
            search_part_in_catalog(epc, vin, epc_id)

        elif choice == "3":
            dump_all_oe(epc, vin)

        elif choice == "4":
            show_option_codes(decode_data)

        elif choice == "5":
            standalone_part_lookup()

        elif choice == "6":
            pn = prompt("Numero OEM para precio")
            part_price(pn)

        elif choice == "7":
            remusa_match_oe(epc, vin)

        elif choice == "b":
            return


def main():
    clear()
    header("PLACA → 17VIN  |  Costa Rica → EPC OEM + Cross-Reference + Precios")
    print(f"  {C.DIM}En cualquier momento: [Q] salir  [C] nueva placa{C.RESET}")

    balance, expiry = check_balance()
    print(f"  {C.DIM}Cuenta: {USERNAME} | Saldo: {balance} CNY | Expira: {expiry}{C.RESET}")

    while True:
        try:
            plate = input(f"\n{C.BOLD}  » Numero de placa (o 'q' salir, 'd' VIN directo, 'p' parte directa): {C.RESET}").strip()
            if not plate:
                continue
            if plate.lower() == "q":
                balance, expiry = check_balance()
                print(f"\n  {C.DIM}Saldo final: {balance} CNY | Expira: {expiry}{C.RESET}")
                print(f"{C.DIM}  Adios!{C.RESET}\n")
                break

            if plate.lower() == "d":
                vin = prompt("VIN (17 digitos)")
                plate_data = None
            elif plate.lower() == "p":
                standalone_part_lookup()
                continue
            else:
                subheader(f"Buscando placa: {plate}")
                plate_data = lookup_plate(plate)

                if not plate_data:
                    error("Placa no encontrada. Intenta de nuevo.")
                    continue

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

                vin = plate_data.get("VIN", "")

            if not vin or len(vin) != 17:
                error("VIN invalido o no encontrado.")
                continue

            # ── VIN Decode (API 3001) ──
            subheader(f"Decodificando VIN: {vin}")
            decode_result = vin_decode(vin)

            if not decode_result:
                error("Error de conexion con 17VIN API.")
                continue

            code = decode_result.get("code")
            msg = decode_result.get("msg", "")
            decode_data = decode_result.get("data", {})

            if code == 0:
                warn(f"VIN no encontrado en 17VIN: {msg}")
                epc = decode_data.get("epc", "") if isinstance(decode_data, dict) else ""
                if epc:
                    info("EPC detectado", epc)
                    info("Ano (VIN)", decode_data.get("model_year_from_vin"))
                    info("Pais fabricacion", decode_data.get("made_in_en"))
                    warn("El vehiculo puede ser muy nuevo o no estar en la base de datos.")
                    warn("La navegacion EPC por categorias no esta disponible,")
                    warn("pero puedes buscar partes por numero OEM directamente.")
                    limited_browser(epc, vin, decode_data)
                continue

            if code != 1:
                error(f"Error API: code={code}, msg={msg}")
                continue

            success(f"VIN decodificado correctamente")
            show_decode_result(decode_result)

            epc = decode_data.get("epc", "")
            epc_id = decode_data.get("epc_id", "")

            if not epc:
                error("No se pudo determinar el EPC. No se puede navegar el catalogo.")
                continue

            success(f"EPC: {epc.upper()} | EPC ID: {epc_id or 'N/A'}")

            # ── Catalog browser ──
            catalog_browser(epc, vin, epc_id, decode_data)

        except UserNewPlate:
            print(f"\n  {C.DIM}Volviendo a busqueda de placa...{C.RESET}")
            continue
        except UserQuit:
            balance, expiry = check_balance()
            print(f"\n  {C.DIM}Saldo final: {balance} CNY | Expira: {expiry}{C.RESET}")
            print(f"{C.DIM}  Adios!{C.RESET}\n")
            break
        except KeyboardInterrupt:
            print(f"\n{C.DIM}  Adios!{C.RESET}\n")
            break


if __name__ == "__main__":
    main()
