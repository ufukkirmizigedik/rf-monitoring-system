# RF Monitoring System

Real-time RF signal monitoring system built on **Raspberry Pi Zero 2W** + **HackRF One**.  
Designed as a commercial-grade embedded product with a fullscreen touchscreen GUI.

---

## Demo

[![Watch the demo](https://img.youtube.com/vi/70yDTlxS74c/0.jpg)](https://youtu.be/70yDTlxS74c)



## Features

- 📡 Real-time RF frequency scanning via `hackrf_sweep`
- 📈 Signal trend analysis (EWMA smoothing + consecutive rise detection)
- ⚡ GPIO relay control — triggers external output on signal detection
- 🖥️ Fullscreen touchscreen GUI (Python / Tkinter) — no keyboard needed
- 📊 Session statistics and 5-day history with CSV logging
- 🔐 Hardware-based license protection (Raspberry Pi serial number lock)
- 🔁 Auto-restart supervisor — recovers from process crashes automatically

---

## Hardware

| Component | Description |
|---|---|
| Raspberry Pi Zero 2W | Main controller, runs the full application |
| HackRF One | SDR receiver for RF scanning |
| GPIO Pin 17 | Relay output (open-drain, active LOW) |
| Touchscreen display | 7" or compatible, fullscreen UI |

---

## How It Works

```
HackRF → hackrf_sweep → Python parser → Signal tracker → Trend analysis → GPIO relay
                                                                  ↓
                                                           Tkinter GUI (live display)
                                                                  ↓
                                                           CSV history log
```

1. User sets target frequency ranges and detection thresholds via the settings screen
2. System scans the defined ranges continuously using HackRF
3. Each detected signal is tracked with EWMA filtering
4. If a signal rises **K times consecutively** above the threshold → relay triggers
5. Relay stays ON for a configurable hold time, then resets automatically

---

## Installation

```bash
# Install dependencies
pip install RPi.GPIO

# Install HackRF tools
sudo apt install hackrf

# Clone and run
git clone https://github.com/ufukkirmizigedik/rf-monitoring-system
cd rf-monitoring-system
python main.py
```

> **Note:** The hardware license protection (serial number lock) is disabled in this public version.  
> In the production build, the system checks the Raspberry Pi's CPU serial number at startup and exits if unauthorized.  
> To enable it, set `AUTHORIZED_SERIAL` in `main.py` to your device's serial number.

---

## Configuration

On startup, the settings screen allows you to configure:

| Parameter | Description |
|---|---|
| Frequency ranges | Up to 4 active scan ranges (MHz) |
| Threshold (dB) | Minimum signal power to track |
| Trend K | Number of consecutive rises to trigger relay |
| Relay hold (sec) | How long relay stays ON after trigger |

---

## Tech Stack

- **Python 3** — core application
- **Tkinter** — fullscreen GUI
- **HackRF / hackrf_sweep** — SDR scanning
- **RPi.GPIO** — relay control
- **Threading** — non-blocking scan + supervisor loop
- **CSV** — local history logging

---

## Project Status

✅ Fully functional  
✅ Tested on Raspberry Pi Zero 2W  
✅ Developed as a commercial product prototype

---

## Author

**Ufuk Kırмızıgedik**  
Electronics Engineer & Automation Developer  
📧 ufukkirmizigedik1984@gmail.com  
💬 Telegram: [@K_Ufuk](https://t.me/K_Ufuk)
