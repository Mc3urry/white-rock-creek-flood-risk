"""
ACS CSV Preprocessor
Strips the GEO_ID prefix (e.g. 1500000US) from each file,
renames the GEO_ID column to GEOID, removes the label row,
and saves clean versions to Data/GIS/Demographics/

Run this ONCE before phase3_schema_build.py.
"""

import csv, os

ROOT  = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
SRC   = os.path.join(ROOT, "Data", "GIS", "Demographics", "Raw")
DEST  = os.path.join(ROOT, "Data", "GIS", "Demographics")
os.makedirs(SRC, exist_ok=True)

# Place the original downloaded CSVs into Data/GIS/Demographics/Raw/
# then run this script.

# Geography mapping based on GEO_ID prefix:
#   1500000US = Block Group (12-digit numeric GEOID)
#   1400000US = Census Tract (11-digit numeric GEOID)

FILES = {
    # (input filename,                  output filename,         join level)
    "ACSDT5Y2024_B01001-Data.csv": ("ACS_B01001_BG.csv",    "block_group"),
    "ACSDT5Y2024_B01003-Data.csv": ("ACS_B01003_BG.csv",    "block_group"),
    "ACSDT5Y2024_B08201-Data.csv": ("ACS_B08201_TRACT.csv", "tract"),
    "ACSDT5Y2024_B17001-Data.csv": ("ACS_B17001_TRACT.csv", "tract"),
    "ACSDT5Y2024_B19013-Data.csv": ("ACS_B19013_BG.csv",    "block_group"),
    "ACSDT5Y2024_B25001-Data.csv": ("ACS_B25001_BG.csv",    "block_group"),
}

print("=== ACS CSV Preprocessor ===")
print("")
print("Source folder:      " + SRC)
print("Destination folder: " + DEST)
print("")
print("Place your downloaded CSVs in the Raw/ subfolder first.")
print("")

for in_name, (out_name, level) in FILES.items():
    in_path  = os.path.join(SRC, in_name)
    out_path = os.path.join(DEST, out_name)

    if not os.path.exists(in_path):
        print("  WARNING: Not found (place in Demographics/Raw/): " + in_name)
        continue

    try:
        with open(in_path, newline="", encoding="utf-8-sig") as fin:
            reader = list(csv.reader(fin))

        # Row 0 = column headers, Row 1 = label row (skip), Row 2+ = data
        headers = reader[0]
        data    = reader[2:]   # skip label row

        # Rename GEO_ID to GEOID and strip prefix
        geo_idx = headers.index("GEO_ID")
        headers[geo_idx] = "GEOID"

        with open(out_path, "w", newline="", encoding="utf-8") as fout:
            writer = csv.writer(fout)
            writer.writerow(headers)
            for row in data:
                if row and row[geo_idx]:
                    raw_geo = row[geo_idx]
                    # Strip everything up to and including "US"
                    numeric = raw_geo.split("US")[-1] if "US" in raw_geo else raw_geo
                    row[geo_idx] = numeric
                writer.writerow(row)

        row_count = len(data)
        print("  OK " + out_name + " (" + level + ") -- " +
              str(row_count) + " rows -- GEOID length: " +
              str(len(data[0][geo_idx].split("US")[-1] if "US" in data[0][geo_idx]
                       else data[0][geo_idx])) + " digits")

    except Exception as e:
        print("  ERROR processing " + in_name + ": " + str(e))

print("")
print("=== Summary ===")
print("")
print("  Block group files (join on GEOID, 12 digits):")
print("    ACS_B01001_BG.csv  -- Age (for PCT_65PLUS calculation)")
print("    ACS_B01003_BG.csv  -- Total population")
print("    ACS_B19013_BG.csv  -- Median household income")
print("    ACS_B25001_BG.csv  -- Housing units")
print("")
print("  Tract-level files (join on TRACT_GEOID, 11 digits):")
print("    ACS_B08201_TRACT.csv -- Vehicle availability")
print("    ACS_B17001_TRACT.csv -- Poverty status")
print("")
print("Now run phase3_schema_build.py")