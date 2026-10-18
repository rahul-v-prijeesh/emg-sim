# EMG gesture display - project files (v4.1, Arduino = RTC only)

Unzip so these files sit directly in `C:\emg_project`, then follow Part 4 of the guide
(venv, `pip install -r requirements.txt`).

## What changed from v4
The Arduino Uno is now **only the real-time clock (RTC) unit**. The failsafe (heartbeat watchdog,
E-STOP, LEDs, buzzer, SD log) is gone.

- Hardware: Uno + DS3231 module. VCC -> 5V, GND -> GND, SDA -> A4, SCL -> A5. Nothing else.
- Sketch: `arduino/rtc_uno/rtc_uno.ino` (needs the RTClib library by Adafruit).
- `live.py --rtc COM6` sends each recognised gesture to the Uno. When the gesture CHANGES the Uno
  replies with the RTC date/time, and live.py appends it to `gesture_log.csv`
  (columns: rtc_time, gesture). A sensor problem is logged as FAULT.
- `set_rtc.py COM6` sets the clock from your laptop time. `uno_test.py COM6` bench-tests the Uno.

## Files
| File | Use |
|---|---|
| arduino/esp32_plotter_test | look at the 3 sensors (Serial Plotter, 115200) |
| arduino/esp32_emg | 1000 samples/s stream (921600 baud) - used for recording and live |
| arduino/rtc_uno | Arduino RTC unit |
| arduino/esp32_wifi_emg | optional WiFi mode |
| emg_lib.py | shared helpers (EDIT ESP32_PORT) |
| make_fake_csv.py, record.py, plot_check.py | data |
| train_subsets.py, train_final.py | experiment and live model |
| set_rtc.py, uno_test.py, live.py | RTC setup, bench test, live screen |

## Quick software test (no hardware)
    python make_fake_csv.py
    python train_subsets.py emg_fake_day1.csv
    python train_final.py 0,1,2 emg_fake_day1.csv
    python live.py --demo

## RTC order of work
1. Wire the DS3231, upload rtc_uno.ino (board: Arduino Uno).
2. `python set_rtc.py COM6`  -> shows the current time.
3. `python uno_test.py COM6` -> all rows should match.
4. Real run: `python live.py --rtc COM6`, then open gesture_log.csv.

Status: the Python files were run on simulated data, including a simulated Uno. The .ino sketches
were not compiled and nothing was tested on real hardware.
