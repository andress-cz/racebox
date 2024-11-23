import asyncio
import struct
import csv
import time
from bleak import BleakScanner, BleakClient
import sys
import json
import os
from math import radians, sin, cos, sqrt, atan2

# UUIDs from the RaceBox protocol
RACEBOX_UART_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
RX_CHAR_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
TX_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
NMEA_TX_UUID = "00001103-0000-1000-8000-00805f9b34fb"
DOWNLOAD_COMMAND = bytes([0xB5, 0x62, 0xFF, 0x23, 0x00, 0x00, 0x22, 0x65])  # Command to initiate data download

# CSV headers based on the parsed data structure
CSV_HEADERS = [
    "iTOW", "Year", "Month", "Day", "Hour", "Minute", "Second", "Longitude", "Latitude", 
    "WGS Altitude", "Speed", "Heading", "G-Force X", "G-Force Y", "G-Force Z", 
    "Rotation rate X", "Rotation rate Y", "Rotation rate Z"
]

# Add these constants at the top with other constants
DEVICE_MEMORY_FILE = "last_device.json"

def format_filename_from_first_record(first_record, device_name):
    """Generate filename using the first record's date."""
    year = first_record['Year']
    month = f"{first_record['Month']:02d}"
    day = f"{first_record['Day']:02d}"
    hour = f"{first_record['Hour']:02d}"
    minute = f"{first_record['Minute']:02d}"
    second = f"{first_record['Second']:02d}"
    timestamp = f"{year}{month}{day}_{hour}{minute}{second}"
    return f"racebox_data_{device_name}_{timestamp}.csv"

# Function to save parsed data into CSV with first record's date and device name
def save_to_csv(data_list, device_name):
    if data_list:
        first_record = data_list[0]
        file_name = format_filename_from_first_record(first_record, device_name)
        with open(file_name, mode='w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=CSV_HEADERS)
            writer.writeheader()
            writer.writerows(data_list)
        print(f"Data saved to {file_name}")

def save_last_device(device):
    """Save the last successfully connected device."""
    device_info = {
        "address": device.address,
        "name": device.name
    }
    with open(DEVICE_MEMORY_FILE, 'w') as f:
        json.dump(device_info, f)

def get_last_device():
    """Get the last successfully connected device info."""
    try:
        if os.path.exists(DEVICE_MEMORY_FILE):
            with open(DEVICE_MEMORY_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error reading device memory: {e}")
    return None

async def scan_and_connect(monitor_only=False, measure=False):
    """Scan for RaceBox devices and connect to them."""
    try:
        # Try to connect to last known device first
        last_device = get_last_device()
        if last_device:
            print(f"Attempting to connect to last known device: {last_device['name']}")
            try:
                device = await BleakScanner.find_device_by_address(last_device['address'])
                if device:
                    print(f"Found last device: {device.name} - {device.address}")
                    if measure:
                        await measure_distances(device)
                    elif monitor_only:
                        await read_current_position(device)
                    else:
                        await connect_and_download(device)
                    return
                else:
                    print("Last known device not found, scanning for devices...")
            except Exception as e:
                print(f"Error connecting to last device: {e}")
                print("Scanning for devices...")

        # If last device connection failed or doesn't exist, scan for new devices
        devices = await BleakScanner.discover()
        racebox_devices = [device for device in devices if device.name and "RaceBox" in device.name]

        if racebox_devices:
            print(f"Found {len(racebox_devices)} RaceBox devices.")
            for device in racebox_devices:
                print(f"Connecting to {device.name} - {device.address}")
                # Save successful connection
                save_last_device(device)
                try:
                    if measure:
                        await measure_distances(device)
                    elif monitor_only:
                        await read_current_position(device)
                    else:
                        await connect_and_download(device)
                    break  # Connect to first available device only
                except Exception as e:
                    print(f"Failed to connect to {device.name}: {e}")
        else:
            print("No RaceBox devices found.")
    except asyncio.CancelledError:
        print("\nOperation cancelled by user")
        raise

def parse_21_message(packet):
    """Parse the 80-byte history data packet (0xFF 0x21) from an 88-byte message."""
    payload = packet[6:86]
    parsed_data = struct.unpack('<I H B B B B B B I i B B B B i i i i I I i i I I H B B h h h h h h', payload[:80])
    record = {
        "iTOW": parsed_data[0],
        "Year": parsed_data[1],
        "Month": parsed_data[2],
        "Day": parsed_data[3],
        "Hour": parsed_data[4],
        "Minute": parsed_data[5],
        "Second": parsed_data[6],
        "Longitude": parsed_data[14] / 1e7,
        "Latitude": parsed_data[15] / 1e7,
        "WGS Altitude": parsed_data[16] / 1000,
        "Speed": parsed_data[20] / 1000,
        "Heading": parsed_data[21] / 100000,
        "G-Force X": parsed_data[27] / 1000,
        "G-Force Y": parsed_data[28] / 1000,
        "G-Force Z": parsed_data[29] / 1000,
        "Rotation rate X": parsed_data[30] / 100,
        "Rotation rate Y": parsed_data[31] / 100,
        "Rotation rate Z": parsed_data[32] / 100
    }
    return record

def parse_01_message(packet):
    """Parse the 80-byte live data packet (0xFF 0x01)."""
    payload = packet[6:86]
    parsed_data = struct.unpack('<I H B B B B B B I i B B B B i i i i I I i i I I H B B h h h h h h', payload[:80])
    record = {
        "iTOW": parsed_data[0],
        "Year": parsed_data[1],
        "Month": parsed_data[2],
        "Day": parsed_data[3],
        "Hour": parsed_data[4],
        "Minute": parsed_data[5],
        "Second": parsed_data[6],
        "Longitude": parsed_data[14] / 1e7,
        "Latitude": parsed_data[15] / 1e7,
        "WGS Altitude": parsed_data[16] / 1000,
        "MSL Altitude": parsed_data[17] / 1000,
        "Horizontal Accuracy": parsed_data[18] / 1000,
        "Vertical Accuracy": parsed_data[19] / 1000,
        "Speed": parsed_data[20] / 1000,
        "Heading": parsed_data[21] / 100000,
        "G-Force X": parsed_data[27] / 1000,
        "G-Force Y": parsed_data[28] / 1000,
        "G-Force Z": parsed_data[29] / 1000,
        "Rotation rate X": parsed_data[30] / 100,
        "Rotation rate Y": parsed_data[31] / 100,
        "Rotation rate Z": parsed_data[32] / 100
    }
    return record

def validate_checksum(buffer):
    """Validates the checksum as per the protocol."""
    ck_a, ck_b = 0, 0
    for byte in buffer[2:-2]:
        ck_a = (ck_a + byte) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    return ck_a == buffer[-2] and ck_b == buffer[-1]

async def connect_and_download(device):
    session_data = []  # Data for the current session
    buffer = bytearray()
    total_records = 0
    download_complete = asyncio.Event()  # Event to track download completion

    async with BleakClient(device) as client:
        await client.connect()  # Establish the connection

        services = client.services  # Use services property instead of deprecated get_services

        if RACEBOX_UART_SERVICE_UUID not in [str(service.uuid) for service in services]:
            print(f"Device {device.name} does not have the UART service.")
            return

        def notification_handler(sender, data):
            nonlocal buffer, session_data, total_records
            buffer.extend(data)

            # Process the buffer
            while len(buffer) >= 8:  # Minimum packet size to check for message class and ID
                if buffer[:2] == bytes([0xB5, 0x62]):
                    message_class, message_id = buffer[2], buffer[3]
                    packet_length = struct.unpack('<H', buffer[4:6])[0]
                    full_packet_length = packet_length + 8
                    
                    if len(buffer) < full_packet_length:
                        break  # Wait for more data if the full packet hasn't been received yet

                    if validate_checksum(buffer[:full_packet_length]):
                        if message_class == 0xFF:
                            if message_id == 0x23:  # Download data start
                                total_records = struct.unpack('<I', buffer[6:10])[0]
                                print(f"Expecting {total_records} records.")
                            elif message_id == 0x21:  # History data
                                record = parse_21_message(buffer[:full_packet_length])
                                session_data.append(record)
                            elif message_id == 0x01:  # Live data
                                record = parse_01_message(buffer[:full_packet_length])
                                session_data.append(record)
                            elif message_id == 0x02:  # ACK indicating download complete
                                print("Download complete.")
                                download_complete.set()  # Set the event when download is done
                            elif message_id == 0x03:  # NACK
                                print("NACK received")
                            elif message_id == 0x26:  # Session change - save current session data
                                print("Standalone recording state changed.")
                                if session_data:
                                    save_to_csv(session_data, device.name)
                                    session_data = []  # Start a new session
                        buffer = buffer[full_packet_length:]

        await client.start_notify(TX_CHAR_UUID, notification_handler)
        await client.write_gatt_char(RX_CHAR_UUID, DOWNLOAD_COMMAND)
        print(f"Downloading data from {device.name}...")

        # Wait for the download to complete
        await download_complete.wait()
        await client.stop_notify(TX_CHAR_UUID)

    # Save the final session's data
    if session_data:
        save_to_csv(session_data, device.name)

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points using Haversine formula."""
    R = 6371000  # Earth's radius in meters
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

async def measure_distances(device):
    """Measure distances between marked points."""
    buffer = bytearray()
    client = None
    first_message = True
    reference_point = None
    points = []
    current_record = None  # Add this to store the most recent record

    try:
        client = BleakClient(device)
        await client.connect()
        print(f"Connected to {device.name}")
        print("Press Enter to mark a position")
        services = client.services

        if RACEBOX_UART_SERVICE_UUID not in [str(service.uuid) for service in services]:
            print(f"Device {device.name} does not have the NMEA service.")
            return

        def notification_handler(sender, data):
            nonlocal buffer, first_message, current_record
            buffer.extend(data)

            while len(buffer) >= 8:
                if buffer[:2] == bytes([0xB5, 0x62]):
                    message_class, message_id = buffer[2], buffer[3]
                    packet_length = struct.unpack('<H', buffer[4:6])[0]
                    full_packet_length = packet_length + 8
                    
                    if len(buffer) < full_packet_length:
                        break

                    if validate_checksum(buffer[:full_packet_length]):
                        if message_class == 0xFF and message_id == 0x01:
                            current_record = parse_01_message(buffer[:full_packet_length])
                            
                            # Clear previous lines
                            if not first_message:
                                lines_to_clear = 4 if reference_point else 3
                                print(f"\033[{lines_to_clear}A\033[K", end='')
                            else:
                                first_message = False
                            
                            # Always show current position
                            print(f"Current: {current_record['Latitude']:.6f}°, {current_record['Longitude']:.6f}°")
                            print(f"Accuracy: ±{current_record['Horizontal Accuracy']:.1f} m")
                            print(f"Altitude: {current_record['WGS Altitude']:.1f} m")
                            
                            # If we have a reference point, show distance to it
                            if reference_point:
                                distance = calculate_distance(
                                    reference_point['Latitude'],
                                    reference_point['Longitude'],
                                    current_record['Latitude'],
                                    current_record['Longitude']
                                )
                                print(f"Distance to marked point: {distance:.1f} m")
                            
                        buffer = buffer[full_packet_length:]

        await client.start_notify(TX_CHAR_UUID, notification_handler)
        
        while True:
            # Wait for Enter key
            await asyncio.get_event_loop().run_in_executor(None, input, "")
            
            # Use the most recent record
            if current_record:
                points.append(current_record)
                reference_point = current_record
                print(f"\nPoint {len(points)} marked at: {current_record['Latitude']:.6f}°, {current_record['Longitude']:.6f}°")
                
                if len(points) > 1:
                    # Calculate total distance through all points
                    total_distance = sum(
                        calculate_distance(
                            points[i-1]['Latitude'],
                            points[i-1]['Longitude'],
                            points[i]['Latitude'],
                            points[i]['Longitude']
                        ) for i in range(1, len(points))
                    )
                    print(f"Total distance through all points: {total_distance:.1f} m")
                    # Add extra newline to maintain display spacing
                    print("")

    except KeyboardInterrupt:
        print("\nMeasuring stopped by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if client and client.is_connected:
            try:
                await client.stop_notify(TX_CHAR_UUID)
                await client.disconnect()
                print("Disconnected from device")
            except Exception as e:
                print(f"Error during disconnect: {e}")

def show_menu():
    """Show menu and get user selection."""
    print("\nRaceBox Data Tool")
    print("1. Download history")
    print("2. Monitor current position")
    print("3. Measure distances")
    print("q. Quit")
    
    while True:
        choice = input("\nSelect option: ").lower()
        if choice in ['1', '2', '3', 'q']:
            return choice
        print("Invalid option, please try again")

async def read_current_position(device):
    """Read and display current position data continuously."""
    buffer = bytearray()
    client = None
    first_message = True

    try:
        client = BleakClient(device)
        await client.connect()
        print(f"Connected to {device.name}")
        services = client.services

        if RACEBOX_UART_SERVICE_UUID not in [str(service.uuid) for service in services]:
            print(f"Device {device.name} does not have the NMEA service.")
            return

        def notification_handler(sender, data):
            nonlocal buffer, first_message
            buffer.extend(data)

            while len(buffer) >= 8:
                if buffer[:2] == bytes([0xB5, 0x62]):
                    message_class, message_id = buffer[2], buffer[3]
                    packet_length = struct.unpack('<H', buffer[4:6])[0]
                    full_packet_length = packet_length + 8
                    
                    if len(buffer) < full_packet_length:
                        break

                    if validate_checksum(buffer[:full_packet_length]):
                        if message_class == 0xFF and message_id == 0x01:  # Live data
                            record = parse_01_message(buffer[:full_packet_length])
                            
                            if not first_message:
                                # Move cursor up 3 lines (exactly matching our output)
                                print("\033[3A\033[K", end='')
                            else:
                                first_message = False
                                
                            print(f"Position: {record['Latitude']:.6f}°, {record['Longitude']:.6f}°")
                            print(f"Speed: {record['Speed']:.1f} km/h")
                            print(f"Altitude: {record['WGS Altitude']:.1f} m")
                        buffer = buffer[full_packet_length:]

        await client.start_notify(TX_CHAR_UUID, notification_handler)
        
        while True:
            await asyncio.sleep(1)
                
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if client and client.is_connected:
            try:
                await client.stop_notify(TX_CHAR_UUID)
                await client.disconnect()
                print("Disconnected from device")
            except Exception as e:
                print(f"Error during disconnect: {e}")

def main():
    while True:
        choice = show_menu()
        
        if choice == 'q':
            print("\nGoodbye!")
            sys.exit(0)
            
        try:
            if choice == '3':
                asyncio.run(scan_and_connect(monitor_only=False, measure=True))
            else:
                monitor_only = (choice == '2')
                asyncio.run(scan_and_connect(monitor_only=monitor_only))
        except KeyboardInterrupt:
            print("\nOperation cancelled by user")
        except Exception as e:
            print(f"\nError: {e}")
        

if __name__ == "__main__":
    main()
