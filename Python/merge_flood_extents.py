"""
Merge FloodExtent_10yr / 50yr / 100yr / 500yr into ONE layer with a RANK field,
so a dashboard category selector can filter it (RANK <= selected) and the flood
boundary grows as rarer events are chosen.

Output: FloodExtent_AllEvents  (in FloodHazards dataset)
Fields:
  EVENT      text   '10yr' / '50yr' / '100yr' / '500yr'
  RANK       short  1 / 2 / 3 / 4
  EVENT_LBL  text   '10-Year (10% AEP)' etc. (for popups)

Draw order note: because polygons overlap, symbolize with the 500yr (rank 4,
largest/palest) at bottom and 10yr (rank 1, darkest) on top, OR just filter
RANK <= N so only the relevant nested set shows. For a single-color flood
boundary that grows with the selector, filter RANK <= {value} and use one blue.
"""
import arcpy, os

ROOT  = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB   = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
FLOOD = os.path.join(GDB, "FloodHazards")
OUT   = os.path.join(FLOOD, "FloodExtent_AllEvents")

events = [("10yr", 1, "10-Year (10% AEP)"),
          ("50yr", 2, "50-Year (2% AEP)"),
          ("100yr", 3, "100-Year (1% AEP)"),
          ("500yr", 4, "500-Year (0.2% AEP)")]

arcpy.env.overwriteOutput = True
sr = arcpy.SpatialReference(2276)

print("=== Merging flood extents into one ranked layer ===")

# Create empty output polygon FC
if arcpy.Exists(OUT):
    arcpy.management.Delete(OUT)
arcpy.management.CreateFeatureclass(FLOOD, "FloodExtent_AllEvents", "POLYGON",
                                    spatial_reference=sr)
arcpy.management.AddField(OUT, "EVENT", "TEXT", field_length=10)
arcpy.management.AddField(OUT, "RANK", "SHORT")
arcpy.management.AddField(OUT, "EVENT_LBL", "TEXT", field_length=40)

# Append each event's dissolved extent as one row
insert_fields = ["SHAPE@", "EVENT", "RANK", "EVENT_LBL"]
with arcpy.da.InsertCursor(OUT, insert_fields) as icur:
    for evt, rank, lbl in events:
        src = os.path.join(FLOOD, "FloodExtent_" + evt)
        if not arcpy.Exists(src):
            print("  WARNING missing " + evt + " -- skipping")
            continue
        # dissolve source to a single multipart polygon so one row per event
        tmp = os.path.join(arcpy.env.scratchGDB, "diss_" + evt)
        if arcpy.Exists(tmp):
            arcpy.management.Delete(tmp)
        arcpy.management.Dissolve(src, tmp, multi_part="MULTI_PART")
        with arcpy.da.SearchCursor(tmp, ["SHAPE@"]) as scur:
            for row in scur:
                icur.insertRow([row[0], evt, rank, lbl])
        arcpy.management.Delete(tmp)
        print("  Added " + evt + " (RANK " + str(rank) + ")")

# Report
print("")
print("Rows in FloodExtent_AllEvents:")
with arcpy.da.SearchCursor(OUT, ["EVENT", "RANK", "SHAPE@AREA"]) as c:
    for evt, rank, area in c:
        print("  " + evt + " (rank " + str(rank) + "): " + str(round(area/43560,0)) + " ac")

print("")
print("=== Done. Publish FloodExtent_AllEvents, add to web map. ===")
print("Selector action: Filter this layer RANK <= {selected value}.")
print("Symbolize as one blue (#3182bd, ~55% opacity) so the boundary grows with the event.")