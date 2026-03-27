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

### 4. Configurá la contraseña de la base de datos (solo la primera vez)

El sistema necesita la contraseña de la base de datos Softland para funcionar.
Los demás datos de conexión ya están configurados en el código.

Para agregar la contraseña como secreto en GitHub Codespaces:

1. Andá a [github.com](https://github.com) y hacé clic en tu foto de perfil (esquina superior derecha).
2. Seleccioná **"Settings"** (Configuración).
3. En el menú de la izquierda, bajá hasta **"Codespaces"**.
4. En la sección **"Codespaces secrets"**, hacé clic en **"New secret"**.
5. En **Name** escribí: `DB2_PASSWORD`
6. En **Value** escribí la contraseña (te la van a compartir por aparte).
7. En **"Repository access"** hacé clic en **"Select repositories"** y seleccioná
   el repositorio **endpointsApisRemusa**. Esto es necesario para que el secreto
   esté disponible cuando abrás el Codespace de este proyecto.
8. Hacé clic en **"Add secret"**.

Este secreto se carga automáticamente cada vez que abrís un Codespace.
Solo hay que hacerlo una vez.

### 5. Conectate a la VPN antes de correr el sistema

> **Importante:** Antes de ejecutar `SistemaRemusa.py`, asegurate de estar
> conectado a la **VPN de Remusa**. El sistema necesita acceso a la red
> interna para conectarse a la base de datos Softland. Si no estás conectado
> a la VPN, la parte de base de datos no va a funcionar.

### 6. Cuando haya cambios nuevos

Si te avisan que hay una actualización, en la terminal escribí:

```
git pull
```

Esto descarga la última versión del código. Después volvé a correr el sistema
con el mismo comando del paso 3.

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

