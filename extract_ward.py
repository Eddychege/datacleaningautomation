import geopandas as gpd
import json

# Load the shapefile
shapefile_path = "C:\\Users\\Ree\\Downloads\\kenya_wards\\Kenya_Wards.shp"

wards_gdf = gpd.read_file(shapefile_path)

# Inspect the GeoDataFrame to find relevant columns
print(wards_gdf.columns)
print(wards_gdf.head())

# Replace 'ward_name' and 'constituency' with actual column names
ward_to_constituency = dict(zip(wards_gdf['ward_name'], wards_gdf['constituency']))

# Save as a Python file
with open("ward.py", "w") as f:
    f.write("ward_to_constituency = ")
    f.write(str(ward_to_constituency))

# Optionally, save as a JSON file
with open("ward_to_constituency.json", "w") as f:
    json.dump(ward_to_constituency, f)

print("Ward to constituency mapping saved successfully.")
