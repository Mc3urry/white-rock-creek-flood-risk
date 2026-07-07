"""
Phase 8 -- Long-format restructure for a fully field-matched dashboard.

Creates LONG-format copies where each feature has ONE ROW PER EVENT it is
exposed to. An exact-match filter EVENT='100yr' then returns the CUMULATIVE
set (all features exposed at that event), because every exposed feature has a
row for that event.

Outputs (in a new 'DashboardLong' dataset):
  Buildings_Long   -- point, EVENT field, 1 row per (building x event-exposed)
  Hospitals_Long   -- point, EVENT field
  Roads_Long       -- line,  EVENT field (+ FLOOD_MI per row)
  FloodExtent_AllEvents already exists (1 row per event) -> the SELECTOR SOURCE

Selector: base on FloodExtent_AllEvents (field EVENT). Field-match EVENT=EVENT
to every long layer + the flood layer. All cumulative, all synchronized.

Population: block groups get one row per event too (BlockGroups_Long) with
POP_EXP per event, so a serial/indicator can sum by EVENT.
"""
import arcpy, os

ROOT  = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB   = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
FLOOD = os.path.join(GDB, "FloodHazards")
LONG  = os.path.join(GDB, "DashboardLong")

BLDG  = os.path.join(GDB, "BaseData", "FC_Buildings_WS")
HOSP  = os.path.join(GDB, "Infrastructure", "FC_Hospitals_WS")
ROADS = os.path.join(GDB, "Infrastructure", "FC_Roads_WS")
BG    = os.path.join(GDB, "Demographics", "FC_BlockGroups_WS")

events = ["10yr","50yr","100yr","500yr"]
lbl = {"10yr":"10-Year (10% AEP)","50yr":"50-Year (2% AEP)",
       "100yr":"100-Year (1% AEP)","500yr":"500-Year (0.2% AEP)"}
rank = {"10yr":1,"50yr":2,"100yr":3,"500yr":4}
sr = arcpy.SpatialReference(2276)
arcpy.env.overwriteOutput = True

if not arcpy.Exists(LONG):
    arcpy.management.CreateFeatureDataset(GDB, "DashboardLong", sr)
    print("Created DashboardLong dataset")

def fex(fc,n): return n in [f.name for f in arcpy.ListFields(fc)]

def build_long_points(src, out_name, geom_type):
    """One row per (feature x event it's exposed to), using EXPOSED_<event> fields."""
    out = os.path.join(LONG, out_name)
    if arcpy.Exists(out): arcpy.management.Delete(out)
    arcpy.management.CreateFeatureclass(LONG, out_name, geom_type, spatial_reference=sr)
    arcpy.management.AddField(out, "EVENT", "TEXT", field_length=10)
    arcpy.management.AddField(out, "EVENT_LBL", "TEXT", field_length=40)
    arcpy.management.AddField(out, "RANK", "SHORT")
    arcpy.management.AddField(out, "SRC_OID", "LONG")

    have = all(fex(src,"EXPOSED_"+e.upper()) for e in events)
    if not have:
        print("  ERROR: " + os.path.basename(src) + " missing EXPOSED_<event> fields. Run phase8_multievent_exposure first.")
        return out, 0

    read = ["OID@","SHAPE@"] + ["EXPOSED_"+e.upper() for e in events]
    ins  = ["SHAPE@","EVENT","EVENT_LBL","RANK","SRC_OID"]
    n = 0
    with arcpy.da.SearchCursor(src, read) as scur, arcpy.da.InsertCursor(out, ins) as icur:
        for row in scur:
            oid, shp = row[0], row[1]
            for i, e in enumerate(events):
                if row[2+i] == "EXPOSED":
                    icur.insertRow([shp, e, lbl[e], rank[e], oid])
                    n += 1
    print("  " + out_name + ": " + str(n) + " rows")
    return out, n

def build_long_roads(src, out_name):
    """Roads: one row per (segment x event), carrying per-event flooded miles."""
    out = os.path.join(LONG, out_name)
    if arcpy.Exists(out): arcpy.management.Delete(out)
    arcpy.management.CreateFeatureclass(LONG, out_name, "POLYLINE", spatial_reference=sr)
    arcpy.management.AddField(out, "EVENT", "TEXT", field_length=10)
    arcpy.management.AddField(out, "EVENT_LBL", "TEXT", field_length=40)
    arcpy.management.AddField(out, "RANK", "SHORT")
    arcpy.management.AddField(out, "FLOOD_MI", "DOUBLE")

    have_flmi = all(fex(src,"FLMI_"+e.upper()) for e in events)
    have_exp  = all(fex(src,"EXPOSED_"+e.upper()) for e in events)
    if not (have_flmi or have_exp):
        print("  ERROR: roads missing FLMI_/EXPOSED_ fields.")
        return out, 0

    read = ["SHAPE@"] + \
           (["FLMI_"+e.upper() for e in events] if have_flmi else []) + \
           (["EXPOSED_"+e.upper() for e in events] if have_exp else [])
    ins = ["SHAPE@","EVENT","EVENT_LBL","RANK","FLOOD_MI"]
    n = 0
    with arcpy.da.SearchCursor(src, read) as scur, arcpy.da.InsertCursor(out, ins) as icur:
        for row in scur:
            shp = row[0]
            for i, e in enumerate(events):
                mi = 0; exposed = False
                idx = 1
                if have_flmi:
                    mi = row[idx + i] or 0
                    idx += len(events)
                    exposed = mi > 0
                if have_exp:
                    exposed = exposed or (row[idx + i] == "EXPOSED")
                if exposed:
                    icur.insertRow([shp, e, lbl[e], rank[e], mi])
                    n += 1
    print("  " + out_name + ": " + str(n) + " rows")
    return out, n

def build_long_bg(src, out_name):
    """Block groups: one row per (BG x event) with POP_EXP for that event."""
    out = os.path.join(LONG, out_name)
    if arcpy.Exists(out): arcpy.management.Delete(out)
    arcpy.management.CreateFeatureclass(LONG, out_name, "POLYGON", spatial_reference=sr)
    for f,t,l in [("EVENT","TEXT",10),("EVENT_LBL","TEXT",40),("RANK","SHORT",None),
                  ("GEOID","TEXT",15),("POP_EXP","DOUBLE",None),("SVI_CLASS","TEXT",15)]:
        if l: arcpy.management.AddField(out, f, t, field_length=l)
        else: arcpy.management.AddField(out, f, t)

    have = all(fex(src,"POP_EXP_"+e.upper()) for e in events)
    if not have:
        print("  ERROR: block groups missing POP_EXP_<event> fields.")
        return out, 0
    svi = fex(src,"SVI_CLASS")
    geoid = fex(src,"GEOID")

    read = ["SHAPE@"] + ["POP_EXP_"+e.upper() for e in events] + \
           (["GEOID"] if geoid else []) + (["SVI_CLASS"] if svi else [])
    ins = ["SHAPE@","EVENT","EVENT_LBL","RANK","GEOID","POP_EXP","SVI_CLASS"]
    n = 0
    with arcpy.da.SearchCursor(src, read) as scur, arcpy.da.InsertCursor(out, ins) as icur:
        for row in scur:
            shp = row[0]
            popvals = [row[1+i] for i in range(len(events))]
            extra = 1 + len(events)
            g = row[extra] if geoid else ""
            s = row[extra + (1 if geoid else 0)] if svi else ""
            for i, e in enumerate(events):
                pop = popvals[i] or 0
                if pop > 0:
                    icur.insertRow([shp, e, lbl[e], rank[e], g, pop, s])
                    n += 1
    print("  " + out_name + ": " + str(n) + " rows")
    return out, n

print("=== Phase 8: Long-format restructure ===")
print("")
print("Buildings ..."); build_long_points(BLDG, "Buildings_Long", "POINT")
print("Hospitals ..."); build_long_points(HOSP, "Hospitals_Long", "POINT")
print("Roads ...");     build_long_roads(ROADS, "Roads_Long")
print("Block groups ..."); build_long_bg(BG, "BlockGroups_Long")

print("")
print("=== Verification: exact-match EVENT counts (should be CUMULATIVE) ===")
for name in ["Buildings_Long","Hospitals_Long"]:
    fc = os.path.join(LONG, name)
    if not arcpy.Exists(fc): continue
    print("  " + name + ":")
    for e in events:
        n = 0
        with arcpy.da.SearchCursor(fc, ["EVENT"], "EVENT = '" + e + "'") as c:
            for _ in c: n += 1
        print("    EVENT='" + e + "': " + str(n))

print("")
print("=== Done. Publish these LONG layers + FloodExtent_AllEvents. ===")
print("Build the selector on FloodExtent_AllEvents (category field = EVENT).")
print("Field-match action: Source EVENT  ->  Target EVENT  on every long layer.")
print("All layers then filter cumulatively by exact EVENT match.")