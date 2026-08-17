# Sentinel Radar 📡

**RF-based Police Proximity Alert System with Motion Detection**

A Python application that detects police radio signals using Software Defined Radio (SDR) and estimates distance via RSSI (Received Signal Strength Indicator). Alerts you when police are detected within 500 meters, with visual indicators that intensify as they get closer.

## Features

- 🎯 **Police Detection**: Scans police frequencies via RTL-SDR
- 📏 **Distance Estimation**: RSSI-based distance calculation (500m - 20m)
- 💡 **Progressive Alerts**: Visual indicator lights at 500m, 400m, 300m, 200m, 100m, 20m
- 🔊 **Audio Alert**: Sound notification when police detected
- 📹 **Motion Detection**: OpenCV-based movement detection overlay
- 🗺️ **Multi-Country Support**: Configurable frequency profiles (NL, DE, BE, FR, etc.)
- 📱 **Display Integration**: Raspberry Pi LCD screen support

## Hardware Requirements

- **Raspberry Pi 4 or 5**
- **RTL-SDR USB Dongle** (~€25-40)
  - Popular options: NooElec NESDR, RTL-SDR.COM v3
- **Dipole Antenna** or external antenna
- **Raspberry Pi Camera Module** (official or USB webcam)
- **LCD Display** (3.5" to 7" SPI/HDMI)
- **Power Bank or USB Power Supply**

## Software Requirements

```bash
Python 3.8+
OpenCV (cv2)
rtl-sdr drivers
pyaudio (for sound alerts)
```

## Installation

### 1. Clone Repository
```bash
git clone https://github.com/arthurhendrickx84-crypto/sentinel-radar.git
cd sentinel-radar
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Install RTL-SDR Drivers
**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install rtl-sdr librtlsdr-dev
```

**Raspberry Pi:**
```bash
sudo apt-get update
sudo apt-get install rtl-sdr librtlsdr-dev
```

### 4. Configure Country & Frequencies
Edit `config/frequencies.json` and select your country:
- `nl` - Netherlands
- `de` - Germany
- `be` - Belgium

## Usage

```bash
python main.py --country nl --distance-threshold 500
```

### Command Line Options
```
--country          Country code (nl, de, be, fr, etc.)
--distance-threshold  Alert distance in meters (default: 500)
--camera           Camera device (default: 0)
--display          Display type (hdmi, spi, terminal)
--debug            Enable debug output
```

## How It Works

### 1. Radio Signal Detection
- Continuously scans police frequencies for your region
- Measures signal strength (RSSI) in dBm

### 2. Distance Estimation
RSSI to Distance Formula:
```
Distance (m) = 10 ^ ((TxPower - RSSI) / (20 * N))
```
Where:
- TxPower = Known transmitter power (~30 dBm for police)
- RSSI = Measured signal strength
- N = Path loss exponent (~2.0 for open space)

### 3. Alert Levels
```
500m → 1 indicator light
400m → 2 indicator lights
300m → 3 indicator lights
200m → 4 indicator lights
100m → 5 indicator lights
20m  → 6 indicator lights + LOUD ALARM
```

### 4. Motion Detection
- OpenCV continuously analyzes camera feed
- Overlays detected motion on display
- Helps identify what triggered the alert

## Project Structure

```
sentinel-radar/
├── main.py                 # Main application
├── requirements.txt        # Python dependencies
├── config/
│   ├── frequencies.json    # Frequency profiles by country
│   └── settings.json       # App configuration
├── src/
│   ├── sdr_handler.py     # RTL-SDR interface
│   ├── motion_detector.py # OpenCV motion detection
│   ├── alert_system.py    # Alert & indicator logic
│   └── display_handler.py # LCD/screen output
├── data/
│   └── sounds/            # Alert sound files
└── docs/
    └── SETUP.md           # Detailed setup guide
```

## Frequency Ranges (Netherlands)

Police use various frequencies in the Netherlands:
- DMR Tier III: 400-470 MHz
- P25 / Tetra: 410-430 MHz
- PMR446: 446-447 MHz

See `config/frequencies.json` for full frequency list.

## Troubleshooting

### RTL-SDR Not Detected
```bash
lsusb | grep RTL
rtl_test -t
```

### No Signal Found
- Check antenna connection
- Verify correct country/frequencies
- Move antenna to window
- Check for interference

### LCD Display Not Working
- Verify I2C/SPI connection
- Check display configuration in `config/settings.json`
- Run display test: `python tests/test_display.py`

## Legal Notice ⚖️

This tool is for **educational and personal use only**. 

- **Police frequencies** are public and monitored legally in most countries
- Check your local laws regarding RF reception and monitoring
- Do not interfere with police communications
- Use responsibly and ethically

## Contributing

Feel free to submit issues, fork, and create pull requests for any improvements.

## License

MIT License - See LICENSE file for details

---

**Made with ❤️ for security-conscious developers** 🛡️
