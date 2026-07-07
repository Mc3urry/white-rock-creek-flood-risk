"""
Finish Phase 4: copy the already-computed watershed from scratch into the
project GDB, then run slope/hillshade/HEC-RAS export/clip.

Run AFTER phase4_watershed_only.py computed the watershed (it printed the area)
but failed to copy back. KEEP ONEDRIVE PAUSED while running this.
"""

import arcpy, os, time
from arcpy.sa import *

ROOT     = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB      = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
BASE     = os.path.join(ROOT, "Data", "GIS", "BaseData")
ANALYSIS = os.path.join(GDB, "Analysis")
SR       = arcpy.SpatialReference(2276)

arcpy.CheckOutExtension("Spatial")
arcpy.env.overwriteOutput = True

scratch        = arcpy.env.scratchGDB
scratch_folder = arcpy.env.scratchFolder

ws_poly_scratch = os.path.join(scratch, "ws_poly")
ws_ras_scratch  = os.path.join(scratch_folder, "ws.tif")
snap_ras_scratch= os.path.join(scratch_folder, "snap.tif")

print("=== Phase 4 finish: copy-back from scratch ===")
print("")

# Verify the scratch watershed still exists
if not arcpy.Exists(ws_poly_scratch):
    print("  ERROR: scratch watershed polygon not found.")
    print("  The scratch GDB may have been cleared. Re-run phase4_watershed_only.py.")
    raise SystemExit
print("  OK Found computed watershed in scratch")

# Report area
ws_area = 0
with arcpy.da.SearchCursor(ws_poly_scratch, ["AREA_ACRES"]) as cur:
    for row in cur:
        ws_area += (row[0] or 0)
print("  Watershed area: " + str(round(ws_area,1)) + " acres (" + str(round(ws_area/640,1)) + " sq mi)")
print("")

def robust_copy(src, dst, kind="features"):
    """Copy with up to 3 retries to ride out transient locks."""
    for attempt in range(1, 4):
        try:
            if arcpy.Exists(dst):
                arcpy.management.Delete(dst)
            if kind == "features":
                arcpy.management.CopyFeatures(src, dst)
            else:
                arcpy.management.CopyRaster(src, dst)
            print("  OK copied: " + os.path.basename(dst))
            return True
        except Exception as e:
            print("  attempt " + str(attempt) + " failed: " + str(e)[:80])
            time.sleep(3)
    print("  ERROR: could not copy " + os.path.basename(dst) + " after 3 tries")
    return False

# -- Copy watershed polygon into project GDB -----------------------------------
print("Copying watershed polygon to project GDB")
ws_poly_final = os.path.join(ANALYSIS, "FC_Watershed_Boundary")
ok = robust_copy(ws_poly_scratch, ws_poly_final, "features")
if not ok:
    raise SystemExit
print("")

# -- Snapped pour point --------------------------------------------------------
if arcpy.Exists(snap_ras_scratch):
    pour_final = os.path.join(ANALYSIS, "PourPoint_Snapped")
    try:
        if arcpy.Exists(pour_final):
            arcpy.management.Delete(pour_final)
        arcpy.conversion.RasterToPoint(snap_ras_scratch, pour_final, "Value")
        print("  OK PourPoint_Snapped copied")
    except Exception as e:
        print("  (skipping pour point copy: " + str(e)[:60] + ")")

# -- Watershed raster to BaseData ----------------------------------------------
if arcpy.Exists(ws_ras_scratch):
    robust_copy(ws_ras_scratch, os.path.join(BASE, "Watershed_Raster.tif"), "raster")
print("")

# -- Slope / Hillshade (compute straight to BaseData) --------------------------
print("Slope and Hillshade")
dem_fill = Raster(os.path.join(BASE, "DEM_Filled.tif"))
arcpy.env.snapRaster = os.path.join(BASE, "DEM_Clipped.tif")
arcpy.env.cellSize   = 10
arcpy.env.outputCoordinateSystem = SR
Slope(dem_fill, "PERCENT_RISE").save(os.path.join(BASE, "Slope_Percent.tif"))
Slope(dem_fill, "DEGREE").save(os.path.join(BASE, "Slope_Degree.tif"))
Hillshade(dem_fill, 315, 45, "SHADOWS", 1).save(os.path.join(BASE, "Hillshade_315.tif"))
Hillshade(dem_fill, 225, 45, "SHADOWS", 1).save(os.path.join(BASE, "Hillshade_225.tif"))
print("  OK slope and hillshade saved")
print("")

# -- HEC-RAS terrain -----------------------------------------------------------
print("HEC-RAS terrain export")
hecras_terrain = os.path.join(ROOT, "Data", "HECRAS", "Terrain", "DEM_HECRAS.tif")
os.makedirs(os.path.dirname(hecras_terrain), exist_ok=True)
arcpy.management.CopyRaster(os.path.join(BASE,"DEM_Filled.tif"), hecras_terrain, pixel_type="32_BIT_FLOAT")
print("  OK DEM_HECRAS.tif exported")
print("")

# -- Clip ----------------------------------------------------------------------
print("Clipping feature classes to watershed")
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
        try:
            if arcpy.Exists(out_fc):
                arcpy.management.Delete(out_fc)
            arcpy.analysis.Clip(in_fc, ws_poly_final, out_fc)
            print("  OK " + fc + "_WS: " + str(int(arcpy.management.GetCount(out_fc)[0])) + " features")
        except Exception as e:
            print("  ERROR clipping " + fc + ": " + str(e)[:60])
    else:
        print("  SKIPPED (not loaded): " + fc)

arcpy.CheckInExtension("Spatial")
print("")
print("=== Phase 4 finish complete ===")
