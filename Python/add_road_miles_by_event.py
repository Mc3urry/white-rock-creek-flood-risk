"""
Add per-event flooded MILEAGE to FC_Roads_WS so the roads indicator can show
dynamic miles (not just segment counts).

Adds FLMI_10YR, FLMI_50YR, FLMI_100YR, FLMI_500YR = cumulative flooded miles
for each event (miles of road within that event's extent). Because these are
cumulative already (a road flooded at 10yr is flooded at higher events), the
dashboard sums the ONE field matching the selected event -- no <= needed.
"""
import arcpy, os

ROOT  = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB   = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
FLOOD = os.path.join(GDB, "FloodHazards")
ROADS = os.path.join(GDB, "Infrastructure", "FC_Roads_WS")

events = ["10yr","50yr","100yr","500yr"]
scratch = arcpy.env.scratchGDB
arcpy.env.overwriteOutput = True

def fex(fc, name): return name in [f.name for f in arcpy.ListFields(fc)]

print("=== Adding per-event flooded miles to roads ===")
for evt in events:
    f = "FLMI_" + evt.upper()
    if not fex(ROADS, f):
        arcpy.management.AddField(ROADS, f, "DOUBLE")

# For each event: clip roads to extent, measure length, attribute back by OID.
# Simpler: intersect roads with extent, sum length per original road OID.
add_oid_field = "SRC_OID"
if not fex(ROADS, add_oid_field):
    arcpy.management.AddField(ROADS, add_oid_field, "LONG")
with arcpy.da.UpdateCursor(ROADS, ["OID@", add_oid_field]) as cur:
    for row in cur:
        row[1] = row[0]; cur.updateRow(row)

miles_by_event = {evt: {} for evt in events}
for evt in events:
    ext = os.path.join(FLOOD, "FloodExtent_" + evt)
    if not arcpy.Exists(ext):
        print("  WARNING missing " + evt); continue
    inter = os.path.join(scratch, "rd_x_" + evt)
    if arcpy.Exists(inter): arcpy.management.Delete(inter)
    arcpy.analysis.Intersect([ROADS, ext], inter)
    with arcpy.da.SearchCursor(inter, [add_oid_field, "SHAPE@LENGTH"]) as c:
        for oid, ln in c:
            miles_by_event[evt][oid] = miles_by_event[evt].get(oid, 0) + (ln or 0)/5280.0
    total = round(sum(miles_by_event[evt].values()), 1)
    print("  " + evt + ": " + str(total) + " flooded miles")
    arcpy.management.Delete(inter)

flds = [add_oid_field] + ["FLMI_" + e.upper() for e in events]
with arcpy.da.UpdateCursor(ROADS, flds) as cur:
    for row in cur:
        oid = row[0]
        for i, evt in enumerate(events):
            row[1+i] = round(miles_by_event[evt].get(oid, 0), 4)
        cur.updateRow(row)

print("")
print("Totals (sum each field for the indicator):")
for evt in events:
    f = "FLMI_" + evt.upper()
    tot = 0
    with arcpy.da.SearchCursor(ROADS, [f]) as c:
        for r in c: tot += (r[0] or 0)
    print("  " + f + ": " + str(round(tot,1)) + " mi")
print("")
print("=== Done. Overwrite roads web layer. Sum FLMI_<event> per selection. ===")