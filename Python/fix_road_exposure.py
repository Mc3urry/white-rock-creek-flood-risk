"""
Stamp EXPOSED_100YR (and flood depth) onto FC_Roads_WS.
Phase 6 computed flooded road mileage but did not write per-segment exposure
status. This selects roads intersecting the 100-yr flood extent and marks them.
"""
import arcpy, os

ROOT     = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB      = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
ROADS    = os.path.join(GDB, "Infrastructure", "FC_Roads_WS")
EXTENT   = os.path.join(GDB, "FloodHazards", "FloodExtent_100yr")

arcpy.env.overwriteOutput = True

print("=== Fixing FC_Roads_WS exposure ===")

def field_exists(fc, name):
    return name in [f.name for f in arcpy.ListFields(fc)]

# Ensure the field exists
if not field_exists(ROADS, "EXPOSED_100YR"):
    arcpy.management.AddField(ROADS, "EXPOSED_100YR", "TEXT", field_length=20)
    print("  Added EXPOSED_100YR field")

# Select roads intersecting the 100-yr flood extent
lyr = arcpy.management.MakeFeatureLayer(ROADS, "roads_lyr")
arcpy.management.SelectLayerByLocation(lyr, "INTERSECT", EXTENT, selection_type="NEW_SELECTION")
exposed_oids = set()
with arcpy.da.SearchCursor(lyr, ["OID@"]) as c:
    for r in c:
        exposed_oids.add(r[0])
print("  Roads intersecting 100-yr extent: " + str(len(exposed_oids)))
arcpy.management.Delete(lyr)

# Write status to every segment
total = 0
with arcpy.da.UpdateCursor(ROADS, ["OID@", "EXPOSED_100YR"]) as cur:
    for row in cur:
        row[1] = "EXPOSED" if row[0] in exposed_oids else "NOT_EXPOSED"
        cur.updateRow(row)
        total += 1

# Report
counts = {}
with arcpy.da.SearchCursor(ROADS, ["EXPOSED_100YR"]) as c:
    for r in c:
        counts[r[0]] = counts.get(r[0], 0) + 1
print("  Result: " + str(counts))
print("  Total segments updated: " + str(total))
print("=== Done ===")
