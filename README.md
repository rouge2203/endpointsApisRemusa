# Herramientas Remusa — Consulta de Placas, VIN y Repuestos

Herramientas para buscar vehículos por placa de Costa Rica, decodificar VIN,
consultar catálogos de repuestos OEM y gestionar datos en Softland.

---

## Cómo ejecutar desde GitHub (paso a paso)

> No necesitás instalar nada en tu computadora. Todo corre en el navegador.

### 1. Abrí el proyecto en GitHub Codespaces

1. Entrá al repositorio en GitHub (el link que te compartieron).
2. Hacé clic en el botón verde **"Code"**.
3. Seleccioná la pestaña **"Codespaces"**.
4. Hacé clic en **"Create codespace on main"**.

Esperá unos 30 segundos. Se va a abrir un editor de código con una **terminal**
en la parte de abajo — es como tener una computadora en la nube.

### 2. Instalá las dependencias

En la terminal (la parte negra de abajo), escribí este comando y presioná Enter:

```
pip install -r requirements.txt
```

Esto instala las librerías que necesita el sistema. Solo hay que hacerlo la
primera vez (o cuando se reinicia el Codespace).

### 3. Ejecutá el sistema

El único script que necesitás correr es **`SistemaRemusa.py`**. En la misma
terminal escribí:

```
python SistemaRemusa.py
```

El programa te va a pedir una placa y va a empezar a buscar. Desde ahí podés
navegar el catálogo de repuestos, ver referencias cruzadas y más.

> Los demás archivos del repositorio son scripts auxiliares de desarrollo.
> Como usuario solo necesitás usar `SistemaRemusa.py`.

### 4. Cuando haya cambios nuevos

Si te avisan que hay una actualización, en la terminal escribí:

```
git pull
```

Esto descarga la última versión del código. Después volvé a correr el sistema
con el mismo comando del paso 3.

---

## Variables de entorno (secretos)

El sistema necesita credenciales para conectarse a la base de datos.
**Nunca se suben al repositorio** — cada usuario las configura por aparte.

| Variable | Descripción |
|----------|-------------|
| `DB2_USER` | Usuario de SQL Server (Softland) |
| `DB2_HOST` | IP del servidor de base de datos |
| `DB2_PORT` | Puerto de SQL Server |
| `DB2_NAME` | Nombre de la base de datos |
| `DB2_PASSWORD` | Contraseña de SQL Server |

### Cómo agregar los secretos en GitHub Codespaces

1. Andá a [github.com](https://github.com) y hacé clic en tu foto de perfil (esquina superior derecha).
2. Seleccioná **"Settings"** (Configuración).
3. En el menú de la izquierda, bajá hasta **"Codespaces"**.
4. En la sección **"Codespaces secrets"**, hacé clic en **"New secret"**.
5. Agregá cada variable de la tabla de arriba con su valor correspondiente.
6. En **"Repository access"** seleccioná este repositorio.
7. Repetí para cada variable.

Los secretos se cargan automáticamente cada vez que abrís un Codespace.

### Opción local (si corrés los scripts en tu computadora)

Creá un archivo llamado `.env` en la carpeta del proyecto con este formato:

```
DB2_USER=tu_usuario
DB2_HOST=192.168.100.14
DB2_PORT=1433
DB2_NAME=SOFTLAND
DB2_PASSWORD=tu_contraseña
```

Este archivo **no se sube a GitHub** (está en `.gitignore`).

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

---

## Nota importante: acceso a la red

La base de datos Softland está en una **red local** (`192.168.100.14`).
Para conectarse desde GitHub Codespaces (que corre en la nube), se necesita
estar en la misma red o tener acceso por VPN/túnel. Si no hay conexión a la
base de datos, el sistema igual funciona para la parte de consulta de
placas y catálogos — solo falla la parte de escritura a Softland.
