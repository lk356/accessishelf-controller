# Raspberry Pi setup

> **Reconstructed, not copied from the original Pi.** The original config files were lost, so this is worked out from what the scripts expect. Items marked **(verify)** were not checked against real hardware. If you still have the old SD card, compare against `/boot/firmware/config.txt` (or `/boot/config.txt`), `~/.bash_history`, `/etc/rc.local` and `crontab -l`.

## 1. Enable SPI, I2C and the CAN HAT

Edit `/boot/firmware/config.txt` (older OS images: `/boot/config.txt`) and add:

```
dtparam=spi=on
dtparam=i2c_arm=on
dtoverlay=mcp2515-can1,oscillator=16000000,interrupt=25
dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=23
```

(verify) The oscillator and interrupt values are the Waveshare 2-CH CAN HAT defaults. Check them against the Waveshare wiki for your HAT version. Reboot afterwards.

## 2. Install packages

```bash
sudo apt install python3-can python3-evdev python3-smbus python3-pigpio pigpio can-utils i2c-tools
sudo systemctl enable --now pigpiod      # needed for the PWM motor
```

Or use `pip install -r requirements.txt` for the Python packages (on newer Raspberry Pi OS add `--break-system-packages`, or use a virtual environment). The code does `import smbus`, which comes from the apt package `python3-smbus` rather than pip, so install that one with apt either way.

## 3. Bring up the CAN interface

The scripts do not do this themselves. It had to be run after every boot (or put in a startup script):

```bash
sudo ip link set can0 up type can bitrate 1000000
sudo ip link set can1 up type can bitrate 1000000   # only for the dual-CAN version in archive/
```

Check with `candump can0`, or run `bringup/01_cantest.py`.

## 4. Wiring

- Motor 1 Spark MAX: CAN bus 0 (CAN H / CAN L) from the HAT, CAN ID 1.
- Motor 13 Spark MAX: PWM signal from **GPIO 12 (physical pin 32)**, ground shared with the Pi. (verify)
- MPU-6500: I2C bus 1 (SDA GPIO 2, SCL GPIO 3), address `0x68`. Confirm with `i2cdetect -y 1`. The code uses the Y axis against X and Z for pitch, so mounting orientation matters.
- 120 ohm termination at both ends of the CAN bus.
- Power: 12 V supply to both Spark MAX units, buck converter to 5 V for the Pi.

## 5. Spark MAX settings (stored on the controllers, not the Pi)

These were set with the REV Hardware Client over USB and live in the controllers' memory, not in any file here:

- CAN ID 1 on the CAN-controlled motor (and 13 on the other, in the dual-CAN version)
- Brake mode. The controller code works around it with the "unspool" power values.
- Speed and current limits (to prevent rope tangling)
- (verify) PWM input mode on the motor 13 controller

## 6. Pair the Bluetooth remote

```bash
bluetoothctl
  scan on
  pair <remote MAC address>
  trust <remote MAC address>
  connect <remote MAC address>
```

The program finds the remote by looking for an input device with "Consumer Control" in its name. Key codes used: 115 (Volume Up), 114 (Volume Down), 164 (Play/Pause). The program grabs the device exclusively, so the remote will not also change the Pi's volume.

## 7. Run

```bash
python3 firmware/shelf_controller.py
```

with the arm fully in, as the angle sensor is zeroed at startup. Stop with Ctrl+C.
