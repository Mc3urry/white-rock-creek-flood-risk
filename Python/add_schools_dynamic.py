"""
Make schools dynamic: add per-event exposure to FC_Schools_WS, then build
Schools_Long (one row per school x event exposed) for the field-matched dashboard.

Run AFTER the flood extents exist. Standalone -- does schools end to end.
"""
import arcpy, os

ROOT  = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB   = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
FLOOD = os.path.join(GDB, "FloodHazards")
LONG  = os.path.join(GDB, "DashboardLong")
SCH   = os.path.join(GDB, "Infrastructure", "FC_Schools_WS")

events = ["10yr","50yr","100yr","500yr"]
lbl = {"10yr":"10-Year (10% AEP)","50yr":"50-Year (2% AEP)",
       "100yr":"100-Year (1% AEP)","500yr":"500-Year (0.2% AEP)"}
rank = {"10yr":1,"50yr":2,"100yr":3,"500yr":4}
sr = arcpy.SpatialReference(2276)
arcpy.env.overwriteOutput = True

def fex(fc,n): return n in [f.name for f in arcpy.ListFields(fc)]

if not arcpy.Exists(LONG):
    arcpy.management.CreateFeatureDataset(GDB, "DashboardLong", sr)

print("=== Schools: per-event exposure + long format ===")

# --- Step 1: per-event exposure on FC_Schools_WS ---
for e in events:
    f = "EXPOSED_" + e.upper()
    if not fex(SCH, f):
        arcpy.management.AddField(SCH, f, "TEXT", field_length=15)
if not fex(SCH, "EVENT_RANK"):
    arcpy.management.AddField(SCH, "EVENT_RANK", "SHORT")

exp = {}
for e in events:
    ext = os.path.join(FLOOD, "FloodExtent_" + e)
    if not arcpy.Exists(ext):
        print("  WARNING missing extent " + e); exp[e] = set(); continue
    lyr = arcpy.management.MakeFeatureLayer(SCH, "sch_" + e)
    arcpy.management.SelectLayerByLocation(lyr, "INTERSECT", ext, selection_type="NEW_SELECTION")
    s = set()
    with arcpy.da.SearchCursor(lyr, ["OID@"]) as c:
        for r in c: s.add(r[0])
    exp[e] = s
    print("  " + e + ": " + str(len(s)) + " schools exposed")
    arcpy.management.Delete(lyr)

flds = ["OID@"] + ["EXPOSED_"+e.upper() for e in events] + ["EVENT_RANK"]
with arcpy.da.UpdateCursor(SCH, flds) as cur:
    for row in cur:
        oid = row[0]; rk = 0
        for i,e in enumerate(events):
            is_e = oid in exp[e]
            row[1+i] = "EXPOSED" if is_e else "NOT_EXPOSED"
            if is_e and rk == 0: rk = rank[e]
        row[-1] = rk
        cur.updateRow(row)

# --- Step 2: Schools_Long (one row per school x event exposed) ---
out = os.path.join(LONG, "Schools_Long")
if arcpy.Exists(out): arcpy.management.Delete(out)
arcpy.management.CreateFeatureclass(LONG, "Schools_Long", "POINT", spatial_reference=sr)
arcpy.management.AddField(out, "EVENT", "TEXT", field_length=10)
arcpy.management.AddField(out, "EVENT_LBL", "TEXT", field_length=40)
arcpy.management.AddField(out, "RANK", "SHORT")
arcpy.management.AddField(out, "SRC_OID", "LONG")

read = ["OID@","SHAPE@"] + ["EXPOSED_"+e.upper() for e in events]
ins  = ["SHAPE@","EVENT","EVENT_LBL","RANK","SRC_OID"]
n = 0
with arcpy.da.SearchCursor(SCH, read) as scur, arcpy.da.InsertCursor(out, ins) as icur:
    for row in scur:
        oid, shp = row[0], row[1]
        for i,e in enumerate(events):
            if row[2+i] == "EXPOSED":
                icur.insertRow([shp, e, lbl[e], rank[e], oid]); n += 1
print("  Schools_Long: " + str(n) + " rows")

print("")
print("Verification (cumulative exact-match EVENT counts):")
for e in events:
    c = 0
    with arcpy.da.SearchCursor(out, ["EVENT"], "EVENT = '" + e + "'") as cur:
        for _ in cur: c += 1
    print("  EVENT='" + e + "': " + str(c))

print("")
print("=== Done. Publish Schools_Long. Wire selector EVENT->EVENT like hospitals. ===")