import socket
import json


class GoveeLan:
    def __init__(self, ip_list):
        if not isinstance(ip_list, list) or not all(isinstance(ip, str) for ip in ip_list):
            raise ValueError(
                "Debe proporcionar una lista de IPs válidas (strings).")
        self.ips = ip_list
        self.brightness = 100
        self.is_on = True

    def _send_command(self, ip, command_dict):
        try:
            message = json.dumps(command_dict).encode("utf-8")
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.sendto(message, (ip, 4003))
            udp_socket.close()
        except Exception as e:
            print(f"[Error] al enviar comando a {ip}: {e}")

    def set_color(self, r, g, b, ip=None):
        target_ips = [ip] if ip else self.ips
        for addr in target_ips:
            command = {
                "msg": {
                    "cmd": "colorwc",
                    "data": {
                        "color": {"r": r, "g": g, "b": b},
                        "colorTemInKelvin": 0
                    }
                }
            }
            self._send_command(addr, command)

    def set_brightness(self, value):
        if not (0 <= value <= 100):
            raise ValueError("El brillo debe estar entre 0 y 100.")
        self.brightness = value
        for ip in self.ips:
            command = {
                "msg": {
                    "cmd": "brightness",
                    "data": {
                        "value": value
                    }
                }
            }
            self._send_command(ip, command)

    def set_state(self, on=True):
        self.is_on = on
        for ip in self.ips:
            command = {
                "msg": {
                    "cmd": "turn",
                    "data": {
                        "value": "on" if on else "off"
                    }
                }
            }
            self._send_command(ip, command)
