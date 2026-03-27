#!/usr/bin/env python3
"""
Softland ERP - Interactive Sales Query Tool (READ ONLY)
Database: SOFTLAND / Schema: REMUSA

Key tables:
  REMUSA.FACTURA        - Invoice headers (FECHA, CLIENTE, VENDEDOR, TOTAL_FACTURA, ANULADA)
  REMUSA.FACTURA_LINEA  - Invoice line items (ARTICULO, CANTIDAD, PRECIO_UNITARIO, PRECIO_TOTAL, COSTO_TOTAL)
  REMUSA.ARTICULO       - Products (DESCRIPCION, CLASIFICACION_1..6, PRECIO_BASE_LOCAL)
  REMUSA.VENDEDOR       - Sales agents (VENDEDOR code, NOMBRE)
  REMUSA.CLIENTE        - Customers (CLIENTE code, NOMBRE, VENDEDOR, ZONA)
  REMUSA.CLASIFICACION  - Product family classifications (F001=CLUTCH, F002=ELECTRICO, etc.)

TIPO_DOCUMENTO: 'F' = Factura, 'D' = Devolución/Nota Crédito
ANULADA: 'N' = active, 'S' = annulled
"""

import pymssql
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from decimal import Decimal
import re
import textwrap

load_dotenv()

DB_CONFIG = {
    "server": "192.168.100.14",
    "port": 1433,
    "user": "RemusaxLobster",
    "password": os.getenv("DB2_PASSWORD", ""),
    "database": "SOFTLAND",
}

SCHEMA = "REMUSA"

BLOCKED_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "EXEC", "EXECUTE", "MERGE", "GRANT", "REVOKE", "DENY",
    "BACKUP", "RESTORE", "SHUTDOWN", "DBCC",
]


def get_connection():
    return pymssql.connect(**DB_CONFIG)


def safe_query(sql: str) -> bool:
    upper = sql.upper().strip()
    for kw in BLOCKED_KEYWORDS:
        pattern = rf'\b{kw}\b'
        if re.search(pattern, upper):
            return False
    return upper.startswith("SELECT") or upper.startswith("WITH")


def run_query(sql: str, params=None):
    if not safe_query(sql):
        print("  *** BLOCKED: Only SELECT / read-only queries allowed ***")
        return []
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return rows
    finally:
        conn.close()


def fmt_money(val):
    if val is None:
        return "₡0"
    return f"₡{val:,.0f}"


def fmt_qty(val):
    if val is None:
        return "0"
    if val == int(val):
        return f"{int(val):,}"
    return f"{val:,.2f}"


def print_table(rows, columns=None, max_col_width=40):
    if not rows:
        print("  (sin resultados)")
        return
    if columns is None:
        columns = list(rows[0].keys())
    col_widths = {}
    for col in columns:
        header_w = len(str(col))
        max_val_w = max(len(str(row.get(col, ""))) for row in rows)
        col_widths[col] = min(max(header_w, max_val_w), max_col_width)
    header = " | ".join(str(col).ljust(col_widths[col])[:col_widths[col]] for col in columns)
    sep = "-+-".join("-" * col_widths[col] for col in columns)
    print(f"  {header}")
    print(f"  {sep}")
    for row in rows:
        line = " | ".join(
            str(row.get(col, "")).ljust(col_widths[col])[:col_widths[col]]
            for col in columns
        )
        print(f"  {line}")
    print(f"\n  ({len(rows)} filas)")


def get_date_range(period: str):
    """Return (start_date, end_date) for common period keywords."""
    now = datetime.now()
    if period in ("hoy", "today"):
        return now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d 23:59:59")
    elif period in ("esta semana", "this week"):
        start = now - timedelta(days=now.weekday())
        return start.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d 23:59:59")
    elif period in ("este mes", "this month", "mes"):
        return now.strftime("%Y-%m-01"), now.strftime("%Y-%m-%d 23:59:59")
    elif period in ("mes pasado", "last month"):
        first_this = now.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        return first_prev.strftime("%Y-%m-%d"), last_prev.strftime("%Y-%m-%d 23:59:59")
    elif period in ("este año", "año", "this year"):
        return now.strftime("%Y-01-01"), now.strftime("%Y-%m-%d 23:59:59")
    elif period in ("año pasado", "last year"):
        y = now.year - 1
        return f"{y}-01-01", f"{y}-12-31 23:59:59"
    else:
        return now.strftime("%Y-%m-01"), now.strftime("%Y-%m-%d 23:59:59")


# ═══════════════════════════════════════════════════════════════
# PREDEFINED QUERIES
# ═══════════════════════════════════════════════════════════════

def articulo_mas_vendido(period="este mes", top_n=20):
    """Top artículos más vendidos por cantidad y monto."""
    start, end = get_date_range(period)
    sql = f"""
    SELECT TOP {top_n}
        fl.ARTICULO,
        a.DESCRIPCION,
        c.DESCRIPCION AS FAMILIA,
        SUM(fl.CANTIDAD) AS TOTAL_CANT,
        SUM(fl.PRECIO_TOTAL) AS TOTAL_VENTA,
        SUM(fl.COSTO_TOTAL) AS TOTAL_COSTO,
        SUM(fl.PRECIO_TOTAL) - SUM(fl.COSTO_TOTAL) AS MARGEN,
        COUNT(DISTINCT f.FACTURA) AS NUM_FACTURAS
    FROM {SCHEMA}.FACTURA_LINEA fl
    JOIN {SCHEMA}.FACTURA f ON f.FACTURA = fl.FACTURA AND f.TIPO_DOCUMENTO = fl.TIPO_DOCUMENTO
    LEFT JOIN {SCHEMA}.ARTICULO a ON a.ARTICULO = fl.ARTICULO
    LEFT JOIN {SCHEMA}.CLASIFICACION c ON c.CLASIFICACION = a.CLASIFICACION_1
    WHERE f.TIPO_DOCUMENTO = 'F'
      AND f.ANULADA = 'N'
      AND fl.ANULADA = 'N'
      AND f.FECHA BETWEEN %s AND %s
    GROUP BY fl.ARTICULO, a.DESCRIPCION, c.DESCRIPCION
    ORDER BY SUM(fl.PRECIO_TOTAL) DESC
    """
    rows = run_query(sql, (start, end))
    print(f"\n  Top {top_n} Artículos Más Vendidos ({period}: {start[:10]} a {end[:10]})")
    print(f"  {'='*90}")
    for i, r in enumerate(rows, 1):
        margin_pct = (r["MARGEN"] / r["TOTAL_VENTA"] * 100) if r["TOTAL_VENTA"] else 0
        print(f"  {i:2d}. {r['ARTICULO']:<20s} | {str(r['DESCRIPCION'] or '')[:35]:<35s} | "
              f"Cant: {fmt_qty(r['TOTAL_CANT']):>8s} | Venta: {fmt_money(r['TOTAL_VENTA']):>12s} | "
              f"Margen: {margin_pct:.1f}% | Facs: {r['NUM_FACTURAS']}")
    return rows


def agente_mas_ventas(period="este mes"):
    """Ranking de vendedores por monto de ventas."""
    start, end = get_date_range(period)
    sql = f"""
    SELECT
        f.VENDEDOR,
        v.NOMBRE AS NOMBRE_VENDEDOR,
        COUNT(DISTINCT f.FACTURA) AS NUM_FACTURAS,
        SUM(f.TOTAL_MERCADERIA) AS TOTAL_MERCADERIA,
        SUM(f.TOTAL_FACTURA) AS TOTAL_FACTURA,
        COUNT(DISTINCT f.CLIENTE) AS NUM_CLIENTES
    FROM {SCHEMA}.FACTURA f
    LEFT JOIN {SCHEMA}.VENDEDOR v ON v.VENDEDOR = f.VENDEDOR
    WHERE f.TIPO_DOCUMENTO = 'F'
      AND f.ANULADA = 'N'
      AND f.FECHA BETWEEN %s AND %s
    GROUP BY f.VENDEDOR, v.NOMBRE
    ORDER BY SUM(f.TOTAL_FACTURA) DESC
    """
    rows = run_query(sql, (start, end))
    total_all = sum(r["TOTAL_FACTURA"] or 0 for r in rows)
    print(f"\n  Ranking de Vendedores ({period}: {start[:10]} a {end[:10]})")
    print(f"  Total general: {fmt_money(total_all)}")
    print(f"  {'='*100}")
    for i, r in enumerate(rows, 1):
        pct = (r["TOTAL_FACTURA"] / total_all * 100) if total_all else 0
        print(f"  {i:2d}. [{r['VENDEDOR']}] {str(r['NOMBRE_VENDEDOR'] or ''):30s} | "
              f"Facturas: {r['NUM_FACTURAS']:>5d} | Clientes: {r['NUM_CLIENTES']:>4d} | "
              f"Total: {fmt_money(r['TOTAL_FACTURA']):>14s} ({pct:.1f}%)")
    return rows


def clasificacion_ventas(period="este mes"):
    """Ventas por clasificación/familia de artículos."""
    start, end = get_date_range(period)
    sql = f"""
    SELECT
        a.CLASIFICACION_1 AS CLASIFICACION,
        c.DESCRIPCION AS FAMILIA,
        SUM(fl.CANTIDAD) AS TOTAL_CANT,
        SUM(fl.PRECIO_TOTAL) AS TOTAL_VENTA,
        SUM(fl.COSTO_TOTAL) AS TOTAL_COSTO,
        SUM(fl.PRECIO_TOTAL) - SUM(fl.COSTO_TOTAL) AS MARGEN,
        COUNT(DISTINCT fl.ARTICULO) AS NUM_ARTICULOS,
        COUNT(DISTINCT f.FACTURA) AS NUM_FACTURAS
    FROM {SCHEMA}.FACTURA_LINEA fl
    JOIN {SCHEMA}.FACTURA f ON f.FACTURA = fl.FACTURA AND f.TIPO_DOCUMENTO = fl.TIPO_DOCUMENTO
    LEFT JOIN {SCHEMA}.ARTICULO a ON a.ARTICULO = fl.ARTICULO
    LEFT JOIN {SCHEMA}.CLASIFICACION c ON c.CLASIFICACION = a.CLASIFICACION_1
    WHERE f.TIPO_DOCUMENTO = 'F'
      AND f.ANULADA = 'N'
      AND fl.ANULADA = 'N'
      AND f.FECHA BETWEEN %s AND %s
    GROUP BY a.CLASIFICACION_1, c.DESCRIPCION
    ORDER BY SUM(fl.PRECIO_TOTAL) DESC
    """
    rows = run_query(sql, (start, end))
    total_venta = sum(r["TOTAL_VENTA"] or 0 for r in rows)
    total_costo = sum(r["TOTAL_COSTO"] or 0 for r in rows)
    total_margen = total_venta - total_costo
    avg_margin = (total_margen / total_venta * 100) if total_venta else 0

    print(f"\n  Ventas por Clasificación ({period}: {start[:10]} a {end[:10]})")
    print(f"  Total Venta: {fmt_money(total_venta)} | Costo: {fmt_money(total_costo)} | Margen: {fmt_money(total_margen)} ({avg_margin:.1f}%)")
    print(f"  {'='*120}")
    print(f"  {'#':>3s}  {'CÓDIGO':<8s} {'FAMILIA':<30s} {'CANT':>10s} {'VENTA':>14s} {'COSTO':>14s} {'MARGEN':>14s} {'%MRG':>6s} {'ARTS':>5s} {'FACS':>5s} {'%PART':>6s}")
    print(f"  {'-'*120}")
    for i, r in enumerate(rows, 1):
        margin_pct = (r["MARGEN"] / r["TOTAL_VENTA"] * 100) if r["TOTAL_VENTA"] else 0
        part_pct = (r["TOTAL_VENTA"] / total_venta * 100) if total_venta else 0
        print(f"  {i:3d}  {str(r['CLASIFICACION'] or ''):8s} {str(r['FAMILIA'] or 'SIN CLASIF.')[:30]:30s} "
              f"{fmt_qty(r['TOTAL_CANT']):>10s} {fmt_money(r['TOTAL_VENTA']):>14s} {fmt_money(r['TOTAL_COSTO']):>14s} "
              f"{fmt_money(r['MARGEN']):>14s} {margin_pct:>5.1f}% {r['NUM_ARTICULOS']:>5d} {r['NUM_FACTURAS']:>5d} {part_pct:>5.1f}%")
    return rows


def resumen_ventas(period="este mes"):
    """Resumen general de ventas del periodo."""
    start, end = get_date_range(period)
    sql = f"""
    SELECT
        COUNT(DISTINCT CASE WHEN TIPO_DOCUMENTO='F' THEN FACTURA END) AS FACTURAS,
        COUNT(DISTINCT CASE WHEN TIPO_DOCUMENTO='D' THEN FACTURA END) AS DEVOLUCIONES,
        SUM(CASE WHEN TIPO_DOCUMENTO='F' THEN TOTAL_FACTURA ELSE 0 END) AS TOTAL_FACTURAS,
        SUM(CASE WHEN TIPO_DOCUMENTO='D' THEN TOTAL_FACTURA ELSE 0 END) AS TOTAL_DEVOLUCIONES,
        SUM(CASE WHEN TIPO_DOCUMENTO='F' THEN TOTAL_MERCADERIA ELSE 0 END) AS TOTAL_MERCADERIA,
        COUNT(DISTINCT CLIENTE) AS NUM_CLIENTES,
        COUNT(DISTINCT VENDEDOR) AS NUM_VENDEDORES,
        AVG(CASE WHEN TIPO_DOCUMENTO='F' THEN TOTAL_FACTURA END) AS PROMEDIO_FACTURA
    FROM {SCHEMA}.FACTURA
    WHERE ANULADA = 'N'
      AND FECHA BETWEEN %s AND %s
    """
    rows = run_query(sql, (start, end))
    if rows:
        r = rows[0]
        neto = (r["TOTAL_FACTURAS"] or 0) - (r["TOTAL_DEVOLUCIONES"] or 0)
        print(f"\n  ══════════════════════════════════════════")
        print(f"  RESUMEN DE VENTAS ({period}: {start[:10]} a {end[:10]})")
        print(f"  ══════════════════════════════════════════")
        print(f"  Facturas emitidas:    {r['FACTURAS']:>8,d}")
        print(f"  Devoluciones:         {r['DEVOLUCIONES']:>8,d}")
        print(f"  Total facturado:      {fmt_money(r['TOTAL_FACTURAS']):>14s}")
        print(f"  Total devoluciones:   {fmt_money(r['TOTAL_DEVOLUCIONES']):>14s}")
        print(f"  VENTA NETA:           {fmt_money(neto):>14s}")
        print(f"  Promedio por factura: {fmt_money(r['PROMEDIO_FACTURA']):>14s}")
        print(f"  Clientes atendidos:   {r['NUM_CLIENTES']:>8,d}")
        print(f"  Vendedores activos:   {r['NUM_VENDEDORES']:>8,d}")
        print(f"  ══════════════════════════════════════════")
    return rows


def ventas_por_dia(period="este mes"):
    """Ventas desglosadas por día."""
    start, end = get_date_range(period)
    sql = f"""
    SELECT
        CONVERT(VARCHAR(10), f.FECHA, 120) AS DIA,
        COUNT(DISTINCT f.FACTURA) AS FACTURAS,
        SUM(f.TOTAL_FACTURA) AS TOTAL,
        SUM(f.TOTAL_MERCADERIA) AS MERCADERIA,
        COUNT(DISTINCT f.CLIENTE) AS CLIENTES
    FROM {SCHEMA}.FACTURA f
    WHERE f.TIPO_DOCUMENTO = 'F'
      AND f.ANULADA = 'N'
      AND f.FECHA BETWEEN %s AND %s
    GROUP BY CONVERT(VARCHAR(10), f.FECHA, 120)
    ORDER BY DIA
    """
    rows = run_query(sql, (start, end))
    print(f"\n  Ventas por Día ({period})")
    print(f"  {'='*80}")
    total = sum(r["TOTAL"] or 0 for r in rows)
    max_total = max((r["TOTAL"] or 0) for r in rows) if rows else 1
    for r in rows:
        bar_len = int((r["TOTAL"] / max_total) * 30) if max_total else 0
        bar = "█" * bar_len
        print(f"  {r['DIA']} | Facs: {r['FACTURAS']:>4d} | Clientes: {r['CLIENTES']:>3d} | "
              f"{fmt_money(r['TOTAL']):>14s} {bar}")
    print(f"\n  Total periodo: {fmt_money(total)}")
    avg = total / len(rows) if rows else 0
    print(f"  Promedio diario: {fmt_money(avg)}")
    return rows


def top_clientes(period="este mes", top_n=20):
    """Top clientes por monto de compra."""
    start, end = get_date_range(period)
    sql = f"""
    SELECT TOP {top_n}
        f.CLIENTE,
        cl.NOMBRE AS NOMBRE_CLIENTE,
        v.NOMBRE AS VENDEDOR_NOMBRE,
        COUNT(DISTINCT f.FACTURA) AS NUM_FACTURAS,
        SUM(f.TOTAL_FACTURA) AS TOTAL_COMPRA
    FROM {SCHEMA}.FACTURA f
    LEFT JOIN {SCHEMA}.CLIENTE cl ON cl.CLIENTE = f.CLIENTE
    LEFT JOIN {SCHEMA}.VENDEDOR v ON v.VENDEDOR = f.VENDEDOR
    WHERE f.TIPO_DOCUMENTO = 'F'
      AND f.ANULADA = 'N'
      AND f.FECHA BETWEEN %s AND %s
    GROUP BY f.CLIENTE, cl.NOMBRE, v.NOMBRE
    ORDER BY SUM(f.TOTAL_FACTURA) DESC
    """
    rows = run_query(sql, (start, end))
    print(f"\n  Top {top_n} Clientes ({period}: {start[:10]} a {end[:10]})")
    print(f"  {'='*110}")
    for i, r in enumerate(rows, 1):
        print(f"  {i:2d}. [{r['CLIENTE']}] {str(r['NOMBRE_CLIENTE'] or '')[:35]:35s} | "
              f"Vendedor: {str(r['VENDEDOR_NOMBRE'] or '')[:20]:20s} | "
              f"Facs: {r['NUM_FACTURAS']:>4d} | Total: {fmt_money(r['TOTAL_COMPRA']):>14s}")
    return rows


def detalle_vendedor(vendedor_code: str, period="este mes"):
    """Detalle de ventas de un vendedor específico."""
    start, end = get_date_range(period)

    sql_header = f"""
    SELECT
        v.VENDEDOR, v.NOMBRE,
        COUNT(DISTINCT f.FACTURA) AS FACTURAS,
        SUM(f.TOTAL_FACTURA) AS TOTAL,
        COUNT(DISTINCT f.CLIENTE) AS CLIENTES,
        AVG(f.TOTAL_FACTURA) AS PROMEDIO
    FROM {SCHEMA}.FACTURA f
    JOIN {SCHEMA}.VENDEDOR v ON v.VENDEDOR = f.VENDEDOR
    WHERE f.TIPO_DOCUMENTO = 'F' AND f.ANULADA = 'N'
      AND f.VENDEDOR = %s
      AND f.FECHA BETWEEN %s AND %s
    GROUP BY v.VENDEDOR, v.NOMBRE
    """
    header = run_query(sql_header, (vendedor_code, start, end))
    if header:
        h = header[0]
        print(f"\n  Vendedor: [{h['VENDEDOR']}] {h['NOMBRE']}")
        print(f"  Periodo: {start[:10]} a {end[:10]}")
        print(f"  Facturas: {h['FACTURAS']} | Total: {fmt_money(h['TOTAL'])} | "
              f"Clientes: {h['CLIENTES']} | Promedio: {fmt_money(h['PROMEDIO'])}")

    sql_detail = f"""
    SELECT TOP 15
        fl.ARTICULO,
        a.DESCRIPCION,
        SUM(fl.CANTIDAD) AS CANT,
        SUM(fl.PRECIO_TOTAL) AS VENTA
    FROM {SCHEMA}.FACTURA_LINEA fl
    JOIN {SCHEMA}.FACTURA f ON f.FACTURA = fl.FACTURA AND f.TIPO_DOCUMENTO = fl.TIPO_DOCUMENTO
    LEFT JOIN {SCHEMA}.ARTICULO a ON a.ARTICULO = fl.ARTICULO
    WHERE f.TIPO_DOCUMENTO = 'F' AND f.ANULADA = 'N' AND fl.ANULADA = 'N'
      AND f.VENDEDOR = %s
      AND f.FECHA BETWEEN %s AND %s
    GROUP BY fl.ARTICULO, a.DESCRIPCION
    ORDER BY SUM(fl.PRECIO_TOTAL) DESC
    """
    detail = run_query(sql_detail, (vendedor_code, start, end))
    if detail:
        print(f"\n  Top artículos vendidos:")
        for i, r in enumerate(detail, 1):
            print(f"    {i:2d}. {r['ARTICULO']:<20s} {str(r['DESCRIPCION'] or '')[:40]:<40s} "
                  f"Cant: {fmt_qty(r['CANT']):>8s} | {fmt_money(r['VENTA']):>12s}")
    return header, detail


def comparar_meses(num_meses=6):
    """Comparar ventas de los últimos N meses."""
    from calendar import monthrange
    now = datetime.now()
    print(f"\n  Comparativo Últimos {num_meses} Meses")
    print(f"  {'='*90}")
    results = []
    cur_y, cur_m = now.year, now.month
    months = []
    for i in range(num_meses):
        m = cur_m - i
        y = cur_y
        while m <= 0:
            m += 12
            y -= 1
        months.append((y, m))
    months.reverse()
    for y, m in months:
        start = f"{y}-{m:02d}-01"
        if y == cur_y and m == cur_m:
            end = now.strftime("%Y-%m-%d 23:59:59")
        else:
            last_day = monthrange(y, m)[1]
            end = f"{y}-{m:02d}-{last_day} 23:59:59"

        sql = f"""
        SELECT
            COUNT(DISTINCT FACTURA) AS FACS,
            ISNULL(SUM(TOTAL_FACTURA), 0) AS TOTAL,
            ISNULL(SUM(TOTAL_MERCADERIA), 0) AS MERC,
            COUNT(DISTINCT CLIENTE) AS CLIS,
            COUNT(DISTINCT VENDEDOR) AS VENDS
        FROM {SCHEMA}.FACTURA
        WHERE TIPO_DOCUMENTO = 'F' AND ANULADA = 'N'
          AND FECHA BETWEEN %s AND %s
        """
        rows = run_query(sql, (start, end))
        if rows:
            r = rows[0]
            results.append({"mes": f"{y}-{m:02d}", **r})

    max_total = max(r["TOTAL"] for r in results) if results else 1
    for r in results:
        bar_len = int((r["TOTAL"] / max_total) * 30) if max_total else 0
        bar = "█" * bar_len
        print(f"  {r['mes']} | Facs: {r['FACS']:>5,d} | Clis: {r['CLIS']:>4,d} | "
              f"{fmt_money(r['TOTAL']):>14s} {bar}")
    return results


def margen_por_clasificacion(period="este mes"):
    """Análisis de márgenes por clasificación."""
    start, end = get_date_range(period)
    sql = f"""
    SELECT
        a.CLASIFICACION_1 AS CLASIF,
        c.DESCRIPCION AS FAMILIA,
        SUM(fl.PRECIO_TOTAL) AS VENTA,
        SUM(fl.COSTO_TOTAL) AS COSTO,
        SUM(fl.PRECIO_TOTAL) - SUM(fl.COSTO_TOTAL) AS MARGEN,
        CASE WHEN SUM(fl.PRECIO_TOTAL) > 0
             THEN (SUM(fl.PRECIO_TOTAL) - SUM(fl.COSTO_TOTAL)) / SUM(fl.PRECIO_TOTAL) * 100
             ELSE 0 END AS PCT_MARGEN,
        AVG(fl.PRECIO_UNITARIO) AS PRECIO_PROMEDIO,
        COUNT(DISTINCT fl.ARTICULO) AS ARTICULOS
    FROM {SCHEMA}.FACTURA_LINEA fl
    JOIN {SCHEMA}.FACTURA f ON f.FACTURA = fl.FACTURA AND f.TIPO_DOCUMENTO = fl.TIPO_DOCUMENTO
    LEFT JOIN {SCHEMA}.ARTICULO a ON a.ARTICULO = fl.ARTICULO
    LEFT JOIN {SCHEMA}.CLASIFICACION c ON c.CLASIFICACION = a.CLASIFICACION_1
    WHERE f.TIPO_DOCUMENTO = 'F' AND f.ANULADA = 'N' AND fl.ANULADA = 'N'
      AND f.FECHA BETWEEN %s AND %s
    GROUP BY a.CLASIFICACION_1, c.DESCRIPCION
    HAVING SUM(fl.PRECIO_TOTAL) > 0
    ORDER BY SUM(fl.PRECIO_TOTAL) - SUM(fl.COSTO_TOTAL) DESC
    """
    rows = run_query(sql, (start, end))
    total_margen = sum(r["MARGEN"] or 0 for r in rows)

    print(f"\n  Análisis de Márgenes por Clasificación ({period})")
    print(f"  Margen total: {fmt_money(total_margen)}")
    print(f"  {'='*130}")
    print(f"  {'CLASIF':<8s} {'FAMILIA':<30s} {'VENTA':>14s} {'COSTO':>14s} {'MARGEN':>14s} {'%MRG':>7s} {'PREC.PROM':>12s} {'ARTS':>5s} {'%PART.MRG':>10s}")
    print(f"  {'-'*130}")
    for r in rows:
        part_mrg = (r["MARGEN"] / total_margen * 100) if total_margen else 0
        print(f"  {str(r['CLASIF'] or ''):8s} {str(r['FAMILIA'] or 'N/A')[:30]:30s} "
              f"{fmt_money(r['VENTA']):>14s} {fmt_money(r['COSTO']):>14s} {fmt_money(r['MARGEN']):>14s} "
              f"{r['PCT_MARGEN']:>6.1f}% {fmt_money(r['PRECIO_PROMEDIO']):>12s} {r['ARTICULOS']:>5d} {part_mrg:>9.1f}%")
    return rows


def buscar_articulo(texto: str):
    """Buscar artículos por código o descripción."""
    sql = f"""
    SELECT TOP 20
        a.ARTICULO, a.DESCRIPCION, a.CLASIFICACION_1,
        c.DESCRIPCION AS FAMILIA,
        a.PRECIO_BASE_LOCAL, a.ACTIVO,
        a.COSTO_PROM_LOC
    FROM {SCHEMA}.ARTICULO a
    LEFT JOIN {SCHEMA}.CLASIFICACION c ON c.CLASIFICACION = a.CLASIFICACION_1
    WHERE a.ARTICULO LIKE %s OR a.DESCRIPCION LIKE %s
    ORDER BY a.ARTICULO
    """
    pattern = f"%{texto}%"
    rows = run_query(sql, (pattern, pattern))
    print(f"\n  Búsqueda de artículos: '{texto}'")
    print(f"  {'='*120}")
    for r in rows:
        margin = ""
        if r["PRECIO_BASE_LOCAL"] and r["COSTO_PROM_LOC"] and r["PRECIO_BASE_LOCAL"] > 0:
            m_pct = (r["PRECIO_BASE_LOCAL"] - r["COSTO_PROM_LOC"]) / r["PRECIO_BASE_LOCAL"] * 100
            margin = f"Mrg:{m_pct:.0f}%"
        print(f"  {r['ARTICULO']:<20s} {str(r['DESCRIPCION'] or '')[:45]:<45s} "
              f"Fam: {str(r['FAMILIA'] or '')[:15]:15s} "
              f"Precio: {fmt_money(r['PRECIO_BASE_LOCAL']):>10s} Costo: {fmt_money(r['COSTO_PROM_LOC']):>10s} "
              f"{margin:>8s} {'✓' if r['ACTIVO'] == 'S' else '✗'}")
    return rows


def historial_articulo(articulo_code: str, period="este año"):
    """Historial de ventas de un artículo específico."""
    start, end = get_date_range(period)
    sql = f"""
    SELECT
        CONVERT(VARCHAR(7), f.FECHA, 120) AS MES,
        SUM(fl.CANTIDAD) AS CANT,
        SUM(fl.PRECIO_TOTAL) AS VENTA,
        SUM(fl.COSTO_TOTAL) AS COSTO,
        COUNT(DISTINCT f.FACTURA) AS FACS,
        COUNT(DISTINCT f.CLIENTE) AS CLIS
    FROM {SCHEMA}.FACTURA_LINEA fl
    JOIN {SCHEMA}.FACTURA f ON f.FACTURA = fl.FACTURA AND f.TIPO_DOCUMENTO = fl.TIPO_DOCUMENTO
    WHERE f.TIPO_DOCUMENTO = 'F' AND f.ANULADA = 'N' AND fl.ANULADA = 'N'
      AND fl.ARTICULO = %s
      AND f.FECHA BETWEEN %s AND %s
    GROUP BY CONVERT(VARCHAR(7), f.FECHA, 120)
    ORDER BY MES
    """
    rows = run_query(sql, (articulo_code, start, end))
    art_info = run_query(
        f"SELECT ARTICULO, DESCRIPCION FROM {SCHEMA}.ARTICULO WHERE ARTICULO = %s",
        (articulo_code,)
    )
    nombre = art_info[0]["DESCRIPCION"] if art_info else articulo_code

    print(f"\n  Historial: {articulo_code} - {nombre} ({period})")
    print(f"  {'='*90}")
    max_v = max((r["VENTA"] or 0) for r in rows) if rows else 1
    for r in rows:
        bar_len = int((r["VENTA"] / max_v) * 25) if max_v else 0
        bar = "█" * bar_len
        print(f"  {r['MES']} | Cant: {fmt_qty(r['CANT']):>8s} | Venta: {fmt_money(r['VENTA']):>12s} | "
              f"Facs: {r['FACS']:>4d} | Clis: {r['CLIS']:>3d} {bar}")
    return rows


def sql_libre(query: str):
    """Execute a free-form read-only SQL query."""
    if not safe_query(query):
        print("  *** BLOCKED: Only SELECT queries are allowed ***")
        return []
    rows = run_query(query)
    print_table(rows)
    return rows


# ═══════════════════════════════════════════════════════════════
# INTERACTIVE MENU
# ═══════════════════════════════════════════════════════════════

MENU = """
╔══════════════════════════════════════════════════════════════╗
║        SOFTLAND ERP - Consultas de Ventas (READ ONLY)       ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1.  Resumen de ventas                                       ║
║  2.  Top artículos más vendidos                              ║
║  3.  Ranking de vendedores (agentes)                         ║
║  4.  Ventas por clasificación/familia                        ║
║  5.  Ventas por día                                          ║
║  6.  Top clientes                                            ║
║  7.  Detalle de un vendedor                                  ║
║  8.  Comparar últimos meses                                  ║
║  9.  Márgenes por clasificación                              ║
║  10. Buscar artículo                                         ║
║  11. Historial de un artículo                                ║
║  12. SQL libre (solo SELECT)                                 ║
║                                                              ║
║  Periodos: hoy, esta semana, este mes, mes pasado,           ║
║            este año, año pasado                               ║
║                                                              ║
║  q/salir = Salir                                             ║
╚══════════════════════════════════════════════════════════════╝
"""


def ask_period():
    p = input("  Periodo [este mes]: ").strip()
    return p if p else "este mes"


def interactive():
    print(MENU)

    try:
        conn = get_connection()
        conn.close()
        print("  ✓ Conexión a SQL Server exitosa\n")
    except Exception as e:
        print(f"  ✗ Error de conexión: {e}")
        return

    while True:
        try:
            choice = input("\n  Opción (1-12, q=salir): ").strip().lower()

            if choice in ("q", "salir", "exit", "quit"):
                print("\n  ¡Hasta luego!")
                break

            elif choice == "1":
                period = ask_period()
                resumen_ventas(period)

            elif choice == "2":
                period = ask_period()
                n = input("  Top N [20]: ").strip()
                n = int(n) if n else 20
                articulo_mas_vendido(period, n)

            elif choice == "3":
                period = ask_period()
                agente_mas_ventas(period)

            elif choice == "4":
                period = ask_period()
                clasificacion_ventas(period)

            elif choice == "5":
                period = ask_period()
                ventas_por_dia(period)

            elif choice == "6":
                period = ask_period()
                n = input("  Top N [20]: ").strip()
                n = int(n) if n else 20
                top_clientes(period, n)

            elif choice == "7":
                code = input("  Código vendedor (ej: 001, 008): ").strip()
                period = ask_period()
                detalle_vendedor(code, period)

            elif choice == "8":
                n = input("  Últimos N meses [6]: ").strip()
                n = int(n) if n else 6
                comparar_meses(n)

            elif choice == "9":
                period = ask_period()
                margen_por_clasificacion(period)

            elif choice == "10":
                texto = input("  Texto a buscar (código o descripción): ").strip()
                buscar_articulo(texto)

            elif choice == "11":
                code = input("  Código artículo: ").strip()
                period = ask_period()
                historial_articulo(code, period)

            elif choice == "12":
                print("  Ingrese su query SELECT (terminar con ;):")
                lines = []
                while True:
                    line = input("  sql> ").strip()
                    lines.append(line)
                    if line.endswith(";"):
                        break
                query = " ".join(lines).rstrip(";")
                sql_libre(query)

            else:
                print("  Opción no válida. Intente de nuevo.")

        except KeyboardInterrupt:
            print("\n\n  ¡Hasta luego!")
            break
        except Exception as e:
            print(f"\n  Error: {e}")


if __name__ == "__main__":
    interactive()
