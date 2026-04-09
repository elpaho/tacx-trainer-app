# Tacx Neo 2T Controller

PyQt6 aplikacija za upravljanje Tacx Neo 2T smart trenažerom via Bluetooth BLE.

## Instalacija

```bash
pip install -r requirements.txt
```

## Pokretanje

```bash
cd tacx_app
python main.py
```

## Struktura projekta

```
tacx_app/
├── main.py                 # Entry point
├── requirements.txt
├── models/
│   └── data.py             # MetricsData, Workout, WorkoutInterval
├── ui/
│   └── main_window.py      # PyQt6 glavni prozor
├── ble/
│   ├── trainer.py          # Tacx Neo 2T BLE (FE-C over BLE)
│   └── heartrate.py        # BLE pulsmetar (standardni HRS)
├── workout/
│   ├── parser.py           # ZWO format parser
│   └── player.py           # Workout reprodukcija, interval tracking
└── simulator/
    └── simulator.py        # Simulator za razvoj bez trenažera
```

## Protokoli

| Protokol | UUID | Svrha |
|---|---|---|
| FE-C Service | `6e40fec1-...` | Tacx proprietary kontrola |
| FE-C Write (RX) | `6e40fec2-...` | PC → trenažer (ERG, nagib) |
| FE-C Notify (TX) | `6e40fec3-...` | trenažer → PC (snaga, kadenca) |
| CPS | `0x1818` | Cycling Power Service |
| HRS | `0x180D` | Heart Rate Service |

## Workout format (ZWO)

Aplikacija podržava standardni Zwift .zwo format:
- `SteadyState` — fiksna snaga (ERG mod)
- `Intervals` — repeating on/off intervali
- `Warmup` / `Cooldown` — ramping segmenti
- `FreeRide` — simulacija nagiba

## Sljedeći koraci

- [ ] Implementirati asyncio BLE skeniranje u UI-u (qasync)
- [ ] FE-C checksum validacija primljenih poruka
- [ ] Export podataka (FIT format)
- [ ] Settings dijalog (FTP, težina vozača)
