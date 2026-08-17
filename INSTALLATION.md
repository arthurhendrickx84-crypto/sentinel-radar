# Sentinel Radar - Installation Guide

Complete step-by-step guide to install and run Sentinel Radar on Raspberry Pi.

---

## 📋 Requirements

### Hardware
- **Raspberry Pi 4** or **Raspberry Pi 5** (recommended: 4GB RAM minimum)
- **RTL-SDR USB Dongle** (~€25-40)
  - NooElec NESDR or RTL-SDR.COM v3
- **Dipole Antenna** (included with dongle or ~€10)
- **Raspberry Pi Camera Module** (official or USB webcam)
- **LCD Display** (3.5"-7" SPI or HDMI)
- **Power Supply** (5V 3A minimum)
- **microSD Card** (16GB minimum)

### Software
- Raspberry Pi OS (Bullseye or Bookworm)
- Python 3.8+
- pip3 package manager

---

## 🔧 Step 1: Prepare Raspberry Pi OS

### 1.1 Flash OS to microSD Card
1. Download **Raspberry Pi Imager** from https://www.raspberrypi.com/software/
2. Use Imager to write **Raspberry Pi OS (64-bit)** to microSD card
3. Insert card into Raspberry Pi and boot

### 1.2 Initial Configuration
```bash
# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Enable interfaces
sudo raspi-config
# Navigate to: Interfacing Options → Enable Camera, I2C, SPI
```

---

## 📦 Step 2: Install Dependencies

### 2.1 System-level packages
```bash
# Install build tools and libraries
sudo apt-get install -y \
    build-essential \
    python3-pip \
    python3-dev \
    libopencv-dev \
    python3-opencv \
    libjasper-dev \
    libtiff5 \
    libjasper1 \
    libharfbuzz0b \
    libwebp6 \
    libtiff5 \
    libjasper1 \
    libatlas-base-dev \
    libjasper-dev \
    libharfbuzz0b \
    libwebp6 \
    libopenjp2-7 \
    libtiff5

# Install RTL-SDR drivers
sudo apt-get install -y \
    rtl-sdr \
    librtlsdr-dev \
    librtlsdr0

# Install audio libraries
sudo apt-get install -y \
    libasound2-dev \
    portaudio19-dev \
    libportaudio2

# Install GPIO libraries
sudo apt-get install -y \
    python3-rpi.gpio \
    python3-smbus \
    i2c-tools
```

### 2.2 Fix potential conflicts
```bash
# If you get conflicts with libopencv, use this:
sudo apt-get install --no-install-recommends -y python3-opencv
```

---

## 🚀 Step 3: Clone & Install Sentinel Radar

### 3.1 Download Repository
```bash
# Create workspace
mkdir -p ~/projects
cd ~/projects

# Clone repository
git clone https://github.com/arthurhendrickx84-crypto/sentinel-radar.git
cd sentinel-radar
```

### 3.2 Create Virtual Environment (Recommended)
```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate
```

### 3.3 Install Python Dependencies
```bash
# Upgrade pip
pip3 install --upgrade pip setuptools wheel

# Install requirements
pip3 install -r requirements.txt
```

### 3.4 Handle PyAudio Separately
PyAudio needs special handling on Raspberry Pi:
```bash
# Install PyAudio with pre-built wheels
pip3 install PyAudio

# If that fails, build from source:
pip3 install --no-cache-dir PyAudio
```

---

## ⚙️ Step 4: Configure Hardware

### 4.1 RTL-SDR Dongle
```bash
# Test SDR connection
rtl_test -t

# Output should show device found
# If it fails, check USB connection or try:
sudo chmod 666 /dev/bus/usb/*/*
```

### 4.2 Camera Module
```bash
# List connected cameras
ls -la /dev/video*

# Test camera
python3 -c "import cv2; cap = cv2.VideoCapture(0); print('Camera OK' if cap.isOpened() else 'Camera FAIL')"
```

### 4.3 LCD Display (SPI)
For 3.5" or 7" SPI display:

```bash
# Enable SPI
sudo raspi-config
# Interface Options → SPI → Enable

# Test I2C/SPI
i2cdetect -y 1
```

---

## 📝 Step 5: Configuration

### 5.1 Edit Settings
```bash
# Edit display settings for your Raspberry Pi
nano config/settings.json
```

**For SPI LCD Display:**
```json
{
  "display": {
    "type": "spi",
    "width": 480,
    "height": 320,
    "fps": 30
  }
}
```

**For HDMI Monitor:**
```json
{
  "display": {
    "type": "hdmi",
    "width": 1920,
    "height": 1080,
    "fps": 30
  }
}
```

### 5.2 Select Country
```bash
# Edit frequencies for your country
nano config/frequencies.json
# Supported: nl (Netherlands), de (Germany), be (Belgium)
```

---

## ▶️ Step 6: Run Sentinel Radar

### 6.1 Test Run
```bash
# Activate virtual environment (if used)
source venv/bin/activate

# Run with debug output
python3 main.py --country nl --debug
```

### 6.2 Full Command Options
```bash
python3 main.py \
  --country nl \
  --distance-threshold 500 \
  --camera 0 \
  --display terminal \
  --debug
```

**Options:**
- `--country` - nl, de, be (default: nl)
- `--distance-threshold` - Alert distance in meters (default: 500)
- `--camera` - Camera device ID (default: 0)
- `--display` - terminal, hdmi, spi (default: terminal)
- `--debug` - Enable debug logging

---

## 🔄 Step 7: Autostart on Boot (Optional)

### 7.1 Create Systemd Service
```bash
# Create service file
sudo nano /etc/systemd/system/sentinel-radar.service
```

Paste this content:
```ini
[Unit]
Description=Sentinel Radar - RF Police Detection
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/projects/sentinel-radar
Environment="PATH=/home/pi/projects/sentinel-radar/venv/bin"
ExecStart=/home/pi/projects/sentinel-radar/venv/bin/python3 main.py --country nl --display spi
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 7.2 Enable Service
```bash
# Enable and start
sudo systemctl enable sentinel-radar
sudo systemctl start sentinel-radar

# Check status
sudo systemctl status sentinel-radar

# View logs
sudo journalctl -u sentinel-radar -f
```

---

## 🐛 Troubleshooting

### RTL-SDR Not Detected
```bash
# Check USB devices
lsusb | grep RTL

# Test SDR
rtl_test -t

# Fix permissions
sudo usermod -a -G dialout pi
sudo usermod -a -G plugdev pi
```

### Camera Not Working
```bash
# Check if enabled in raspi-config
vcgencmd get_camera

# List cameras
libcamera-hello

# Check OpenCV camera support
python3 -c "import cv2; print(cv2.getBuildInformation())" | grep Camera
```

### Audio/Sound Not Playing
```bash
# List audio devices
arecord -l
pactl list short sinks

# Test audio
speaker-test -t wav -c 2
```

### Display Issues
```bash
# For SPI display, check I2C
i2cdetect -y 1

# Check SPI enabled
ls -la /dev/spidev*

# Test display initialization
python3 -c "from src.display_handler import DisplayHandler; d = DisplayHandler('spi'); print('Display OK')"
```

### Python Import Errors
```bash
# Make sure you're in virtual environment
source venv/bin/activate

# Reinstall packages
pip3 install -r requirements.txt --force-reinstall
```

---

## 📊 Performance Tips

1. **Reduce Camera Resolution** (if slow)
   ```json
   "camera": {
     "width": 320,
     "height": 240,
     "fps": 15
   }
   ```

2. **Increase Scan Interval** (to reduce CPU)
   Edit `main.py` line ~190:
   ```python
   scan_interval = 1.0  # Scan every 1 second instead of 0.5
   ```

3. **Disable Motion Detection** (if not needed)
   In `main.py`, comment out motion detection section

4. **Disable Video Display** (runs faster)
   ```bash
   python3 main.py --display terminal
   ```

---

## 📚 Additional Resources

- **RTL-SDR Documentation**: https://www.rtl-sdr.com/
- **Raspberry Pi Docs**: https://www.raspberrypi.com/documentation/
- **OpenCV Python**: https://docs.opencv.org/master/d6/d00/tutorial_py_root.html
- **PyAudio Documentation**: https://people.csail.mit.edu/hubert/pyaudio/

---

## 🆘 Support

If you encounter issues:

1. Check the logs: `tail -f ~/projects/sentinel-radar/*.log`
2. Enable debug mode: `python3 main.py --debug`
3. Check system resources: `htop`
4. Verify all hardware connections
5. Test individual components with provided test scripts

---

**Happy scanning! 📡** 🚨
