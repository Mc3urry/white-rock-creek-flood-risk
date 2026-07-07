import arcpy, os

ROOT        = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB         = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
BASE        = os.path.join(ROOT, "Data", "GIS", "BaseData")
TARGET_WKID = 2276

arcpy.env.workspace = GDB
issues = []

print("=== Phase 3: Projection Verification ===")
print("")

datasets = arcpy.ListDatasets("*", "Feature") or []
for ds in datasets:
    arcpy.env.workspace = os.path.join(GDB, ds)
    fcs = arcpy.ListFeatureClasses() or []
    for fc in fcs:
        desc   = arcpy.Describe(os.path.join(GDB, ds, fc))
        sr     = desc.spatialReference
        status = "OK" if sr.factoryCode == TARGET_WKID else "MISMATCH"
        if status == "MISMATCH":
            issues.append(ds + "/" + fc + " -> " + sr.name + " (WKID " + str(sr.factoryCode) + ")")
        print("  [" + status + "] " + ds + "/" + fc + " -- " + sr.name)

print("")
print("=== Rasters ===")
arcpy.env.workspace = BASE
rasters = arcpy.ListRasters() or []
for r in rasters:
    desc   = arcpy.Describe(r)
    sr     = desc.spatialReference
    status = "OK" if sr.factoryCode == TARGET_WKID else "MISMATCH"
    if status == "MISMATCH":
        issues.append("BaseData/" + r + " -> " + sr.name)
    print("  [" + status + "] " + r + " -- " + sr.name)

print("")
if issues:
    print("WARNING: " + str(len(issues)) + " projection issue(s) found:")
    for i in issues:
        print("  " + i)
else:
    print("All datasets projected correctly to WKID 2276")