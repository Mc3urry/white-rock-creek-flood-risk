"""
Phase 4 watershed-only, hardened against OneDrive locks.
Writes the snapped pour point and watershed raster to the LOCAL scratch GDB first,
then copies the final polygon into the project geodatabase at the end.

PAUSE ONEDRIVE SYNC before running (tray icon -> Settings gear -> Pause syncing -> 2 hours).
"""

import arcpy, os
from arcpy.sa import *

ROOT     = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB      = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
BASE     = os.path.join(ROOT, "Data", "GIS", "BaseData")
ANALYSIS = os.path.join(GDB, "Analysis")
SR       = arcpy.SpatialReference(2276)

PX, PY = 2511687.4, 6958597.9

arcpy.CheckOutExtension("Spatial")
arcpy.env.overwriteOutput = True
arcpy.env.snapRaster = os.path.join(BASE, "DEM_Clipped.tif")
arcpy.env.cellSize   = 10
arcpy.env.outputCoordinateSystem = SR

# Use LOCAL scratch for all intermediates -- not the OneDrive-synced project GDB
scratch = arcpy.env.scratchGDB
scratch_folder = arcpy.env.scratchFolder
print("Scratch GDB (local): " + scratch)
print("")

flow_dir = Raster(os.path.join(BASE, "FlowDirection.tif"))
flow_acc = Raster(os.path.join(BASE, "FlowAccum.tif"))
dem_fill = Raster(os.path.join(BASE, "DEM_Filled.tif"))

if not arcpy.Exists(ANALYSIS):
    arcpy.management.CreateFeatureDataset(GDB, "Analysis", SR)

print("=== Watershed delineation (lock-hardened) ===")
print("")

# -- Pour point in scratch -----------------------------------------------------
print("Step 7: Pour point at (" + str(PX) + ", " + str(PY) + ")")
pour_pt = os.path.join(scratch, "PourPoint")
if arcpy.Exists(pour_pt):
    arcpy.management.Delete(pour_pt)
arcpy.management.CreateFeatureclass(scratch, "PourPoint", "POINT", spatial_reference=SR)
with arcpy.da.InsertCursor(pour_pt, ["SHAPE@XY"]) as cur:
    cur.insertRow([(PX, PY)])
print("  OK pour point created in scratch")

# Snap (returns a raster -> save to scratch)
snapped_ras = os.path.join(scratch_folder, "snap.tif")
if arcpy.Exists(snapped_ras):
    arcpy.management.Delete(snapped_ras)
snap_out = arcpy.sa.SnapPourPoint(pour_pt, flow_acc, 200)
snap_out.save(snapped_ras)
print("  OK snapped pour point raster saved to scratch")
print("")

# -- Watershed in scratch ------------------------------------------------------
print("Step 8: Watershed delineation (this is the slow step -- be patient)")
ws_ras = Watershed(flow_dir, snapped_ras, "Value")
ws_ras_path = os.path.join(scratch_folder, "ws.tif")
if arcpy.Exists(ws_ras_path):
    arcpy.management.Delete(ws_ras_path)
ws_ras.save(ws_ras_path)
print("  OK watershed raster computed and saved to scratch")

# Polygon in scratch
ws_poly_scratch = os.path.join(scratch, "ws_poly")
if arcpy.Exists(ws_poly_scratch):
    arcpy.management.Delete(ws_poly_scratch)
arcpy.conversion.RasterToPolygon(ws_ras_path, ws_poly_scratch, "SIMPLIFY", "Value")
arcpy.management.CalculateGeometryAttributes(ws_poly_scratch, [["AREA_ACRES","AREA"]], area_unit="ACRES")

ws_area = 0
with arcpy.da.SearchCursor(ws_poly_scratch, ["AREA_ACRES"]) as cur:
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

# -- Copy final products into project GDB --------------------------------------
print("Step 8b: Copying results into project geodatabase")
ws_poly_final = os.path.join(ANALYSIS, "FC_Watershed_Boundary")
if arcpy.Exists(ws_poly_final):
    arcpy.management.Delete(ws_poly_final)
arcpy.management.CopyFeatures(ws_poly_scratch, ws_poly_final)
print("  OK FC_Watershed_Boundary copied to project GDB")

pour_final = os.path.join(ANALYSIS, "PourPoint_Snapped")
# Convert snapped raster to a point for the record
if arcpy.Exists(pour_final):
    arcpy.management.Delete(pour_final)
arcpy.conversion.RasterToPoint(snapped_ras, pour_final, "Value")
print("  OK PourPoint_Snapped copied to project GDB")

# Save watershed raster to BaseData too
ws_ras_final = os.path.join(BASE, "Watershed_Raster.tif")
if arcpy.Exists(ws_ras_final):
    arcpy.management.Delete(ws_ras_final)
arcpy.management.CopyRaster(ws_ras_path, ws_ras_final)
print("  OK Watershed_Raster.tif saved to BaseData")
print("")

# -- Slope / Hillshade ---------------------------------------------------------
print("Step 9-10: Slope and Hillshade")
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
arcpy.management.CopyRaster(os.path.join(BASE,"DEM_Filled.tif"), hecras_terrain, pixel_type="32_BIT_FLOAT")
print("  OK DEM_HECRAS.tif exported")
print("")

# -- Clip ----------------------------------------------------------------------
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
        arcpy.analysis.Clip(in_fc, ws_poly_final, out_fc)
        print("  OK " + fc + "_WS: " + str(int(arcpy.management.GetCount(out_fc)[0])) + " features")
    else:
        print("  SKIPPED (not loaded): " + fc)

arcpy.CheckInExtension("Spatial")
print("")
print("=== Phase 4 watershed complete ===")
