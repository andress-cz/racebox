import asyncio
import struct
import csv
import time
from bleak import BleakScanner, BleakClient

# UUIDs from the RaceBox protocol
RACEBOX_UART_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
RX_CHAR_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
TX_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
DOWNLOAD_COMMAND = bytes([0xB5, 0x62, 0xFF, 0x23, 0x00, 0x00, 0x22, 0x65])  # Command to initiate data download

# CSV headers based on the parsed data structure
CSV_HEADERS = [
    "iTOW", "Year", "Month", "Day", "Hour", "Minute", "Second", "Longitude", "Latitude", 
    "WGS Altitude", "Speed", "Heading", "G-Force X", "G-Force Y", "G-Force Z", 
    "Rotation rate X", "Rotation rate Y", "Rotation rate Z"
]

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

async def scan_and_connect():
    devices = await BleakScanner.discover()
    racebox_devices = [device for device in devices if device.name and "RaceBox" in device.name]

    if racebox_devices:
        print(f"Found {len(racebox_devices)} RaceBox devices.")
        for device in racebox_devices:
            print(f"Connecting to {device.name} - {device.address}")
            await connect_and_download(device)
    else:
        print("No RaceBox devices found.")

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

async def main():
    await scan_and_connect()

if __name__ == "__main__":
    asyncio.run(main())
