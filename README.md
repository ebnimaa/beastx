# Beast X Config

Standalone desktop app for configuring the **WL Mouse Beast X** (original wireless version).

No Python install needed — just download and run the binary for your OS from the [Releases](../../releases) page.

---

## Download

Go to **[Releases](../../releases)** and grab the latest build for your platform:

| Platform | File |
|---|---|
| Windows 10/11 | `BeastX-Windows.exe` |
| Linux | `BeastX-Linux` |
| macOS | `BeastX-macOS` |

---

## Features

- **Polling Rate** — 125 / 250 / 500 / 1000 / 2000 / 4000 Hz (sent directly to mouse)
- **Lift-Off Distance** — 1mm or 2mm (sent directly to mouse)
- **DPI Profiles** — up to 5 profiles, 50–26,000 DPI (saved locally)
- Settings persist between sessions (`~/.config/beastx/config.json`)
- Auto-reconnects on launch

---

## Platform Notes

### Windows
Just run `BeastX-Windows.exe`. If Windows Defender / SmartScreen shows a warning,
click **More info → Run anyway** (it's not signed with a paid certificate).

### Linux setup

The app needs permission to access the HID device without sudo.
Run this once:

```bash
echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="36a7", ATTRS{idProduct}=="a887", MODE="0666"' \
  | sudo tee /etc/udev/rules.d/99-beastx.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Then make the binary executable and run it:

```bash
chmod +x BeastX-Linux
./BeastX-Linux
```

### macOS
Right-click the app → **Open** the first time to bypass Gatekeeper.
Or run: `xattr -cr BeastX-macOS && ./BeastX-macOS`

---

## Hardware

| | |
|---|---|
| Mouse | WL Mouse Beast X (original, 2023) |
| Sensor | PixArt PAW3395 |
| MCU | Nordic nRF52840 |
| VID:PID | `36A7:A887` |

Protocol reverse-engineered from USB captures of the stock WL Mouse software.

---

## Build from source

```bash
pip install hid customtkinter pyinstaller
python build.py
```

Or just push to `main` — GitHub Actions builds all three platforms automatically.
