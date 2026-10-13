import can
import struct
import time
import threading
import sys
import math
import evdev
from evdev import ecodes
import smbus
import pigpio 

# --- CONFIGURATION ---
M1_ID  = 1
PWM_PIN_M13 = 12 # GPIO 12 (Physical Pin 32) safely bypasses the Waveshare SPI pins

# Duty Cycle Command IDs
ARB_ID_DUTY_M1  = 0x02050080 | M1_ID  
ARB_ID_HEARTBEAT = 0x02052C80 

# --- MOTOR DIRECTION SETUP ---
M1_PULL_POWER  = -0.15  
M13_PULL_POWER = 0.15   
STOP_POWER     = 0.0      

# Active unspooling to overcome Spark MAX brake mode (Adjust these if it falls too fast/slow)
M1_UNSPOOL_POWER  = 0.02   
M13_UNSPOOL_POWER = -0.06  

# --- KINEMATIC LIMITS & HYSTERESIS ---
MAX_IN_ANGLE = 0.0       
MAX_DOWN_ANGLE = -114.0  

TRANSITION_DOWN = -21.0  
TRANSITION_UP   = -30.0  

# MPU6500 I2C Setup
MPU_ADDRESS = 0x68
PWR_MGMT_1 = 0x6B
ACCEL_XOUT_H = 0x3B

class ArmController:
    def __init__(self):
        self.running = True
        self.user_cmd = "STOP"  
        self.current_pitch = 0.0
        self.pitch_offset = 0.0
        self.raw_pitch_filtered = 0.0
        
        # --- HARDWARE PWM SETUP FOR M13 ---
        self.pi = pigpio.pi()
        if not self.pi.connected:
            print("ERROR: pigpio daemon not running.")
            print("Please run 'sudo pigpiod' in the terminal and try again.")
            sys.exit(1)
            
        # 1500 microseconds is perfect neutral for a Spark MAX
        self.pi.set_servo_pulsewidth(PWM_PIN_M13, 1500) 
        print(f"Hardware PWM for Motor 13 initialized on GPIO {PWM_PIN_M13}.")

        # --- CAN SETUP FOR M1 ---
        try:
            self.bus0 = can.interface.Bus(channel='can0', bustype='socketcan')
            print("CAN Bus (can0) connected successfully.")
        except Exception as e:
            print(f"CAN Init Error: {e}")
            sys.exit(1)

        self.imu_thread = threading.Thread(target=self._imu_loop)
        self.imu_thread.daemon = True
        self.imu_thread.start()
        
        self.motor_thread = threading.Thread(target=self._motor_loop)
        self.motor_thread.daemon = True
        self.motor_thread.start()

    def _init_imu(self):
        try:
            self.i2c_bus = smbus.SMBus(1)
            self.i2c_bus.write_byte_data(MPU_ADDRESS, PWR_MGMT_1, 0)
            time.sleep(0.5) 
            
            tare_sum = 0
            for _ in range(10):
                tare_sum += self._get_raw_pitch()
                time.sleep(0.05)
                
            self.pitch_offset = tare_sum / 10.0
            self.raw_pitch_filtered = self.pitch_offset
            print(f"MPU6500 Tared. 0° set at physical pitch: {self.pitch_offset:.1f}°")
            return True
        except Exception as e:
            print(f"MPU6500 Init Error: {e}")
            return False

    def _read_word_2c(self, reg):
        try:
            high = self.i2c_bus.read_byte_data(MPU_ADDRESS, reg)
            low = self.i2c_bus.read_byte_data(MPU_ADDRESS, reg + 1)
            val = (high << 8) + low
            if val >= 0x8000:
                return -((65535 - val) + 1)
            else:
                return val
        except:
            return 0

    def _get_raw_pitch(self):
        accel_x = self._read_word_2c(ACCEL_XOUT_H)
        accel_y = self._read_word_2c(ACCEL_XOUT_H + 2)
        accel_z = self._read_word_2c(ACCEL_XOUT_H + 4)
        
        if accel_x == 0 and accel_z == 0: return 0.0
        pitch_rad = math.atan2(accel_y, math.sqrt((accel_x * accel_x) + (accel_z * accel_z)))
        return math.degrees(pitch_rad)

    def _imu_loop(self):
        if not self._init_imu(): return
        while self.running:
            try:
                new_pitch = self._get_raw_pitch()
                self.raw_pitch_filtered = (0.8 * self.raw_pitch_filtered) + (0.2 * new_pitch)
                self.current_pitch = self.raw_pitch_filtered - self.pitch_offset
            except Exception: pass 
            time.sleep(0.02)

    def _send_can_duty_cycle(self, percent):
        data = struct.pack('<f', float(percent)) + b'\x00\x00\x00\x00'
        msg = can.Message(arbitration_id=ARB_ID_DUTY_M1, data=data, is_extended_id=True)
        try: self.bus0.send(msg)
        except can.CanError: pass

    def _send_can_heartbeat(self):
        msg = can.Message(arbitration_id=ARB_ID_HEARTBEAT, data=b'\x02\x00\x00\x00\x00\x00\x00\x00', is_extended_id=True)
        try: self.bus0.send(msg)
        except can.CanError: pass

    def _send_pwm_m13(self, power):
        """Converts -1.0 to 1.0 power into exactly 1000us to 2000us"""
        # 1500us = Neutral, 1000us = Full Reverse, 2000us = Full Forward
        pulse_width_us = int(1500 + (power * 500))
        # Clamp it just for safety
        pulse_width_us = max(1000, min(2000, pulse_width_us))
        self.pi.set_servo_pulsewidth(PWM_PIN_M13, pulse_width_us)

    def _motor_loop(self):
        while self.running:
            m1_out = STOP_POWER
            m13_out = STOP_POWER
            
            # --- HYSTERESIS STATE MACHINE ---
            if self.user_cmd == "UP":
                if self.current_pitch >= MAX_IN_ANGLE: 
                    m1_out, m13_out = STOP_POWER, STOP_POWER
                elif self.current_pitch < TRANSITION_UP: 
                    m1_out, m13_out = M1_PULL_POWER, M13_PULL_POWER
                else: 
                    m1_out, m13_out = STOP_POWER, M13_PULL_POWER

            elif self.user_cmd == "DOWN":
                if self.current_pitch <= MAX_DOWN_ANGLE:
                    m1_out, m13_out = STOP_POWER, STOP_POWER
                elif self.current_pitch > TRANSITION_DOWN:
                    m1_out, m13_out = M1_PULL_POWER, STOP_POWER
                else:
                    # Actively drive it down against the brake mode resistance
                    m1_out, m13_out = M1_UNSPOOL_POWER, M13_UNSPOOL_POWER

            # Send commands
            self._send_can_heartbeat()
            self._send_can_duty_cycle(m1_out)
            self._send_pwm_m13(m13_out)
            
            sys.stdout.write(f"\rPitch: {self.current_pitch:6.1f}° | Cmd: {self.user_cmd:4} | M1: {m1_out:5.2f} | M13: {m13_out:5.2f}    ")
            sys.stdout.flush()
            time.sleep(0.02) 

    def set_command(self, cmd_type):
        self.user_cmd = cmd_type

    def stop(self):
        self.user_cmd = "STOP"
        self.running = False
        time.sleep(0.1)
        # 0 stops the pulses entirely
        self.pi.set_servo_pulsewidth(PWM_PIN_M13, 0)
        self.pi.stop()

# --- REMOTE SETUP ---
def find_remote():
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    for device in devices:
        if "Consumer Control" in device.name: return device
    return None

def main():
    arm = ArmController()
    remote = find_remote()
    
    if not remote:
        print("\nRemote not found.")
        arm.stop()
        return

    print(f"\nConnected to {remote.name}")
    print("Ensure arm is in the FULL IN (0°) position before continuing.")
    print("-" * 50)
    
    try:
        remote.grab() 
        for event in remote.read_loop():
            if event.type == ecodes.EV_KEY:
                val = event.value
                code = event.code
                if code == 115: 
                    if val == 1: arm.set_command("UP")
                    elif val == 0: arm.set_command("STOP")
                elif code == 114: 
                    if val == 1: arm.set_command("DOWN")
                    elif val == 0: arm.set_command("STOP")
                elif code == 164: 
                    arm.set_command("STOP")

    except KeyboardInterrupt:
        pass
    finally:
        arm.stop()
        try: remote.ungrab()
        except: pass
        print("\nTerminated.")

if __name__ == "__main__":
    main()
