# uno_test.py - bench test of the Arduino RTC unit WITHOUT the ESP32, sensors or model.
# Run: python uno_test.py COM6     (COM6 = the port of the Arduino Uno)
import sys, time, serial

if len(sys.argv) != 2:
    sys.exit("usage: python uno_test.py COM6")
uno = serial.serial_for_url(sys.argv[1], 115200, timeout=0.3)
time.sleep(2)                          # the Uno restarts when the port opens


def ask(text, expect):
    uno.reset_input_buffer()
    uno.write((text + "\n").encode())
    time.sleep(0.4)
    reply = uno.read(4096).decode(errors="ignore").strip()
    print(f"\n>>> sent {text!r:28} EXPECT: {expect}\n    Uno says: {reply or '(nothing)'}")
    return reply


# the boot message was printed before we listened; resetting is not needed, TIME? proves the RTC works
r = ask("TIME?", "TIME <date and time>  (not ERR NO RTC)")
ok = r.startswith("TIME 2")
r = ask("REST", "EVT,<time>,REST");   ok &= r.startswith("EVT,") and r.endswith(",REST")
r = ask("REST", "(nothing: same word again is not a change)"); ok &= (r == "")
r = ask("OPEN", "EVT,<time>,OPEN");   ok &= r.endswith(",OPEN")
r = ask("FAULT", "EVT,<time>,FAULT"); ok &= r.endswith(",FAULT")
r = ask("garbage", "(nothing: unknown words are ignored)"); ok &= (r == "")
r = ask("SET 2026-10-17 12:00:00", "OK SET"); ok &= (r == "OK SET")
r = ask("TIME?", "TIME 2026-10-17 12:00:0x  (clock was just set)"); ok &= r.startswith("TIME 2026-10-17 12:00")
print("\nRESULT:", "ALL OK - now run python set_rtc.py to put the real time back" if ok
      else "SOMETHING DID NOT MATCH - check wiring (SDA=A4, SCL=A5, VCC=5V) and the sketch")
