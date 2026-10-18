# Sensor simulator (no hardware needed)

Two programs pretend to be your hardware. Your normal scripts connect to them over a local network
port instead of a COM port, so no drivers and no virtual COM ports are needed.

| Program | Pretends to be | Address |
|---|---|---|
| `sim_esp32.py` | ESP32 + 3 EMG sensors (1000 lines/s, same format as `esp32_emg.ino`) | `socket://127.0.0.1:7001` |
| `sim_uno.py` | Arduino Uno + DS3231 RTC (same commands/replies as `rtc_uno.ino`) | `socket://127.0.0.1:7002` |

The signal is **simulated** (band-limited noise whose strength depends on the gesture). It checks that
the software works. It says nothing about how well EMG works on a real arm.

## 1. One-command check

    python sim_selftest.py

About 2 minutes. It works in a temporary folder (your own files are not touched) and checks:
uno_test.py, set_rtc.py, a full record.py session, plot_check.py, train_subsets.py, train_final.py,
and the real live.py (gesture changes, an unplugged sensor, RTC-stamped gesture_log.csv).
It ends with `18/18 checks passed`.

## 2. Try it by hand

**Record a full session (about 25 seconds):**

    python sim_esp32.py --run-record sim 1 --speed 20
    python plot_check.py emg_sim_day1.csv
    python train_subsets.py emg_sim_day1.csv
    python train_final.py 0,1,2 emg_sim_day1.csv

**Live screen, you control the "muscle"** (3 terminals, all in the project folder):

    Terminal 1:  python sim_esp32.py
    Terminal 2:  python sim_uno.py
    Terminal 3 (Windows cmd):    set EMG_PORT=socket://127.0.0.1:7001
                                 python live.py --rtc socket://127.0.0.1:7002
    Terminal 3 (PowerShell):     $env:EMG_PORT="socket://127.0.0.1:7001"
                                 python live.py --rtc socket://127.0.0.1:7002

Needs a `model.joblib` made from simulator data (step above). A model trained on `make_fake_csv.py`
data or on real data will not match the simulator's signal.

Type in Terminal 1:

| Command | What happens |
|---|---|
| `rest` `open` `close` `pinch` `index` (or `0`-`4`) | perform that gesture |
| `unplug 2` | sensor 2 goes flat -> live.py shows SENSOR FAULT |
| `stuck 1` | sensor 1 stuck at 4095 -> SENSOR FAULT |
| `hum` | very strong 50 Hz mains hum on/off |
| `ok` | clear faults |
| `quit` | stop |

Hands-free alternative: `python sim_esp32.py --auto 4` cycles through all gestures, 4 s each.

**RTC unit tests:**

    python sim_uno.py
    python uno_test.py socket://127.0.0.1:7002      (expect: ALL OK)
    python set_rtc.py  socket://127.0.0.1:7002

Rehearse failures: `python sim_uno.py --lost-power` (boots with "RTC LOST POWER" and the date
2000-01-01) or `python sim_uno.py --no-rtc` (boots with "RTC FAILED", answers "ERR NO RTC").
`sim_uno.py` prints every line it receives (`<-`) and sends (`->`).

## What changed in the original files

Only so that a `socket://` address works in place of a COM port. COM ports work exactly as before.

- `emg_lib.py`: `ESP32_PORT` can be overridden by the environment variable `EMG_PORT`;
  `serial.Serial(...)` -> `serial.serial_for_url(...)`.
- `live.py`, `set_rtc.py`, `uno_test.py`: `serial.Serial(...)` -> `serial.serial_for_url(...)`.
- `live.py`, `uno_test.py`: `read(in_waiting or 1)` -> `read(4096)` (same result on a real serial port).

If you had already edited `ESP32_PORT = "COM5"` in `emg_lib.py`, set your port there again.

`sim_live_check.py` is a helper used by the self-test (runs live.py without a window).
