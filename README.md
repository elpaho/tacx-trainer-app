# Tacx Neo 2T Smart Trainer App

PyQt6 desktop aplikacija za upravljanje i praćenje treninga na Tacx Neo 2T smart trenažeru putem Bluetooth BLE. Razvijena za Windows, testirana u stvarnim uvjetima treninga.

Trenutna verzija: **v2.06**

## Instalacija

```bash
pip install -r requirements.txt
python main.py
```

## Struktura projekta

```
tacx_app/
├── main.py                   # Entry point
├── main.pyw                  # Pokretanje bez Command Prompt prozora
├── requirements.txt
├── models/
│   └── data.py               # MetricsData, Workout, WorkoutInterval dataclassevi
├── ui/
│   └── main_window.py        # Cijeli PyQt6 UI — gaugeovi, paneli, logika
├── ble/
│   ├── trainer.py            # Tacx Neo 2T BLE (FE-C over BLE + CPS)
│   └── heartrate.py          # BLE pulsmetar (standardni HRS profil)
├── workout/
│   ├── parser.py             # ZWO, intervals.icu JSON i description parser
│   └── player.py             # Workout reprodukcija, interval tracking (wall clock)
└── intervals/
    ├── client.py             # intervals.icu API klijent, lokalno spremanje profila
    ├── settings_dialog.py    # Postavke dialog (intervals.icu, slope signal, zone)
    └── __init__.py
```

## BLE protokoli

| Protokol | UUID | Svrha |
|---|---|---|
| FE-C Service | `6e40fec1-...` | Tacx proprietary kontrola |
| FE-C Write (RX) | `6e40fec2-...` | PC → trenažer (ERG target, nagib) |
| FE-C Notify (TX) | `6e40fec3-...` | trenažer → PC (snaga, kadenca, brzina) |
| CPS | `0x1818` | Cycling Power Service (subscribe pri spajanju) |
| HRS | `0x180D` | Heart Rate Service (zasebni BLE uređaj) |

## Workout formati

- **ZWO** — Zwift `.zwo` XML format (`SteadyState`, `Intervals`, `Warmup`, `Cooldown`, `FreeRide`)
- **intervals.icu JSON** — direktno učitavanje iz kalendara
- **Description text** — slobodni tekst format koji koristi intervals.icu AI coach:
  - `- 20m 75% FTP` — steady state
  - `- 10m Ramp 55-75%` — ramp (auto Warmup/Cooldown ako prvi/zadnji bez naziva)
  - `- 20m 70-74% FTP @90rpm` — raspon → sredina; RPM iz opisa
  - `Main set 4x` — repeat blok
  - `@85rpm` / `85rpm` — kadenca direktno u intervalu

## Glavne funkcionalnosti

### Trening i upravljanje
- **ERG mod** — automatska regulacija otpora prema zadanoj snazi
- **Slope mod** — simulacija nagiba ceste; ručna korekcija nagiba ±0.5% u toku treninga
- **Interval evaluacija** — svaki interval se ocjenjuje (zelena/žuta/crvena) prema prosječnoj snazi
- **Auto-stop** s cooldown periodom pri nultoj snazi

### Vizualizacija
- **Arc gaugeovi** — snaga (s iglicom i lampicama), kadenca, puls
- **Zone barovi** — power i HR zone s time-in-zone praćenjem
- **Workout graf** — real-time prikaz snage i pulsa s interval barovima
- **Interval dot widgeti** — evaluacija prethodnih intervala u boji

### Kadenca
- Preporučeni range se određuje prema power zoni trenutnog intervala (iz postavki)
- Direktni RPM u opisu intervala (`@90rpm`) ima prioritet
- **Interpolacija zadnjih 10s** — range se lagano pomiče prema sljedećem intervalu
- Zvučni signal 10s prije kraja intervala i na početku novog

### intervals.icu integracija
- Automatsko učitavanje profila (FTP, HR max, power zone, HR zone) pri pokretanju
- Prikaz treninga iz kalendara za danas s učitavanjem jednim klikom
- **Lokalni profil (fallback)** — zone i kadenca se spremi lokalno; koristi se ako nema pristupa internetu

### Postavke (Postavke ↗ gumb)
- **intervals.icu** — Athlete ID i API key
- **Slope signal** — tolerancija za lampice (±W od referentne snage)
- **Zone** — FTP, HR max, 7 power zona (Od/Do/Kadenca), HR zone, kadenca tolerancija

## Lokalno spremanje profila

Konfiguracijska datoteka: `~/.tacx_app/intervals_config.json`

Sadrži intervals.icu credentials i `local_athlete` objekt s FTP, HR max, power i HR zonama (uključujući `cadence_rpm` po zoni) i `cadence_tolerance`. Automatski se ažurira pri svakom uspješnom spajanju s intervals.icu — kadenca po zonama se pritom **ne briše** nego mergea.

## Tehnički detalji

- Python 3.11+, PyQt6, Bleak (asyncio BLE), qasync
- Wall clock based workout player (ne tick counter) — otporno na zakašnjela UI ažuriranja
- Thread-safe Qt signali za BLE i intervals.icu callbackove
- Pokretanje bez terminala: `pythonw main.pyw`
