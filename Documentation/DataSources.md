# Data Sources & Provenance
### White Rock Creek Flood Risk Assessment

All datasets were obtained from authoritative public sources and reprojected to
**NAD83 State Plane Texas North Central (FIPS 4202 / EPSG 2276)**, US survey feet.

| Dataset | Provider | Product | Use in Project |
|---|---|---|---|
| Digital Elevation Model | USGS | 3DEP (1/3 arc-second) | Terrain, watershed delineation, HEC-RAS terrain |
| Hydrography | USGS | National Hydrography Dataset (NHD) | Stream network, waterbodies, White Rock Lake |
| Land Cover | USGS | National Land Cover Database (NLCD) | Manning's roughness, impervious context |
| Precipitation Frequency | NOAA | Atlas 14 | Design-storm depths (10/50/100/500-yr) |
| Demographics | US Census Bureau | ACS 2024 5-Year Estimates | Population, housing, poverty, vehicle access, age |
| Critical Facilities | Esri | Living Atlas | Hospitals, fire stations, police stations, schools |
| Building Footprints | Dallas County | Building centroids | Building exposure analysis |
| Regulatory Floodplain | FEMA | National Flood Hazard Layer (NFHL) | Modeled-vs-regulatory comparison |

## Census Variables (ACS 2024 5-Year)

| Variable | Table | Geography |
|---|---|---|
| Total population | B01003 | Block group |
| Population by age (65+) | B01001 | Block group |
| Median household income | B19013 | Block group |
| Total housing units | B25001 | Block group |
| Poverty status | B17001 | Tract |
| Vehicle availability | B08201 | Tract |

## Design-Storm Depths (NOAA Atlas 14, 24-hour, watershed centroid)

| Recurrence Interval | Depth (in) |
|---|---|
| 10-year (10% AEP) | 6.03 |
| 50-year (2% AEP) | 8.42 |
| 100-year (1% AEP) | 9.55 |
| 500-year (0.2% AEP) | 12.60 |

## Notes

- The Homeland Infrastructure Foundation-Level Data (HIFLD) portal was unavailable
  during data acquisition; critical-facility layers were sourced from Esri Living Atlas
  as an authoritative substitute.
- Building data were provided as point centroids with square-footage attributes;
  polygon footprints were not required for the point-based exposure analysis.
- FEMA zones were filtered to the 100-year regulatory floodplain (A, AE, AO) for
  comparison; shaded-X (500-year) and unshaded-X (minimal hazard) zones were excluded.
