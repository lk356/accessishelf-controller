# Accessishelf Controller

Control software for **Accessishelf**, a retrofit, remote-controlled cabinet shelf that lowers itself to a seated user's reach. Built for an engineering design (EDD) capstone project.

Over 110 million Americans have limited vertical mobility, and a standard kitchen cabinet's lowest shelf starts around 54 in, above the 48 in ADA reach limit for wheelchair users. Accessishelf is meant to bring that shelf down to the user and put it back with one button on a Bluetooth remote.

## Photos of completed build
<img width="448" height="595" alt="signal-2026-10-13-00-45-57-051_002" src="https://github.com/user-attachments/assets/d8bf03ca-9bde-48f6-a40b-5188bd1fe980" />


## How it works

A Raspberry Pi Zero 2W runs a small Python program (`firmware/shelf_controller.py`) that:

1. Reads the arm angle from an **MPU-6500 accelerometer** over I2C. The angle is zeroed at startup, so power on with the arm fully in (0°).
2. Listens to a **Bluetooth media remote** (Volume Up = bring the shelf in, Volume Down = lower it, Play/Pause = stop).
3. Drives two **NEO brushless motors** through **REV Spark MAX** controllers using a state machine with hysteresis, so the two winch motors take over at different arm angles:

| Direction | Arm angle | Motor 1 (CAN) | Motor 13 (PWM) |
|---|---|---|---|
| Up | below -30° | pulls | pulls |
| Up | -30° to 0° | off | pulls |
| Down | 0° to -21° | pulls to keep tension | off |
| Down | -21° to -114° | slight unspool | unspool against brake mode |

Motor 1 is controlled over **CAN** (duty cycle plus a heartbeat frame, via a Waveshare 2-channel CAN HAT). Motor 13 is controlled with **servo-style PWM** on GPIO 12 using `pigpio`. The original design ran both motors over CAN (`archive/shelf_controller_dual_can.py`), but one CAN bus stopped working, so motor 13 was moved to PWM.

## Hardware

- Raspberry Pi Zero 2W + Waveshare 2-CH CAN HAT
- 2x NEO V1.1 brushless motors + 2x REV Spark MAX controllers
- MPU-6500 IMU (I2C, address `0x68`)
- Bluetooth remote
- 12 V 100 A power unit, 12 V to 5 V USB buck converter for the Pi
- 120 ohm termination resistors on the CAN bus

## Test results (from the project board)

- Remote operation: 100% pass rate over all extension/retraction test cycles
- Lifted and lowered payloads up to 15 lb
- Noise: 50-54 dB descending, 60-63 dB ascending
- Stored items shifted at most 36 mm and stayed upright

Full design process and results: [`docs/Accessishelf_Board_FINAL.pdf`](docs/Accessishelf_Board_FINAL.pdf)

## Setup and running

See [`docs/pi-setup.md`](docs/pi-setup.md) for the Raspberry Pi configuration (CAN HAT overlays, I2C, pigpio, Bluetooth pairing). Then:

```bash
pip install -r requirements.txt        # plus: sudo apt install python3-smbus
sudo pigpiod
sudo ip link set can0 up type can bitrate 1000000
python3 firmware/shelf_controller.py
```

Make sure the arm is fully in (0°) before starting. **Test with the load removed first** and keep a hand on the power switch.

## Repository layout

| Folder | What's in it |
|---|---|
| `firmware/` | The final controller that ran on the finished prototype |
| `bringup/` | Small scripts used to bring the system up step by step (see below) |
| `archive/` | The earlier controller with both motors over CAN |
| `docs/` | Project board and Pi setup notes |

Bring-up order: `01_cantest` (is anything talking on the CAN bus?), `02_anglesensor` (does the IMU read correctly?), `03_winchcontrol_single_motor` (one motor with the remote), `04_bothwinchcontrol_encoder_readout` (both motors, printing encoder positions, used to pick the angle thresholds).

## About this project

Accessishelf was a four-person engineering design capstone. The team built the physical shelf, did the research and surveys, and wrote the documentation together. This repository contains the control software, which I designed and wrote: the motor control, angle-sensor logic, CAN/PWM interface and remote integration.
