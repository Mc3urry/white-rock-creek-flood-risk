import arcpy, os
from arcpy.sa import *

# -- Configuration -------------------------------------------------------------
ROOT      = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB       = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
BASE      = os.path.join(ROOT, "Data", "GIS", "BaseData")
HYDRO_DS  = os.path.join(GDB, "Hydrology")
ANALYSIS  = os.path.join(GDB, "Analysis")
DEM_IN    = os.path.join(BASE, "DEM_Clipped.tif")
COUNTY    = os.path.join(BASE, "DallasCountyBoundary", "DallasCounty_Boundary.shp")
SR        = arcpy.SpatialReference(2276)

# NHD streams used to constrain the auto pour-point search to White Rock Creek.
# Uses the loaded FC_Streams if present (clipped NHD). Falls back to manual coords.
NHD_STREAMS = os.path.join(GDB, "Hydrology", "FC_Streams")

# ============================================================================
# POUR POINT MODE
#   "AUTO"   = script finds the outlet automatically (highest flow accumulation
#              along White Rock Creek). Recommended -- no manual coordinate hunt.
#   "MANUAL" = use the POUR_X / POUR_Y coordinates below instead.
# ============================================================================
POUR_MODE = "AUTO"
POUR_X = 2480500   # only used if POUR_MODE = "MANUAL"
POUR_Y = 6970000
# ============================================================================

arcpy.CheckOutExtension("Spatial")
arcpy.env.overwriteOutput = True
arcpy.env.snapRaster      = DEM_IN
arcpy.env.cellSize        = 10
arcpy.env.outputCoordinateSystem = SR
arcpy.env.mask            = COUNTY

print("=== Phase 4: Terrain Analysis and Watershed Delineation ===")
print("")

# -- Pre-flight ----------------------------------------------------------------
print("Pre-flight checks")
if not arcpy.Exists(DEM_IN):
    print("  ERROR: DEM_Clipped.tif not found. Run Phase 2 raster steps first.")
    raise SystemExit
print("  OK DEM_Clipped.tif found")
if not arcpy.Exists(ANALYSIS):
    arcpy.management.CreateFeatureDataset(GDB, "Analysis", SR)
    print("  OK Created missing Analysis feature dataset")
else:
    print("  OK Analysis feature dataset present")
print("")

def save_raster(raster_obj, name):
    out = os.path.join(BASE, name)
    raster_obj.save(out)
    desc = arcpy.Describe(out)
    print("  OK Saved: " + name + " | extent: " +
          str(round(desc.extent.width,0)) + " x " + str(round(desc.extent.height,0)) + " ft")
    return out

# -- Step 1: Fill --------------------------------------------------------------
print("Step 1: Fill sinks")
dem_fill      = Fill(DEM_IN)
dem_fill_path = save_raster(dem_fill, "DEM_Filled.tif")
diff_max = float(arcpy.management.GetRasterProperties(Minus(dem_fill, Raster(DEM_IN)), "MAXIMUM")[0])
print("  Max fill change: " + str(round(diff_max, 2)) + " ft")
print("")

# -- Step 2: Flow direction ----------------------------------------------------
print("Step 2: Flow direction")
flow_dir = FlowDirection(dem_fill, "NORMAL", "", "D8")
save_raster(flow_dir, "FlowDirection.tif")
print("")

# -- Step 3: Flow accumulation -------------------------------------------------
print("Step 3: Flow accumulation")
flow_acc      = FlowAccumulation(flow_dir, "", "FLOAT", "D8")
flow_acc_path = save_raster(flow_acc, "FlowAccum.tif")
max_acc = float(arcpy.management.GetRasterProperties(flow_acc, "MAXIMUM")[0])
print("  Max flow accumulation: " + str(round(max_acc, 0)) + " cells")
print("")

# -- Step 4: Stream raster -----------------------------------------------------
print("Step 4: Stream raster extraction")
STREAM_THRESHOLD = 1000
streams_raster = Con(flow_acc > STREAM_THRESHOLD, 1)
save_raster(streams_raster, "Streams_Raster.tif")
print("")

# -- Step 5: Stream order ------------------------------------------------------
print("Step 5: Stream order")
save_raster(StreamOrder(streams_raster, flow_dir, "STRAHLER"), "StreamOrder.tif")
print("")

# -- Step 6: Stream to polyline ------------------------------------------------
print("Step 6: Stream raster to polyline")
streams_fc = os.path.join(HYDRO_DS, "FC_Streams_Derived")
if arcpy.Exists(streams_fc):
    arcpy.management.Delete(streams_fc)
arcpy.sa.StreamToFeature(streams_raster, flow_dir, streams_fc, "SIMPLIFY")
print("  OK FC_Streams_Derived: " + str(int(arcpy.management.GetCount(streams_fc)[0])) + " segments")
print("")

# -- Step 7: Pour point (AUTO or MANUAL) ---------------------------------------
print("Step 7: Pour point placement (mode = " + POUR_MODE + ")")
scratch = arcpy.env.scratchGDB

def auto_find_outlet():
    """
    Find the outlet automatically:
      - If NHD White Rock Creek streams are available, restrict the flow-accumulation
        search to a buffer around them (avoids snapping to the Trinity River).
      - Otherwise use the global max-accumulation cell.
    Returns (x, y) of the highest-accumulation cell in the search area.
    """
    search_acc = flow_acc

    if arcpy.Exists(NHD_STREAMS):
        # Try to isolate White Rock Creek by name if a name field exists
        name_field = None
        for f in arcpy.ListFields(NHD_STREAMS):
            if f.name.upper() in ("GNIS_NAME", "NAME", "FULLNAME", "GNIS_NM"):
                name_field = f.name
                break

        streams_lyr = arcpy.management.MakeFeatureLayer(NHD_STREAMS, "nhd_lyr")
        used_name = False
        if name_field:
            arcpy.management.SelectLayerByAttribute(
                streams_lyr, "NEW_SELECTION",
                name_field + " LIKE '%White Rock%'")
            sel = int(arcpy.management.GetCount(streams_lyr)[0])
            if sel > 0:
                used_name = True
                print("  Found " + str(sel) + " White Rock Creek segments by name")
            else:
                arcpy.management.SelectLayerByAttribute(streams_lyr, "CLEAR_SELECTION")

        # Buffer the (selected) streams and mask flow accumulation to that buffer
        buf = os.path.join(scratch, "wr_buffer")
        if arcpy.Exists(buf):
            arcpy.management.Delete(buf)
        arcpy.analysis.Buffer(streams_lyr, buf, "500 Feet", dissolve_option="ALL")
        search_acc = ExtractByMask(flow_acc, buf)
        if used_name:
            print("  Searching for outlet within 500 ft of White Rock Creek")
        else:
            print("  Searching for outlet within 500 ft of all NHD streams")
        arcpy.management.Delete(streams_lyr)
    else:
        print("  NHD streams not found -- using global max accumulation cell")

    # Find max value within the search area
    max_val = float(arcpy.management.GetRasterProperties(search_acc, "MAXIMUM")[0])
    # Isolate the max cell(s), convert to point
    max_cell = Con(search_acc >= max_val - 0.5, 1)
    max_pts  = os.path.join(scratch, "max_acc_pt")
    if arcpy.Exists(max_pts):
        arcpy.management.Delete(max_pts)
    arcpy.conversion.RasterToPoint(max_cell, max_pts, "Value")
    # Take the first point
    with arcpy.da.SearchCursor(max_pts, ["SHAPE@XY"]) as cur:
        for row in cur:
            x, y = row[0]
            arcpy.management.Delete(max_pts)
            return (x, y)
    return None

if POUR_MODE == "AUTO":
    coords = auto_find_outlet()
    if coords is None:
        print("  ERROR: Auto outlet detection failed -- switch POUR_MODE to MANUAL")
        raise SystemExit
    px, py = coords
    print("  Auto-detected outlet at (" + str(round(px,1)) + ", " + str(round(py,1)) + ")")
else:
    px, py = POUR_X, POUR_Y
    print("  Manual outlet at (" + str(px) + ", " + str(py) + ")")

pour_pt_path = os.path.join(ANALYSIS, "PourPoint")
if arcpy.Exists(pour_pt_path):
    arcpy.management.Delete(pour_pt_path)
arcpy.management.CreateFeatureclass(ANALYSIS, "PourPoint", "POINT", spatial_reference=SR)
arcpy.management.AddField(pour_pt_path, "Name", "TEXT", field_length=50)
with arcpy.da.InsertCursor(pour_pt_path, ["SHAPE@XY", "Name"]) as cur:
    cur.insertRow([(px, py), "White Rock Creek Outlet"])

pour_snapped = os.path.join(ANALYSIS, "PourPoint_Snapped")
if arcpy.Exists(pour_snapped):
    arcpy.management.Delete(pour_snapped)
snapped = arcpy.sa.SnapPourPoint(pour_pt_path, flow_acc, 200)
snapped.save(pour_snapped)
print("  OK Pour point snapped to stream")
print("")

# -- Step 8: Watershed ---------------------------------------------------------
print("Step 8: Watershed delineation")
watershed_raster = Watershed(flow_dir, pour_snapped, "Value")
watershed_raster_path = save_raster(watershed_raster, "Watershed_Raster.tif")

watershed_poly = os.path.join(ANALYSIS, "FC_Watershed_Boundary")
if arcpy.Exists(watershed_poly):
    arcpy.management.Delete(watershed_poly)
arcpy.conversion.RasterToPolygon(watershed_raster_path, watershed_poly, "SIMPLIFY", "Value")
arcpy.management.CalculateGeometryAttributes(watershed_poly, [["AREA_ACRES","AREA"]], area_unit="ACRES")

ws_area = 0
with arcpy.da.SearchCursor(watershed_poly, ["AREA_ACRES"]) as cur:
    for row in cur:
        ws_area += (row[0] or 0)
sqmi = ws_area / 640
print("  Watershed area: " + str(round(ws_area, 1)) + " acres (" + str(round(sqmi, 1)) + " sq miles)")

if ws_area < 50000:
    print("  WARNING: Watershed small (<78 sq mi) -- outlet may be too far upstream")
    print("           Try POUR_MODE = MANUAL with a point further downstream.")
elif ws_area > 120000:
    print("  WARNING: Watershed large (>187 sq mi) -- may have caught the Trinity River")
    print("           Ensure NHD White Rock Creek streams are loaded for AUTO mode.")
else:
    print("  LOOKS GOOD: area is in the expected range for White Rock Creek")
print("")

# -- Step 9: Slope -------------------------------------------------------------
print("Step 9: Slope")
save_raster(Slope(dem_fill, "PERCENT_RISE"), "Slope_Percent.tif")
save_raster(Slope(dem_fill, "DEGREE"),       "Slope_Degree.tif")
print("")

# -- Step 10: Hillshade --------------------------------------------------------
print("Step 10: Hillshade")
save_raster(Hillshade(dem_fill, 315, 45, "SHADOWS", 1), "Hillshade_315.tif")
save_raster(Hillshade(dem_fill, 225, 45, "SHADOWS", 1), "Hillshade_225.tif")
print("")

# -- Step 11: HEC-RAS terrain --------------------------------------------------
print("Step 11: Export terrain for HEC-RAS")
hecras_terrain = os.path.join(ROOT, "Data", "HECRAS", "Terrain", "DEM_HECRAS.tif")
os.makedirs(os.path.dirname(hecras_terrain), exist_ok=True)
arcpy.management.CopyRaster(dem_fill_path, hecras_terrain, pixel_type="32_BIT_FLOAT")
print("  OK DEM_HECRAS.tif exported")
print("")

# -- Step 12: Clip to watershed ------------------------------------------------
print("Step 12: Clipping feature classes to watershed boundary")
clip_targets = [
    ("BaseData",      "FC_Buildings"),
    ("Infrastructure","FC_Roads"),
    ("Infrastructure","FC_Hospitals"),
    ("Infrastructure","FC_FireStations"),
    ("Infrastructure","FC_PoliceStations"),
    ("Infrastructure","FC_Schools"),
    ("Demographics",  "FC_BlockGroups"),
    ("FloodHazards",  "FC_FEMA_FloodZones"),
    ("Hydrology",     "FC_Streams"),
]
clipped = 0
for ds, fc in clip_targets:
    in_fc  = os.path.join(GDB, ds, fc)
    out_fc = os.path.join(GDB, ds, fc + "_WS")
    if arcpy.Exists(in_fc):
        if arcpy.Exists(out_fc):
            arcpy.management.Delete(out_fc)
        arcpy.analysis.Clip(in_fc, watershed_poly, out_fc)
        print("  OK " + fc + "_WS: " + str(int(arcpy.management.GetCount(out_fc)[0])) + " features")
        clipped += 1
    else:
        print("  SKIPPED (not loaded): " + fc)
print("  Clipped " + str(clipped) + " layers")
print("")

# -- Step 13: Stats ------------------------------------------------------------
print("=== Terrain Statistics ===")
for rname, label in [("DEM_Filled.tif","Elevation (ft)"),
                      ("Slope_Percent.tif","Slope (%)")]:
    rpath = os.path.join(BASE, rname)
    if arcpy.Exists(rpath):
        mn = float(arcpy.management.GetRasterProperties(rpath,"MINIMUM")[0])
        mx = float(arcpy.management.GetRasterProperties(rpath,"MAXIMUM")[0])
        print("  " + label + ": " + str(round(mn,1)) + " - " + str(round(mx,1)))

arcpy.CheckInExtension("Spatial")
print("")
print("=== Phase 4 complete ===")
if 50000 <= ws_area <= 120000:
    print("Watershed area looks correct. Verify the boundary visually, then proceed to Phase 5.")
else:
    print("Watershed area is outside expected range -- review the warning above before Phase 5.")