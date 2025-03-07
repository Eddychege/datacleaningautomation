import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import requests

# ============== USER CONFIG ================
CSV_PATH = "Sites.csv"             # Your CSV file
UPDATED_PATH = "updated_sites.csv" # Final output
SHAPEFILE_PATH = "/home/shemking/Downloads/Kenya_Wards" # Path to your .shp
API_KEY = ""                       # Your Google Maps API key
MAX_REQUESTS = 5                   # Limit geocoding calls

# CSV column names
REGION_COL = "REGION"
COUNTY_COL = "COUNTY"
SITENAME_COL = "SITENAME"
SITECOORDS_COL = "SITECOORDINATES"
WARD_COL = "WARD"
CONST_COL = "CONSTITUENCY"

#  Load CSV Data
df= pd.read_csv(path) # update the path to the data


# Shapefile column names (based on your preview: 'county', 'subcounty', 'ward')
SHP_COUNTY = "county"
SHP_SUBCOUNTY = "subcounty"  # we'll treat as 'CONSTITUENCY' in CSV
SHP_WARD = "ward"

# ==========================================
request_count = 0
changed_rows = []


# =========== 1. Load CSV ===========
df = pd.read_csv(CSV_PATH, encoding="ISO-8859-1")

# Region Selection
def filter_by_region(df,selected_region):
    return df[df[REGION_COL]==selected_region]

# =========== 2. Forward Geocode ===========
def forward_geocode(region, county, sitename):
    """
    Query Google Maps for lat/lng, given region+county+sitename.
    Returns (lat, lng, status) or (None, None, 'some status').
    """
    global request_count
    if request_count >= MAX_REQUESTS:
        return (None, None, "Limit Reached")

    address = f"{sitename}, {county}, {region}"
    params = {"address": address, "key": API_KEY}
    try:
        resp = requests.get("https://maps.googleapis.com/maps/api/geocode/json", params=params, timeout=10)
        data = resp.json()
        status_code = data.get("status", "API Error")

        if status_code == "OK":
            loc = data["results"][0]["geometry"]["location"]
            request_count += 1
            return (loc["lat"], loc["lng"], "OK")
        else:
            return (None, None, status_code)
    except requests.exceptions.RequestException:
        return (None, None, "Request Error")
    except Exception:
        return (None, None, "Unexpected Error")

def fill_coordinates(row):
    """
    If SITECOORDINATES is missing/invalid, do forward geocode
    using (REGION, COUNTY, SITENAME).
    """
    coords = row[SITECOORDS_COL]
    if pd.isna(coords) or not isinstance(coords, str) or ("," not in coords or "0,0" in coords):
        region = row.get(REGION_COL, "")
        county = row.get(COUNTY_COL, "")
        sitename = row.get(SITENAME_COL, "")
        lat, lng, st = forward_geocode(region, county, sitename)
        if lat is not None and lng is not None:
            new_coords = f"{lat},{lng}"
            return new_coords, st
        else:
            return coords, st  # Return original or None plus status
    else:
        return coords, "AlreadyFilled"

def process_row(row):
    old_coords = row[SITECOORDS_COL]
    new_coords, status = fill_coordinates(row)
    if new_coords != old_coords:
        changed_rows.append(row.name)
    return pd.Series([new_coords, status])

# Apply forward geocoding to fill coordinates
tmp = df.apply(process_row, axis=1)
tmp.columns = [SITECOORDS_COL, "GEOCODE_STATUS"]
df[SITECOORDS_COL] = tmp[SITECOORDS_COL]
df["GEOCODE_STATUS"] = tmp["GEOCODE_STATUS"]

print("Forward Geocoding Done. Rows updated:", changed_rows)

# =========== 3. Spatial Join with Wards Shapefile to fill WARD & CONSTITUENCY ===========
def coords_to_point(coord_str):
    if isinstance(coord_str, str) and "," in coord_str:
        try:
            lat_str, lng_str = coord_str.split(",")
            lat, lng = float(lat_str), float(lng_str)
            return Point(lng, lat)  # x=lng, y=lat
        except:
            pass
    return None

df["geometry"] = df[SITECOORDS_COL].apply(coords_to_point)
gdf_sites = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")

# Load wards shapefile
try:
    wards_gdf = gpd.read_file(SHAPEFILE_PATH)
    # Reproject if needed
    wards_gdf = wards_gdf.to_crs(epsg=4326)
except Exception as e:
    wards_gdf = None
    print("Error loading shapefile:", e)

if wards_gdf is not None:
    # Perform point-in-polygon join
    joined = gpd.sjoin(gdf_sites, wards_gdf, how="left", predicate="within")

    # Fill WARD and CONSTITUENCY from shapefile
    def fill_ward_const(row):
        csv_ward = row[WARD_COL]           # from CSV
        csv_const = row[CONST_COL]         # from CSV
        shp_ward = row.get(SHP_WARD, None) # from shapefile
        shp_const = row.get(SHP_SUBCOUNTY, None) # from shapefile

        # We'll treat shapefile's "subcounty" as CSV's "CONSTITUENCY"
        final_ward = csv_ward
        final_const = csv_const

        if not final_ward or str(final_ward).lower() in ["nan", "0", "not found"]:
            if shp_ward and isinstance(shp_ward, str):
                final_ward = shp_ward

        if not final_const or str(final_const).lower() in ["nan", "0", "not found"]:
            if shp_const and isinstance(shp_const, str):
                final_const = shp_const

        changed = (final_ward != csv_ward) or (final_const != csv_const)
        if changed:
            changed_rows.append(row.name)

        return pd.Series([final_ward, final_const])

    joined[[WARD_COL, CONST_COL]] = joined.apply(fill_ward_const, axis=1)

    # Drop geometry columns
    joined.drop(columns=["geometry", "index_right"], inplace=True, errors="ignore")

    # Save
    joined.to_csv(UPDATED_PATH, index=False, encoding="ISO-8859-1")
    print(f"Shapefile Join Complete. Final saved -> {UPDATED_PATH}")
    print("Rows updated (including shapefile step):", set(changed_rows))

else:
    # If shapefile missing or error, just save partial
    df.drop(columns=["geometry"], inplace=True, errors="ignore")
    df.to_csv(UPDATED_PATH, index=False, encoding="ISO-8859-1")
    print("Shapefile not loaded; partial results only.")
    print(f"Saved -> {UPDATED_PATH}")
    print("Rows updated so far:", set(changed_rows))



