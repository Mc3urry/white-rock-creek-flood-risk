import arcpy, os, csv
from datetime import datetime

ROOT  = r"C:\Users\mccul\OneDrive\Professional Information\Resume Items\WhiteRockFloodProject"
GDB   = os.path.join(ROOT, "Data", "GIS", "WhiteRock.gdb")
DEMOG = os.path.join(ROOT, "Data", "GIS", "Demographics")
DOCS  = os.path.join(ROOT, "Documentation")
BASE  = os.path.join(ROOT, "Data", "GIS", "BaseData")
SR    = arcpy.SpatialReference(2276)

arcpy.env.overwriteOutput = True
os.makedirs(DOCS, exist_ok=True)

# -- Helpers -------------------------------------------------------------------
def add_field_safe(fc, name, ftype, length=None, alias=None):
    existing = [f.name for f in arcpy.ListFields(fc)]
    if name not in existing:
        kwargs = {"field_name": name, "field_type": ftype}
        if length: kwargs["field_length"]  = length
        if alias:  kwargs["field_alias"]   = alias
        arcpy.management.AddField(fc, **kwargs)
        print("    + Field added: " + name)
    else:
        print("    ~ Field exists: " + name)

def create_domain(gdb, name, desc, field_type, coded_values):
    existing = [d.name for d in arcpy.da.ListDomains(gdb)]
    if name not in existing:
        arcpy.management.CreateDomain(gdb, name, desc, field_type, "CODED")
        for code, val in coded_values.items():
            arcpy.management.AddCodedValueToDomain(gdb, name, code, val)
        print("  OK Domain created: " + name)
    else:
        print("  ~ Domain exists: " + name)

print("=== Phase 3: Schema Build ===")
print("")

# -- Step 1: Domains -----------------------------------------------------------
print("Step 1: Creating domains")

create_domain(GDB, "FloodZone", "FEMA Flood Zone Classification", "TEXT", {
    "AE":   "1% Annual Chance (AE)",
    "AH":   "1% Annual Chance Shallow (AH)",
    "AO":   "1% Annual Chance Sheet Flow (AO)",
    "A":    "1% Annual Chance (A)",
    "VE":   "1% Annual Chance Coastal (VE)",
    "X":    "Minimal Flood Hazard (X)",
    "X500": "0.2% Annual Chance (X500)",
})
create_domain(GDB, "FloodDepthClass", "Flood Depth Classification", "TEXT", {
    "MINOR":    "Minor (0-1 ft)",
    "MODERATE": "Moderate (1-3 ft)",
    "MAJOR":    "Major (3-6 ft)",
    "SEVERE":   "Severe (>6 ft)",
})
create_domain(GDB, "FloodHazardClass", "Flood Hazard Classification", "TEXT", {
    "LOW":      "Low",
    "MODERATE": "Moderate",
    "HIGH":     "High",
    "EXTREME":  "Extreme",
})
create_domain(GDB, "ExposureStatus", "Flood Exposure Status", "TEXT", {
    "EXPOSED":     "Exposed to Flooding",
    "NOT_EXPOSED": "Not Exposed",
    "PARTIAL":     "Partially Exposed",
})
create_domain(GDB, "FacilityType", "Critical Facility Type", "TEXT", {
    "HOSPITAL": "Hospital",
    "FIRE":     "Fire Station",
    "POLICE":   "Police Station",
    "SCHOOL":   "School",
    "SHELTER":  "Emergency Shelter",
})
create_domain(GDB, "RoadClass", "Road Classification", "TEXT", {
    "INTERSTATE": "Interstate Highway",
    "US_HWY":     "US Highway",
    "STATE_HWY":  "State Highway",
    "ARTERIAL":   "Major Arterial",
    "COLLECTOR":  "Collector",
    "LOCAL":      "Local Road",
})
create_domain(GDB, "MitigationPriority", "Mitigation Priority", "TEXT", {
    "MONITOR":   "Low -- Monitor",
    "EVALUATE":  "Moderate -- Evaluate",
    "IMPROVE":   "High -- Improve",
    "IMMEDIATE": "Critical -- Immediate Action",
})

# -- Step 2: FC_Buildings schema -----------------------------------------------
# NOTE: FC_Buildings is a POINT layer created from CSV via XYTableToPoint.
# Area comes from the SQFEET column already in the CSV -- not calculated from geometry.
print("")
print("Step 2: FC_Buildings schema")
buildings = os.path.join(GDB, "BaseData", "FC_Buildings")

if arcpy.Exists(buildings):
    fields = [
        ("BLDG_ID",        "LONG",   None, "Building ID"),
        ("BLDG_TYPE",      "TEXT",   50,   "Building Type"),
        ("AREA_SQFT",      "DOUBLE", None, "Building Area (sq ft)"),
        ("EXPOSED_10YR",   "TEXT",   20,   "Exposed 10-Year Flood"),
        ("EXPOSED_50YR",   "TEXT",   20,   "Exposed 50-Year Flood"),
        ("EXPOSED_100YR",  "TEXT",   20,   "Exposed 100-Year Flood"),
        ("EXPOSED_500YR",  "TEXT",   20,   "Exposed 500-Year Flood"),
        ("DEPTH_100YR",    "DOUBLE", None, "Flood Depth 100-Year (ft)"),
        ("DEPTH_CLASS",    "TEXT",   20,   "Depth Classification"),
        ("HAZARD_CLASS",   "TEXT",   20,   "Hazard Classification"),
        ("RISK_INDEX",     "DOUBLE", None, "Flood Risk Index Score"),
    ]
    for fname, ftype, flen, falias in fields:
        add_field_safe(buildings, fname, ftype, flen, falias)

    for fld in ["EXPOSED_10YR","EXPOSED_50YR","EXPOSED_100YR","EXPOSED_500YR"]:
        arcpy.management.AssignDomainToField(buildings, fld, "ExposureStatus")
    arcpy.management.AssignDomainToField(buildings, "DEPTH_CLASS",  "FloodDepthClass")
    arcpy.management.AssignDomainToField(buildings, "HAZARD_CLASS", "FloodHazardClass")

    # Use SQFEET from the source CSV -- already populated, just copy to AREA_SQFT
    arcpy.management.CalculateField(buildings, "AREA_SQFT", "!SQFEET!", "PYTHON3")
    arcpy.management.CalculateField(buildings, "BLDG_ID", "!OBJECTID!", "PYTHON3")
    print("  OK FC_Buildings schema complete")
else:
    print("  WARNING: FC_Buildings not found -- run XYTableToPoint conversion first")

# -- Step 3: FC_Roads schema ---------------------------------------------------
print("")
print("Step 3: FC_Roads schema")
roads = os.path.join(GDB, "Infrastructure", "FC_Roads")

if arcpy.Exists(roads):
    road_fields = [
        ("ROAD_CLASS",    "TEXT",   20,   "Road Classification"),
        ("LENGTH_FT",     "DOUBLE", None, "Length (feet)"),
        ("LENGTH_MI",     "DOUBLE", None, "Length (miles)"),
        ("EXPOSED_100YR", "TEXT",   20,   "Exposed 100-Year Flood"),
        ("FLOOD_DEPTH",   "DOUBLE", None, "Max Flood Depth (ft)"),
    ]
    for fname, ftype, flen, falias in road_fields:
        add_field_safe(roads, fname, ftype, flen, falias)

    arcpy.management.AssignDomainToField(roads, "ROAD_CLASS",    "RoadClass")
    arcpy.management.AssignDomainToField(roads, "EXPOSED_100YR", "ExposureStatus")
    arcpy.management.CalculateGeometryAttributes(roads, [["LENGTH_FT","LENGTH"]], length_unit="FEET_US")
    arcpy.management.CalculateField(roads, "LENGTH_MI", "!LENGTH_FT! / 5280", "PYTHON3")
    print("  OK FC_Roads schema complete")
else:
    print("  WARNING: FC_Roads not found -- download TxDOT roads and re-run Phase 2")

# -- Step 4: FC_BlockGroups schema + ACS joins ---------------------------------
# B01003 (population) and B25001 (housing) joined at BLOCK GROUP level
# B17001 (poverty), B19013 (income), B08201 (vehicles) joined at TRACT level
# Tract GEOID = first 11 characters of block group GEOID
print("")
print("Step 4: FC_BlockGroups schema + ACS joins")
bg = os.path.join(GDB, "Demographics", "FC_BlockGroups")

if arcpy.Exists(bg):
    bg_fields = [
        ("GEOID",          "TEXT",   20,   "Census GEOID"),
        ("TRACT_GEOID",    "TEXT",   11,   "Parent Tract GEOID"),
        ("POP_TOTAL",      "LONG",   None, "Total Population"),
        ("HU_TOTAL",       "LONG",   None, "Total Housing Units"),
        ("PCT_POVERTY",    "DOUBLE", None, "Percent Below Poverty"),
        ("MED_INC",        "DOUBLE", None, "Median Household Income"),
        ("PCT_NO_VEH",     "DOUBLE", None, "Percent No Vehicle"),
        ("PCT_65PLUS",     "DOUBLE", None, "Percent Age 65+"),
        ("SVI_SCORE",      "DOUBLE", None, "Social Vulnerability Index"),
        ("SVI_CLASS",      "TEXT",   20,   "SVI Classification"),
        ("POP_EXPOSED",    "DOUBLE", None, "Estimated Population Exposed"),
        ("HU_EXPOSED",     "DOUBLE", None, "Estimated Housing Units Exposed"),
        ("FLOOD_AREA_PCT", "DOUBLE", None, "Percent Area Flooded"),
        ("TOTAL_AREA",     "DOUBLE", None, "Total Block Group Area (sq ft)"),
    ]
    for fname, ftype, flen, falias in bg_fields:
        add_field_safe(bg, fname, ftype, flen, falias)

    arcpy.management.AssignDomainToField(bg, "SVI_CLASS", "FloodHazardClass")

    # Derive tract GEOID from block group GEOID (first 11 digits)
    arcpy.management.CalculateField(
        bg, "TRACT_GEOID",
        "!GEOID![:11] if !GEOID! else None",
        "PYTHON3")
    print("  OK TRACT_GEOID derived from GEOID")

    # Block-group-level tables (GEOID = 12 digits, prefix 1500000US)
    # Confirmed from actual ACS 2024 5-year files:
    #   B01001 age, B01003 population, B19013 median income, B25001 housing units
    bg_tables = {
        "B01001": os.path.join(DEMOG, "ACS_B01001_BG.csv"),
        "B01003": os.path.join(DEMOG, "ACS_B01003_BG.csv"),
        "B19013": os.path.join(DEMOG, "ACS_B19013_BG.csv"),
        "B25001": os.path.join(DEMOG, "ACS_B25001_BG.csv"),
    }
    for tbl_name, tbl_path in bg_tables.items():
        if os.path.exists(tbl_path):
            arcpy.management.JoinField(bg, "GEOID", tbl_path, "GEOID", None)
            print("  OK Joined block-group table: " + tbl_name)
        else:
            print("  WARNING: ACS CSV not found -- run prep_acs_csvs.py first: " + tbl_path)

    # Tract-level tables (TRACT_GEOID = 11 digits, prefix 1400000US)
    # Confirmed from actual ACS 2024 5-year files:
    #   B08201 vehicle availability, B17001 poverty status
    tract_tables = {
        "B08201": os.path.join(DEMOG, "ACS_B08201_TRACT.csv"),
        "B17001": os.path.join(DEMOG, "ACS_B17001_TRACT.csv"),
    }
    for tbl_name, tbl_path in tract_tables.items():
        if os.path.exists(tbl_path):
            arcpy.management.JoinField(bg, "TRACT_GEOID", tbl_path, "GEOID", None)
            print("  OK Joined tract-level table: " + tbl_name + " (via TRACT_GEOID)")
        else:
            print("  WARNING: Tract CSV not found -- run prep_acs_csvs.py first: " + tbl_path)

    print("  OK FC_BlockGroups schema complete")
else:
    print("  WARNING: FC_BlockGroups not found -- download Census block groups and re-run Phase 2")

# -- Step 5: Critical facility schemas -----------------------------------------
print("")
print("Step 5: Critical facility schemas")

facility_fcs = {
    "FC_Hospitals":      "HOSPITAL",
    "FC_FireStations":   "FIRE",
    "FC_PoliceStations": "POLICE",
    "FC_Schools":        "SCHOOL",
}
fac_fields = [
    ("FAC_TYPE",      "TEXT",   20,  "Facility Type"),
    ("FAC_NAME",      "TEXT",   100, "Facility Name"),
    ("EXPOSED_100YR", "TEXT",   20,  "Exposed 100-Year Flood"),
    ("DEPTH_100YR",   "DOUBLE", None,"Flood Depth 100-Year (ft)"),
    ("HAZARD_CLASS",  "TEXT",   20,  "Hazard Classification"),
    ("PRIORITY",      "TEXT",   20,  "Mitigation Priority"),
]
for fc_name, fac_code in facility_fcs.items():
    fc_path = os.path.join(GDB, "Infrastructure", fc_name)
    if arcpy.Exists(fc_path):
        for fname, ftype, flen, falias in fac_fields:
            add_field_safe(fc_path, fname, ftype, flen, falias)
        arcpy.management.AssignDomainToField(fc_path, "FAC_TYPE",      "FacilityType")
        arcpy.management.AssignDomainToField(fc_path, "EXPOSED_100YR", "ExposureStatus")
        arcpy.management.AssignDomainToField(fc_path, "HAZARD_CLASS",  "FloodHazardClass")
        arcpy.management.AssignDomainToField(fc_path, "PRIORITY",      "MitigationPriority")
        arcpy.management.CalculateField(fc_path, "FAC_TYPE", '"' + fac_code + '"', "PYTHON3")
        print("  OK " + fc_name + " schema complete")
    else:
        print("  WARNING: " + fc_name + " not found -- download from Living Atlas and re-run Phase 2")

# -- Step 6: Metadata ----------------------------------------------------------
print("")
print("Step 6: Writing metadata")

from arcpy import metadata as md
today = datetime.now().strftime("%Y-%m-%d")

meta_map = {
    os.path.join(GDB,"BaseData","FC_Buildings"):
        ("Building Points","Building centroid points for Dallas County TX. "
         "Source: Dallas County. Point layer with SQFEET attribute. WKID 2276."),
    os.path.join(GDB,"Infrastructure","FC_Roads"):
        ("Road Network","TxDOT road network clipped to Dallas County. WKID 2276."),
    os.path.join(GDB,"FloodHazards","FC_FEMA_FloodZones"):
        ("FEMA Flood Zones","FEMA NFHL flood zones for Dallas County TX. Source: FEMA MSC."),
    os.path.join(GDB,"Hydrology","FC_Streams"):
        ("NHD Streams","USGS NHD Flowlines for HUC 12030105 White Rock Creek watershed."),
    os.path.join(GDB,"Demographics","FC_BlockGroups"):
        ("Census Block Groups","US Census ACS 5-Year block groups for Dallas County. "
         "Poverty/income/vehicle fields joined at tract level due to ACS suppression."),
}
for fc_path, (title, abstract) in meta_map.items():
    if arcpy.Exists(fc_path):
        fc_md          = md.Metadata(fc_path)
        fc_md.title    = title
        fc_md.summary  = abstract
        fc_md.tags     = "White Rock Creek, Flood Risk, Dallas County, GIS"
        fc_md.credits  = "White Rock Flood Risk Assessment. Processed " + today
        fc_md.save()
        print("  OK Metadata written: " + title)
    else:
        print("  WARNING: Layer not found for metadata: " + fc_path)

# -- Step 7: GDB schema report -------------------------------------------------
print("")
print("Step 7: Generating GDB schema report")

report_path = os.path.join(DOCS, "GDB_SchemaReport.csv")
with open(report_path, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Dataset","FeatureClass","Field","Type","Length","Domain","Alias"])
    arcpy.env.workspace = GDB
    for ds in arcpy.ListDatasets("*", "Feature") or []:
        arcpy.env.workspace = os.path.join(GDB, ds)
        for fc in arcpy.ListFeatureClasses() or []:
            for fld in arcpy.ListFields(os.path.join(GDB, ds, fc)):
                writer.writerow([ds, fc, fld.name, fld.type,
                                  fld.length, fld.domain, fld.aliasName])

print("  OK Schema report saved: " + report_path)
print("")
print("=== Phase 3 complete ===")