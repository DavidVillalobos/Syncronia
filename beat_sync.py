import time


def run_manual_beat(colors, delay, govee):
    print("\nIniciando efecto manual. Presiona Ctrl+C para detener.")
    try:
        while True:
            for color in colors:
                print(f"Encendiendo {color}")
                govee.set_color(*color)
                time.sleep(delay)
                print("Apagando...")
                govee.set_color(0, 0, 0)
                time.sleep(delay)
    except KeyboardInterrupt:
        print("\nEfecto detenido.")
        govee.set_color(0, 0, 0)
