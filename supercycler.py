import sys
import time
import socket
import requests
import argparse
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import xml.etree.ElementTree as ET

def calcular_proximo_cambio(file):
    """
    Encuentra el próximo cambio de estado ON/OFF analizando el último cambio registrado.

    Args:
        file (str): Ruta al archivo XML.

    Returns:
        dict: Diccionario con la fecha, hora y estado del próximo cambio y las horas restantes.
    """
    try:
        tree = ET.parse(file)
        root = tree.getroot()

        eventos = []

        # Leer eventos del XML respetando el orden
        for event in root.findall("event"):
            date_str = event.find("date").text  # Formato esperado: DD/MM/YYYY
            hour_str = event.find("hour").text.zfill(2)  # Asegurar formato HH
            state = event.find("state").text

            # Convertir a objeto datetime
            event_datetime = datetime.strptime(f"{date_str} {hour_str}", "%d/%m/%Y %H")
            eventos.append((event_datetime, state))

        # Obtener la fecha y hora actual
        now = datetime.now()

        # Encontrar el último estado antes de la hora actual
        estado_actual = None
        for i in range(len(eventos) - 1):
            if eventos[i][0] <= now < eventos[i + 1][0]:
                estado_actual = eventos[i][1]
                break

        if estado_actual is None:
            return {"error": "No se pudo determinar el estado actual."}

        # Buscar el próximo cambio de estado distinto al actual
        for evento in eventos:
            if evento[0] > now and evento[1] != estado_actual:
                tiempo_restante = (evento[0] - now).total_seconds() / 3600
                return {
                    "fecha": evento[0].strftime("%d/%m/%Y"),
                    "hora": evento[0].strftime("%H:%M"),
                    "estado": evento[1],
                    "faltan_horas": round(tiempo_restante, 2)
                }

        return {"error": "No hay más cambios de estado programados."}

    except Exception as e:
        return {"error": f"Error al procesar el archivo XML: {e}"}

def calcular_ciclo_on_off(file):
    """
    Analiza el XML y calcula cada cuántas horas cambia el estado ON/OFF.
    
    Args:
        file (str): Ruta al archivo XML.
    
    Returns:
        str: Un string en formato "X horas ON / Y horas OFF".
    """
    try:
        tree = ET.parse(file)
        root = tree.getroot()

        cambios = []  # Lista de horas entre cambios de estado
        last_state = None
        last_hour = None

        for event in root.findall("event"):
            hour = int(event.find("hour").text)  # Convertir hora a entero
            state = event.find("state").text  # Estado ON / OFF

            # Si es el primer evento, inicializar estado previo
            if last_state is None:
                last_state = state
                last_hour = hour
                continue

            # Si el estado cambió, calcular diferencia horaria
            if state != last_state:
                diff = hour - last_hour if hour >= last_hour else (hour + 24 - last_hour)
                cambios.append(diff)
                last_state = state
                last_hour = hour

        # Si no hubo cambios, no se puede calcular
        if len(cambios) < 2:
            return "No se detectaron suficientes cambios para calcular el ciclo."

        # Separar horas ON y OFF alternadamente
        horas_on = cambios[::2]  # ON -> OFF
        horas_off = cambios[1::2]  # OFF -> ON

        # Calcular promedios
        promedio_on = sum(horas_on) / len(horas_on) if horas_on else 0
        promedio_off = sum(horas_off) / len(horas_off) if horas_off else 0

        return int(promedio_on),int(promedio_off)

    except Exception as e:
        return f"Error al procesar el archivo XML: {e}"


def calcular_dia_de_flora(file):
    """
    Lee la primera fecha del XML y calcula el día de floración en función de la fecha actual.

    Args:
        file (str): Ruta al archivo XML.

    Returns:
        int: Día de floración actual.
    """
    try:
        tree = ET.parse(file)
        root = tree.getroot()

        # Obtener la primera fecha registrada en el XML
        first_event = root.find("event")
        if first_event is None:
            print("No hay eventos en el archivo XML.")
            return None

        start_date_str = first_event.find("date").text  # Formato esperado: DD/MM/YYYY
        start_date = datetime.strptime(start_date_str, "%d/%m/%Y")  # Convertir a objeto datetime
        
        # Obtener la fecha actual
        today = datetime.today()

        # Calcular la diferencia en días
        dias_de_flora = (today - start_date).days

        return dias_de_flora

    except Exception as e:
        print(f"Error al procesar el archivo XML: {e}")
        return None



def read_configuration(file):
    """
    Reads the configuration XML file and normalizes the keys.

    Args:
        file (str): Path to the configuration XML file.

    Returns:
        dict: A dictionary storing the states indexed by date and hour.
        dict: A dictionary storing additional metadata (fotoperiodism, mode, alert).
    """
    configuration = {}
    metadata = {}

    try:
        tree = ET.parse(file)
        root = tree.getroot()

        for event in root.findall("event"):
            date = event.find("date").text  # Ejemplo: 30/01/2025
            hour = event.find("hour").text  # Asegurar que tenga dos dígitos
            state = event.find("state").text
            
            # Crear estructura por fecha si no existe
            if date not in configuration:
                configuration[date] = {}
            # Guardar estado dentro de la fecha
            configuration[date][hour] = state

            # Guardar datos adicionales
            metadata[f"{date}#{hour}"] = {
                "fotoperiodism": event.find("fotoperiodism").text if event.find("fotoperiodism") is not None else "N/A",
                "mode": event.find("mode").text if event.find("mode") is not None else "N/A",
                "alert": event.find("alert").text if event.find("alert") is not None else "N/A"
            }

    except Exception as e:
        print(f"Error reading configuration file: {e}")

    return configuration, metadata

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

    state_str = "ON" if state == 1 else "OFF"
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

    day = 0
    week = 1
    
    #day, week = calculate_flowering_day_and_week(config)
    #light_hours, dark_hours, total_cycle_hours = calculate_first_cycle_duration(config)
    light_hours = 0 
    dark_hours = 0
    total_cycle_hours=0
    #if photoperiodism_minutes:
    #    config = apply_photoperiodism_change(config, photoperiodism_minutes, day)

    dia_de_flora = calcular_dia_de_flora(file)
    ciclo_on,ciclo_off = calcular_ciclo_on_off(file)
    week = dia_de_flora / 7
    diatotal  = ciclo_on + ciclo_off
 

    proximo_cambio = calcular_proximo_cambio(file)
    fecha_proximo_cambio = proximo_cambio["fecha"]
    hora_proximo_cambio = proximo_cambio["hora"]
    estado_proximo_cambio = proximo_cambio["estado"]
    faltan_proximo_cambio = int(round(proximo_cambio["faltan_horas"], 2))

    # Definir colores ANSI
    RESET = ""
    WHITE = ""
    GREEN_FLUO = ""
    PINK_FLUO = ""
    CYAN = ""

# Imprimir con colores llamativos
    print(f"\n{WHITE}Current flowering day {GREEN_FLUO}{dia_de_flora}{WHITE}, Week {PINK_FLUO}{int(week)}{WHITE}\n"
        f"SuperCycle: {CYAN}{ciclo_on}/{ciclo_off}{WHITE}, "
        f"Virtual day length: {GREEN_FLUO}{diatotal} hours{WHITE}\n"
        f"Next change to {PINK_FLUO}{estado_proximo_cambio}{WHITE} in {CYAN}{faltan_proximo_cambio} hours "
        f"({GREEN_FLUO}{fecha_proximo_cambio} {PINK_FLUO}{hora_proximo_cambio}{WHITE})")

 
    config, meta = read_configuration(file)
     
    now = datetime.now()
    date_key = now.strftime("%d/%m/%Y")  # Formato correcto para el XML
    hour_key = now.strftime("%H")  # Asegurar dos dígitos

    #print(f"Buscando configuración para: {date_key} {hour_key}")

   # Buscar estado en la fecha y hora exactas
    state = config.get(date_key, {}).get(hour_key, None)

    if state is None:
        print(f"⚠️ Warning: No configuration found for {date_key} at {hour_key}h.")

    if state == "ON":
        send_command_tasmota(1, "AUTO", ip_address)
    elif state == "OFF":
        send_command_tasmota(0, "AUTO", ip_address)
    else:
        print(f"❌ No command executed. Found state: {state}")



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


