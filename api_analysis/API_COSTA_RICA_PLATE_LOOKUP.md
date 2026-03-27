# API Documentation: Costa Rica License Plate Lookup

> **Generated:** 2026-03-25 | **Provider:** RegCheck.org.uk | **Country:** Costa Rica

---

## 1. Endpoint

```
GET https://www.regcheck.org.uk/api/reg.asmx/CheckCostaRica
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `RegistrationNumber` | string | Yes | The Costa Rican license plate number (e.g., `DEV-404`, `681636`, `BKT385`) |
| `username` | string | Yes | API username for authentication |

### Example Request
```
GET https://www.regcheck.org.uk/api/reg.asmx/CheckCostaRica?RegistrationNumber=DEV-404&username=jruiz2203
```

### Plate Number Formats Supported
| Format | Example | Type |
|--------|---------|------|
| Letters-Numbers | `DEV-404` | Standard private vehicle |
| Numbers only | `681636` | Older numeric plates |
| Letters+Numbers | `BKT385` | Mixed format |

---

## 2. Response Format

The API returns an **XML document** containing a `vehicleJson` field with a JSON string, plus structured XML fields under `vehicleData`.

### JSON Response Schema (`vehicleJson`)

```json
{
  "Description": "string — Full make + model description",
  "CarMake": {
    "CurrentTextValue": "string — Manufacturer name"
  },
  "CarModel": {
    "CurrentTextValue": "string — Model name"
  },
  "MakeDescription": {
    "CurrentTextValue": "string — Manufacturer (same as CarMake)"
  },
  "ModelDescription": {
    "CurrentTextValue": "string — Model (same as CarModel)"
  },
  "EngineSize": {
    "CurrentTextValue": "string — Engine displacement (e.g., '2000 C.C')"
  },
  "RegistrationYear": "string — Year (e.g., '2026')",
  "Body": "string — Body type in Spanish",
  "Transmission": "string — Transmission type (may be empty)",
  "Fuel": "string — Fuel type in Spanish",
  "Cabin": "string — Cabin type or 'NO APLICA' / 'DESCONOCIDO'",
  "WheelPlan": "string — Drive configuration (e.g., '4X2', '4X4')",
  "VIN": "string — Vehicle Identification Number",
  "Colour": "string — Color in Spanish",
  "EngineCode": "string — Engine serial/code or 'NOEXISTE'",
  "owner": "string — Full owner name + ID number",
  "ImageUrl": "string — URL to vehicle image on placa.co.cr"
}
```

### Field Reference

| Field | Type | Description | Example Values |
|-------|------|-------------|----------------|
| `Description` | string | Full vehicle description | `"HYUNDAI TUCSON GL"`, `"KIA SPORTAGE EX"` |
| `CarMake.CurrentTextValue` | string | Manufacturer | `"HYUNDAI"`, `"KIA"` |
| `CarModel.CurrentTextValue` | string | Model + trim | `"TUCSON GL"`, `"SPORTAGE EX"`, `"ACCENT GLS"` |
| `EngineSize.CurrentTextValue` | string | Engine displacement in CC | `"2000 C.C"`, `"1991 C.C"`, `"1600 C.C"` |
| `RegistrationYear` | string | Registration/model year | `"2026"`, `"2007"`, `"2012"` |
| `Body` | string | Body style (Spanish) | `"TODO TERRENO 4 PUERTAS"`, `"SEDAN 4 PUERTAS"` |
| `Transmission` | string | Transmission type | `""` (often empty) |
| `Fuel` | string | Fuel type (Spanish) | `"GASOLINA"`, `"DIESEL"` |
| `Cabin` | string | Cabin config | `"NO APLICA"`, `"DESCONOCIDO"` |
| `WheelPlan` | string | Drive type | `"4X2"`, `"4X4"` |
| `VIN` | string | Full 17-char VIN | `"KMHJB81DBTU408502"` |
| `Colour` | string | Color (Spanish) | `"VERDE"`, `"DORADO"`, `"GRIS"` |
| `EngineCode` | string | Engine serial number | `"G4NLSU982315"`, `"D4EA6H255054"`, `"NOEXISTE"` |
| `owner` | string | Owner full name + cédula | `"RUIZ CALVO CARLOS ENRIQUE (701010926)"` |
| `ImageUrl` | string | Vehicle image URL | `"http://www.placa.co.cr/image.aspx/@..."` |

---

## 3. Sample Responses

### Sample 1: `DEV-404` — Hyundai Tucson GL (2026)

| Field | Value |
|-------|-------|
| **Plate** | DEV-404 |
| **Description** | HYUNDAI TUCSON GL |
| **Make** | HYUNDAI |
| **Model** | TUCSON GL |
| **Year** | 2026 |
| **Engine** | 2000 C.C |
| **Engine Code** | G4NLSU982315 |
| **Body** | TODO TERRENO 4 PUERTAS (SUV 4-door) |
| **Fuel** | GASOLINA (Gasoline) |
| **Drivetrain** | 4X2 |
| **Color** | VERDE (Green) |
| **VIN** | KMHJB81DBTU408502 |
| **Owner** | RUIZ CALVO CARLOS ENRIQUE (701010926) |

---

### Sample 2: `681636` — Kia Sportage EX (2007)

| Field | Value |
|-------|-------|
| **Plate** | 681636 |
| **Description** | KIA SPORTAGE EX |
| **Make** | KIA |
| **Model** | SPORTAGE EX |
| **Year** | 2007 |
| **Engine** | 1991 C.C |
| **Engine Code** | D4EA6H255054 |
| **Body** | TODO TERRENO 4 PUERTAS (SUV 4-door) |
| **Fuel** | DIESEL |
| **Drivetrain** | 4X4 |
| **Color** | DORADO (Gold) |
| **VIN** | KNAJE551877340075 |
| **Owner** | HURTADO HURTADO XINIA MARICELA (205290625) |

---

### Sample 3: `BKT385` — Hyundai Accent GLS (2012)

| Field | Value |
|-------|-------|
| **Plate** | BKT385 |
| **Description** | HYUNDAI ACCENT GLS |
| **Make** | HYUNDAI |
| **Model** | ACCENT GLS |
| **Year** | 2012 |
| **Engine** | 1600 C.C |
| **Engine Code** | NOEXISTE |
| **Body** | SEDAN 4 PUERTAS (Sedan 4-door) |
| **Fuel** | GASOLINA (Gasoline) |
| **Drivetrain** | 4X2 |
| **Color** | GRIS (Gray) |
| **VIN** | KMHCT4AE9CU158089 |
| **Owner** | PADILLA VARGAS JEYMI DE LOS ANGELES (117390725) |

---

## 4. Spanish → English Field Value Translations

### Body Types
| Spanish | English |
|---------|---------|
| TODO TERRENO 4 PUERTAS | SUV / All-Terrain 4-Door |
| SEDAN 4 PUERTAS | Sedan 4-Door |
| SEDAN 2 PUERTAS | Coupe 2-Door |
| PICK UP | Pickup Truck |
| STATION WAGON | Station Wagon |

### Fuel Types
| Spanish | English |
|---------|---------|
| GASOLINA | Gasoline |
| DIESEL | Diesel |
| ELECTRICO | Electric |
| HIBRIDO | Hybrid |

### Colors
| Spanish | English |
|---------|---------|
| VERDE | Green |
| DORADO | Gold |
| GRIS | Gray |
| BLANCO | White |
| NEGRO | Black |
| ROJO | Red |
| AZUL | Blue |
| PLATA / PLATEADO | Silver |

### Other
| Spanish | English |
|---------|---------|
| NO APLICA | Not Applicable |
| DESCONOCIDO | Unknown |
| NOEXISTE | Does Not Exist |

---

## 5. Data Source

The data originates from the **Costa Rican National Vehicle Registry** (Registro Nacional), served via:
- **API Gateway:** `regcheck.org.uk` (UK-based vehicle data aggregator)
- **Image Source:** `placa.co.cr` (Costa Rican plate lookup service)

### Data Available Per Lookup
| Data Point | Available |
|------------|-----------|
| Make & Model | Yes |
| Year | Yes |
| Engine Size (CC) | Yes |
| Engine Code/Serial | Yes (when registered) |
| Body Type | Yes |
| Fuel Type | Yes |
| Drivetrain (2WD/4WD) | Yes |
| Color | Yes |
| VIN | Yes |
| Transmission | Partial (often empty) |
| Owner Name | Yes |
| Owner ID (Cédula) | Yes |
| Vehicle Image | Yes (via placa.co.cr) |

---

## 6. Integration Notes

### Request
- **Method:** GET
- **Content-Type:** XML response (wrapping JSON)
- **Auth:** Username passed as query parameter (no API key header)
- **Rate Limits:** Unknown — use responsibly

### Parsing the Response
The response is XML. To extract vehicle data:

```python
import requests
import json
import xml.etree.ElementTree as ET

def lookup_plate_cr(plate, username="jruiz2203"):
    url = "https://www.regcheck.org.uk/api/reg.asmx/CheckCostaRica"
    params = {
        "RegistrationNumber": plate,
        "username": username
    }
    resp = requests.get(url, params=params)

    # Parse XML
    root = ET.fromstring(resp.text)

    # Extract the vehicleJson field (namespace may vary)
    ns = {'ns': 'http://regcheck.org.uk'}
    vehicle_json_str = root.find('.//ns:vehicleJson', ns).text

    # Parse the embedded JSON
    vehicle = json.loads(vehicle_json_str)

    return {
        "plate": plate,
        "description": vehicle.get("Description"),
        "make": vehicle.get("CarMake", {}).get("CurrentTextValue"),
        "model": vehicle.get("CarModel", {}).get("CurrentTextValue"),
        "year": vehicle.get("RegistrationYear"),
        "engine_cc": vehicle.get("EngineSize", {}).get("CurrentTextValue"),
        "engine_code": vehicle.get("EngineCode"),
        "body": vehicle.get("Body"),
        "fuel": vehicle.get("Fuel"),
        "drivetrain": vehicle.get("WheelPlan"),
        "color": vehicle.get("Colour"),
        "vin": vehicle.get("VIN"),
        "transmission": vehicle.get("Transmission"),
        "owner": vehicle.get("owner"),
        "image_url": vehicle.get("ImageUrl"),
    }

# Usage
vehicle = lookup_plate_cr("DEV-404")
print(vehicle)
```

```javascript
// Node.js example
async function lookupPlateCR(plate, username = "jruiz2203") {
  const url = `https://www.regcheck.org.uk/api/reg.asmx/CheckCostaRica?RegistrationNumber=${plate}&username=${username}`;
  const resp = await fetch(url);
  const xml = await resp.text();

  // Extract vehicleJson from XML (simple regex approach)
  const jsonMatch = xml.match(/<vehicleJson>(.*?)<\/vehicleJson>/s);
  if (!jsonMatch) throw new Error("No vehicle data found");

  const vehicle = JSON.parse(jsonMatch[1]);
  return {
    plate,
    description: vehicle.Description,
    make: vehicle.CarMake?.CurrentTextValue,
    model: vehicle.CarModel?.CurrentTextValue,
    year: vehicle.RegistrationYear,
    engineCC: vehicle.EngineSize?.CurrentTextValue,
    body: vehicle.Body,
    fuel: vehicle.Fuel,
    drivetrain: vehicle.WheelPlan,
    color: vehicle.Colour,
    vin: vehicle.VIN,
    owner: vehicle.owner,
  };
}
```

---

## 7. Linking Plate Lookup → TecDoc Parts Catalog

You can chain the plate lookup with the TecDoc catalog API to go from **plate → vehicle → parts**:

```
1. Plate Lookup (this API)
   Input:  "DEV-404"
   Output: Make=HYUNDAI, Model=TUCSON GL, Year=2026, VIN=KMHJB81DBTU408502

2. VIN Decode (TecDoc)
   Tool:   VIN_Decoder_v1 / v2 / v3 / all-in-one
   Input:  VIN "KMHJB81DBTU408502"
   Output: vehicleId, modelId, manufacturerId

3. Get Part Categories (TecDoc)
   Tool:   List_Categories_by_Vehicle_ID__v3
   Input:  vehicleId from step 2, typeId=1
   Output: Full category tree (Steering, Brakes, Engine, etc.)

4. Get Parts (TecDoc)
   Tool:   Article_List_by_Vehicle_ID__Category_ID
   Input:  vehicleId + categoryId
   Output: All compatible parts with suppliers & images
```

This creates a complete **plate-to-parts** pipeline for Costa Rican vehicles.
