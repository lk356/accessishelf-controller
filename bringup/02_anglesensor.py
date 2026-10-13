import smbus
import math
import time

# --- MPU-6500 CONFIGURATION ---
PWR_MGMT_1   = 0x6B
ACCEL_XOUT_H = 0x3B
ACCEL_YOUT_H = 0x3D
ACCEL_ZOUT_H = 0x3F

# Initialize I2C (Bus 1) and standard MPU address (0x68)
bus = smbus.SMBus(1)
DEVICE_ADDRESS = 0x68

# Offsets for our software tare
offset_pitch = 0.0
offset_roll = 0.0

def init_mpu():
    """Wakes up the MPU-6500."""
    try:
        # Write to power management register to wake it up
        bus.write_byte_data(DEVICE_ADDRESS, PWR_MGMT_1, 0)
        print("MPU-6500 Initialized.")
    except Exception as e:
        print(f"I2C Error: {e}")
        print("Check wiring and ensure the address is 0x68 (or 0x69).")
        exit(1)

def read_raw_data(addr):
    """Reads two bytes (high and low) and converts to a signed 16-bit integer."""
    high = bus.read_byte_data(DEVICE_ADDRESS, addr)
    low = bus.read_byte_data(DEVICE_ADDRESS, addr+1)
    
    # Combine high and low bytes
    value = ((high << 8) | low)
    
    # Get signed value (raw data is 16-bit two's complement)
    if value > 32768:
        value = value - 65536
    return value

def get_angles():
    """Reads raw accelerometer data and calculates Pitch and Roll in degrees."""
    accel_x = read_raw_data(ACCEL_XOUT_H)
    accel_y = read_raw_data(ACCEL_YOUT_H)
    accel_z = read_raw_data(ACCEL_ZOUT_H)
    
    # Prevent division by zero errors
    if accel_z == 0 and accel_x == 0:
        return 0.0, 0.0

    # Calculate pitch and roll using standard gravity vectors
    pitch = math.degrees(math.atan2(accel_y, math.sqrt(accel_x**2 + accel_z**2)))
    roll = math.degrees(math.atan2(-accel_x, accel_z))
    
    return pitch, roll

def tare_sensor():
    """Sets the current physical position as 0 degrees."""
    global offset_pitch, offset_roll
    print("Calibrating... Keep the arm still.")
    time.sleep(1)
    
    # Take an average of 10 readings for a clean tare
    p_total, r_total = 0, 0
    for _ in range(10):
        p, r = get_angles()
        p_total += p
        r_total += r
        time.sleep(0.01)
        
    offset_pitch = p_total / 10
    offset_roll = r_total / 10
    print(f"Tare Complete! Offsets -> Pitch: {offset_pitch:.1f}, Roll: {offset_roll:.1f}")

def main():
    init_mpu()
    tare_sensor()
    
    print("\nReading Angles. Press Ctrl+C to stop.")
    print("-" * 40)
    
    try:
        while True:
            raw_pitch, raw_roll = get_angles()
            
            # Apply our tare offsets
            rel_pitch = raw_pitch - offset_pitch
            rel_roll = raw_roll - offset_roll
            
            print(f"Pitch: {rel_pitch:6.1f}°  |  Roll: {rel_roll:6.1f}°", end='\r')
            time.sleep(0.05) # 20Hz update rate
            
    except KeyboardInterrupt:
        print("\nTest stopped.")

if __name__ == "__main__":
    main()
