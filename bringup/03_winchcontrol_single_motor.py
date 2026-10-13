import can
import struct
import time
import threading
import sys
import evdev
from evdev import ecodes

# --- CONFIGURATION ---
DEVICE_ID = 1

# Duty Cycle Command ID (Base + Device ID)
ARB_ID_DUTY_CYCLE = 0x02050080 | DEVICE_ID  

# YOUR EXACT HEARTBEAT ID (Broadcast, no Device ID attached)
ARB_ID_HEARTBEAT  = 0x02052C80 

# Speed (Safe start: 0.15 = 15% Power)
UP_POWER   = 0.10     
DOWN_POWER = -0.10    
STOP_POWER = 0.0      

class WinchController:
    def __init__(self):
        self.running = True
        self.target_output = 0.0
        
        try:
            self.bus = can.interface.Bus(channel='can0', bustype='socketcan')
            print("CAN Bus connected.")
        except Exception as e:
            print(f"CAN Init Error: {e}")
            sys.exit(1)

        self.thread = threading.Thread(target=self._motor_loop)
        self.thread.daemon = True
        self.thread.start()

    def _send_duty_cycle(self, percent):
        """Sends Duty Cycle (Percent Voltage)"""
        data = struct.pack('<f', float(percent))
        data += b'\x00\x00\x00\x00' # Pad to 8 bytes
        
        msg = can.Message(
            arbitration_id=ARB_ID_DUTY_CYCLE,
            data=data,
            is_extended_id=True
        )
        try:
            self.bus.send(msg)
        except can.CanError as e:
            print(f"CAN Send Error (Duty): {e}")

    def _send_heartbeat(self):
        """Your exact original heartbeat"""
        msg = can.Message(
            arbitration_id=ARB_ID_HEARTBEAT,
            data=b'\x02\x00\x00\x00\x00\x00\x00\x00', # Restored to \x02
            is_extended_id=True
        )
        try:
            self.bus.send(msg)
        except can.CanError as e:
            print(f"CAN Send Error (Heartbeat): {e}")

    def _motor_loop(self):
        while self.running:
            self._send_heartbeat()
            self._send_duty_cycle(self.target_output)
            time.sleep(0.02) 

    def set_command(self, cmd_type):
        if cmd_type == "UP":
            self.target_output = UP_POWER
            print(f">> UP ({UP_POWER*100}%)")
        elif cmd_type == "DOWN":
            self.target_output = DOWN_POWER
            print(f">> DOWN ({DOWN_POWER*100}%)")
        elif cmd_type == "STOP":
            self.target_output = STOP_POWER
            print(f">> STOP")

    def stop(self):
        self.target_output = 0.0
        self.running = False
        time.sleep(0.1)

# --- REMOTE SETUP ---
def find_remote():
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    for device in devices:
        if "Consumer Control" in device.name: 
            return device
    return None

def main():
    winch = WinchController()
    remote = find_remote()
    
    if not remote:
        print("Remote not found. Is it paired via Bluetooth?")
        winch.stop()
        return

    print(f"Connected to {remote.name}")
    print("Press Volume Up/Down to move. Play to Stop.")
    
    try:
        remote.grab() 
        for event in remote.read_loop():
            if event.type == ecodes.EV_KEY:
                val = event.value
                code = event.code
                
                # 115 = VOL UP, 114 = VOL DOWN, 164 = PLAY/PAUSE
                if code == 115: 
                    if val == 1: winch.set_command("UP")
                    elif val == 0: winch.set_command("STOP")
                elif code == 114: 
                    if val == 1: winch.set_command("DOWN")
                    elif val == 0: winch.set_command("STOP")
                elif code == 164: 
                    winch.set_command("STOP")

    except KeyboardInterrupt:
        print("\nStopping...")
    except OSError:
        print("Remote disconnected.")
    finally:
        winch.stop()
        try:
            remote.ungrab()
        except:
            pass

if __name__ == "__main__":
    main()

