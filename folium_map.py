import os
import csv
import folium
from shapely.geometry import Point
import numpy as np
import math
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

# Define the bounding box for the Czech Republic
LAT_MIN, LAT_MAX = 48.5, 51.5
LON_MIN, LON_MAX = 12.0, 18.9

# Function to read and filter GPS data for the Czech Republic
def read_gps_data(csv_file):
    longitudes = []
    latitudes = []
    speeds = []

    with open(csv_file, mode='r') as file:
        reader = csv.DictReader(file)
        for i, row in enumerate(reader):
            longitude = float(row["Longitude"])
            latitude = float(row["Latitude"])
            speed = float(row["Speed"])

            # Print the first few rows to check the data
            if i < 5:
                print(f"Row {i}: Longitude={longitude}, Latitude={latitude}, Speed={speed}")

            # Filter for valid latitude and longitude within the Czech Republic bounds
            if LON_MIN <= longitude <= LON_MAX and LAT_MIN <= latitude <= LAT_MAX:
                longitudes.append(longitude)
                latitudes.append(latitude)
                speeds.append(speed)
            else:
                print(f"Data outside CZ skipped: Longitude={longitude}, Latitude={latitude}")

    return longitudes, latitudes, speeds

# Function to map speed to a color (blue = slow, red = fast) using matplotlib's 'coolwarm' colormap
def speed_to_color(speed, max_speed):
    cmap = plt.get_cmap('cool')  # Blue for slow speeds, red for fast speeds
    norm_speed = min(speed / max_speed, 1.0)  # Normalize speed between 0 and 1
    return mcolors.to_hex(cmap(norm_speed))

# Function to plot the GPS path on an interactive folium map
def plot_gps_path(csv_file):
    longitudes, latitudes, speeds = read_gps_data(csv_file)

    # Check if there are fewer than 1000 rows of data, and skip if true
    if len(longitudes) < 1000 or len(latitudes) < 1000:
        print(f"Skipping {csv_file}: Less than 1000 rows of data.")
        return

    if len(longitudes) == 0 or len(latitudes) == 0:
        print(f"No valid GPS data to plot for {csv_file}.")
        return

    # Create the folium map, centered on the average of the data points
    avg_lat = np.mean(latitudes)
    avg_lon = np.mean(longitudes)
    map_folium = folium.Map(location=[avg_lat, avg_lon], zoom_start=13)

    # Calculate maximum speed for normalization
    max_speed = max(speeds)

    # Add GPS points as polylines with varying colors (based on speed)
    for i in range(1, len(latitudes)):
        start_point = [latitudes[i-1], longitudes[i-1]]
        end_point = [latitudes[i], longitudes[i]]
        speed = speeds[i]

        # Map speed to color
        color = speed_to_color(speed, max_speed)

        # Add the polyline segment to the map with thinner lines and increased opacity
        folium.PolyLine(
            [start_point, end_point],
            color=color,
            weight=3,  # Reduce the path width to 3 for a thinner line
            opacity=1.0  # Increase opacity to make the path fully solid
        ).add_to(map_folium)

    # Save the map as an HTML file for interactive viewing
    map_name = f"{os.path.basename(csv_file).replace('.csv', '')}_map.html"
    map_folium.save(map_name)
    print(f"Map saved as {map_name}")

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
