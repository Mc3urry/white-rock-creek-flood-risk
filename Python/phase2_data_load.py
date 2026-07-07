import arcpy
import os

# -- Configuration -------------------------------------------------------------
ROOT  = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB   = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
BASE  = os.path.join(ROOT, "Data", "GIS", "BaseData")
HYDRO = os.path.join(ROOT, "Data", "GIS", "Hydrology")
INFRA = os.path.join(ROOT, "Data", "GIS", "Infrastructure")
FLOOD = os.path.join(ROOT, "Data", "GIS", "FloodHazards")
DEMOG = os.path.join(ROOT, "Data", "GIS", "Demographics")
DOCS  = os.path.join(ROOT, "Documentation")

# Dallas County boundary
COUNTY_BOUNDARY = os.path.join(BASE, "DallasCountyBoundary", "DallasCounty_Boundary.shp")

# Coordinate system -- NAD83 Texas State Plane North Central (feet)
SR = arcpy.SpatialReference(2276)

arcpy.env.overwriteOutput = True

# -- Helper functions ----------------------------------------------------------
def project_and_clip(input_fc, output_name, dataset):
    """Project to SR, clip to Dallas County, load into GDB feature dataset."""
    out_path = os.path.join(GDB, dataset, output_name)
    scratch  = arcpy.env.scratchGDB
    tmp_proj = os.path.join(scratch, "tmp_proj_" + output_name)
    tmp_clip = os.path.join(scratch, "tmp_clip_" + output_name)
    try:
        # Clean up any leftover scratch files from prior runs
        for tmp in [tmp_proj, tmp_clip]:
            if arcpy.Exists(tmp):
                arcpy.management.Delete(tmp)

        print("  Projecting: " + output_name)
        arcpy.management.Project(input_fc, tmp_proj, SR)

        if not arcpy.Exists(tmp_proj):
            raise RuntimeError("Project produced no output -- check source file and CRS")

        print("  Clipping:   " + output_name)
        arcpy.analysis.Clip(tmp_proj, COUNTY_BOUNDARY, tmp_clip)
        arcpy.management.CopyFeatures(tmp_clip, out_path)
        count = int(arcpy.management.GetCount(out_path)[0])
        print("  OK " + output_name + " -> " + str(count) + " features loaded")

    except Exception as e:
        print("  ERROR loading " + output_name + ": " + str(e))
    finally:
        for tmp in [tmp_proj, tmp_clip]:
            if arcpy.Exists(tmp):
                arcpy.management.Delete(tmp)


def project_raster(input_raster, output_name):
    """
    Reproject raster from native CRS to WKID 2276 (TX State Plane feet).
    Raw download (WGS84) -> Projected (TX State Plane).
    Output saved directly to BaseData/ folder.
    """
    out_path = os.path.join(BASE, output_name)
    try:
        print("  Projecting raster: " + os.path.basename(input_raster) + " -> " + output_name)
        arcpy.management.ProjectRaster(
            input_raster, out_path, SR,
            resampling_type="BILINEAR",
            cell_size="10"
        )
        print("  OK " + output_name + " projected to WKID 2276")
    except Exception as e:
        print("  ERROR projecting raster " + output_name + ": " + str(e))


def check_geometry(fc):
    """Run Check Geometry; auto-repair if errors found."""
    scratch = arcpy.env.scratchGDB
    tmp = os.path.join(scratch, "geom_check")
    try:
        if arcpy.Exists(tmp):
            arcpy.management.Delete(tmp)
        arcpy.management.CheckGeometry(fc, tmp)
        count = int(arcpy.management.GetCount(tmp)[0])
        if count > 0:
            print("  WARNING: " + str(count) + " geometry error(s) -- running Repair Geometry")
            arcpy.management.RepairGeometry(fc)
        else:
            print("  Geometry OK")
    except Exception as e:
        print("  ERROR checking geometry: " + str(e))
    finally:
        if arcpy.Exists(tmp):
            arcpy.management.Delete(tmp)


# -- Pre-flight checks ---------------------------------------------------------
print("")
print("=== Pre-flight checks ===")

if not arcpy.Exists(GDB):
    print("ERROR: GDB not found: " + GDB)
    print("Run the Phase 1 setup script first to create WhiteRock.gdb")
    raise SystemExit

if not arcpy.Exists(COUNTY_BOUNDARY):
    print("ERROR: County boundary not found: " + COUNTY_BOUNDARY)
    print("Expected: Data/GIS/BaseData/DallasCountyBoundary/DallasCounty_Boundary.shp")
    raise SystemExit

print("  OK: GDB found")
print("  OK: County boundary found")
print("  Scratch GDB: " + arcpy.env.scratchGDB)


# -- Step 1: Vector datasets ---------------------------------------------------
print("")
print("=== Step 1: Loading vector datasets ===")
print("    Skipped files just mean that dataset is not downloaded yet.")
print("    Add them and re-run -- already-loaded layers overwrite cleanly.")
print("")

vector_loads = [
    # (source path,                                          output name,           GDB dataset)
    # Hydrology
    (os.path.join(HYDRO, "NHDFlowline.shp"),                "FC_Streams",          "Hydrology"),
    (os.path.join(HYDRO, "NHDWaterbody.shp"),               "FC_Waterbodies",      "Hydrology"),
    # Flood hazards
    (os.path.join(FLOOD, "S_Fld_Haz_Ar.shp"),              "FC_FEMA_FloodZones",  "FloodHazards"),
    # Buildings -- loaded separately via XYTableToPoint, skip here
    # (os.path.join(BASE,  "Texas_Buildings.shp"),           "FC_Buildings",        "BaseData"),
    # Infrastructure
    (os.path.join(INFRA, "Roads_Dallas.shp"),               "FC_Roads",            "Infrastructure"),
    (os.path.join(INFRA, "Hospitals.shp"),                  "FC_Hospitals",        "Infrastructure"),
    (os.path.join(INFRA, "FireStations.shp"),               "FC_FireStations",     "Infrastructure"),
    (os.path.join(INFRA, "PoliceStations.shp"),             "FC_PoliceStations",   "Infrastructure"),
    (os.path.join(INFRA, "PublicSchools.shp"),              "FC_Schools",          "Infrastructure"),
    # Demographics
    (os.path.join(DEMOG, "CensusBlockGroups.shp"),          "FC_BlockGroups",      "Demographics"),
]

loaded  = []
skipped = []

for src, name, ds in vector_loads:
    if arcpy.Exists(src):
        project_and_clip(src, name, ds)
        loaded.append(name)
    else:
        print("  SKIPPED -- file not found: " + src)
        skipped.append(name)

print("")
print("  Loaded: " + str(len(loaded)) + "  |  Skipped: " + str(len(skipped)))


# -- Step 2: Check geometry on everything loaded -------------------------------
print("")
print("=== Step 2: Checking geometry ===")

for ds in ["BaseData", "Hydrology", "Infrastructure", "FloodHazards", "Demographics"]:
    ds_path = os.path.join(GDB, ds)
    if not arcpy.Exists(ds_path):
        print("  WARNING: Feature dataset not found, skipping: " + ds)
        continue
    arcpy.env.workspace = ds_path
    fcs = arcpy.ListFeatureClasses() or []
    if not fcs:
        print("  (no feature classes yet in " + ds + ")")
        continue
    for fc in fcs:
        full_path = os.path.join(GDB, ds, fc)
        print("  Checking: " + fc)
        check_geometry(full_path)


# -- Step 3: Project rasters ---------------------------------------------------
# Raw   = as downloaded (WGS84 decimal degrees)
# Proj  = reprojected to WKID 2276 TX State Plane feet
# Clip  = projected + clipped to Dallas County (final working raster)
print("")
print("=== Step 3: Projecting rasters ===")
print("    Raw (WGS84) -> Projected (WKID 2276) -> Clipped (Dallas County)")
print("")

raster_loads = [
    # (full path to raw input,                                                       projected output name)
    (os.path.join(BASE, "DEM", "DEM_Raw.tif"),
     "DEM_Projected.tif"),

    (os.path.join(BASE, "NLCD_14e27cbc-7e48-4eff-8425-5f828aa7a60d", "NLCD_LandCover.tif"),
     "NLCD_LandCover_Proj.tif"),

    (os.path.join(BASE, "NLCD_1a7e4da8-68a7-4573-bb13-5c0c8a62a645", "NLCD_Impervious.tif"),
     "NLCD_Impervious_Proj.tif"),
]

for raw_path, proj_name in raster_loads:
    if arcpy.Exists(raw_path):
        project_raster(raw_path, proj_name)
    else:
        print("  SKIPPED -- raw raster not found: " + raw_path)


# -- Step 4: Clip projected rasters to Dallas County --------------------------
print("")
print("=== Step 4: Clipping rasters to Dallas County boundary ===")

desc   = arcpy.Describe(COUNTY_BOUNDARY)
extent = desc.extent
arcpy.env.mask = COUNTY_BOUNDARY

rasters_to_clip = [
    # (projected input name,           clipped output name)
    ("DEM_Projected.tif",         "DEM_Clipped.tif"),
    ("NLCD_LandCover_Proj.tif",   "NLCD_LandCover_Clipped.tif"),
    ("NLCD_Impervious_Proj.tif",  "NLCD_Impervious_Clipped.tif"),
]

for proj_name, clip_name in rasters_to_clip:
    src = os.path.join(BASE, proj_name)
    out = os.path.join(BASE, clip_name)
    if arcpy.Exists(src):
        try:
            arcpy.management.Clip(
                src,
                str(extent.XMin) + " " + str(extent.YMin) + " " +
                str(extent.XMax) + " " + str(extent.YMax),
                out,
                COUNTY_BOUNDARY,
                "#",
                "ClippingGeometry"
            )
            print("  OK Clipped: " + clip_name)
        except Exception as e:
            print("  ERROR clipping " + proj_name + ": " + str(e))
    else:
        print("  SKIPPED -- projected raster not found: " + proj_name)
        print("    Step 3 must complete before Step 4 can clip it")


# -- Step 5: Data inventory report --------------------------------------------
print("")
print("=== Step 5: Generating data inventory report ===")

os.makedirs(DOCS, exist_ok=True)
report_path = os.path.join(DOCS, "DataInventory_LoadReport.txt")

with open(report_path, "w") as f:
    f.write("WHITE ROCK FLOOD RISK PROJECT\n")
    f.write("Data Load Report\n")
    f.write("=" * 50 + "\n\n")

    for ds in ["BaseData", "Hydrology", "Infrastructure", "FloodHazards", "Demographics"]:
        arcpy.env.workspace = os.path.join(GDB, ds)
        fcs = arcpy.ListFeatureClasses() or []
        f.write("Dataset: " + ds + "\n")
        if not fcs:
            f.write("  (no feature classes loaded yet)\n")
        for fc in fcs:
            full_path = os.path.join(GDB, ds, fc)
            count = int(arcpy.management.GetCount(full_path)[0])
            desc2 = arcpy.Describe(full_path)
            f.write("  " + fc + ": " + str(count) + " features | " +
                    desc2.shapeType + " | " + desc2.spatialReference.name + "\n")
        f.write("\n")

    f.write("Rasters in BaseData/\n")
    raster_checks = [
        os.path.join(BASE, "DEM", "DEM_Raw.tif"),
        os.path.join(BASE, "DEM_Projected.tif"),
        os.path.join(BASE, "DEM_Clipped.tif"),
        os.path.join(BASE, "NLCD_14e27cbc-7e48-4eff-8425-5f828aa7a60d", "NLCD_LandCover.tif"),
        os.path.join(BASE, "NLCD_LandCover_Proj.tif"),
        os.path.join(BASE, "NLCD_LandCover_Clipped.tif"),
        os.path.join(BASE, "NLCD_1a7e4da8-68a7-4573-bb13-5c0c8a62a645", "NLCD_Impervious.tif"),
        os.path.join(BASE, "NLCD_Impervious_Proj.tif"),
        os.path.join(BASE, "NLCD_Impervious_Clipped.tif"),
    ]
    for rpath in raster_checks:
        label  = os.path.basename(rpath)
        status = "present" if arcpy.Exists(rpath) else "not yet created"
        f.write("  " + label + ": " + status + "\n")

    if skipped:
        f.write("\nSkipped vector datasets (download and re-run):\n")
        for s in skipped:
            f.write("  " + s + "\n")

print("  OK Report saved: " + report_path)


# -- Final summary -------------------------------------------------------------
print("")
print("=== Phase 2 summary ===")
if skipped:
    print("")
    print("  " + str(len(skipped)) + " vector dataset(s) still needed:")
    for s in skipped:
        print("    - " + s)
    print("")
    print("  Download the missing files, save with the expected filenames,")
    print("  and re-run. Already-loaded layers will overwrite cleanly.")
else:
    print("  All datasets loaded successfully. Proceed to Phase 3.")