# Parts-Catalogs API (Provider 2) — Detailed Analysis

**Base URL:** `https://api.parts-catalogs.com/v1`
**Auth:** Header `Authorization: <API_KEY>`
**Language:** Header `Accept-Language: es` (supports: en, ru, de, bg, fr, es, he)

---

## Endpoints

### 1. GET `/ip/`
- **Purpose:** Check connectivity and see which IP the API sees
- **Auth:** None required
- **Response:** `{ "ip": "201.195.104.118" }`
- **Notes:** IP whitelist is enforced — must use VPN or register IP

### 2. GET `/catalogs/`
- **Purpose:** List all available manufacturer catalogs
- **Response:** Array of `{ id, name, modelsCount, actuality }`
- **Result:** **72 catalogs** including: Toyota (165 models), Chevrolet (173), Nissan (144), Hyundai (91), Kia (60), Mercedes (47), Mitsubishi (52), BMW (32), plus trucks (Scania, MAN, DAF, Volvo Trucks, etc.)
- **Notable:** Includes separate Korean catalogs: `hyundai-korea` (89 models) and `kia-korea` (51 models) in addition to international versions

### 3. GET `/catalogs/{catalogId}/models/`
- **Purpose:** List all models within a catalog
- **Response:** Array of `{ id, name, img }`
- **Example:** Nissan has 144 models, Hyundai has 91

### 4. GET `/catalogs/{catalogId}/cars2/`
- **Purpose:** List specific car configurations within a model
- **Params:** `catalogId` (path), `modelId` (query, required), `parameter` (query, filter by idx), `page` (query, 25 per page)
- **Response:** Array of `Car2` objects with id, name, description, vin, frame, criteria, brand, parameters, modelImg
- **Note:** Vehicle identifiers may change over time when catalogs are updated

### 5. GET `/catalogs/{catalogId}/cars2/{carId}`
- **Purpose:** Get specific car by ID
- **Response:** Single `Car2` object

### 6. GET `/catalogs/{catalogId}/cars-parameters/`
- **Purpose:** Get filter parameters for cars within a model (year, engine, body type, etc.)
- **Params:** `catalogId` (path), `modelId` (query, required), `parameter` (query, filter by idx)
- **Response:** Array of parameter groups with filterable values + idx hashes
- **Header:** `X-Cars-Count` — total cars matching current filters

### 7. GET `/car/info` ⭐ (KEY ENDPOINT — VIN/FRAME lookup)
- **Purpose:** Search cars by VIN or FRAME number across all or selected catalogs
- **Params:** `q` (VIN or frame), `catalogs` (optional comma-separated list like "kia,hyundai")
- **Response:** Array of `CarInfo` objects containing:
  - `catalogId`, `brand`, `modelId`, `modelName`, `carId`
  - `criteria` (critical — needed for filtering groups/parts)
  - `vin`, `frame`
  - `description` (rich text: production date, body, engine, fuel, transmission)
  - `parameters` (array of key/value: engine code, year, body type, etc.)
  - `optionCodes` (array of code+description — can be 100+ factory options)
  - `groupsTreeAvailable` (boolean)

### 8. GET `/catalogs/{catalogId}/groups2/`
- **Purpose:** Browse part groups (categories) — hierarchical navigation
- **Params:** `catalogId` (path), `carId` (query, required), `groupId` (query, drill down), `criteria` (query, from car/info)
- **Response:** Array of `Group` objects with `id`, `name`, `img`, `hasSubgroups`, `hasParts`, `description`
- **Flow:** Navigate until `hasParts: true`, then call `parts2`
- **Result:** ~20 top-level groups (Engine, Brakes, Suspension, etc.)

### 9. GET `/catalogs/{catalogId}/parts2` ⭐ (KEY ENDPOINT — OEM Parts)
- **Purpose:** Get OEM parts within a group for a specific car
- **Params:** `catalogId` (path), `carId` (query), `groupId` (query), `criteria` (query)
- **Response:** `Parts` object containing:
  - `img` — full-size diagram image URL
  - `brand` — catalog brand
  - `partGroups[]` — groups of parts, each with:
    - `name`, `number`, `positionNumber`, `description`
    - `parts[]` — individual parts with:
      - `id` / `number` — **OEM part number** (e.g. "A  2054230181")
      - `name` — part name in selected language
      - `notice` — short applicability note
      - `description` — detailed description with option codes, quantities, applicability
      - `positionNumber` — position on the diagram
      - `url` — search results URL (if x-redirect-template header sent)
  - `positions[]` — coordinate data for parts on the diagram image (X, Y, H, W)

### 10. GET `/catalogs/{catalogId}/groups-suggest`
- **Purpose:** Search/autocomplete for part groups by name
- **Params:** `catalogId` (path), `q` (query, search text)
- **Response:** Array of `{ sid, name }` (e.g. "Disc brake pads", "Brake pad wear sensor")

### 11. GET `/catalogs/{catalogId}/groups-by-sid` (DEPRECATED)
- **Purpose:** Get groups by search ID from groups-suggest
- **Params:** `catalogId`, `sid`, `carId`, `criteria`, `text`

### 12. GET `/catalogs/{catalogId}/groups-tree`
- **Purpose:** Get full group hierarchy as a tree in one call
- **Params:** `catalogId` (path), `carId`, `criteria`, `cached` (boolean)
- **Response:** Nested tree structure with `subGroups[]` at each level
- **Result:** Full tree with ~20 top-level, each with nested subgroups
- **Note:** `cached=true` returns unfiltered tree (faster), `cached=false` returns VIN-filtered tree (slower)

### 13. GET `/catalogs/{catalogId}/schemas`
- **Purpose:** Get parts diagram pages with images and part name filters
- **Params:** `catalogId`, `carId`, `branchId` (group filter), `criteria`, `page` (24 per page), `partNameIds`, `partName`
- **Response:** `{ group, list[] }` — each schema has groupId, img, name, description, partNames[]
- **Header:** `X-Total-Count` — total schemas available
- **Example:** Mercedes C250 has 24+ schema pages (oil filter, front brakes, rear brakes, battery, etc.)

### 14. GET `/example/prices` (DEMO ONLY)
- **Purpose:** Demonstration endpoint for pricing integration
- **Params:** `code` (part number), `brand`
- **Response:** Fake/example data — NOT production-ready
- **Returns:** Dummy prices, stock qty, delivery times

---

## VIN Lookup Results — All 6 Test VINs

| Plate | VIN | Vehicle | Provider 1 (TecDoc) | Provider 2 (Parts-Catalogs) |
|-------|-----|---------|---------------------|----------------------------|
| DEV404 | KMHJB81DBTU408502 | Hyundai Tucson GL 2026 | ✅ Mfr + Model + 1 vehicle | ❌ No matches |
| VGS189 | WDDWF4FB1HF453826 | Mercedes C 2017 | ✅ Mfr + Model + 1 vehicle | ✅ Full match: C250, body, engine, production date |
| 903682 | JTMZD33V305204380 | Toyota RAV4 2012 | ✅ Mfr + Model + 1 vehicle | ✅ 2 matches: RAV4, engine code 2AZFE, grade, transmission |
| 691626 | JMY0RV460XJ000760 | Mitsubishi Montero 1999 | ✅ Mfr + Model + 1 vehicle | ✅ 2 matches: V46W 2800D-TURBO, sales region |
| BKT385 | KMHCT4AE9CU158089 | Hyundai Accent 2012 | ⚠️ Mfr + Model, 0 vehicles | ✅ Full match: ACCENT 11, 1600CC GAMMA DOHC GDI, 199 option codes |
| 681636 | KNAJE551877340075 | KIA Sportage 2007 | ✅ Mfr + Model + 8 vehicles | ✅ Match: SPORTAGE 2007 |

**VIN Match Score:**
- **Provider 1 (TecDoc):** 6/6 found manufacturer, 6/6 found model, 4/6 found specific vehicles
- **Provider 2 (Parts-Catalogs):** 5/6 found (missed Hyundai Tucson 2026 — likely too new for catalog)

---

## Comparison: Provider 1 (TecDoc) vs Provider 2 (Parts-Catalogs)

### Architecture / Approach

| Aspect | TecDoc (Provider 1) | Parts-Catalogs (Provider 2) |
|--------|--------------------|-----------------------------|
| **Data source** | Aftermarket parts database (TecAlliance) | OEM manufacturer catalogs (official) |
| **Parts type** | **Aftermarket** — multiple suppliers per part | **OEM** — original manufacturer part numbers |
| **Catalogs** | Universal (all brands in one system) | Per-manufacturer catalogs (72 catalogs) |
| **VIN decode** | VIN Check → TecDoc vehicleId | VIN → carId + criteria string |
| **Language** | 40+ languages | 7 languages (en, ru, de, bg, fr, es, he) |
| **Part numbers** | Aftermarket article numbers (Bosch, Brembo, etc.) | OEM numbers (A 2054230181, etc.) |
| **Cross-references** | ✅ Built-in: OEM↔aftermarket, aftermarket↔aftermarket | ❌ Not available (OEM numbers only) |
| **Diagrams** | ❌ No diagram images | ✅ Full diagrams with part positions (coordinates) |
| **Pricing** | ❌ No pricing | ⚠️ Demo endpoint only (not real data) |
| **Option codes** | ❌ Not available | ✅ Full factory option codes (100+) from VIN |
| **Part specs** | ✅ Rich specs (dimensions, weight, thread, etc.) | ⚠️ Description text only (no structured specs) |
| **Compatible vehicles** | ✅ List of all cars a part fits | ❌ Parts are catalog-specific, no cross-vehicle |

### Key Differences

1. **OEM vs Aftermarket** — This is the fundamental difference. Parts-Catalogs shows you the ORIGINAL manufacturer part numbers from the official catalog. TecDoc shows you AFTERMARKET replacement parts from third-party suppliers (Bosch, MANN, Brembo, etc.).

2. **Cross-references** — TecDoc has full cross-reference capability (OEM→aftermarket, aftermarket→aftermarket, equivalent parts). Parts-Catalogs does NOT have this — it only shows OEM numbers. To find aftermarket equivalents for an OEM number, you'd need to take the OEM number from Parts-Catalogs and search it in TecDoc.

3. **Diagrams** — Parts-Catalogs provides actual exploded-view diagram images with pixel coordinates for each part's position. TecDoc has no diagrams.

4. **VIN precision** — Parts-Catalogs returns richer VIN data: exact production date, factory options, engine code, transmission, sales region. TecDoc returns TecDoc vehicle IDs but less VIN-decoded detail.

5. **Coverage** — TecDoc found all 6 VINs (though 2 without exact vehicle match). Parts-Catalogs found 5/6 (missed the 2026 Tucson). For the Hyundai Accent that TecDoc couldn't match to a specific vehicle (0 vehicles), Parts-Catalogs returned a perfect match with 199 option codes.

### What Each Provider is Best For

| Use Case | Best Provider |
|----------|--------------|
| Find aftermarket replacements for a part | **TecDoc** |
| Find OEM part numbers for a specific car | **Parts-Catalogs** |
| Cross-reference OEM ↔ aftermarket | **Both together** (OEM from PC → search in TecDoc) |
| Visual part identification (diagrams) | **Parts-Catalogs** |
| Price comparison across suppliers | **TecDoc** (has supplier data) |
| Detailed part specifications | **TecDoc** (structured specs) |
| Factory option code decode | **Parts-Catalogs** |
| VIN-to-exact-car matching | **Parts-Catalogs** (more precise for most brands) |

### OEM Cross-Reference Gap (Item #2 from your request)

**Parts-Catalogs does NOT have a built-in cross-reference endpoint.** The `url` field in parts is empty, and the `example/prices` endpoint returns dummy data. Once you get an OEM part number (e.g. `A 2054230181`) from Parts-Catalogs, to find equivalent aftermarket parts you would need to:

1. Take the OEM number from Parts-Catalogs
2. Search it in TecDoc using the "Search Articles by OEM" endpoint
3. TecDoc returns aftermarket equivalents with full supplier info

**This makes the two APIs complementary, not competing.**
