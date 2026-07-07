"""
Fix FC_BlockGroups -- robust version.

Does NOT use JoinField (which left empty columns) or CalculateField code blocks.
Instead it reads the cleaned ACS CSVs into Python dictionaries keyed by GEOID,
then writes everything with a single UpdateCursor.

Run after prep_acs_csvs.py has produced the cleaned CSVs in Data/GIS/Demographics/.
"""

import arcpy, os, csv

ROOT  = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB   = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
DEMOG = os.path.join(ROOT, "Data", "GIS", "Demographics")
bg    = os.path.join(GDB, "Demographics", "FC_BlockGroups")

arcpy.env.overwriteOutput = True

print("=== Fixing FC_BlockGroups (robust CSV-dictionary method) ===")
print("")

# -- Step 1: Drop leftover failed-join columns ---------------------------------
print("Step 1: Removing leftover failed-join columns")
existing = [f.name for f in arcpy.ListFields(bg)]
drop_prefixes = ("B01001_", "B01003_", "B19013_", "B25001_", "B08201_", "B17001_")
drop_exact = ["GEOID_1","GEOID_12","GEOID_12_13","GEOID_12_13_14",
              "GEOID_12_13_14_15","GEOID_12_13_14_15_16",
              "NAME","NAME_1","NAME_12","NAME_12_13","NAME_12_13_14","NAME_12_13_14_15",
              "Field101","Field5","Field5_1","Field5_12","Field63","Field121"]
dropped = 0
for f in existing:
    if f.startswith(drop_prefixes) or f in drop_exact:
        try:
            arcpy.management.DeleteField(bg, f)
            dropped += 1
        except Exception:
            pass
print("  OK Removed " + str(dropped) + " columns")

# -- Step 2: Populate GEOID from FIPS, derive TRACT_GEOID ----------------------
print("")
print("Step 2: Populating GEOID from FIPS and deriving TRACT_GEOID")
fields_now = [f.name for f in arcpy.ListFields(bg)]
if "FIPS" not in fields_now:
    print("  ERROR: FIPS field not found")
    raise SystemExit

with arcpy.da.UpdateCursor(bg, ["FIPS","GEOID","TRACT_GEOID"]) as cur:
    for row in cur:
        fips = row[0]
        if fips:
            row[1] = str(fips)
            row[2] = str(fips)[:11]
        cur.updateRow(row)
print("  OK GEOID and TRACT_GEOID populated")

# Show samples
with arcpy.da.SearchCursor(bg, ["GEOID","TRACT_GEOID"]) as cur:
    for i, row in enumerate(cur):
        print("    sample: GEOID=" + str(row[0]) + "  TRACT=" + str(row[1]))
        if i >= 2: break

# -- Step 3: Read cleaned ACS CSVs into dictionaries ---------------------------
print("")
print("Step 3: Reading cleaned ACS CSVs into lookup dictionaries")

def load_csv(path, key_col="GEOID"):
    """Return dict {geoid: {col: value}} from a cleaned ACS CSV."""
    if not os.path.exists(path):
        print("  WARNING: not found: " + os.path.basename(path))
        return {}
    d = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            key = str(r.get(key_col, "")).strip()
            if key:
                d[key] = r
    print("  OK Loaded " + os.path.basename(path) + " -- " + str(len(d)) + " rows")
    return d

b01001 = load_csv(os.path.join(DEMOG, "ACS_B01001_BG.csv"))
b01003 = load_csv(os.path.join(DEMOG, "ACS_B01003_BG.csv"))
b19013 = load_csv(os.path.join(DEMOG, "ACS_B19013_BG.csv"))
b25001 = load_csv(os.path.join(DEMOG, "ACS_B25001_BG.csv"))
b08201 = load_csv(os.path.join(DEMOG, "ACS_B08201_TRACT.csv"))
b17001 = load_csv(os.path.join(DEMOG, "ACS_B17001_TRACT.csv"))

def num(v):
    """Safe float conversion -- returns None for blanks, '-', 'N', etc."""
    try:
        if v is None: return None
        v = str(v).strip()
        if v in ("", "-", "N", "null", "*", "**", "(X)", "-666666666"):
            return None
        return float(v)
    except (ValueError, TypeError):
        return None

# -- Step 4: Write all values via single UpdateCursor --------------------------
print("")
print("Step 4: Writing demographic values to FC_BlockGroups")

write_fields = ["GEOID","TRACT_GEOID","POP_TOTAL","HU_TOTAL","MED_INC",
                "PCT_POVERTY","PCT_NO_VEH","PCT_65PLUS"]

# Age 65+ columns (male 20-25, female 44-49 in B01001)
age65_cols = ["B01001_020E","B01001_021E","B01001_022E","B01001_023E",
              "B01001_024E","B01001_025E","B01001_044E","B01001_045E",
              "B01001_046E","B01001_047E","B01001_048E","B01001_049E"]

updated = 0
no_match = 0
with arcpy.da.UpdateCursor(bg, write_fields) as cur:
    for row in cur:
        geoid = str(row[0]).strip() if row[0] else ""
        tract = str(row[1]).strip() if row[1] else ""

        # POP_TOTAL from B01003
        if geoid in b01003:
            row[2] = num(b01003[geoid].get("B01003_001E"))
        # HU_TOTAL from B25001
        if geoid in b25001:
            row[3] = num(b25001[geoid].get("B25001_001E"))
        # MED_INC from B19013
        if geoid in b19013:
            row[4] = num(b19013[geoid].get("B19013_001E"))
        # PCT_POVERTY from B17001 (tract)
        if tract in b17001:
            below = num(b17001[tract].get("B17001_002E"))
            univ  = num(b17001[tract].get("B17001_001E"))
            if below is not None and univ and univ > 0:
                row[5] = round(below / univ * 100, 2)
        # PCT_NO_VEH from B08201 (tract)
        if tract in b08201:
            noveh = num(b08201[tract].get("B08201_002E"))
            tot   = num(b08201[tract].get("B08201_001E"))
            if noveh is not None and tot and tot > 0:
                row[6] = round(noveh / tot * 100, 2)
        # PCT_65PLUS from B01001 (block group)
        if geoid in b01001:
            total_pop = num(b01001[geoid].get("B01001_001E"))
            over65 = sum((num(b01001[geoid].get(c)) or 0) for c in age65_cols)
            if total_pop and total_pop > 0:
                row[7] = round(over65 / total_pop * 100, 2)

        if geoid in b01003:
            updated += 1
        else:
            no_match += 1
        cur.updateRow(row)

print("  OK Updated " + str(updated) + " block groups")
if no_match > 0:
    print("  NOTE: " + str(no_match) + " block groups had no matching ACS record")

# -- Step 5: Verify ------------------------------------------------------------
print("")
print("Verification -- first 5 rows:")
print("  POP_TOTAL | HU_TOTAL | MED_INC | PCT_POVERTY | PCT_NO_VEH | PCT_65PLUS")
with arcpy.da.SearchCursor(bg, ["POP_TOTAL","HU_TOTAL","MED_INC",
                                 "PCT_POVERTY","PCT_NO_VEH","PCT_65PLUS"]) as cur:
    for i, row in enumerate(cur):
        print("  " + str(row))
        if i >= 4: break

print("")
print("=== Fix complete ===")
print("If values are populated above, Phase 3 is done. Proceed to Phase 4.")