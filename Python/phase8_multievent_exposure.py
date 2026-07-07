"""
Phase 8 helper -- Multi-event exposure for a fully dynamic dashboard.

Stamps per-event exposure + an EVENT_RANK on every layer the dashboard's
indicators use, so a single category selector (values 1..4) can filter them
all by EVENT_RANK <= selected:

  Buildings    -> EVENT_RANK (1=10yr .. 4=500yr)
  Hospitals    -> EVENT_RANK  (+ EXPOSED_<event>)
  BlockGroups  -> POP_EXP_<event>, and a per-event population via areal weight
  Roads        -> EVENT_RANK  (+ per-event flooded flag)

Cumulative logic: a feature flooded at 10yr is also flooded at 50/100/500,
so EVENT_RANK = the SMALLEST event that floods it. Filtering EVENT_RANK<=N
gives the cumulative set for event N.

Run in ArcGIS Pro Python window (OneDrive paused), then OVERWRITE each web layer.
"""
import arcpy, os

ROOT  = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB   = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
FLOOD = os.path.join(GDB, "FloodHazards")

BLDG   = os.path.join(GDB, "BaseData", "FC_Buildings_Exposed")
if not arcpy.Exists(BLDG):
    BLDG = os.path.join(GDB, "BaseData", "FC_Buildings_WS")
HOSP   = os.path.join(GDB, "Infrastructure", "FC_Hospitals_WS")
ROADS  = os.path.join(GDB, "Infrastructure", "FC_Roads_WS")
BG     = os.path.join(GDB, "Demographics", "FC_BlockGroups_WS")

events = ["10yr", "50yr", "100yr", "500yr"]
rank_of = {"10yr":1, "50yr":2, "100yr":3, "500yr":4}
scratch = arcpy.env.scratchGDB
arcpy.env.overwriteOutput = True

def fex(fc, name):
    return name in [f.name for f in arcpy.ListFields(fc)]

def add_if_missing(fc, name, ftype, length=None):
    if not fex(fc, name):
        if length:
            arcpy.management.AddField(fc, name, ftype, field_length=length)
        else:
            arcpy.management.AddField(fc, name, ftype)

def extent_path(evt):
    return os.path.join(FLOOD, "FloodExtent_" + evt)

def exposed_oids(fc, evt):
    """OIDs of features in fc intersecting the event extent."""
    ext = extent_path(evt)
    if not arcpy.Exists(ext):
        print("    WARNING missing extent " + evt)
        return set()
    lyr = arcpy.management.MakeFeatureLayer(fc, "lyr_tmp")
    arcpy.management.SelectLayerByLocation(lyr, "INTERSECT", ext, selection_type="NEW_SELECTION")
    oids = set()
    with arcpy.da.SearchCursor(lyr, ["OID@"]) as c:
        for r in c:
            oids.add(r[0])
    arcpy.management.Delete(lyr)
    return oids

def stamp_rank(fc, label):
    """Add EVENT_RANK + EXPOSED_<event> to a point/line layer by intersection."""
    print("  " + label + " ...")
    for evt in events:
        add_if_missing(fc, "EXPOSED_" + evt.upper(), "TEXT", 15)
    add_if_missing(fc, "EVENT_RANK", "SHORT")
    exp = {evt: exposed_oids(fc, evt) for evt in events}
    for evt in events:
        print("    " + evt + ": " + str(len(exp[evt])) + " exposed")
    flds = ["OID@"] + ["EXPOSED_" + e.upper() for e in events] + ["EVENT_RANK"]
    with arcpy.da.UpdateCursor(fc, flds) as cur:
        for row in cur:
            oid = row[0]
            rank = 0
            for i, evt in enumerate(events):
                is_exp = oid in exp[evt]
                row[1 + i] = "EXPOSED" if is_exp else "NOT_EXPOSED"
                if is_exp and rank == 0:
                    rank = rank_of[evt]
            row[-1] = rank
            cur.updateRow(row)

print("=== Phase 8: Multi-event exposure for dynamic dashboard ===")
print("")

# --- Buildings ---
if arcpy.Exists(BLDG):
    stamp_rank(BLDG, "Buildings")
else:
    print("  WARNING: buildings layer not found")

# --- Hospitals ---
if arcpy.Exists(HOSP):
    stamp_rank(HOSP, "Hospitals")
else:
    print("  WARNING: hospitals layer not found")

# --- Roads ---
if arcpy.Exists(ROADS):
    stamp_rank(ROADS, "Roads")
else:
    print("  WARNING: roads layer not found")

# --- Block groups: per-event exposed population via areal weighting ---
if arcpy.Exists(BG):
    print("  Block groups (population by event) ...")
    for evt in events:
        add_if_missing(BG, "POP_EXP_" + evt.upper(), "DOUBLE")
    # ensure total area
    add_if_missing(BG, "BG_AREA", "DOUBLE")
    with arcpy.da.UpdateCursor(BG, ["SHAPE@AREA", "BG_AREA"]) as cur:
        for row in cur:
            row[1] = row[0]
            cur.updateRow(row)
    # for each event, intersect and areal-weight population
    pop_by_event = {evt: {} for evt in events}
    for evt in events:
        ext = extent_path(evt)
        if not arcpy.Exists(ext):
            print("    WARNING missing extent " + evt)
            continue
        inter = os.path.join(scratch, "bg_x_" + evt)
        if arcpy.Exists(inter):
            arcpy.management.Delete(inter)
        arcpy.analysis.Intersect([BG, ext], inter)
        arcpy.management.AddField(inter, "FL_AREA", "DOUBLE")
        with arcpy.da.UpdateCursor(inter, ["SHAPE@AREA", "FL_AREA"]) as cur:
            for row in cur:
                row[1] = row[0]
                cur.updateRow(row)
        with arcpy.da.SearchCursor(inter, ["GEOID", "POP_TOTAL", "BG_AREA", "FL_AREA"]) as cur:
            for geoid, pop, tot, fl in cur:
                if tot and tot > 0:
                    ratio = min((fl or 0)/tot, 1.0)
                    pop_by_event[evt][geoid] = pop_by_event[evt].get(geoid, 0) + (pop or 0)*ratio
        arcpy.management.Delete(inter)
        total = round(sum(pop_by_event[evt].values()), 0)
        print("    " + evt + ": pop exposed = " + str(total))
    # write per-event population fields
    flds = ["GEOID"] + ["POP_EXP_" + e.upper() for e in events]
    with arcpy.da.UpdateCursor(BG, flds) as cur:
        for row in cur:
            geoid = row[0]
            for i, evt in enumerate(events):
                row[1 + i] = round(pop_by_event[evt].get(geoid, 0), 0)
            cur.updateRow(row)
else:
    print("  WARNING: block groups not found")

print("")
print("=== Verification: cumulative counts ===")
for fc, label in [(BLDG,"Buildings"), (HOSP,"Hospitals"), (ROADS,"Roads")]:
    if not arcpy.Exists(fc) or not fex(fc, "EVENT_RANK"):
        continue
    print("  " + label + ":")
    for rank, evt in [(1,"10yr"),(2,"50yr"),(3,"100yr"),(4,"500yr")]:
        n = 0
        with arcpy.da.SearchCursor(fc, ["EVENT_RANK"]) as c:
            for r in c:
                if r[0] is not None and 1 <= r[0] <= rank:
                    n += 1
        print("    <= " + evt + ": " + str(n))

print("")
print("=== Done. OVERWRITE these web layers in AGOL: ===")
print("  Buildings, Hospitals, Roads (now have EVENT_RANK + EXPOSED_<event>)")
print("  BlockGroups (now has POP_EXP_<event>)")
print("Then wire the selector: filter EVENT_RANK <= {value} on buildings/hospitals/roads,")
print("and switch the population indicator's field per event (see notes).")