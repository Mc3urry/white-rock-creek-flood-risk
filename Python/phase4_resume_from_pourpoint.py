"""
Resume Phase 4 from the pour point step onward.
Uses the already-created rasters on disk (DEM_Filled, FlowDirection, FlowAccum)
so it skips the slow steps 1-6. Picks up at pour point -> watershed -> clip.

Run this if phase4 errored at/after Step 7 but the rasters from steps 1-6 exist.
"""

import arcpy, os
from arcpy.sa import *

ROOT     = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB      = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
BASE     = os.path.join(ROOT, "Data", "GIS", "BaseData")
ANALYSIS = os.path.join(GDB, "Analysis")
SR       = arcpy.SpatialReference(2276)

# Auto-detected outlet from the prior run
PX, PY = 2511687.4, 6958597.9

arcpy.CheckOutExtension("Spatial")
arcpy.env.overwriteOutput = True
arcpy.env.snapRaster = os.path.join(BASE, "DEM_Clipped.tif")
arcpy.env.cellSize   = 10
arcpy.env.outputCoordinateSystem = SR

flow_dir_path = os.path.join(BASE, "FlowDirection.tif")
flow_acc_path = os.path.join(BASE, "FlowAccum.tif")
dem_fill_path = os.path.join(BASE, "DEM_Filled.tif")

print("=== Phase 4 RESUME (from pour point) ===")
print("")

# Verify the rasters from steps 1-6 exist
for p in [flow_dir_path, flow_acc_path, dem_fill_path]:
    if not arcpy.Exists(p):
        print("  ERROR: missing required raster: " + os.path.basename(p))
        print("  Re-run the full phase4 script instead.")
        raise SystemExit
print("  OK Found FlowDirection, FlowAccum, DEM_Filled from prior run")
print("")

flow_dir = Raster(flow_dir_path)
flow_acc = Raster(flow_acc_path)

# Ensure Analysis dataset exists
if not arcpy.Exists(ANALYSIS):
    arcpy.management.CreateFeatureDataset(GDB, "Analysis", SR)

# -- Pour point ----------------------------------------------------------------
print("Step 7: Creating pour point at (" + str(PX) + ", " + str(PY) + ")")
pour_pt = os.path.join(ANALYSIS, "PourPoint")
if arcpy.Exists(pour_pt):
    arcpy.management.Delete(pour_pt)
arcpy.management.CreateFeatureclass(ANALYSIS, "PourPoint", "POINT", spatial_reference=SR)
arcpy.management.AddField(pour_pt, "Name", "TEXT", field_length=50)
with arcpy.da.InsertCursor(pour_pt, ["SHAPE@XY","Name"]) as cur:
    cur.insertRow([(PX, PY), "White Rock Creek Outlet"])

pour_snapped = os.path.join(ANALYSIS, "PourPoint_Snapped")
if arcpy.Exists(pour_snapped):
    arcpy.management.Delete(pour_snapped)
snapped = arcpy.sa.SnapPourPoint(pour_pt, flow_acc, 200)
snapped.save(pour_snapped)
print("  OK Pour point snapped")
print("")

# -- Watershed -----------------------------------------------------------------
print("Step 8: Watershed delineation")
ws_raster = Watershed(flow_dir, pour_snapped, "Value")
ws_raster_path = os.path.join(BASE, "Watershed_Raster.tif")
ws_raster.save(ws_raster_path)

watershed_poly = os.path.join(ANALYSIS, "FC_Watershed_Boundary")
if arcpy.Exists(watershed_poly):
    arcpy.management.Delete(watershed_poly)
arcpy.conversion.RasterToPolygon(ws_raster_path, watershed_poly, "SIMPLIFY", "Value")
arcpy.management.CalculateGeometryAttributes(watershed_poly, [["AREA_ACRES","AREA"]], area_unit="ACRES")

ws_area = 0
with arcpy.da.SearchCursor(watershed_poly, ["AREA_ACRES"]) as cur:
    for row in cur:
        ws_area += (row[0] or 0)
print("  Watershed area: " + str(round(ws_area,1)) + " acres (" + str(round(ws_area/640,1)) + " sq mi)")
if ws_area < 50000:
    print("  WARNING: small -- outlet may be too far upstream")
elif ws_area > 120000:
    print("  WARNING: large -- may have caught the Trinity River")
else:
    print("  LOOKS GOOD")
print("")

# -- Slope / Hillshade ---------------------------------------------------------
print("Step 9-10: Slope and Hillshade")
dem_fill = Raster(dem_fill_path)
Slope(dem_fill, "PERCENT_RISE").save(os.path.join(BASE, "Slope_Percent.tif"))
Slope(dem_fill, "DEGREE").save(os.path.join(BASE, "Slope_Degree.tif"))
Hillshade(dem_fill, 315, 45, "SHADOWS", 1).save(os.path.join(BASE, "Hillshade_315.tif"))
Hillshade(dem_fill, 225, 45, "SHADOWS", 1).save(os.path.join(BASE, "Hillshade_225.tif"))
print("  OK slope and hillshade saved")
print("")

# -- HEC-RAS terrain -----------------------------------------------------------
print("Step 11: HEC-RAS terrain export")
hecras_terrain = os.path.join(ROOT, "Data", "HECRAS", "Terrain", "DEM_HECRAS.tif")
os.makedirs(os.path.dirname(hecras_terrain), exist_ok=True)
arcpy.management.CopyRaster(dem_fill_path, hecras_terrain, pixel_type="32_BIT_FLOAT")
print("  OK DEM_HECRAS.tif exported")
print("")

# -- Clip to watershed ---------------------------------------------------------
print("Step 12: Clipping feature classes to watershed")
clip_targets = [
    ("BaseData","FC_Buildings"),("Infrastructure","FC_Roads"),
    ("Infrastructure","FC_Hospitals"),("Infrastructure","FC_FireStations"),
    ("Infrastructure","FC_PoliceStations"),("Infrastructure","FC_Schools"),
    ("Demographics","FC_BlockGroups"),("FloodHazards","FC_FEMA_FloodZones"),
    ("Hydrology","FC_Streams"),
]
for ds, fc in clip_targets:
    in_fc  = os.path.join(GDB, ds, fc)
    out_fc = os.path.join(GDB, ds, fc + "_WS")
    if arcpy.Exists(in_fc):
        if arcpy.Exists(out_fc):
            arcpy.management.Delete(out_fc)
        arcpy.analysis.Clip(in_fc, watershed_poly, out_fc)
        print("  OK " + fc + "_WS: " + str(int(arcpy.management.GetCount(out_fc)[0])) + " features")
    else:
        print("  SKIPPED (not loaded): " + fc)

arcpy.CheckInExtension("Spatial")
print("")
print("=== Phase 4 resume complete ===")