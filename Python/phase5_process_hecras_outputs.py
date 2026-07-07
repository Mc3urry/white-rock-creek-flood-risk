import arcpy, os, time
from arcpy.sa import *

ROOT     = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB      = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
BASE     = os.path.join(ROOT, "Data", "GIS", "BaseData")
FLOOD_DS = os.path.join(GDB, "FloodHazards")
ANALYSIS = os.path.join(GDB, "Analysis")
EXPORTS  = os.path.join(ROOT, "Data", "HECRAS", "Exports")
DOCS     = os.path.join(ROOT, "Documentation")
DEM      = os.path.join(BASE, "DEM_Filled.tif")
SR       = arcpy.SpatialReference(2276)

arcpy.CheckOutExtension("Spatial")
arcpy.env.overwriteOutput = True
arcpy.env.snapRaster      = DEM
arcpy.env.cellSize        = 10
arcpy.env.outputCoordinateSystem = SR

scratch = arcpy.env.scratchGDB
EVENTS  = ["10yr", "50yr", "100yr", "500yr"]

print("=== Phase 5: Processing HEC-RAS Outputs ===")
print("")
print("PREREQUISITE -- export these from RAS Mapper to:")
print("  " + EXPORTS)
print("  Reading WSE_<event>.Terrain.DEM_HECRAS.tif and Velocity_<event>.Terrain.DEM_HECRAS.tif")
print("  Results -> Velocity -> Export Raster -> Velocity_10yr.tif (etc.)")
print("  Keep OneDrive PAUSED while running this script.")
print("")

# -- Ensure FloodHazards dataset exists ----------------------------------------
if not arcpy.Exists(FLOOD_DS):
    arcpy.management.CreateFeatureDataset(GDB, "FloodHazards", SR)
    print("  OK Created FloodHazards feature dataset")

# -- Step 1: Verify WSE rasters ------------------------------------------------
print("Step 1: Verifying WSE exports")
wse_paths = {}
for evt in EVENTS:
    p = os.path.join(EXPORTS, "WSE_" + evt + ".Terrain.DEM_HECRAS.tif")
    if arcpy.Exists(p):
        mn = float(arcpy.management.GetRasterProperties(p, "MINIMUM")[0])
        mx = float(arcpy.management.GetRasterProperties(p, "MAXIMUM")[0])
        print("  OK WSE_" + evt + ".tif | range " + str(round(mn,1)) + " - " + str(round(mx,1)) + " ft")
        wse_paths[evt] = p
    else:
        print("  MISSING: WSE_" + evt + ".tif  (export from RAS Mapper)")

if not wse_paths:
    print("")
    print("  No WSE rasters found. Complete the HEC-RAS modeling and export first.")
    print("  See the Phase 5 manual steps. Nothing to process yet.")
    raise SystemExit

# -- Step 2: Flood depth (WSE - terrain) ---------------------------------------
print("")
print("Step 2: Flood depth rasters (WSE minus terrain)")
depth_paths = {}
terrain = Raster(DEM)
for evt in EVENTS:
    if evt not in wse_paths:
        continue
    wse   = Raster(wse_paths[evt])
    depth = Con((wse - terrain) > 0, wse - terrain, 0)
    out_path = os.path.join(BASE, "Depth_" + evt + ".tif")
    depth.save(out_path)
    mx = float(arcpy.management.GetRasterProperties(out_path, "MAXIMUM")[0])
    print("  OK Depth_" + evt + ".tif | max depth " + str(round(mx,1)) + " ft")
    depth_paths[evt] = out_path
    # Filtered depth for clean floodplain mapping (rain-on-grid: mask < 1.0 ft)
    depth_filt = Con(Raster(out_path) >= 1.0, Raster(out_path))
    depth_filt.save(os.path.join(BASE, "DepthFiltered_" + evt + ".tif"))
    print("    OK DepthFiltered_" + evt + ".tif (>= 1.0 ft only, for mapping)")

# -- Step 3: Classify depth ----------------------------------------------------
print("")
print("Step 3: Classifying flood depths")
for evt, dpath in depth_paths.items():
    remap = RemapRange([[0,1,1],[1,3,2],[3,6,3],[6,9999,4]])
    Reclassify(dpath, "Value", remap, "NODATA").save(
        os.path.join(BASE, "DepthClass_" + evt + ".tif"))
    print("  OK DepthClass_" + evt + ".tif (1=Minor 2=Moderate 3=Major 4=Severe)")

# -- Step 4: Velocity ----------------------------------------------------------
print("")
print("Step 4: Velocity rasters")
vel_paths = {}
for evt in EVENTS:
    p = os.path.join(EXPORTS, "Velocity_" + evt + ".Terrain.DEM_HECRAS.tif")
    if arcpy.Exists(p):
        mx = float(arcpy.management.GetRasterProperties(p, "MAXIMUM")[0])
        print("  OK Velocity_" + evt + ".tif | max " + str(round(mx,1)) + " fps")
        vel_paths[evt] = p
        remap_v = RemapRange([[0,2,1],[2,5,2],[5,999,3]])
        Reclassify(p, "Value", remap_v, "NODATA").save(
            os.path.join(BASE, "VelClass_" + evt + ".tif"))
        print("    OK VelClass_" + evt + ".tif")
    else:
        print("  MISSING: Velocity_" + evt + ".tif")

# -- Step 5: Flood extent polygons ---------------------------------------------
print("")
print("Step 5: Flood extent polygons")
for evt, dpath in depth_paths.items():
    # Rain-on-grid filter: only keep depths >= 1.0 ft as true floodplain
    # (strips the thin rain film that rain-on-grid leaves on hillsides)
    FLOOD_DEPTH_THRESHOLD = 1.0
    flooded = Con(Raster(dpath) >= FLOOD_DEPTH_THRESHOLD, 1)
    tmp_ras = os.path.join(scratch, "flooded_" + evt)
    if arcpy.Exists(tmp_ras):
        arcpy.management.Delete(tmp_ras)
    flooded.save(tmp_ras)
    out_fc = os.path.join(FLOOD_DS, "FloodExtent_" + evt)
    if arcpy.Exists(out_fc):
        arcpy.management.Delete(out_fc)
    arcpy.conversion.RasterToPolygon(tmp_ras, out_fc, "SIMPLIFY", "Value")
    with arcpy.da.UpdateCursor(out_fc, ["gridcode"]) as cur:
        for row in cur:
            if row[0] != 1:
                cur.deleteRow()
    arcpy.management.AddField(out_fc, "FLOOD_EVENT", "TEXT", field_length=20)
    arcpy.management.CalculateField(out_fc, "FLOOD_EVENT", '"' + evt + '"', "PYTHON3")
    arcpy.management.CalculateGeometryAttributes(out_fc, [["AREA_ACRES","AREA"]], area_unit="ACRES")
    total = 0
    with arcpy.da.SearchCursor(out_fc, ["AREA_ACRES"]) as cur:
        for r in cur:
            total += (r[0] or 0)
    print("  OK FloodExtent_" + evt + ": " + str(round(total,1)) + " acres")
    arcpy.management.Delete(tmp_ras)

# -- Step 6: FEMA comparison ---------------------------------------------------
print("")
print("Step 6: FEMA vs modeled 100-year comparison")
fema_fc  = os.path.join(GDB, "FloodHazards", "FC_FEMA_FloodZones_WS")
model_fc = os.path.join(FLOOD_DS, "FloodExtent_100yr")

if arcpy.Exists(fema_fc) and arcpy.Exists(model_fc):
    # find the flood zone field
    zone_field = None
    for f in arcpy.ListFields(fema_fc):
        if f.name.upper() in ("FLD_ZONE","ZONE","FLDZONE"):
            zone_field = f.name
            break
    fema_area = 0
    if zone_field:
        lyr = arcpy.management.MakeFeatureLayer(fema_fc, "fema_lyr", zone_field + " = 'AE'")
        arcpy.management.CalculateGeometryAttributes(lyr, [["AREA_ACRES","AREA"]], area_unit="ACRES")
        with arcpy.da.SearchCursor(lyr, ["AREA_ACRES"]) as cur:
            fema_area = sum((r[0] or 0) for r in cur)
        arcpy.management.Delete(lyr)
    model_area = 0
    with arcpy.da.SearchCursor(model_fc, ["AREA_ACRES"]) as cur:
        model_area = sum((r[0] or 0) for r in cur)
    diff = model_area - fema_area
    pct  = (diff/fema_area*100) if fema_area > 0 else 0
    print("  FEMA 100-yr (AE):  " + str(round(fema_area,1)) + " acres")
    print("  Modeled 100-yr:    " + str(round(model_area,1)) + " acres")
    print("  Difference:        " + str(round(diff,1)) + " acres (" + str(round(pct,1)) + "%)")
    os.makedirs(DOCS, exist_ok=True)
    with open(os.path.join(DOCS, "FEMA_Comparison.txt"), "w") as f:
        f.write("FEMA vs Modeled Floodplain Comparison\n")
        f.write("=" * 40 + "\n")
        f.write("FEMA 100-yr (AE): " + str(round(fema_area,1)) + " acres\n")
        f.write("Modeled 100-yr:   " + str(round(model_area,1)) + " acres\n")
        f.write("Difference:       " + str(round(diff,1)) + " acres (" + str(round(pct,1)) + "%)\n")
    print("  OK FEMA_Comparison.txt saved")
else:
    print("  SKIPPED -- need FC_FEMA_FloodZones_WS and FloodExtent_100yr")

# -- Step 7: Summary -----------------------------------------------------------
print("")
print("=== Flood Simulation Summary ===")
print("{:<8} {:<20} {:<16} {}".format("Event","Inundation (ac)","Max Depth (ft)","Max Vel (fps)"))
print("-" * 60)
for evt in EVENTS:
    dpath  = os.path.join(BASE, "Depth_" + evt + ".tif")
    vpath  = os.path.join(EXPORTS, "Velocity_" + evt + ".Terrain.DEM_HECRAS.tif")
    ext_fc = os.path.join(FLOOD_DS, "FloodExtent_" + evt)
    area = md = mv = "N/A"
    if arcpy.Exists(ext_fc):
        with arcpy.da.SearchCursor(ext_fc, ["AREA_ACRES"]) as cur:
            area = str(round(sum((r[0] or 0) for r in cur),0))
    if arcpy.Exists(dpath):
        md = str(round(float(arcpy.management.GetRasterProperties(dpath,"MAXIMUM")[0]),1))
    if arcpy.Exists(vpath):
        mv = str(round(float(arcpy.management.GetRasterProperties(vpath,"MAXIMUM")[0]),1))
    print("{:<8} {:<20} {:<16} {}".format(evt, area, md, mv))

arcpy.CheckInExtension("Spatial")
print("")
print("=== Phase 5 processing complete ===")