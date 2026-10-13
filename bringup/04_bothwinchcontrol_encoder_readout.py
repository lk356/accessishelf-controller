import can
import struct
import time
import threading
import sys
import evdev
from evdev import ecodes

# --- CONFIGURATION ---
MOTOR_1_ID = 1
MOTOR_13_ID = 13

# Command CAN IDs
ARB_ID_DUTY_1  = 0x02050080 | MOTOR_1_ID
ARB_ID_DUTY_13 = 0x02050080 | MOTOR_13_ID
ARB_ID_HEARTBEAT = 0x02052C80 # Your working broadcast heartbeat

# Status CAN IDs (For reading position)
ARB_ID_POS_1  = 0x02052880 | MOTOR_1_ID
ARB_ID_POS_13 = 0x02052880 | MOTOR_13_ID

# --- POWER TUNING ---
# Tweak these for your temporary manual testing
PULL_POWER = 0.10
SLACK_POWER = -0.03
HOLD_POWER = 0.03   # 3% power to fight gravity when "Stopped"

class ShelfController:
    def __init__(self):
        self.running = True
        self.m1_cmd = 0.0
        self.m13_cmd = 0.0
        
        self.m1_pos = 0.0
        self.m13_pos = 0.0

        try:
            self.bus = can.interface.Bus(channel='can0', bustype='socketcan')
        except Exception as e:
            print(f"CAN Init Error: {e}")
            sys.exit(1)

        # Thread 1: Sends Commands
        self.send_thread = threading.Thread(target=self._send_loop)
        self.send_thread.daemon = True
        self.send_thread.start()

        # Thread 2: Listens for Position
        self.listen_thread = threading.Thread(target=self._listen_loop)
        self.listen_thread.daemon = True
        self.listen_thread.start()

    def _send_duty_cycle(self, arb_id, percent):
        data = struct.pack('<f', float(percent)) + b'\x00\x00\x00\x00'
        msg = can.Message(arbitration_id=arb_id, data=data, is_extended_id=True)
        try:
            self.bus.send(msg)
        except can.CanError:
            pass

    def _send_heartbeat(self):
        msg = can.Message(arbitration_id=ARB_ID_HEARTBEAT, 
                          data=b'\x02\x00\x00\x00\x00\x00\x00\x00', 
                          is_extended_id=True)
        try:
            self.bus.send(msg)
        except can.CanError:
            pass

    def _send_loop(self):
        while self.running:
            self._send_heartbeat()
            self._send_duty_cycle(ARB_ID_DUTY_1, self.m1_cmd)
            self._send_duty_cycle(ARB_ID_DUTY_13, self.m13_cmd)
            time.sleep(0.02)

    def _listen_loop(self):
        """Continuously reads the CAN bus to grab encoder data"""
        while self.running:
            try:
                msg = self.bus.recv(timeout=0.1)
                if not msg: continue

                # Unpack the first 4 bytes as a Float32
                if msg.arbitration_id == ARB_ID_POS_1:
                    self.m1_pos = struct.unpack('<f', msg.data[0:4])[0]
                elif msg.arbitration_id == ARB_ID_POS_13:
                    self.m13_pos = struct.unpack('<f', msg.data[0:4])[0]
                    
            except Exception:
                pass

    def print_telemetry(self):
        """Overwrites the same line in the terminal so it's easy to read"""
        sys.stdout.write(f"\r[POS] Motor 1: {self.m1_pos:>8.2f} rot | Motor 13: {self.m13_pos:>8.2f} rot   ")
        sys.stdout.flush()

    # --- MANUAL TEST COMMANDS ---
    def move_up(self):
        self.m1_cmd = PULL_POWER
        self.m13_cmd = PULL_POWER

    def move_down(self):
        self.m1_cmd = SLACK_POWER
        self.m13_cmd = 0.0 # Or whatever your Phase 1 down is

    def hold(self):
        self.m1_cmd = HOLD_POWER
        self.m13_cmd = HOLD_POWER

    def shutdown(self):
        self.m1_cmd = 0.0
        self.m13_cmd = 0.0
        self.running = False
        time.sleep(0.1)

# --- MAIN ---
def find_remote():
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    for device in devices:
        if "Consumer Control" in device.name: 
            return device
    return None

def main():
    shelf = ShelfController()
    remote = find_remote()
    
    if not remote:
        print("Remote not found. Ensure it is paired.")
        shelf.shutdown()
        return

    print("Telemetry Active. Move the shelf to calibrate.")
    remote.grab() 
    
    try:
        for event in remote.read_loop():
            # Print telemetry every time a button is pressed
            shelf.print_telemetry()
            
            if event.type == ecodes.EV_KEY:
                val = event.value
                code = event.code
                
                if code == 115: # VOL UP
                    if val == 1: shelf.move_up()
                    elif val == 0: shelf.hold()
                elif code == 114: # VOL DOWN
                    if val == 1: shelf.move_down()
                    elif val == 0: shelf.hold()
                elif code == 164: # PLAY/PAUSE
                    shelf.hold()

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        shelf.shutdown()
        try:
            remote.ungrab()
        except:
            pass

if __name__ == "__main__":
    main()
