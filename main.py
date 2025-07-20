import json
import time
import os
from beat_sync import run_manual_beat
from multi_sync import seleccionar_config_por_luz, run_multi_sync
from govee_lan import GoveeLan

CONFIG_PATH = "config.json"
CONFIG_CACHE = "last_config.json"


def cargar_ips_json():
    if not os.path.exists(CONFIG_PATH):
        print("Archivo config.json no encontrado.")
        return []
    with open(CONFIG_PATH) as f:
        return json.load(f).get("ips", [])


def guardar_config(grupos):
    with open(CONFIG_CACHE, "w") as f:
        json.dump(grupos, f, indent=2)
    print("✅ Configuración guardada en 'last_config.json'.")


def cargar_config_existente():
    if os.path.exists(CONFIG_CACHE):
        with open(CONFIG_CACHE) as f:
            return json.load(f)
    return []


def menu():
    print("\nSelecciona modo:")
    print("1. Efecto Manual (Pulso por tiempo)")
    print("2. Sincronización por grupos / instrumentos (multi banda)")
    print("3. Usar última configuración de grupos")
    print("4. Salir")
    return input("\nOpción: ").strip()


if __name__ == "__main__":
    opcion = menu()

    if opcion == "1":
        ips = cargar_ips_json()
        if not ips:
            exit("No se encontraron IPs en config.json")
        lights = GoveeLan(ips)

        brightness = int(input("Brillo deseado(1–100): ").strip() or 100)
        lights.set_brightness(brightness)

        print("\nColores disponibles para pulso manual (ej: 255,0,0;0,0,0):")
        raw = input("Colores separados por punto y coma: ").strip()
        color_pairs = raw.split(";")
        colors = [tuple(map(int, c.split(","))) for c in color_pairs if c]

        delay = float(input("\nIntervalo entre pulsos (segundos): "))
        run_manual_beat(colors, delay, lights)

    elif opcion == "2":
        ips = cargar_ips_json()
        if not ips:
            exit("No se encontraron IPs en config.json")
        grupos = seleccionar_config_por_luz(ips)
        guardar_config(grupos)
        run_multi_sync(grupos)

    elif opcion == "3":
        grupos = cargar_config_existente()
        if not grupos:
            exit("No hay configuración guardada.")
        run_multi_sync(grupos)

    elif opcion == "4":
        print("Saliendo.")

    else:
        print("\nOpción no válida.")
