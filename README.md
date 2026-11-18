# Govee Light Engine

Controlador modular de iluminación Govee desarrollado en Python. Diseñado para controlar dispositivos, consultar su estado, realizar diagnósticos y recopilar estadísticas desde línea de comandos.

La arquitectura permite incorporar posteriormente una interfaz gráfica, sincronización por BPM, Rekordbox/Ableton Link y dispositivos DMX sin modificar el núcleo del sistema.

## Requisitos

* Python 3.10+
* macOS, Linux o Windows
* Cuenta Govee
* Govee API Key
* Conexión a Internet

## Instalación

Crear el entorno virtual:

```bash
python3 -m venv .venv
```

Activarlo en macOS/Linux:

```bash
source .venv/bin/activate
```

Instalar dependencias:

```bash
pip install -r requirements.txt
```

## Configuración

Crear `.env` a partir del ejemplo:

```bash
cp .env.example .env
```

Editar `.env`:

```env
GOVEE_API_KEY=TU_API_KEY
```

> No subir `.env` a Git. El archivo ya está incluido en `.gitignore`.

### Variables de entorno

| Variable        | Requerida | Descripción                         |
| --------------- | --------- | ----------------------------------- |
| `GOVEE_API_KEY` | Sí        | API Key de Govee Developer Platform |

---

# Uso

Todos los comandos utilizan:

```bash
python -m light_engine <comando>
```

## Dispositivos

### Listar dispositivos

```bash
python -m light_engine devices
```

Muestra los dispositivos disponibles, modelo y cantidad de capacidades.

### Ver capacidades

```bash
python -m light_engine capabilities "<dispositivo>"
```

Ejemplo:

```bash
python -m light_engine capabilities "Rope Cuarto David"
```

Permite conocer funciones disponibles como:

* Encendido/apagado
* Brillo
* RGB
* Temperatura de color
* Segmentos
* Escenas
* Music Mode

---

# Estado y diagnóstico

## Status

Consulta el estado actual de un dispositivo.

```bash
python -m light_engine status "<dispositivo>"
```

Ejemplo:

```bash
python -m light_engine status "Rope Cuarto David"
```

Incluye:

* Estado online/offline
* Latencia
* Encendido
* Brillo
* Estados disponibles

Para mostrar la respuesta completa de Govee:

```bash
python -m light_engine status "Rope Cuarto David" --raw
```

## Health

Realiza varias pruebas de conexión.

```bash
python -m light_engine health "<dispositivo>"
```

Por defecto realiza 3 pruebas.

Cambiar cantidad:

```bash
python -m light_engine health "Rope Cuarto David" --samples 5
```

Muestra:

* Pruebas exitosas
* Pruebas fallidas
* Porcentaje de éxito
* Estado online
* Latencia promedio
* Latencia mínima
* Latencia máxima

`--samples` acepta valores de `1` a `10`.

## Doctor

Diagnóstico general de todos los dispositivos.

```bash
python -m light_engine doctor
```

Ejemplo de resultado:

```text
OK   Rope Cuarto David      H61D5   online    170 ms
OK   Rope Cuarto David 2    H61D5   online    185 ms
FAIL Luz B1                 H61A0   offline   -
```

La prueba es **read-only** y no modifica las luces.

---

# Estadísticas

Las pruebas realizadas se almacenan localmente en:

```text
data/stats.jsonl
```

Consultar estadísticas:

```bash
python -m light_engine stats
```

Consultar un dispositivo:

```bash
python -m light_engine stats "Rope Cuarto David"
```

Incluye:

* Número de muestras
* Porcentaje de éxito
* Latencia promedio
* Latencia mínima/máxima
* Último estado online conocido

---

# Control de dispositivos

Todos los controles utilizan:

```bash
python -m light_engine action "<dispositivo>" <acción> [valores]
```

## Encender

```bash
python -m light_engine action "Rope Cuarto David" on
```

## Apagar

```bash
python -m light_engine action "Rope Cuarto David" off
```

## Brillo

```bash
python -m light_engine action "Rope Cuarto David" brightness 50
```

Rango:

```text
0 - 100
```

## Color RGB

```bash
python -m light_engine action "Rope Cuarto David" color 255 0 80
```

Formato:

```text
color <R> <G> <B>
```

Cada componente acepta:

```text
0 - 255
```

Ejemplos:

```bash
# Rojo
python -m light_engine action "Rope Cuarto David" color 255 0 0

# Verde
python -m light_engine action "Rope Cuarto David" color 0 255 0

# Azul
python -m light_engine action "Rope Cuarto David" color 0 0 255

# Blanco
python -m light_engine action "Rope Cuarto David" color 255 255 255
```

---

# Escenas DIY

Syncronia permite consultar y ejecutar escenas DIY de un dispositivo que exponga la capacidad `diyScene` en la API de Govee.

Consultar las escenas DIY disponibles:

```bash
python -m light_engine scenes "Rope Cuarto David" --instance diyScene
```

Ejecutar una escena por nombre:

```bash
python -m light_engine scenes "Rope Cuarto David" \
  --instance diyScene \
  --invoke-by-name diyScene "Nombre de la escena"
```

La búsqueda por nombre no distingue mayúsculas y minúsculas. El dispositivo debe estar conectado a la cuenta Govee configurada en `.env` y ser compatible con escenas DIY.

**Alcance actual:** consulta y ejecución sobre un dispositivo por comando. La ejecución coordinada en dos luces del mismo modelo todavía está pendiente; no se debe asumir sincronización simultánea entre dispositivos.

---

# Referencia rápida

| Categoría                | Comando                        |
| ------------------------ | ------------------------------ |
| Dispositivos             | `devices`                      |
| Capacidades              | `capabilities <device>`        |
| Estado                   | `status <device>`              |
| Estado completo          | `status <device> --raw`        |
| Salud                    | `health <device>`              |
| Pruebas                  | `health <device> --samples N`  |
| Diagnóstico general      | `doctor`                       |
| Estadísticas             | `stats`                        |
| Estadísticas dispositivo | `stats <device>`               |
| Encender                 | `action <device> on`           |
| Apagar                   | `action <device> off`          |
| Brillo                   | `action <device> brightness N` |
| RGB                      | `action <device> color R G B`  |

---

# Arquitectura

```text
light_engine/
├── cli.py
├── controller.py
├── device_registry.py
├── diagnostics.py
├── govee_client.py
├── models.py
├── stats.py
└── errors.py
```

### `cli.py`

Interfaz de línea de comandos.

### `controller.py`

Acciones de iluminación.

### `device_registry.py`

Descubrimiento y resolución de dispositivos.

### `diagnostics.py`

Estado, conectividad y pruebas.

### `govee_client.py`

Comunicación con Govee API.

### `models.py`

Modelos internos de datos.

### `stats.py`

Registro y procesamiento de estadísticas.

### `errors.py`

Errores específicos del sistema.

---

# Solución de problemas

### API Key no configurada

```text
ERROR: set GOVEE_API_KEY first.
```

Verificar `.env`:

```env
GOVEE_API_KEY=TU_API_KEY
```

### Dispositivo no encontrado

Ejecutar:

```bash
python -m light_engine devices
```

y utilizar el nombre mostrado.

### Nombre ambiguo

Si varios dispositivos coinciden con el texto introducido, utiliza el nombre completo.

### Revisar problemas generales

Ejecutar:

```bash
python -m light_engine doctor
```

Después comprobar específicamente el dispositivo:

```bash
python -m light_engine health "<dispositivo>" --samples 5
```

---

# Roadmap

Funciones previstas:

* Control RGB por segmentos
* Control de brillo por segmentos
* Listado y ejecución de escenas DIY en un dispositivo
* Ejecución coordinada de escenas DIY en dos luces del mismo modelo
* Motor de efectos
* Sincronización por BPM
* Integración Rekordbox / Ableton Link
* Control DMX
* Aliases de dispositivos
* Caché de dispositivos y escenas
* Interfaz gráfica
* Monitoreo y recuperación automática ante fallos
