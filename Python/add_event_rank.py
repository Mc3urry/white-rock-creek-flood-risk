"""
Add EVENT_RANK to FC_Buildings_Exposed (or FC_Buildings_WS) so a dashboard
category selector can drive a cumulative 'buildings exposed at <= event' count.

EVENT_RANK: 1=first flooded at 10yr, 2=50yr, 3=100yr, 4=500yr.
A building flooded at 10yr is also counted at 50/100/500, so the dashboard
filters EVENT_RANK <= selected_rank:
   selecting 10yr  (rank 1) -> counts rank<=1  = 1,778
   selecting 50yr  (rank 2) -> counts rank<=2  = 3,050
   selecting 100yr (rank 3) -> counts rank<=3  = 3,766
   selecting 500yr (rank 4) -> counts rank<=4  = 6,018
"""
import arcpy, os

ROOT = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB  = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")

# Use whichever buildings layer you're publishing. Default: exposed-only.
BLDG = os.path.join(GDB, "BaseData", "FC_Buildings_Exposed")
if not arcpy.Exists(BLDG):
    BLDG = os.path.join(GDB, "BaseData", "FC_Buildings_WS")

arcpy.env.overwriteOutput = True

def field_exists(fc, name):
    return name in [f.name for f in arcpy.ListFields(fc)]

print("=== Adding EVENT_RANK to " + os.path.basename(BLDG) + " ===")

if not field_exists(BLDG, "EVENT_RANK"):
    arcpy.management.AddField(BLDG, "EVENT_RANK", "SHORT")
    print("  Added EVENT_RANK field")

# Prefer MAX_EVENT if present (smallest event that floods each building)
has_max = field_exists(BLDG, "MAX_EVENT")
has_fields = all(field_exists(BLDG, "EXPOSED_" + e) for e in ["10YR","50YR","100YR","500YR"])

rank_map = {"10yr":1, "50yr":2, "100yr":3, "500yr":4, "None":0, None:0}

updated = 0
if has_max:
    with arcpy.da.UpdateCursor(BLDG, ["MAX_EVENT", "EVENT_RANK"]) as cur:
        for row in cur:
            row[1] = rank_map.get(row[0], 0)
            cur.updateRow(row)
            updated += 1
    print("  Populated EVENT_RANK from MAX_EVENT")
elif has_fields:
    flds = ["EXPOSED_10YR","EXPOSED_50YR","EXPOSED_100YR","EXPOSED_500YR","EVENT_RANK"]
    with arcpy.da.UpdateCursor(BLDG, flds) as cur:
        for row in cur:
            rank = 0
            if row[0] == "EXPOSED": rank = 1
            elif row[1] == "EXPOSED": rank = 2
            elif row[2] == "EXPOSED": rank = 3
            elif row[3] == "EXPOSED": rank = 4
            row[4] = rank
            cur.updateRow(row)
            updated += 1
    print("  Populated EVENT_RANK from EXPOSED_<event> fields")
else:
    print("  ERROR: neither MAX_EVENT nor EXPOSED_<event> fields found.")

# Verify cumulative counts
print("")
print("Cumulative counts (what the dashboard will show):")
for rank, label, expect in [(1,"10yr","~1,778"),(2,"50yr","~3,050"),
                             (3,"100yr","~3,766"),(4,"500yr","~6,018")]:
    n = 0
    with arcpy.da.SearchCursor(BLDG, ["EVENT_RANK"]) as c:
        for r in c:
            if r[0] is not None and 1 <= r[0] <= rank:
                n += 1
    print("  <= " + label + ": " + str(n) + "  (expected " + expect + ")")

print("")
print("=== Done. Republish this layer, then filter EVENT_RANK <= selected in the dashboard. ===")