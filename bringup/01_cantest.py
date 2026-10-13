import can
import time

print("Checking CAN Bus connection...")
try:
    # Open the bus
    bus = can.interface.Bus(channel='can0', bustype='socketcan')
    print("Bus opened. Waiting for ANY message...")
    
    start = time.time()
    while time.time() - start < 10: # Listen for 10 seconds
        msg = bus.recv(timeout=1.0)
        if msg:
            print(f"Rx: ID={hex(msg.arbitration_id)}  Data={msg.data.hex()}")
        else:
            print("...")
            
except OSError:
    print("ERROR: Could not find 'can0'. Did you run the 'sudo ip link' command?")
except Exception as e:
    print(f"Error: {e}")
