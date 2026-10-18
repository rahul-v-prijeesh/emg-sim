# set_rtc.py - sets the DS3231 clock on the Arduino to your laptop's current time.
# Run: python set_rtc.py COM6        (COM6 = the port of the Arduino Uno)
# Do this once after wiring the clock, and again if the Uno prints "RTC LOST POWER".
import sys, time, datetime, serial

if len(sys.argv) != 2:
    sys.exit("usage: python set_rtc.py COM6")
uno = serial.serial_for_url(sys.argv[1], 115200, timeout=2)
time.sleep(2)                         # the Uno restarts when the port opens
uno.reset_input_buffer()
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
uno.write(f"SET {now}\n".encode())
print("sent: SET", now)
print("Uno says:", uno.readline().decode(errors="ignore").strip() or "(nothing - wrong port or sketch?)")
uno.write(b"TIME?\n")
print("Uno says:", uno.readline().decode(errors="ignore").strip() or "(nothing)")
