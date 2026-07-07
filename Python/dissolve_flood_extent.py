"""
Dissolve FloodExtent_100yr into a single polygon so it can be symbolized as
ONE clean outline (instead of thousands of overlapping small-polygon outlines
that visually merge into solid fill). Creates FloodExtent_100yr_Dissolved.
"""
import arcpy, os

ROOT   = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB    = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
FLOOD  = os.path.join(GDB, "FloodHazards", "FloodExtent_100yr")
OUT    = os.path.join(GDB, "FloodHazards", "FloodExtent_100yr_Dissolved")

arcpy.env.overwriteOutput = True

print("=== Dissolving FloodExtent_100yr ===")
n_before = int(arcpy.management.GetCount(FLOOD)[0])
print("  Polygons before: " + str(n_before))

# Dissolve all features into one (multipart) polygon
arcpy.management.Dissolve(FLOOD, OUT, dissolve_field=None, multi_part="MULTI_PART")

n_after = int(arcpy.management.GetCount(OUT)[0])
print("  Polygons after:  " + str(n_after))
print("  Created: FloodExtent_100yr_Dissolved")
print("")
print("Now symbolize FloodExtent_100yr_Dissolved with:")
print("  Fill = No Color")
print("  Outline = dark blue, 2 pt")
print("  -> single clean floodplain boundary over the SVI choropleth")
print("=== Done ===")
