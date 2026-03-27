# Herramientas Remusa — Consulta de Placas, VIN y Repuestos

Herramientas para buscar vehículos por placa de Costa Rica, decodificar VIN,
consultar catálogos de repuestos OEM y gestionar datos en Softland.

---

## Cómo ejecutar en tu computadora (paso a paso)

### 1. Instalá Python

Si no tenés Python instalado, descargalo desde [python.org/downloads](https://www.python.org/downloads/).

- Descargá la versión más reciente (botón amarillo grande).
- Durante la instalación en Windows, **marcá la casilla "Add Python to PATH"**
  antes de hacer clic en "Install Now".
- En Mac, Python ya viene preinstalado. Si no lo tenés, descargá el instalador
  de la misma página.

Para verificar que quedó instalado, abrí una terminal y escribí:

```
python --version
```

Si te muestra un número de versión (ej. `Python 3.12.x`), está listo.

> **¿Cómo abrir una terminal?**
> - **Windows:** Buscá "cmd" o "PowerShell" en el menú de inicio.
> - **Mac:** Abrí la aplicación "Terminal" (está en Aplicaciones → Utilidades).

### 2. Descargá el proyecto

1. Entrá al repositorio en GitHub (el link que te compartieron).
2. Hacé clic en el botón verde **"Code"**.
3. Seleccioná **"Download ZIP"**.
4. Descomprimí el archivo ZIP en una carpeta de tu computadora
   (por ejemplo, en el Escritorio).

### 3. Configurá la contraseña de la base de datos

Abrí la carpeta del proyecto descomprimida y creá un archivo nuevo llamado
**`.env`** (sin nombre, solo la extensión). Adentro escribí:

```
DB2_PASSWORD=aca_va_la_contraseña
```

Reemplazá `aca_va_la_contraseña` con la contraseña real (te la van a compartir
por aparte).

> **Tip para crear el archivo `.env`:**
> - **Windows:** Abrí el Bloc de Notas, escribí la línea de arriba, y guardalo
>   como `.env` (en "Tipo" seleccioná "Todos los archivos", no ".txt").
> - **Mac:** Abrí TextEdit, andá a Formato → "Convertir a texto sin formato",
>   escribí la línea y guardalo como `.env` en la carpeta del proyecto.

### 4. Conectate a la VPN

> **Importante:** Antes de ejecutar el sistema, asegurate de estar conectado
> a la **VPN de Remusa**. El sistema necesita acceso a la red interna para
> conectarse a la base de datos Softland. Si no estás conectado a la VPN,
> la parte de base de datos no va a funcionar.

### 5. Instalá las dependencias

Abrí una terminal, navegá hasta la carpeta del proyecto y ejecutá:

```
cd ruta/de/la/carpeta/endpointsApisRemusa-main
pip install -r requirements.txt
```

Reemplazá `ruta/de/la/carpeta/` con la ubicación real. Por ejemplo:

- **Windows:** `cd C:\Users\TuNombre\Desktop\endpointsApisRemusa-main`
- **Mac:** `cd ~/Desktop/endpointsApisRemusa-main`

Solo hay que hacerlo la primera vez.

### 6. Ejecutá el sistema

En la misma terminal escribí:

```
python SistemaRemusa.py
```

El programa te va a pedir una placa y va a empezar a buscar. Desde ahí podés
navegar el catálogo de repuestos, ver referencias cruzadas y más.

> Los demás archivos del repositorio son scripts auxiliares de desarrollo.
> Como usuario solo necesitás usar `SistemaRemusa.py`.

### 7. Cuando haya cambios nuevos

Si te avisan que hay una actualización:

1. Entrá de nuevo al repositorio en GitHub.
2. Hacé clic en **"Code"** → **"Download ZIP"**.
3. Descomprimí el ZIP nuevo y reemplazá los archivos viejos.
4. **No borres tu archivo `.env`** — ese es tu archivo de contraseña y no
   viene en la descarga.

Después volvé a correr el sistema con el mismo comando del paso 6.

---

## ¿Se puede usar desde GitHub Codespaces?

Codespaces permite correr código en el navegador sin instalar nada, pero tiene
una limitación: **no puede acceder a la red interna de Remusa**. La base de
datos Softland está en un servidor local (`192.168.100.14`) y Codespaces corre
en la nube de Microsoft, por lo que las funciones que escriben o leen de
Softland **no van a funcionar** desde Codespaces.

Las funciones de consulta de placas y catálogos de repuestos (que usan APIs
públicas) sí funcionan desde Codespaces. Pero para tener el sistema completo
con acceso a la base de datos, es necesario correrlo **localmente** siguiendo
los pasos de arriba.

---

## Archivos del proyecto

### Sistema principal (el que vas a usar)

| Archivo | Descripción |
|---------|-------------|
| **`SistemaRemusa.py`** | Sistema completo: placa → VIN → catálogo de repuestos → base de datos Softland |

Este es el **único archivo que necesitás ejecutar**. Todo lo demás son herramientas
de desarrollo.

### Scripts auxiliares (carpeta `scripts/` — solo para desarrollo)

| Script | Descripción |
|--------|-------------|
| `scripts/plate_to_17vin.py` | Placa → VIN → catálogo EPC de 17VIN (sin base de datos) |
| `scripts/plate_to_oem.py` | Placa → búsqueda de repuestos OEM |
| `scripts/plate_to_parts.py` | Placa → búsqueda de repuestos aftermarket |
| `scripts/softland_consultas.py` | Consultas directas a la base de datos Softland |
| `scripts/remusa_crossref_builder.py` | Construye tabla de referencias cruzadas en Softland |
