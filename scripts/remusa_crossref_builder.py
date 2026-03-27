#!/usr/bin/env python3
"""
REMUSA Cross-Reference Builder

Enriches REMUSA's ALIAS_PRODUCCION table by searching TecDoc for
OEM and aftermarket equivalents of existing REMUSA article codes.

Flow:
  1. Connect to REMUSA (SOFTLAND) database
  2. Show CLASIFICACION_1 options with article counts
  3. User picks a classification (e.g. FAJAS)
  4. Gather all codes: ARTICULO + ALIAS_PRODUCCION + ARTICULO_ALTERNO
  5. For each code → TecDoc _Analog_Spare_Parts_by_OEM (1 API call)
  6. Collect all equivalent OEM + aftermarket codes found
  7. Generate .sql file with INSERT statements for ALIAS_PRODUCCION
  8. Show summary → ask user to review → optionally execute

TecDoc Endpoint:
  GET /artlookup/search-for-analogue-of-spare-parts-by-oem-number
  Host: tecdoc-catalog.p.rapidapi.com
  Returns: aftermarket articles with their OEM cross-refs

Requires:
  - RAPIDAPI_KEY env var
  - pymssql (pip install pymssql)
  - DB2_PASSWORD environment variable
"""

import os
import re
import sys
import time
import json
import datetime
import requests
import pymssql

# ── Config ──────────────────────────────────────────────────────────────────

TECDOC_BASE = "https://tecdoc-catalog.p.rapidapi.com"
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
TECDOC_HEADERS = {
    "x-rapidapi-host": "tecdoc-catalog.p.rapidapi.com",
    "x-rapidapi-key": RAPIDAPI_KEY,
}
LANG_ID = 8   # Español
TYPE_ID = 1   # Passenger car

# ── Colors ──────────────────────────────────────────────────────────────────

class C:
    BOLD = "\033[1m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    DIM = "\033[2m"
    MAGENTA = "\033[95m"
    RESET = "\033[0m"

# ── Helpers ─────────────────────────────────────────────────────────────────

def header(title):
    w = 70
    print(f"\n{C.CYAN}{'═' * w}")
    print(f"  {C.BOLD}{title}{C.RESET}{C.CYAN}")
    print(f"{'═' * w}{C.RESET}\n")


def subheader(title):
    print(f"\n{C.GREEN}── {title} {'─' * max(0, 55 - len(title))}{C.RESET}\n")


def info(label, value):
    if value and str(value).strip():
        print(f"  {C.BOLD}{label:.<30}{C.RESET} {value}")


def warn(msg):
    print(f"  {C.YELLOW}⚠  {msg}{C.RESET}")


def error(msg):
    print(f"  {C.RED}✖  {msg}{C.RESET}")


def ok(msg):
    print(f"  {C.GREEN}✔  {msg}{C.RESET}")


def prompt(msg, allow_empty=False):
    while True:
        val = input(f"\n  {C.BOLD}» {msg}: {C.RESET}").strip()
        if val or allow_empty:
            return val


def normalize(code):
    return re.sub(r"[^A-Za-z0-9]", "", code).upper()


def progress_bar(current, total, width=40, extra=""):
    pct = current / total if total else 0
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    print(f"\r  {C.CYAN}[{bar}] {current}/{total} ({pct:.0%}){C.RESET} {extra}", end="", flush=True)


# ── .env loader ─────────────────────────────────────────────────────────────

def load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def get_db_conn():
    return pymssql.connect(
        server="192.168.100.14",
        port=1433,
        user="RemusaxLobster",
        password=os.environ.get("DB2_PASSWORD", ""),
        database="SOFTLAND",
        charset="UTF-8",
    )


# ── TecDoc API ──────────────────────────────────────────────────────────────

def tecdoc_search_analogues(part_number):
    """Search TecDoc for analogue/equivalent parts by OEM number.
    Returns list of dicts with articleNo, supplierName, oemNumbers, etc."""
    clean = re.sub(r"[^A-Za-z0-9]", "", part_number)
    url = (
        f"{TECDOC_BASE}/artlookup/search-for-analogue-of-spare-parts-by-oem-number"
        f"/oem-number/{clean}/lang-id/{LANG_ID}/type-id/{TYPE_ID}"
    )
    try:
        resp = requests.get(url, headers=TECDOC_HEADERS, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("data", data.get("articles", []))
        return []
    except Exception:
        return []


def extract_codes_from_tecdoc(results):
    """Extract all unique part codes from TecDoc analogue results."""
    codes = {}
    for article in results:
        art_no = article.get("articleNo", "")
        supplier = article.get("supplierName", "")
        if art_no:
            codes[normalize(art_no)] = {
                "code": art_no,
                "brand": supplier,
                "type": "AFTERMARKET",
            }

        for oem in article.get("oemNumbers", []):
            oem_no = oem.get("oemNumber", "")
            oem_brand = oem.get("mfrName", "")
            if oem_no:
                norm = normalize(oem_no)
                if norm not in codes:
                    codes[norm] = {
                        "code": oem_no,
                        "brand": oem_brand,
                        "type": "OEM",
                    }

    return codes


# ── DB queries (READ-ONLY) ─────────────────────────────────────────────────

def get_classifications(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.CLASIFICACION_1, c.DESCRIPCION, COUNT(*) as cnt
        FROM REMUSA.ARTICULO a
        LEFT JOIN REMUSA.CLASIFICACION c
          ON a.CLASIFICACION_1 = c.CLASIFICACION AND c.AGRUPACION = 1
        WHERE a.CLASIFICACION_1 IS NOT NULL AND a.CLASIFICACION_1 != ''
        GROUP BY a.CLASIFICACION_1, c.DESCRIPCION
        ORDER BY cnt DESC
    """)
    return cursor.fetchall()


def get_articles_for_classification(conn, clasif1):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ARTICULO, DESCRIPCION
        FROM REMUSA.ARTICULO
        WHERE CLASIFICACION_1 = %s
    """, (clasif1,))
    return cursor.fetchall()


def get_existing_aliases(conn, articulo):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ALIAS_PRODUCCION FROM REMUSA.ALIAS_PRODUCCION
        WHERE ARTICULO = %s
    """, (articulo,))
    return {normalize(row[0]) for row in cursor.fetchall()}


def get_existing_alternos(conn, articulo):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ALTERNO FROM REMUSA.ARTICULO_ALTERNO
        WHERE ARTICULO = %s
    """, (articulo,))
    return {normalize(row[0]) for row in cursor.fetchall()}


def get_all_known_codes(conn):
    """Load all codes already in REMUSA (ARTICULO + ALIAS + ALTERNO) as normalized set."""
    cursor = conn.cursor()
    known = set()

    cursor.execute("SELECT ARTICULO FROM REMUSA.ARTICULO")
    for row in cursor.fetchall():
        known.add(normalize(row[0]))

    cursor.execute("SELECT ALIAS_PRODUCCION FROM REMUSA.ALIAS_PRODUCCION")
    for row in cursor.fetchall():
        known.add(normalize(row[0]))

    cursor.execute("SELECT ALTERNO FROM REMUSA.ARTICULO_ALTERNO")
    for row in cursor.fetchall():
        known.add(normalize(row[0]))

    return known


# ── Main Flow ───────────────────────────────────────────────────────────────

def pick_classification(conn):
    classifications = get_classifications(conn)
    if not classifications:
        error("No classifications found.")
        return None

    subheader(f"Clasificaciones disponibles ({len(classifications)} familias)")
    for i, (code, desc, cnt) in enumerate(classifications, 1):
        label = f"{desc}" if desc else code
        print(f"  {C.BOLD}[{i:3d}]{C.RESET} {label:<40s} {C.DIM}({cnt} articulos){C.RESET}")

    choice = prompt("Selecciona clasificacion (numero)")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(classifications):
            return classifications[idx]
    except ValueError:
        pass
    error("Opcion invalida.")
    return None


def process_classification(conn, clasif_code, clasif_desc, article_count):
    header(f"Procesando: {clasif_desc or clasif_code} ({article_count} articulos)")

    # Step 1: Get all articles
    print(f"  {C.DIM}Cargando articulos de REMUSA...{C.RESET}")
    articles = get_articles_for_classification(conn, clasif_code)
    print(f"  {C.GREEN}✔ {len(articles)} articulos cargados{C.RESET}")

    # Step 2: Load all known codes in REMUSA
    print(f"  {C.DIM}Cargando todos los codigos existentes en REMUSA...{C.RESET}")
    all_known = get_all_known_codes(conn)
    print(f"  {C.GREEN}✔ {len(all_known)} codigos ya conocidos en REMUSA{C.RESET}")

    # Step 3: Gather unique codes to search per article
    print(f"  {C.DIM}Recopilando codigos por articulo (ARTICULO + ALIAS + ALTERNO)...{C.RESET}")
    article_codes = {}
    for art, desc in articles:
        codes_to_search = set()
        codes_to_search.add(art.strip())

        existing_aliases = get_existing_aliases(conn, art)
        for alias_norm in existing_aliases:
            if alias_norm:
                codes_to_search.add(alias_norm)

        existing_alternos = get_existing_alternos(conn, art)
        for alt_norm in existing_alternos:
            if alt_norm:
                codes_to_search.add(alt_norm)

        article_codes[art] = {
            "desc": desc or "",
            "search_codes": codes_to_search,
        }

    total_unique_codes = sum(len(v["search_codes"]) for v in article_codes.values())
    print(f"  {C.GREEN}✔ {total_unique_codes} codigos unicos a buscar en TecDoc{C.RESET}")

    # Step 4: Search TecDoc for each code
    subheader("Buscando en TecDoc (esto puede tomar varios minutos)")
    new_inserts = []
    articles_with_matches = 0
    articles_without_matches = 0
    total_new_codes = 0
    api_calls = 0
    api_errors = 0
    already_searched = set()
    start_time = time.time()

    art_list = list(article_codes.items())
    total_arts = len(art_list)

    for art_idx, (articulo, art_info) in enumerate(art_list):
        found_new_for_this = False

        for code in art_info["search_codes"]:
            norm_code = normalize(code)
            if norm_code in already_searched or not norm_code:
                continue
            already_searched.add(norm_code)

            api_calls += 1
            elapsed = time.time() - start_time
            rate = api_calls / elapsed if elapsed > 0 else 0
            eta = (total_unique_codes - api_calls) / rate if rate > 0 else 0
            eta_str = f"ETA {int(eta // 60)}m{int(eta % 60)}s" if api_calls > 5 else "calculando..."

            progress_bar(
                art_idx + 1, total_arts,
                extra=f"{C.DIM}API:{api_calls} | +{total_new_codes} nuevos | {eta_str}  {code[:20]:<20s}{C.RESET}"
            )

            results = tecdoc_search_analogues(code)
            if results is None:
                api_errors += 1
                continue

            if not results:
                continue

            equivalent_codes = extract_codes_from_tecdoc(results)

            for norm, code_info in equivalent_codes.items():
                if norm in all_known:
                    continue
                if norm == normalize(articulo):
                    continue

                new_inserts.append({
                    "alias": code_info["code"],
                    "articulo": articulo,
                    "descripcion": art_info["desc"],
                    "brand": code_info["brand"],
                    "type": code_info["type"],
                    "source_code": code,
                })
                all_known.add(norm)
                total_new_codes += 1
                found_new_for_this = True

            time.sleep(0.15)

        if found_new_for_this:
            articles_with_matches += 1
        else:
            articles_without_matches += 1

    print()  # newline after progress bar

    # Step 5: Summary
    elapsed_total = time.time() - start_time
    subheader("Resumen")
    info("Clasificacion", f"{clasif_desc or clasif_code} ({clasif_code})")
    info("Articulos procesados", str(total_arts))
    info("Llamadas API TecDoc", str(api_calls))
    info("Errores API", str(api_errors))
    info("Tiempo total", f"{int(elapsed_total // 60)}m {int(elapsed_total % 60)}s")
    print()
    ok(f"{articles_with_matches} articulos CON matches ({total_new_codes} codigos nuevos encontrados)")
    if articles_without_matches:
        warn(f"{articles_without_matches} articulos SIN matches en TecDoc")

    if not new_inserts:
        warn("No se encontraron codigos nuevos para agregar.")
        return

    # Step 6: Generate SQL script
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    safe_name = re.sub(r"[^A-Za-z0-9]", "_", clasif_desc or clasif_code)
    sql_filename = f"remusa_alias_{safe_name}_{timestamp}.sql"
    sql_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), sql_filename)

    generate_sql(new_inserts, sql_path, clasif_desc or clasif_code)

    ok(f"Script SQL generado: {sql_filename}")
    info("Total INSERTs", str(len(new_inserts)))
    print(f"\n  {C.DIM}Revisa el archivo antes de ejecutar.{C.RESET}")

    # Step 7: Ask to execute
    choice = prompt("Ejecutar el script SQL? (s/n)").lower()
    if choice == "s":
        execute_sql(conn, sql_path)
    else:
        print(f"\n  {C.DIM}Script guardado en: {sql_path}{C.RESET}")
        print(f"  {C.DIM}Puedes ejecutarlo manualmente cuando lo revises.{C.RESET}")


def generate_sql(inserts, filepath, clasif_label):
    """Generate a .sql file with INSERT statements for ALIAS_PRODUCCION."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"-- REMUSA Cross-Reference Builder\n")
        f.write(f"-- Clasificacion: {clasif_label}\n")
        f.write(f"-- Generado: {datetime.datetime.now().isoformat()}\n")
        f.write(f"-- Total inserts: {len(inserts)}\n")
        f.write(f"-- Fuente: TecDoc _Analog_Spare_Parts_by_OEM\n")
        f.write(f"--\n")
        f.write(f"-- IMPORTANTE: Solo ejecuta despues de revisar.\n")
        f.write(f"-- Estos INSERTs agregan codigos equivalentes a ALIAS_PRODUCCION\n")
        f.write(f"-- para que coincidan al buscar por codigo OEM o aftermarket.\n")
        f.write(f"--\n\n")

        f.write(f"BEGIN TRANSACTION;\n\n")

        current_art = None
        for ins in inserts:
            if ins["articulo"] != current_art:
                current_art = ins["articulo"]
                f.write(f"\n-- Articulo: {current_art} | {ins['descripcion']}\n")

            alias_escaped = ins["alias"].replace("'", "''")
            art_escaped = ins["articulo"].replace("'", "''")
            brand = ins["brand"]
            code_type = ins["type"]
            desc = ins["descripcion"].replace("'", "''")

            f.write(
                f"INSERT INTO REMUSA.ALIAS_PRODUCCION (ALIAS_PRODUCCION, ARTICULO, DESCRIPCION) "
                f"SELECT '{alias_escaped}', '{art_escaped}', '{desc}' "
                f"WHERE NOT EXISTS (SELECT 1 FROM REMUSA.ALIAS_PRODUCCION "
                f"WHERE ALIAS_PRODUCCION = '{alias_escaped}' AND ARTICULO = '{art_escaped}');"
                f"  -- {code_type} | {brand}\n"
            )

        f.write(f"\n-- Verifica los datos antes de confirmar:\n")
        f.write(f"-- Si todo esta correcto, ejecuta COMMIT;\n")
        f.write(f"-- Si algo esta mal, ejecuta ROLLBACK;\n\n")
        f.write(f"-- COMMIT;\n")
        f.write(f"-- ROLLBACK;\n")


def execute_sql(conn, sql_path):
    """Execute the generated SQL file against REMUSA."""
    subheader("Ejecutando script SQL")

    with open(sql_path, "r", encoding="utf-8") as f:
        content = f.read()

    statements = []
    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        if line.upper() in ("BEGIN TRANSACTION;", "COMMIT;", "ROLLBACK;"):
            continue
        if line.endswith(";"):
            stmt = line.rsplit("--", 1)[0].strip().rstrip(";")
            if stmt:
                statements.append(stmt)

    if not statements:
        warn("No se encontraron statements validos.")
        return

    cursor = conn.cursor()
    executed = 0
    errors = 0

    for i, stmt in enumerate(statements, 1):
        progress_bar(i, len(statements), extra=f"{C.DIM}+{executed} ok | {errors} err{C.RESET}")
        try:
            cursor.execute(stmt)
            executed += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"\n  {C.RED}Error [{i}]: {str(e)[:80]}{C.RESET}")

    print()

    if errors:
        warn(f"{errors} errores durante ejecucion.")
        choice = prompt("COMMIT cambios de todas formas? (s/n)").lower()
        if choice != "s":
            conn.rollback()
            warn("ROLLBACK ejecutado. Ningun cambio aplicado.")
            return

    conn.commit()
    ok(f"{executed} registros insertados exitosamente en ALIAS_PRODUCCION.")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    if not RAPIDAPI_KEY:
        error("RAPIDAPI_KEY no configurada!")
        error("Ejecuta: export RAPIDAPI_KEY=tu_clave_aqui")
        sys.exit(1)

    load_dotenv()

    header("REMUSA Cross-Reference Builder")
    print(f"  {C.DIM}Enriquece ALIAS_PRODUCCION con codigos equivalentes de TecDoc{C.RESET}")
    print(f"  {C.DIM}Endpoint: _Analog_Spare_Parts_by_OEM (1 call por codigo){C.RESET}")

    print(f"\n  {C.DIM}Conectando a REMUSA (SOFTLAND)...{C.RESET}")
    try:
        conn = get_db_conn()
        ok("Conectado a base de datos")
    except Exception as e:
        error(f"No se pudo conectar: {e}")
        sys.exit(1)

    while True:
        selected = pick_classification(conn)
        if not selected:
            continue

        clasif_code, clasif_desc, count = selected

        print(f"\n  {C.BOLD}Seleccionado:{C.RESET} {clasif_desc or clasif_code} ({clasif_code})")
        info("Articulos", str(count))

        confirm = prompt(f"Procesar {count} articulos? (s/n)").lower()
        if confirm != "s":
            continue

        process_classification(conn, clasif_code, clasif_desc, count)

        another = prompt("Procesar otra clasificacion? (s/n)").lower()
        if another != "s":
            break

    print(f"\n  {C.DIM}Fin.{C.RESET}\n")


if __name__ == "__main__":
    main()
