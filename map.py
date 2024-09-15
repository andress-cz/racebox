import os
import csv
import matplotlib.pyplot as plt
import geopandas as gpd
from shapely.geometry import Point
import contextily as ctx
import numpy as np

# Define the bounding box for the Czech Republic
LAT_MIN, LAT_MAX = 48.5, 51.5
LON_MIN, LON_MAX = 12.0, 18.9

# Function to read and filter GPS data for the Czech Republic
def read_gps_data(csv_file):
    longitudes = []
    latitudes = []

    with open(csv_file, mode='r') as file:
        reader = csv.DictReader(file)
        for i, row in enumerate(reader):
            longitude = float(row["Longitude"])
            latitude = float(row["Latitude"])

            # Print the first few rows to check the data
            if i < 5:
                print(f"Row {i}: Longitude={longitude}, Latitude={latitude}")

            # Filter for valid latitude and longitude within the Czech Republic bounds
            if LON_MIN <= longitude <= LON_MAX and LAT_MIN <= latitude <= LAT_MAX:
                longitudes.append(longitude)
                latitudes.append(latitude)
            else:
                print(f"Data outside CZ skipped: Longitude={longitude}, Latitude={latitude}")

    return longitudes, latitudes

# Function to dynamically adjust zoom to fit the session's GPS data
def calculate_bounds(longitudes, latitudes):
    return min(longitudes), max(longitudes), min(latitudes), max(latitudes)

# Function to estimate the zoom level based on the bounding box
def estimate_zoom(min_lon, max_lon, min_lat, max_lat):
    # Calculate the difference between the bounds
    lon_diff = max_lon - min_lon
    lat_diff = max_lat - min_lat

    # If the difference is zero, return the maximum zoom level (19)
    if lon_diff == 0 and lat_diff == 0:
        return 19

    # Approximate zoom level based on the difference (adjust these values to tune zoom)
    zoom = int(12 - np.log(max(lon_diff, lat_diff)) / np.log(2))

    # Ensure the zoom level is within the allowed range (0 - 19)
    return max(0, min(zoom, 19))

# Function to plot the GPS path on an actual map using geopandas
def plot_gps_path(csv_file):
    longitudes, latitudes = read_gps_data(csv_file)

    # Check if there are fewer than 1000 rows of data, and skip if true
    if len(longitudes) < 1000 or len(latitudes) < 1000:
        print(f"Skipping {csv_file}: Less than 1000 rows of data.")
        return

    if len(longitudes) == 0 or len(latitudes) == 0:
        print(f"No valid GPS data to plot for {csv_file}.")
        return

    # Create a GeoDataFrame
    gdf = gpd.GeoDataFrame(
        {'Longitude': longitudes, 'Latitude': latitudes},
        geometry=[Point(lon, lat) for lon, lat in zip(longitudes, latitudes)],
        crs="EPSG:4326"  # Set the CRS to WGS84 (EPSG:4326)
    )

    # Reproject to Web Mercator (EPSG:3857) for compatibility with the basemap
    gdf = gdf.to_crs(epsg=3857)

    # Plot the GPS path on a map
    ax = gdf.plot(figsize=(10, 10), marker='o', markersize=1, linewidth=1, color='b', alpha=0.6)

    # Set dynamic zoom by adjusting bounds
    min_lon, max_lon, min_lat, max_lat = calculate_bounds(longitudes, latitudes)

    # Recalculate the bounds in the new CRS
    bounds = gpd.GeoSeries([Point(min_lon, min_lat), Point(max_lon, max_lat)], crs="EPSG:4326").to_crs(epsg=3857).total_bounds
    ax.set_xlim([bounds[0], bounds[2]])
    ax.set_ylim([bounds[1], bounds[3]])

    # Estimate a reasonable zoom level
    zoom = estimate_zoom(min_lon, max_lon, min_lat, max_lat)
    print(f"Using zoom level: {zoom}")

    # Add basemap using OpenStreetMap tiles with calculated zoom
    ctx.add_basemap(ax, crs=gdf.crs, source=ctx.providers.OpenStreetMap.Mapnik, zoom=zoom)

    plt.title(f'GPS Path Visualization: {os.path.basename(csv_file)}')
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')

    plt.grid(True)
    plt.show()

# Function to find all CSV files in the current directory
def find_csv_files():
    return [f for f in os.listdir('.') if f.endswith('.csv')]

if __name__ == "__main__":
    csv_files = find_csv_files()
    
    if not csv_files:
        print("No CSV files found in the current directory.")
    else:
        for csv_file in csv_files:
            print(f"Plotting: {csv_file}")
            plot_gps_path(csv_file)
