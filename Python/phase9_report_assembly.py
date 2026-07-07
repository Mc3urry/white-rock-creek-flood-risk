"""
Phase 9 -- Report Assembly & Portfolio Documentation
Regenerates result tables, a data dictionary, and a metadata summary from the
LIVE geodatabase so the documentation always matches the actual data.

Run in the ArcGIS Pro Python window:
exec(open(r"...\Python\phase9_report_assembly.py").read())

Note: The written report (WhiteRockCreek_FloodRiskAssessment.docx) and the
GitHub README.md were authored separately with finalized figures; this script
produces the supporting CSV/metadata that document the GDB contents.
"""
import arcpy, os, csv
from datetime import datetime

ROOT   = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB    = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
BASE   = os.path.join(ROOT, "Data", "GIS", "BaseData")
TABLES = os.path.join(ROOT, "Report", "Tables")
DOCS   = os.path.join(ROOT, "Documentation")
for d in (TABLES, DOCS):
    os.makedirs(d, exist_ok=True)

arcpy.env.overwriteOutput = True
TODAY = datetime.now().strftime("%Y-%m-%d")

print("=== Phase 9: Documentation Assembly ===")
print("")

FLOOD_DS = os.path.join(GDB, "FloodHazards")
events = ["10yr", "50yr", "100yr", "500yr"]
labels = {"10yr":"10-Year (10% AEP)", "50yr":"50-Year (2% AEP)",
          "100yr":"100-Year (1% AEP)", "500yr":"500-Year (0.2% AEP)"}

# --- Result Table: Inundation summary (from live extents) ---------------------
print("Generating inundation summary from live flood extents...")
ta = os.path.join(TABLES, "TableA_InundationSummary.csv")
with open(ta, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Event", "Recurrence", "Inundated Area (ac)", "Max Depth (ft)"])
    for evt in events:
        ext = os.path.join(FLOOD_DS, "FloodExtent_" + evt)
        dep = os.path.join(BASE, "Depth_" + evt + ".tif")
        area = "N/A"; mx = "N/A"
        if arcpy.Exists(ext):
            tot = 0
            with arcpy.da.SearchCursor(ext, ["SHAPE@AREA"]) as c:
                for r in c: tot += r[0]
            area = str(round(tot/43560, 0))
        if arcpy.Exists(dep):
            mx = str(round(float(arcpy.management.GetRasterProperties(dep, "MAXIMUM")[0]), 1))
        w.writerow([evt, labels[evt], area, mx])
        print("  " + evt + ": " + area + " ac, max " + mx + " ft")
print("  OK " + ta)
print("")

# --- Data Dictionary (every field in every FC, via Walk) ---------------------
print("Generating data dictionary from GDB schema...")
dd = os.path.join(DOCS, "DataDictionary.csv")
type_map = {"String":"Text", "Integer":"Long", "SmallInteger":"Short",
            "Double":"Double", "Single":"Float", "Date":"Date",
            "OID":"ObjectID", "Geometry":"Geometry", "GlobalID":"GlobalID"}
row_count = 0
with open(dd, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Dataset", "Feature Class", "Field", "Type", "Length", "Alias"])
    # Walk finds every feature class regardless of dataset nesting
    for dirpath, dirnames, filenames in arcpy.da.Walk(GDB, datatype="FeatureClass"):
        parent = os.path.basename(dirpath)
        # if the parent is the gdb itself, label as (root)
        ds_label = "(root)" if parent.lower().endswith(".gdb") else parent
        for fc in filenames:
            fc_path = os.path.join(dirpath, fc)
            try:
                for fld in arcpy.ListFields(fc_path):
                    w.writerow([ds_label, fc, fld.name,
                                type_map.get(fld.type, fld.type),
                                fld.length, fld.aliasName])
                    row_count += 1
            except Exception as e:
                print("  WARNING reading " + fc + ": " + str(e))
print("  OK " + dd + "  (" + str(row_count) + " field rows)")
print("")

# --- Metadata summary --------------------------------------------------------
print("Generating metadata summary...")
meta = os.path.join(DOCS, "ProjectMetadata.txt")
sr_name = arcpy.Describe(GDB).spatialReference.name if hasattr(arcpy.Describe(GDB), "spatialReference") else "NAD83 StatePlane TX N Central (2276)"
with open(meta, "w") as f:
    f.write("WHITE ROCK CREEK FLOOD RISK ASSESSMENT\n")
    f.write("Project Metadata\n")
    f.write("Generated: " + TODAY + "\n")
    f.write("=" * 50 + "\n\n")
    f.write("Author: Joshua McCulley\n")
    f.write("Institution: The University of Texas at Dallas\n")
    f.write("Projection: NAD83 State Plane TX North Central (FIPS 4202 / EPSG 2276)\n")
    f.write("Study area: White Rock Creek Watershed, Dallas County, TX\n")
    f.write("Drainage area: 85.5 sq mi (54,696 ac)\n\n")
    f.write("Feature classes in geodatabase:\n")
    for dirpath, dirnames, filenames in arcpy.da.Walk(GDB, datatype="FeatureClass"):
        parent = os.path.basename(dirpath)
        ds_label = "(root)" if parent.lower().endswith(".gdb") else parent
        for fc in filenames:
            try:
                n = arcpy.management.GetCount(os.path.join(dirpath, fc))[0]
            except Exception:
                n = "?"
            f.write("  " + ds_label + "/" + fc + " (" + str(n) + " features)\n")
print("  OK " + meta)
print("")
print("=== Phase 9 documentation complete ===")
print("Files written to Report/Tables/ and Documentation/")