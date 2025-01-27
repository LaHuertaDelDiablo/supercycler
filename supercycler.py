import sys
import time
import socket
import requests
import argparse
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

def read_configuration(file):
    """
    Reads the configuration file and normalizes the keys.

    Args:
        file (str): Path to the configuration file.

    Returns:
        dict: A dictionary with normalized keys (date#hour) and their states (ON/OFF).
    """
    configuration = {}
    try:
        with open(file, "r") as f:
            for line in f:
                line = line.strip()  # Remove whitespace and newlines
                if not line:
                    continue  # Skip empty lines
                key, state = line.split(",")
                # Normalize keys to ensure compatibility (if hours are single digits)
                day, hour = key.split("#")
                normalized_hour = hour.zfill(2)  # Ensure two-digit hours
                configuration[f"{day}#{normalized_hour}"] = state
    except Exception as e:
        print(f"Error reading configuration file: {e}")
    return configuration

def calculate_first_cycle_duration(configuration):
    """
    Calculates the total duration of the first light and dark cycle from the configuration file.

    Args:
        configuration (dict): The parsed configuration dictionary.

    Returns:
        tuple: Light duration (hours), Dark duration (hours), Total cycle duration (hours).
    """
    light_hours = 0
    dark_hours = 0

    # Sort configuration keys to process them in chronological order
    sorted_keys = configuration.keys()
    #sorted_keys = sorted(configuration.keys())
    state_tracking = None

    for key in sorted_keys:
        state = configuration[key]
        if state_tracking is None:
            state_tracking = state

        # Count "ON" hours for light and "OFF" hours for dark until the cycle resets
        if state == "ON":
            #print (f"on {key}")
            if state_tracking == "OFF":
                break  # End of the first cycle
            light_hours += 1
        elif state == "OFF":
            #print (f"off {key}")
            if state_tracking == "ON":
                state_tracking = "OFF"
            dark_hours += 1

    #print ( light_hours)
    #print ( dark_hours)
    total_cycle_hours = light_hours + dark_hours
    return light_hours, dark_hours, total_cycle_hours

def calculate_flowering_day_and_week(configuration):
    """
    Calculates the current flowering day and week based on the configuration file.

    Args:
        configuration (dict): The parsed configuration dictionary with date-hour keys.

    Returns:
        tuple: (current_day, current_week) representing the day and week of flowering.
    """
    if not configuration:
        return 0, 0

    # Extract the first date from the configuration
    first_key = list(configuration.keys())[0]
    first_date_str = first_key.split("#")[0]
    first_date = datetime.strptime(first_date_str, "%d/%m/%Y")

    # Calculate the difference in days from the first date
    now = datetime.now()
    days_difference = (now - first_date).days + 1  # Include the first day as day 1

    current_week = (days_difference // 7) + 1

    return days_difference, current_week

def send_command_tasmota(state, mode, ip_address):
    """
    Sends the command to the Tasmota device to turn the light ON or OFF.

    Args:
        state (int): 1 to turn ON, 0 to turn OFF.
        mode (str): Operation mode (e.g., MANUAL, AUTO).
        ip_address (str): IP address of the Tasmota device.

    Notes:
        This function uses the Tasmota HTTP API to send commands to the device.
        Ensure the Tasmota device is properly configured and accessible over the network.
    """
    url = f"http://{ip_address}:5000/setSta"
    headers = {"Content-Type": "application/json"}
    payload = {"status": state}

    state_str = "on" if state == 1 else "off"
    print(f"{datetime.now()}: Light {state_str} ({mode})")

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            with open("supercycler.log", "a") as file:
                file.write(f"{datetime.now()}: Light {state_str} ({mode})\n")
        else:
            with open("supercycler.log", "a") as file:
                print(f"\n###### ERROR {url} ######\n")
                file.write(f"{datetime.now()}: Error in device response ({mode}).\n")
                print(f"{datetime.now()}: Error in device response ({mode}).\n")
    except requests.exceptions.RequestException as e:
        with open("supercycler.log", "a") as file:
            print(f"\n###### ERROR {url} ######\n")
            file.write(f"{datetime.now()}: ERROR connecting to device ({mode}). {e}\n")
            print(f"{datetime.now()}: ERROR connecting to device ({mode}). {e}\n")

def automatic(file, ip_address, photoperiodism_minutes=None):
    """
    Automatically controls the light based on the configuration file.

    Args:
        file (str): Path to the configuration file.
        ip_address (str): IP address of the Tasmota device.
        photoperiodism_minutes (int): Minutes to adjust the light duration each day.
    """
    now = datetime.now()
    config = read_configuration(file)

    day, week = calculate_flowering_day_and_week(config)
    light_hours, dark_hours, total_cycle_hours = calculate_first_cycle_duration(config)

    if photoperiodism_minutes:
        config = apply_photoperiodism_change(config, photoperiodism_minutes, day)

    print(f"Current flowering day: {day}, Current flowering week: {week}, "
          f"Light {light_hours} hours, Dark {dark_hours} hours, "
          f"Cycle duration: {total_cycle_hours} hours")

    key = now.strftime("%d/%m/%Y#%H")
    state = config.get(key)

    if state is None:
        print(f"Warning: No configuration found for key {key}.")

    if state == "ON":
        send_command_tasmota(1, "AUTO", ip_address)
    elif state == "OFF":
        send_command_tasmota(0, "AUTO", ip_address)
    else:
        print(f"No command executed. Found state: {state}")

def supercycle_loop(file, ip_address, photoperiodism_minutes=None):
    """
    Executes the supercycle mode in a loop that checks the state every 10 minutes.

    Args:
        file (str): Path to the configuration file.
        ip_address (str): IP address of the Tasmota device.
        photoperiodism_minutes (int): Minutes to adjust the light duration each day.
    """
    while True:
        automatic(file, ip_address, photoperiodism_minutes)
        time.sleep(600)  # Wait for 10 minutes

def main():
    """
    Main program to control the WiFi device.

    This function parses command-line arguments to determine the operation mode:
    - Manual: Turn the light ON or OFF.
    - Automatic: Use a configuration file for scheduled control.
    - Supercycle: Loop through the configuration, checking every 10 minutes.
    """
    parser = argparse.ArgumentParser(
        description="Indoor light control.",
        epilog="""
WiFi device IP address.

Usage examples:

- Manual mode:
  python script.py -m on -ip 192.168.1.100
  python script.py -m off -ip 192.168.1.100

- One-time mode:
  python script.py -o supercycle.txt -ip 192.168.1.100

- Supercycle mode (checks every 10 minutes):
  python script.py -s supercycle.txt -ip 192.168.1.100

NOTE: Ensure the configuration file is correctly formatted.
        """
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-m", "--manual",
        choices=["on", "off"],
        help="Turn the light on or off manually."
    )
    group.add_argument(
        "-o", "--onetime",
        help="Execute a one-time automatic configuration. Provide the file path."
    )
    group.add_argument(
        "-s", "--supercycle",
        help="Select the configuration file for supercycle mode (checks every 10 minutes)."
    )

    parser.add_argument(
        "-ip", "--ip_address",
        help="WiFi device IP address.",
        required=True
    )

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    if args.manual:
        state = 1 if args.manual == "on" else 0
        send_command_tasmota(state, "MANUAL", args.ip_address)
    elif args.onetime:
        automatic(args.onetime, args.ip_address)
    elif args.supercycle:
        supercycle_loop(args.supercycle, args.ip_address)



if __name__ == "__main__":
    main()


