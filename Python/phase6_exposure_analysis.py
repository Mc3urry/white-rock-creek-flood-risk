import arcpy, os, csv, math
from arcpy.sa import *

ROOT     = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB      = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
BASE     = os.path.join(ROOT, "Data", "GIS", "BaseData")
ANALYSIS = os.path.join(GDB, "Analysis")
FLOOD_DS = os.path.join(GDB, "FloodHazards")
INFRA_DS = os.path.join(GDB, "Infrastructure")
DEMOG_DS = os.path.join(GDB, "Demographics")
BASE_DS  = os.path.join(GDB, "BaseData")
TABLES   = os.path.join(ROOT, "Report", "Tables")
os.makedirs(TABLES, exist_ok=True)

arcpy.CheckOutExtension("Spatial")
arcpy.env.overwriteOutput = True

# Ensure Analysis dataset exists
if not arcpy.Exists(ANALYSIS):
    arcpy.management.CreateFeatureDataset(GDB, "Analysis", arcpy.SpatialReference(2276))

BUILDINGS  = os.path.join(BASE_DS,  "FC_Buildings_WS")
ROADS      = os.path.join(INFRA_DS, "FC_Roads_WS")
BLOCKGRPS  = os.path.join(DEMOG_DS, "FC_BlockGroups_WS")
DEPTH_100  = os.path.join(BASE, "Depth_100yr.tif")
VEL_100    = os.path.join(BASE, "VelClass_100yr.tif")
EXTENTS = {
    "10yr":  os.path.join(FLOOD_DS, "FloodExtent_10yr"),
    "50yr":  os.path.join(FLOOD_DS, "FloodExtent_50yr"),
    "100yr": os.path.join(FLOOD_DS, "FloodExtent_100yr"),
    "500yr": os.path.join(FLOOD_DS, "FloodExtent_500yr"),
}
EXTENT_100 = EXTENTS["100yr"]

FACILITIES = {
    "Hospitals":      os.path.join(INFRA_DS, "FC_Hospitals_WS"),
    "FireStations":   os.path.join(INFRA_DS, "FC_FireStations_WS"),
    "PoliceStations": os.path.join(INFRA_DS, "FC_PoliceStations_WS"),
    "Schools":        os.path.join(INFRA_DS, "FC_Schools_WS"),
}

scratch = arcpy.env.scratchGDB

def field_exists(fc, name):
    return name in [f.name for f in arcpy.ListFields(fc)]

print("=== Phase 6: Exposure Analysis and Risk Assessment ===")
print("")

# -- Analysis 1: Building exposure ---------------------------------------------
print("Analysis 1: Building exposure")
bldg_stats = {}
total_bldgs = int(arcpy.management.GetCount(BUILDINGS)[0]) if arcpy.Exists(BUILDINGS) else 0

for evt, extent_fc in EXTENTS.items():
    if not arcpy.Exists(extent_fc) or not arcpy.Exists(BUILDINGS):
        print("  WARNING: Skipping " + evt + " -- layer not found")
        continue
    lyr = arcpy.management.MakeFeatureLayer(BUILDINGS, "bldg_lyr_" + evt)
    arcpy.management.SelectLayerByLocation(lyr, "INTERSECT", extent_fc, selection_type="NEW_SELECTION")
    exposed = int(arcpy.management.GetCount(lyr)[0])
    bldg_stats[evt] = exposed
    # write exposure status for this event
    fld = "EXPOSED_" + evt.upper()
    if field_exists(BUILDINGS, fld):
        sel_oids = set()
        with arcpy.da.SearchCursor(lyr, ["OID@"]) as cur:
            for r in cur:
                sel_oids.add(r[0])
        with arcpy.da.UpdateCursor(BUILDINGS, ["OID@", fld]) as cur:
            for row in cur:
                row[1] = "EXPOSED" if row[0] in sel_oids else "NOT_EXPOSED"
                cur.updateRow(row)
    arcpy.management.Delete(lyr)
    print("  " + evt + ": " + str(exposed) + " buildings exposed")

print("  Total buildings in watershed: " + str(total_bldgs))
if total_bldgs > 0 and "100yr" in bldg_stats:
    print("  100-yr exposure rate: " + str(round(bldg_stats["100yr"]/total_bldgs*100,1)) + "%")

# Extract 100-yr depth at building points
print("  Extracting depth at building points (100-yr)...")
if arcpy.Exists(BUILDINGS) and arcpy.Exists(DEPTH_100):
    # ExtractMultiValuesToPoints writes the raster value directly onto the
    # building points in place -- no separate output, no ID-matching needed.
    if not field_exists(BUILDINGS, "DEPTH_TMP"):
        arcpy.management.AddField(BUILDINGS, "DEPTH_TMP", "DOUBLE")
    arcpy.sa.ExtractMultiValuesToPoints(BUILDINGS, [[DEPTH_100, "DEPTH_TMP"]], "NONE")
    if field_exists(BUILDINGS, "DEPTH_100YR") and field_exists(BUILDINGS, "DEPTH_CLASS"):
        with arcpy.da.UpdateCursor(BUILDINGS, ["DEPTH_TMP","DEPTH_100YR","DEPTH_CLASS"]) as cur:
            for row in cur:
                depth = row[0]
                if depth is not None and depth > 0:
                    row[1] = depth
                    if   depth <= 1: row[2] = "MINOR"
                    elif depth <= 3: row[2] = "MODERATE"
                    elif depth <= 6: row[2] = "MAJOR"
                    else:            row[2] = "SEVERE"
                cur.updateRow(row)
    # clean up temp field
    if field_exists(BUILDINGS, "DEPTH_TMP"):
        arcpy.management.DeleteField(BUILDINGS, "DEPTH_TMP")
    print("  OK Depth and class written to FC_Buildings_WS")

# -- Analysis 2: Population exposure (areal weighting) -------------------------
print("")
print("Analysis 2: Population exposure (areal weighting, 100-yr)")
total_pop_exposed = 0
total_hu_exposed  = 0
total_pop = 0
bg_exposure = {}

if arcpy.Exists(BLOCKGRPS) and arcpy.Exists(EXTENT_100):
    arcpy.management.CalculateGeometryAttributes(BLOCKGRPS, [["TOTAL_AREA","AREA"]], area_unit="SQUARE_FEET_US")
    bg_intersect = os.path.join(scratch, "BG_Flood_Intersect")
    if arcpy.Exists(bg_intersect):
        arcpy.management.Delete(bg_intersect)
    arcpy.analysis.Intersect([BLOCKGRPS, EXTENT_100], bg_intersect)
    arcpy.management.CalculateGeometryAttributes(bg_intersect, [["FLOOD_AREA","AREA"]], area_unit="SQUARE_FEET_US")

    with arcpy.da.SearchCursor(bg_intersect, ["GEOID","POP_TOTAL","HU_TOTAL","TOTAL_AREA","FLOOD_AREA"]) as cur:
        for row in cur:
            geoid, pop, hu, tot_area, fld_area = row
            if tot_area and tot_area > 0:
                ratio   = min(fld_area / tot_area, 1.0)
                exp_pop = (pop or 0) * ratio
                exp_hu  = (hu  or 0) * ratio
                total_pop_exposed += exp_pop
                total_hu_exposed  += exp_hu
                if geoid in bg_exposure:
                    bg_exposure[geoid]["pop"]  += exp_pop
                    bg_exposure[geoid]["hu"]   += exp_hu
                    bg_exposure[geoid]["ratio"] = max(bg_exposure[geoid]["ratio"], ratio)
                else:
                    bg_exposure[geoid] = {"pop":exp_pop,"hu":exp_hu,"ratio":ratio}

    with arcpy.da.UpdateCursor(BLOCKGRPS, ["GEOID","POP_EXPOSED","HU_EXPOSED","FLOOD_AREA_PCT"]) as cur:
        for row in cur:
            if row[0] in bg_exposure:
                row[1] = round(bg_exposure[row[0]]["pop"], 0)
                row[2] = round(bg_exposure[row[0]]["hu"],  0)
                row[3] = round(bg_exposure[row[0]]["ratio"] * 100, 1)
            cur.updateRow(row)

    with arcpy.da.SearchCursor(BLOCKGRPS, ["POP_TOTAL"]) as cur:
        total_pop = sum((r[0] or 0) for r in cur)

    print("  Total watershed population:   " + str(round(total_pop, 0)))
    print("  Population exposed (100-yr):  " + str(round(total_pop_exposed, 0)))
    print("  Housing units exposed:        " + str(round(total_hu_exposed, 0)))
    if total_pop > 0:
        print("  Population exposure rate:     " + str(round(total_pop_exposed/total_pop*100,1)) + "%")
    arcpy.management.Delete(bg_intersect)
else:
    print("  WARNING: Block groups or flood extent not found -- skipping")

# -- Analysis 3: Road exposure -------------------------------------------------
print("")
print("Analysis 3: Road exposure (100-yr)")
total_road_mi = 0
all_road_mi   = 0
if arcpy.Exists(ROADS) and arcpy.Exists(EXTENT_100):
    roads_flooded = os.path.join(ANALYSIS, "Roads_Flooded_100yr")
    if arcpy.Exists(roads_flooded):
        arcpy.management.Delete(roads_flooded)
    arcpy.analysis.Intersect([ROADS, EXTENT_100], roads_flooded)
    arcpy.management.CalculateGeometryAttributes(roads_flooded, [["FLOOD_LEN_FT","LENGTH"]], length_unit="FEET_US")
    with arcpy.da.SearchCursor(roads_flooded, ["FLOOD_LEN_FT"]) as cur:
        total_road_mi = sum((r[0] or 0) for r in cur) / 5280
    if field_exists(ROADS, "LENGTH_MI"):
        with arcpy.da.SearchCursor(ROADS, ["LENGTH_MI"]) as cur:
            all_road_mi = sum((r[0] or 0) for r in cur)
    print("  Total road miles in watershed:  " + str(round(all_road_mi,1)))
    print("  Road miles flooded (100-yr):    " + str(round(total_road_mi,1)))
    if all_road_mi > 0:
        print("  Road exposure rate:             " + str(round(total_road_mi/all_road_mi*100,1)) + "%")
else:
    print("  WARNING: Roads or flood extent not found -- skipping")

# -- Analysis 4: Critical facility exposure ------------------------------------
print("")
print("Analysis 4: Critical facility exposure (100-yr)")
fac_results = {}
for fac_name, fac_fc in FACILITIES.items():
    if not arcpy.Exists(fac_fc):
        print("  WARNING: Not found: " + fac_name)
        continue
    total = int(arcpy.management.GetCount(fac_fc)[0])
    lyr   = arcpy.management.MakeFeatureLayer(fac_fc, "lyr_" + fac_name)
    arcpy.management.SelectLayerByLocation(lyr, "INTERSECT", EXTENT_100, selection_type="NEW_SELECTION")
    exposed = int(arcpy.management.GetCount(lyr)[0])
    fac_results[fac_name] = {"total":total, "exposed":exposed}
    pct = round(exposed/total*100,0) if total > 0 else 0
    print("  " + fac_name + ": " + str(exposed) + " / " + str(total) + " exposed (" + str(pct) + "%)")
    if field_exists(fac_fc, "EXPOSED_100YR"):
        sel = set()
        with arcpy.da.SearchCursor(lyr, ["OID@"]) as s:
            for r in s:
                sel.add(r[0])
        with arcpy.da.UpdateCursor(fac_fc, ["OID@","EXPOSED_100YR"]) as cur:
            for row in cur:
                row[1] = "EXPOSED" if row[0] in sel else "NOT_EXPOSED"
                cur.updateRow(row)
    arcpy.management.Delete(lyr)

# -- Analysis 5: Social Vulnerability Index ------------------------------------
print("")
print("Analysis 5: Social Vulnerability Index")
high_svi_exposed = 0
svi_vars = ["PCT_POVERTY","PCT_NO_VEH","PCT_65PLUS"]
if arcpy.Exists(BLOCKGRPS) and all(field_exists(BLOCKGRPS, v) for v in svi_vars):
    raw = {v: [] for v in svi_vars}
    with arcpy.da.SearchCursor(BLOCKGRPS, svi_vars) as cur:
        for row in cur:
            for i, v in enumerate(svi_vars):
                if row[i] is not None and row[i] >= 0:
                    raw[v].append(row[i])

    def mean(lst): return sum(lst)/len(lst) if lst else 0
    def std(lst):
        if len(lst) < 2: return 1
        m = mean(lst)
        return math.sqrt(sum((x-m)**2 for x in lst)/(len(lst)-1))
    stats = {v:{"mean":mean(raw[v]),"std":std(raw[v])} for v in svi_vars}

    with arcpy.da.UpdateCursor(BLOCKGRPS, svi_vars + ["SVI_SCORE","SVI_CLASS"]) as cur:
        for row in cur:
            zs = []
            for i, v in enumerate(svi_vars):
                val = row[i]
                if val is not None and stats[v]["std"] > 0:
                    zs.append((val - stats[v]["mean"]) / stats[v]["std"])
            if zs:
                svi = sum(zs)/len(zs)
                row[-2] = round(svi, 3)
                row[-1] = "HIGH" if svi >= 1.0 else ("MODERATE" if svi >= 0.0 else "LOW")
            cur.updateRow(row)

    with arcpy.da.SearchCursor(BLOCKGRPS, ["SVI_CLASS","FLOOD_AREA_PCT"]) as cur:
        for row in cur:
            if row[0] == "HIGH" and (row[1] or 0) > 10:
                high_svi_exposed += 1
    print("  High-vulnerability BGs with >10% flooded: " + str(high_svi_exposed))
    print("  OK SVI scores written to FC_BlockGroups_WS")
else:
    print("  WARNING: Block groups or SVI input fields not found -- skipping")

# -- Analysis 6: Flood hazard classification raster ----------------------------
print("")
print("Analysis 6: Flood hazard classification raster (100-yr)")
if arcpy.Exists(DEPTH_100) and arcpy.Exists(VEL_100):
    depth_r   = Raster(DEPTH_100)
    vel_r     = Raster(VEL_100)
    depth_cls = Con(depth_r<=1,1,Con(depth_r<=3,2,Con(depth_r<=6,3,4)))
    hazard    = CellStatistics([depth_cls, vel_r], "MAXIMUM", "DATA")
    hazard_path = os.path.join(BASE, "HazardClass_100yr.tif")
    hazard.save(hazard_path)
    print("  OK HazardClass_100yr.tif (1=Low 2=Mod 3=High 4=Extreme)")
    hp = os.path.join(ANALYSIS, "FloodHazard_Polygons_100yr")
    if arcpy.Exists(hp):
        arcpy.management.Delete(hp)
    arcpy.conversion.RasterToPolygon(hazard_path, hp, "SIMPLIFY", "Value")
    arcpy.management.AddField(hp, "HAZARD_CLASS", "TEXT", field_length=20)
    lblmap = {1:"LOW",2:"MODERATE",3:"HIGH",4:"EXTREME"}
    with arcpy.da.UpdateCursor(hp, ["gridcode","HAZARD_CLASS"]) as cur:
        for row in cur:
            row[1] = lblmap.get(row[0], "LOW")
            cur.updateRow(row)
    print("  OK FloodHazard_Polygons_100yr created")
else:
    print("  WARNING: Depth or velocity raster not found -- skipping")

# -- Analysis 7: Flood Risk Index ----------------------------------------------
print("")
print("Analysis 7: Flood Risk Index (100-yr)")
print("  Risk = 0.40*depth + 0.25*velocity + 0.20*pop + 0.15*infra")
if arcpy.Exists(DEPTH_100) and arcpy.Exists(VEL_100):
    depth_r    = Raster(DEPTH_100)
    vel_r      = Raster(VEL_100)
    depth_norm = Con(depth_r>0, Con(depth_r>10, 1.0, depth_r/10.0), 0)
    vel_norm   = Con(vel_r>0,   Con(vel_r>10,   1.0, vel_r/10.0),   0)

    pop_raster = os.path.join(BASE, "PopDensity.tif")
    if arcpy.Exists(BLOCKGRPS):
        arcpy.conversion.PolygonToRaster(BLOCKGRPS, "POP_TOTAL", pop_raster, "CELL_CENTER", "", 10)
        pop_r   = Raster(pop_raster)
        pop_max = float(arcpy.management.GetRasterProperties(pop_r,"MAXIMUM")[0])
        pop_norm = Con(pop_r>0, pop_r/pop_max, 0) if pop_max > 0 else pop_r*0
    else:
        pop_norm = depth_r*0

    fac_fcs = [f for f in FACILITIES.values() if arcpy.Exists(f)]
    if fac_fcs:
        merged = os.path.join(scratch, "CritFac_Combined")
        if arcpy.Exists(merged):
            arcpy.management.Delete(merged)
        arcpy.management.Merge(fac_fcs, merged)
        buf = os.path.join(scratch, "CritFac_Buf500")
        if arcpy.Exists(buf):
            arcpy.management.Delete(buf)
        arcpy.analysis.Buffer(merged, buf, "500 Feet", dissolve_option="ALL")
        infra_ras = os.path.join(BASE, "InfraProximity.tif")
        arcpy.conversion.FeatureToRaster(buf, "OBJECTID", infra_ras, 10)
        infra_r = Con(IsNull(Raster(infra_ras)), 0, 1)
    else:
        infra_r = depth_r*0

    risk = (depth_norm*0.40) + (vel_norm*0.25) + (pop_norm*0.20) + (infra_r*0.15)
    risk_path = os.path.join(BASE, "FloodRiskIndex.tif")
    risk.save(risk_path)
    print("  OK FloodRiskIndex.tif (0-1 scale)")

    # Analysis 8: Mitigation priority
    print("")
    print("Analysis 8: Mitigation priority areas")
    mit = Con(risk>=0.75,4,Con(risk>=0.50,3,Con(risk>=0.25,2,1)))
    mit_path = os.path.join(BASE, "MitigationPriority.tif")
    mit.save(mit_path)
    mp = os.path.join(ANALYSIS, "MitigationPriority_Polygons")
    if arcpy.Exists(mp):
        arcpy.management.Delete(mp)
    arcpy.conversion.RasterToPolygon(mit_path, mp, "SIMPLIFY", "Value")
    arcpy.management.AddField(mp, "PRIORITY", "TEXT", field_length=20)
    arcpy.management.AddField(mp, "PRIORITY_LABEL", "TEXT", field_length=40)
    pmap = {1:("MONITOR","Low -- Monitor"),2:("EVALUATE","Moderate -- Evaluate"),
            3:("IMPROVE","High -- Improve"),4:("IMMEDIATE","Critical -- Immediate Action")}
    with arcpy.da.UpdateCursor(mp, ["gridcode","PRIORITY","PRIORITY_LABEL"]) as cur:
        for row in cur:
            p = pmap.get(row[0], ("MONITOR","Low -- Monitor"))
            row[1], row[2] = p[0], p[1]
            cur.updateRow(row)
    arcpy.management.CalculateGeometryAttributes(mp, [["AREA_ACRES","AREA"]], area_unit="ACRES")
    for code,(lbl,full) in pmap.items():
        a = 0
        with arcpy.da.SearchCursor(mp, ["gridcode","AREA_ACRES"]) as cur:
            for row in cur:
                if row[0]==code:
                    a += (row[1] or 0)
        print("  " + full + ": " + str(round(a,0)) + " acres")
    print("  OK MitigationPriority_Polygons created")
else:
    print("  WARNING: Depth/velocity rasters not available -- skipping risk index")

# -- Report tables -------------------------------------------------------------
print("")
print("=== Generating report tables ===")

t1 = os.path.join(TABLES, "Table1_BuildingExposure.csv")
with open(t1, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Flood Event","Return Period","Buildings Exposed","Total Buildings","Percent Exposed"])
    labels = {"10yr":"10% Annual Chance","50yr":"2% Annual Chance",
              "100yr":"1% Annual Chance","500yr":"0.2% Annual Chance"}
    for evt in ["10yr","50yr","100yr","500yr"]:
        exp = bldg_stats.get(evt, 0)
        pct = round(exp/total_bldgs*100,1) if total_bldgs > 0 else 0
        w.writerow([evt, labels[evt], exp, total_bldgs, str(pct)+"%"])
print("  OK " + t1)

t2 = os.path.join(TABLES, "Table2_PopulationExposure.csv")
with open(t2, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Metric","Value"])
    w.writerow(["Total watershed population", str(round(total_pop,0))])
    w.writerow(["Population exposed (100-yr)", str(round(total_pop_exposed,0))])
    pct_pop = round(total_pop_exposed/total_pop*100,1) if total_pop > 0 else 0
    w.writerow(["Population exposure rate", str(pct_pop)+"%"])
    w.writerow(["Housing units exposed (100-yr)", str(round(total_hu_exposed,0))])
    w.writerow(["High-vulnerability BGs exposed", str(high_svi_exposed)])
print("  OK " + t2)

t3 = os.path.join(TABLES, "Table3_RoadExposure.csv")
with open(t3, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Metric","Value"])
    w.writerow(["Total road miles in watershed", str(round(all_road_mi,1))])
    w.writerow(["Road miles flooded (100-yr)", str(round(total_road_mi,1))])
    pct_rd = round(total_road_mi/all_road_mi*100,1) if all_road_mi > 0 else 0
    w.writerow(["Road exposure rate", str(pct_rd)+"%"])
print("  OK " + t3)

t4 = os.path.join(TABLES, "Table4_FacilityExposure.csv")
with open(t4, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Facility Type","Total in Watershed","Exposed (100-yr)","Percent"])
    for fac, vals in fac_results.items():
        pct = round(vals["exposed"]/vals["total"]*100,0) if vals["total"] > 0 else 0
        w.writerow([fac, vals["total"], vals["exposed"], str(pct)+"%"])
print("  OK " + t4)

arcpy.CheckInExtension("Spatial")
print("")
print("=== Phase 6 complete ===")