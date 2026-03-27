# 17VIN API (Provider 3) — Detailed Analysis

> **Generated:** 2026-03-26 | **Provider:** 17VIN (17vin.com) | **Origin:** China-based EPC data provider

**Base URL:** `http://api.17vin.com:8080` (HTTP) / `https://api.17vin.com:8443` (HTTPS)
**Auth:** Dynamic MD5 token per request (see Token Generation below)
**Response Format:** JSON
**Methods:** GET or POST (POST required for VIN OCR)

---

## Account Info

| Field | Value |
|-------|-------|
| **Username** | `international_lobsterlabs` |
| **Balance** | 199.23 yuan (as of 2026-03-26) |
| **Expiry** | 2026-04-04 |
| **Pricing Model** | Per-query deduction from balance |

---

## Authentication — Token Generation

Unlike traditional API key auth, 17VIN uses a **per-request dynamic token** derived from an MD5 hash chain:

```
token = MD5( MD5(username) + MD5(password) + url_parameters )
```

Where `url_parameters` is the path + query string **before** appending `user` and `token`. Each unique request requires a freshly computed token.

### Python Implementation

```python
import hashlib

def generate_token(username, password, url_params):
    md5_user = hashlib.md5(username.encode()).hexdigest()
    md5_pass = hashlib.md5(password.encode()).hexdigest()
    return hashlib.md5((md5_user + md5_pass + url_params).encode()).hexdigest()

# Example: VIN decode
url_params = "/?vin=JTMZD33V305204380"
token = generate_token("international_lobsterlabs", "e0ikkf8", url_params)
url = f"http://api.17vin.com:8080{url_params}&user=international_lobsterlabs&token={token}"
```

### JavaScript Implementation

```javascript
const crypto = require('crypto');

function generateToken(username, password, urlParams) {
  const md5 = (s) => crypto.createHash('md5').update(s).digest('hex');
  return md5(md5(username) + md5(password) + urlParams);
}
```

---

## Global Status Codes

| Code | Meaning |
|------|---------|
| `1` | Success — data returned |
| `0` | No data / Unknown error |
| `1001` | Invalid request |
| `1002` | Authentication required |
| `1003` | Unsupported brand |
| `1004` | Permission denied — invalid token |
| `1005` | Permission denied — quota exhausted or expired |
| `1006` | Internal server error |
| `1007` | Interface not available (under development) |

All responses follow:
```json
{ "code": 1, "msg": "success", "data": { ... } }
```

---

## Endpoints

### 1. Account Balance (API 1002)

```
GET /?action=myapicount&user={user}&token={token}
```

**Token url_params:** `/?action=myapicount`

**Response:**
```json
{
  "code": 1,
  "data": [{
    "Username": "international_lobsterlabs",
    "Count": "余额:199.23元",
    "Remark": "账户过期时间：2026-04-04 00:00:00"
  }],
  "msg": "success"
}
```

---

### 2. VIN Decoder (API 3001) ⭐ KEY ENDPOINT

```
GET /?vin={vin}&user={user}&token={token}
```

**Token url_params:** `/?vin={vin}`

| Parameter | Required | Description |
|-----------|----------|-------------|
| `vin` | Yes | 17-digit VIN |
| `gonggao_no` | No | Chinese announcement model number (for disambiguation) |

**Response contains 3 data layers (prioritized):**

1. **`model_original_epc_list`** — Highest reliability. Raw OEM EPC data with `CarAttributes[]` (model code, engine code, transmission, grade, build options). Format varies per brand.
2. **`model_list`** — Standardized vehicle models with consistent structure across all brands (brand, model, series, engine, transmission, displacement, year, price, etc.)
3. **`model_import_list`** — Fallback for niche imported brands when other lists are empty.

**Critical output field: `epc`** — Required for all subsequent parts catalog queries (e.g., `toyota`, `benz`, `hyundai`, `kia`, `mitsubishi`, `subaru`).

---

### 3. VIN OCR (API 3002)

```
POST /?action=vin_ocr
```

**POST body params:** `action`, `base64_urlencode_imagestring`, `user`, `token`

Extracts a 17-character VIN from a photo of a vehicle nameplate, windshield, or driver's license. Image must be < 4MB, min 15px shortest side, max 4096px longest side. Supports jpg, png, bmp.

**Response:** `{ "code": 1, "data": "LFMGJE720DS070251" }`

---

### 4. VIN OCR + VIN Decoder (API 3003)

Combines 3002 (OCR) and 3001 (decode) in a single call. Same POST format as 3002 but returns full vehicle decode alongside the recognized VIN.

---

### 5. Search Part Info via OE/Brand Part Number (API 4001)

```
GET /?action=search_epc&query_part_number={pn}&query_match_type={type}&user={user}&token={token}
```

**Token url_params:** `/?action=search_epc&query_part_number={pn}` (add `&query_match_type={type}` if not smart)

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query_part_number` | Yes | OE or aftermarket part number |
| `query_match_type` | No | `exact`, `inexact` (fuzzy), `smart` (default — tries exact first) |

**Response:** Array of matches with `Partnumber`, `Epc`, `Brand_name_en`, `Part_name_en`, `Part_name_zh`, `Group_id`, `Epc_id`, `Part_img`.

**Tested Result — 34140AA030 (Subaru Inner Tie Rod):**
- Found in 3 sources: NISSAN (EPC=nissan), SUBARU (EPC=subaru, name="TIE ROD COMPLETE-GEAR BOX,LEFT"), CTR (aftermarket, no EPC)

---

### 6. Search Part EPC Illustration (API 4002)

```
GET /{epc}?action=search_illustration&query_part_number={pn}&user={user}&token={token}
```

Returns the exploded-view diagram(s) containing a specific OE part number. Provides `cata_code` needed for API 4005.

**Tested Result — 041110Q021 (Toyota):** 4 illustration results across different catalog pages.

---

### 7. Get Applicable Vehicle Models via OE Number (API 40031)

```
GET /?action=get_modellist_from_part_number_and_group_id&part_number={pn}&group_id={gid}&user={user}&token={token}
```

Returns standardized vehicle models compatible with a part. Includes `ModelListStd[]` with brand, model, series, engine, year, displacement, transmission, price, and `InterchangeInfo`.

**Tested Result — 34140AA030:** 11 standard models (Subaru Impreza, Legacy), total 4 aftermarket model groups.

---

### 8. Get Aftermarket Applicable Vehicle Models (API 40032)

```
GET /?action=get_modellist_from_part_number_and_group_id_for_aftermarket&part_number={pn}&group_id={gid}&based_on={engine|transmission}&user={user}&token={token}
```

Simplified/aggregated version of 40031. Groups models by engine or transmission for aftermarket products.

**Tested Result — 34140AA030:**
| Brand | Series | CC | Years | Engines |
|-------|--------|----|-------|---------|
| Subaru | Legacy | 2.5L | 2001-2020 | EJ25, EJ253, FB25, FB25Y |
| Subaru | Legacy | 2.5T | 2010-2014 | EJ255 |
| Subaru | Impreza | 1.8L | 1994 | — |
| Subaru | Impreza | 2.0T | 1998-2016 | EJ20, EJ205, FA20 |

---

### 9. Retrieve Replacement/Interchange Numbers (API 4004) ⭐ KEY ENDPOINT

```
GET /?action=get_interchange_from_part_number_and_group_id_plus_zh&part_number={pn}&group_id={gid}&user={user}&token={token}
```

Returns cross-reference/replacement numbers split into **OE interchange** (other OEM numbers) and **Factory interchange** (aftermarket equivalents).

**Tested Result — 34140AA030:**
- **Total:** 99 interchange records
- **OE interchange:** 16 records (31310GA152, 34140AA003, 34140AA010, 34140AA011, 34140AA012, ...)
- **Factory interchange:** 83 records (TRW JAR1287, SPIDAN 45233, RUVILLE 918111, BENDIX 041200B, ...)

Each record includes: `Part_number`, `Brand_name_en`, `Part_name_en`, `Similarity_degree`, `Distance`, `Weight`, `Is_oe_interchange`.

---

### 10. Get Part List for Illustration (API 4005)

```
GET /{epc}?action=illustration&cata_code={cata_code}&user={user}&token={token}
```

Returns all parts within a specific exploded-view diagram page. Includes part numbers, names, quantities, callout positions, and image hotspot coordinates.

**Tested:** 27 parts returned for a Toyota standard tool illustration, with full diagram coordinates.

---

### 11. Get 4S Store Price (API 4006)

```
GET /?action=price&partnumber={pn}&user={user}&token={token}
```

Returns 4S dealership prices for an OE number. Prices are primarily for Chinese-market dealerships.

**Tested Result — 000098713A (VW):**
| Brand | Price (CNY) |
|-------|-------------|
| Audi (Import) | 289.78 |
| SAIC VW | 401.06 |
| SAIC VW Skoda | 398.20 |

**Note:** 34140AA030 (Subaru) returned no pricing data — coverage is primarily Chinese-market brands (VW, Toyota, Honda, BMW, etc.)

---

### 12. Private Part Query (API 40071/40072/40073)

Restricted endpoints for brand owners/authorized dealers. Searches aftermarket brand-specific part databases. Requires `manufacturer_brand` parameter. Not accessible with our demo account.

---

### 13. Get Primary Category List via VIN (API 5101)

```
GET /{epc}?action=cata1&vin={vin}&user={user}&token={token}
```

**Token url_params:** `/{epc}?action=cata1&vin={vin}`

First level of the hierarchical EPC parts catalog. Navigate until `is_last=1`, then call 5105 for parts.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `epc` | Yes | From VIN decode (3001) — e.g., `toyota`, `benz`, `kia` |
| `vin` | Yes | 17-digit VIN |
| `is_vin_filter_open` | No | `1` = filter by VIN applicability (default), `0` = show all |
| `epc_id` | No | Sub-model ID from VIN decode |
| `js_id` | No | Standard model ID from VIN decode |

---

### 14. Get Secondary Category List (API 5102)

```
GET /{epc}?action=cata2&vin={vin}&cata1_code={code}&user={user}&token={token}
```

Second level. Requires `cata1_code` from 5101.

---

### 15. Get Tertiary Category List (API 5103)

```
GET /{epc}?action=cata3&vin={vin}&cata2_code={code}&user={user}&token={token}
```

Third level. Requires `cata2_code` from 5102. Some brands go 3 levels deep (e.g., Land Rover, Jaguar), others stop at 2 (e.g., Toyota).

---

### 16. Get Part List via VIN (API 5105) ⭐ KEY ENDPOINT

```
GET /{epc}?action=part&vin={vin}&last_cata_code={code}&last_cata_code_level={1|2|3}&user={user}&token={token}
```

Returns the actual OEM parts list for a final-level catalog category, including:
- **Part numbers** (OE number + original formatting)
- **Part names** (EN + ZH)
- **Quantities**
- **Date ranges** (begin_date, end_date)
- **VIN applicability** flag
- **Replacement numbers**
- **Diagram image** with hotspot coordinates (X, Y per callout)

**Tested — Toyota RAV4, Standard Tool category:** 9 parts with full diagram (1592×1099px, 26 hotspots).

---

### 17. Search Part Number via VIN (API 5106)

```
GET /{epc}?action=search_part_number&vin={vin}&query_match_type=exact&query_part_number={pn}&user={user}&token={token}
```

Exact search for a part number within a specific vehicle's EPC catalog. Returns catalog location, category, and part details.

---

### 18. Search OE Part Name via VIN (API 5107)

```
GET /{epc}?action=search_epc_part_name&vin={vin}&query_match_type={type}&query_part_name={name}&user={user}&token={token}
```

Search by OEM part name. Supports base64 encoding for non-ASCII names. **Limited English support** — primarily Chinese part names.

---

### 19. Search Standard Part Name via VIN (API 5108)

```
GET /{epc}?action=search_std_part_name&vin={vin}&query_match_type={type}&query_part_name={name}&user={user}&token={token}
```

Search by 17VIN's standardized part naming system (brand-agnostic). **Chinese only** — not applicable for international users.

---

### 20. Get All OE Part Numbers via VIN (API 5109)

```
GET /{epc}?action=all_part_number&vin={vin}&user={user}&token={token}
```

Returns **every OE part number** for a vehicle as an `@`-delimited string.

**Tested Results:**
| Vehicle | OE Part Count |
|---------|--------------|
| Toyota RAV4 2012 | **2,558** |
| Mercedes C250 2017 | **2,874** |
| Kia Sportage 2007 | **2,706** |
| Mitsubishi Montero 1999 | **2,985** |
| Hyundai Accent 2012 | **0** (EPC navigation failed for this VIN) |

---

### 21. Get All OEM Part Names via VIN (API 5110)

```
GET /{epc}?action=all_epc_part_name&vin={vin}&user={user}&token={token}
```

All OEM part names as `@`-delimited string. **Chinese only**.

---

### 22. Get All Standard Part Names via VIN (API 5111)

```
GET /{epc}?action=all_std_part_name&vin={vin}&user={user}&token={token}
```

All 17VIN standardized part names. **Chinese only**.

---

### 23. Search Suggestions via VIN (API 5112)

```
GET /{epc}?action=search_suggest&vin={vin}&suggest_key={keyword}&user={user}&token={token}
```

Autocomplete suggestions for part names or OE numbers. **Not recommended for international users** — primarily Chinese.

---

## VIN Decode Results — All 6 Test VINs

| Plate | VIN | Vehicle | code | epc | Match Mode | Build Date | Model List | OEM EPC List |
|-------|-----|---------|------|-----|------------|------------|------------|--------------|
| DEV404 | KMHJB81DBTU408502 | Hyundai Tucson 2026 | **0** | hyundai | in_exact_match | — | ❌ Empty | ❌ Empty |
| VGS189 | WDDWF4FB1HF453826 | Mercedes C250 2017 | **1** | benz | exact_match | 20160901 | ✅ 2 models | ✅ Full attrs (87+ option codes) |
| 903682 | JTMZD33V305204380 | Toyota RAV4 2012 | **1** | toyota | exact_match | 201109 | ✅ 2 models | ✅ Full attrs (model code, engine, trans) |
| 691626 | JMY0RV460XJ000760 | Mitsubishi Montero 1999 | **1** | mitsubishi | exact_match | 199902 | ❌ Empty | ✅ Partial attrs (model, grade, colors) |
| BKT385 | KMHCT4AE9CU158089 | Hyundai Accent 2012 | **1** | hyundai | exact_match | 20111102 | ✅ 2 models | ✅ Full attrs (150+ option codes) |
| 681636 | KNAJE551877340075 | Kia Sportage 2007 | **1** | kia | exact_match | 20061028 | ❌ Empty | ✅ Full attrs (120+ option codes) |

### VIN Decode Detail Highlights

**Mercedes C250 (WDDWF4FB1HF453826):**
- Model: C 250 (205045)
- Engine: 274920, Transmission: 722995
- Build: 2016-09-01, Delivery: 2016-09-02
- Paint: 775U (Iridium Silver Metallic)
- Interior: 101A (Imitation Leather Black/Anthracite)
- Destination: **723L = COSTA RICA**
- 87+ factory option codes including: Active Park Assist, Rear-View Camera, Audio 20 Navigation, LED Headlamps, etc.

**Hyundai Accent (KMHCT4AE9CU158089):**
- Model: ACCENT 11 (2011-2014)
- Engine: G4FDBU714208 (1600cc GAMMA DOHC)
- Body Color: SAE-CARBON GRAY
- Nation: U.S.A
- 150+ option codes covering every specification from tire size to speaker locations

**Kia Sportage (KNAJE551877340075):**
- Model: SPORTAGE 04 (SEP.2006-)
- Engine: D4EA6H255054 (2000cc Diesel SOHC TCI)
- Transmission: Auto 4-speed 4WD
- Body Color: Y3-GREENISH GOLD
- Nation: **COSTA RICA**
- 120+ option codes

---

## EPC Category Navigation Results

### Toyota RAV4 (JTMZD33V305204380)
| Level 1 | Categories |
|---------|-----------|
| 1 | Engine, fuel system and tools |
| 2 | Transmission and chassis |
| 3 | Body and interior |
| 4 | Electrics |

Level 2 under "Engine": 26 sub-categories (Standard Tool, Partial Engine Assembly, Short Block, Gasket Kit, Cylinder Head, Cylinder Block, Timing Gear Cover, Mounting, Ventilation Hose, etc.)

### Mercedes C250 (WDDWF4FB1HF453826)
**54 primary categories** including: Main Assembly Mounting Kit, Engine Mount, Clutch, Gearshift System, Automatic Transmission, Pedal Mechanism, Adjuster, Springs/Mounts/Hydraulic, Half Front Axle, and many more.

### Kia Sportage (KNAJE551877340075)
8 primary categories: Engine, Transmission, Chassis, Body, Trim, Electric, Wire Harness Repair Kit, PL2 Parts.

### Mitsubishi Montero (JMY0RV460XJ000760)
27 primary categories (mix of English and Chinese names): Engine, Lubrication, Fuel, Cooling, Intake & Exhaust, Electrical, Clutch, Manual Transmission, Automatic Transmission, Transfer Case, Propeller Shaft, Front Axle, Rear Axle, Wheels & Tires, Front Suspension, and more.

### Hyundai Accent (KMHCT4AE9CU158089)
**❌ EPC navigation returned no categories** despite successful VIN decode. The `epc_id=209114` did not map to browsable catalog data. This appears to be a coverage gap for this specific Hyundai sub-model.

### Hyundai Tucson 2026 (KMHJB81DBTU408502)
**❌ VIN decode failed** (code=0, "No Standardize vehicle results found"). Vehicle too new for catalog.

---

## Cross-Reference / Interchange Capability

17VIN's API 4004 provides **both OE and aftermarket cross-references** in a single call — a capability that Parts-Catalogs (Provider 2) lacks entirely.

**Example — 34140AA030 (Subaru Inner Tie Rod):**

| Type | Count | Examples |
|------|-------|---------|
| **OE Interchange** | 16 | 31310GA152, 34140AA003, 34140AA010, 34140AA011, 34140AA012 |
| **Factory (Aftermarket)** | 83 | TRW JAR1287, SPIDAN 45233, RUVILLE 918111/918112, BENDIX 041200B |

Each interchange record includes:
- `Similarity_degree` — confidence score
- `Distance` — how many steps removed from original
- `Weight` — ranking weight
- `Is_oe_interchange` — boolean distinguishing OE vs aftermarket

---

## Comparison: Provider 1 (TecDoc) vs Provider 2 (Parts-Catalogs) vs Provider 3 (17VIN)

### VIN Decode Results

| Plate | Vehicle | TecDoc (P1) | Parts-Catalogs (P2) | 17VIN (P3) |
|-------|---------|-------------|---------------------|------------|
| DEV404 | Tucson 2026 | ✅ Found | ❌ Not found | ❌ Not found (code=0) |
| VGS189 | Mercedes C250 2017 | ✅ Found | ✅ Rich match | ✅ Exact match + 87 option codes |
| 903682 | RAV4 2012 | ✅ Found | ✅ 2 matches | ✅ Exact match + full EPC attrs |
| 691626 | Montero 1999 | ✅ Found | ✅ 2 matches | ✅ EPC attrs only (no std models) |
| BKT385 | Accent 2012 | ⚠️ 0 vehicles | ✅ Full match + 199 options | ✅ 2 models + 150 option codes |
| 681636 | Sportage 2007 | ✅ 8 matches | ✅ Found | ✅ EPC attrs + 120 option codes |

**VIN Match Score:**
- **TecDoc (P1):** 6/6 found brand, 4/6 found specific vehicles
- **Parts-Catalogs (P2):** 5/6 found (missed 2026 Tucson)
- **17VIN (P3):** 5/6 found (missed 2026 Tucson), richest option code data

### EPC / Parts Catalog Navigation

| Plate | Vehicle | TecDoc (P1) | Parts-Catalogs (P2) | 17VIN (P3) |
|-------|---------|-------------|---------------------|------------|
| DEV404 | Tucson 2026 | ✅ Categories | ❌ No data | ❌ No data |
| VGS189 | Mercedes C250 | ✅ Categories | ✅ Full tree | ✅ 54 categories |
| 903682 | RAV4 2012 | ✅ Categories | ✅ Full tree | ✅ 4 L1 / 26 L2 categories, 2558 OE parts |
| 691626 | Montero 1999 | ✅ Categories | ✅ Full tree | ✅ 27 categories, 2985 OE parts |
| BKT385 | Accent 2012 | ⚠️ Limited | ✅ Full tree + options | ❌ No EPC categories (decode OK, navigation failed) |
| 681636 | Sportage 2007 | ✅ Categories | ✅ Full tree | ✅ 8 categories, 2706 OE parts |

### Architecture Comparison

| Aspect | TecDoc (P1) | Parts-Catalogs (P2) | 17VIN (P3) |
|--------|-------------|---------------------|------------|
| **Data source** | Aftermarket (TecAlliance) | OEM catalogs (official) | OEM EPC + aftermarket database |
| **Parts type** | Aftermarket only | OEM only | **Both OEM + aftermarket** |
| **Cross-references** | ✅ Full OEM↔aftermarket | ❌ None | ✅ OE interchange + factory interchange |
| **Diagrams** | ❌ None | ✅ Full diagrams + coordinates | ✅ Full diagrams + hotspot coordinates |
| **VIN option codes** | ❌ None | ✅ Full factory options | ✅ Full factory options (richest data) |
| **Pricing** | ❌ None | ⚠️ Demo only | ✅ Real 4S store prices (Chinese market) |
| **Language** | 40+ languages | 7 languages | Bilingual (EN + ZH), some endpoints ZH-only |
| **Coverage focus** | Global | Global | **China-centric** + global VIN decode |
| **VIN OCR** | ❌ None | ❌ None | ✅ Photo → VIN extraction |
| **Part specs** | ✅ Rich (dimensions, weight) | ⚠️ Text description only | ⚠️ Part name + image only |
| **Auth** | API key header | API key header | MD5 token per request |
| **All OE numbers** | ❌ Not available | ❌ Not available | ✅ Full dump (2500-3000 per vehicle) |

### What Each Provider is Best For

| Use Case | Best Provider |
|----------|--------------|
| Find aftermarket part suppliers | **TecDoc (P1)** — 85+ suppliers per part |
| Find OEM part numbers from diagrams | **Parts-Catalogs (P2)** or **17VIN (P3)** |
| Cross-reference OEM ↔ aftermarket | **17VIN (P3)** — single API call, or TecDoc + PC combo |
| Visual part identification (diagrams) | **Parts-Catalogs (P2)** or **17VIN (P3)** — both have hotspots |
| Detailed part specifications | **TecDoc (P1)** — structured specs (dimensions, weight, thread) |
| Factory option code decoding | **17VIN (P3)** — richest option data (150+ codes per VIN) |
| 4S/dealer pricing (China market) | **17VIN (P3)** — real prices |
| VIN-to-vehicle for brand-new cars | **TecDoc (P1)** — only one that found 2026 Tucson |
| Photo-to-VIN (OCR) | **17VIN (P3)** — exclusive capability |
| Dump all OE numbers for a vehicle | **17VIN (P3)** — 2500-3000 part numbers per vehicle |
| English-first experience | **TecDoc (P1)** or **Parts-Catalogs (P2)** |

---

## Key Findings & Limitations

### Strengths
1. **Richest VIN decode data** — 87-150+ factory option codes per vehicle, including destination country, paint code, interior code, exact build date
2. **Combined OEM + aftermarket** — unique among the 3 providers; single API (4004) returns both OE cross-references and aftermarket equivalents
3. **Full OE part number dump** — API 5109 returns every OE number for a vehicle (2500-3000 parts) in one call
4. **VIN OCR** — exclusive photo-to-VIN capability
5. **4S dealer pricing** — real Chinese market prices (not available from other providers)
6. **Diagram hotspots** — full exploded-view diagrams with clickable coordinates, similar to Parts-Catalogs

### Limitations
1. **China-centric** — pricing, some categories, and part names heavily weighted toward Chinese domestic market
2. **Language gaps** — APIs 5107, 5108, 5110, 5111, 5112 are Chinese-only, limiting international usability
3. **Inconsistent EPC coverage** — Hyundai Accent decoded successfully but EPC navigation returned no categories; some brands return mixed EN/ZH category names
4. **No structured part specifications** — unlike TecDoc, there are no dimensions, weight, thread size, or other technical specs per part
5. **Complex auth** — per-request token generation adds implementation complexity vs simple API key
6. **Balance-based pricing** — no unlimited plans visible; each query costs from balance
7. **Part names in Spanish** — Toyota EPC returns Spanish part names (e.g., "LLAVE DE TUERCAS" = Wrench), likely reflecting the catalog source region
8. **2026 vehicles not yet supported** — same gap as Parts-Catalogs for very new models

### Coverage Gaps (Per VIN)
- **Hyundai Tucson 2026** — VIN decode failed entirely (code=0)
- **Hyundai Accent 2012** — VIN decode succeeded but EPC category navigation returned empty (code=0)
- **Mitsubishi Montero 1999** — VIN decode succeeded with EPC attrs but no standardized model_list (older vehicle)

---

## Integration Recommendation

17VIN is **most valuable as a complement** to the existing TecDoc + Parts-Catalogs stack:

```
Pipeline: Plate → VIN → All 3 Providers

1. Plate Lookup (RegCheck)
   → Get VIN, Make, Model, Year

2. VIN Decode (all 3 in parallel)
   → TecDoc: vehicleId for aftermarket lookup
   → Parts-Catalogs: carId + criteria for OEM catalog
   → 17VIN: richest option codes + build date + epc identifier

3. Parts Lookup (choose based on need)
   → OEM parts with diagrams: Parts-Catalogs OR 17VIN
   → Aftermarket alternatives: TecDoc
   → Cross-references: 17VIN (single call) or TecDoc (from OEM number)
   → All OE numbers dump: 17VIN API 5109

4. Price check (17VIN)
   → 4S dealer pricing for Chinese-market parts
```

### Complementary Value

| Data Point | Primary Source | Complement |
|------------|---------------|------------|
| Factory option codes | 17VIN | Parts-Catalogs |
| Aftermarket suppliers | TecDoc | 17VIN (via interchange) |
| OEM diagrams | Parts-Catalogs | 17VIN |
| Part specifications | TecDoc | — |
| Cross-references | 17VIN | TecDoc |
| Dealer pricing | 17VIN | — |
| All OE numbers | 17VIN | — |
| Photo → VIN | 17VIN | — |

---

## API Endpoints Summary

| # | API | Endpoint | Purpose | Tested |
|---|-----|----------|---------|--------|
| 1 | 1002 | `/?action=myapicount` | Account balance inquiry | ✅ |
| 2 | 3001 | `/?vin={vin}` | VIN decoder | ✅ (6 VINs) |
| 3 | 3002 | `/?action=vin_ocr` (POST) | VIN OCR from photo | ⬜ (no test image) |
| 4 | 3003 | `/?action=vin_ocr` (POST) | VIN OCR + decode combo | ⬜ |
| 5 | 4001 | `/?action=search_epc&query_part_number={pn}` | Search part info by OE/brand number | ✅ |
| 6 | 4002 | `/{epc}?action=search_illustration&query_part_number={pn}` | Find diagram for OE number | ✅ |
| 7 | 40031 | `/?action=get_modellist_from_part_number_and_group_id` | Applicable vehicle models (standard) | ✅ |
| 8 | 40032 | `/?action=get_modellist_from_part_number_and_group_id_for_aftermarket` | Applicable models (aftermarket aggregated) | ✅ |
| 9 | 4004 | `/?action=get_interchange_from_part_number_and_group_id_plus_zh` | Replacement/interchange numbers | ✅ |
| 10 | 4005 | `/{epc}?action=illustration&cata_code={code}` | Parts list for a diagram page | ✅ |
| 11 | 4006 | `/?action=price&partnumber={pn}` | 4S store dealer pricing | ✅ |
| 12 | 40071 | `/?action=aftermarket_private_part_search` | Private brand part search | ⬜ (restricted) |
| 13 | 40072 | Private | Aftermarket vehicle models (private) | ⬜ (restricted) |
| 14 | 40073 | Private | Part info + vehicle models (private) | ⬜ (restricted) |
| 15 | 5101 | `/{epc}?action=cata1&vin={vin}` | Primary category list | ✅ (5 VINs) |
| 16 | 5102 | `/{epc}?action=cata2&vin={vin}&cata1_code={c1}` | Secondary category list | ✅ |
| 17 | 5103 | `/{epc}?action=cata3&vin={vin}&cata2_code={c2}` | Tertiary category list | ✅ |
| 18 | 5105 | `/{epc}?action=part&vin={vin}&last_cata_code={code}&last_cata_code_level={lvl}` | Part list for final category | ✅ |
| 19 | 5106 | `/{epc}?action=search_part_number&vin={vin}&query_part_number={pn}` | Search part number within VIN's EPC | ✅ |
| 20 | 5107 | `/{epc}?action=search_epc_part_name&vin={vin}&query_part_name={name}` | Search by OEM part name | ⬜ (ZH-primary) |
| 21 | 5108 | `/{epc}?action=search_std_part_name&vin={vin}&query_part_name={name}` | Search by 17VIN standard name | ⬜ (ZH-only) |
| 22 | 5109 | `/{epc}?action=all_part_number&vin={vin}` | Get ALL OE part numbers | ✅ (5 VINs) |
| 23 | 5110 | `/{epc}?action=all_epc_part_name&vin={vin}` | Get all OEM part names | ⬜ (ZH-only) |
| 24 | 5111 | `/{epc}?action=all_std_part_name&vin={vin}` | Get all standard part names | ⬜ (ZH-only) |
| 25 | 5112 | `/{epc}?action=search_suggest&vin={vin}&suggest_key={key}` | Search suggestions/autocomplete | ⬜ (ZH-primary) |

---

## Full Python Helper

```python
import hashlib
import json
import urllib.request
import urllib.parse

class SeventeenVinAPI:
    BASE = "http://api.17vin.com:8080"

    def __init__(self, username, password):
        self.username = username
        self.md5_user = hashlib.md5(username.encode()).hexdigest()
        self.md5_pass = hashlib.md5(password.encode()).hexdigest()

    def _token(self, url_params):
        return hashlib.md5(
            (self.md5_user + self.md5_pass + url_params).encode()
        ).hexdigest()

    def _get(self, url_params):
        t = self._token(url_params)
        sep = '&' if '?' in url_params else '?'
        url = f"{self.BASE}{url_params}{sep}user={self.username}&token={t}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    def balance(self):
        return self._get("/?action=myapicount")

    def decode_vin(self, vin):
        return self._get(f"/?vin={vin}")

    def search_part(self, part_number, match_type="smart"):
        p = f"/?action=search_epc&query_part_number={part_number}"
        if match_type != "smart":
            p += f"&query_match_type={match_type}"
        return self._get(p)

    def get_interchange(self, part_number, group_id):
        return self._get(
            f"/?action=get_interchange_from_part_number_and_group_id_plus_zh"
            f"&part_number={part_number}&group_id={group_id}"
        )

    def get_price(self, part_number):
        return self._get(f"/?action=price&partnumber={part_number}")

    def get_categories_l1(self, epc, vin):
        return self._get(f"/{epc}?action=cata1&vin={vin}")

    def get_categories_l2(self, epc, vin, cata1_code):
        return self._get(f"/{epc}?action=cata2&vin={vin}&cata1_code={cata1_code}")

    def get_parts(self, epc, vin, last_cata_code, level):
        return self._get(
            f"/{epc}?action=part&vin={vin}"
            f"&last_cata_code={last_cata_code}&last_cata_code_level={level}"
        )

    def get_all_oe_numbers(self, epc, vin):
        r = self._get(f"/{epc}?action=all_part_number&vin={vin}")
        if r.get("code") == 1 and isinstance(r.get("data"), str):
            return [p for p in r["data"].split("@") if p.strip()]
        return []

# Usage
api = SeventeenVinAPI("international_lobsterlabs", "e0ikkf8")
result = api.decode_vin("JTMZD33V305204380")
```

---

## Diagram Image URLs

All diagram/illustration images follow this pattern:
```
http://resource.17vin.com/img/{epc}/{illustration_img_address}
```

Examples:
- `http://resource.17vin.com/img/toyota/090376D.png`
- `http://resource.17vin.com/img/benz/C205FW_21_050.png`
- `http://resource.17vin.com/img/kia/...`

Car images from model_list:
```
http://resource.17vin.com/img/car/all/{Img_adress}
```

Part images from 4001:
```
http://resource.17vin.com/img/{Part_img}
```
