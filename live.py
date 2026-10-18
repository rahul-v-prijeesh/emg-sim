# live.py - live gesture screen + talks to the Arduino RTC unit.
# Run: python live.py                  (ESP32 only, no clock)
#      python live.py --rtc COM6       (ESP32 + Arduino RTC: gesture changes get a date/time stamp)
#      python live.py --demo           (SIMULATED signal, no hardware, for testing)
#      (--uno is accepted as another name for --rtc)
# Every gesture change that the Arduino stamps is appended to gesture_log.csv.
import argparse, csv, os, queue, sys, threading, time, joblib, serial
import numpy as np
from collections import deque
from emg_lib import (clean, window_features, check_signal, WIN, STEP, N_FEAT,
                     samples_serial, samples_demo)
# for WiFi later: from emg_lib import samples_udp as samples_serial

ap = argparse.ArgumentParser()
ap.add_argument("--rtc", "--uno", dest="rtc", help="serial port of the Arduino RTC unit, e.g. COM6")
ap.add_argument("--demo", action="store_true", help="use simulated data (no hardware)")
ap.add_argument("--seconds", type=float, help="close automatically after N seconds (for testing)")
ap.add_argument("--log", default="gesture_log.csv", help="where RTC-stamped gesture changes are saved")
ap.add_argument("--terminal", action="store_true", help="force terminal mode (no GUI window)")
args = ap.parse_args()

SOURCE = samples_demo if args.demo else samples_serial
THRESH, NEED = 0.70, 3        # need >= 70% confidence, 3 windows in a row
BUF_LEN = 600                 # keep the last 0.6 s so the filters can settle

model, cols = joblib.load("model.joblib")
sensors = sorted({c // N_FEAT for c in cols})   # which sensors this model uses


def log_event(stamp, word):
    new = not os.path.exists(args.log)
    with open(args.log, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["rtc_time", "gesture"])
        w.writerow([stamp, word])


def worker(q, stop):
    """Background: read samples -> classify -> tell the Arduino -> tell the screen."""
    try:
        rtc, rtc_text, rtc_clock, rtc_last = None, "", "", "no Arduino RTC"
        if args.rtc:
            rtc = serial.serial_for_url(args.rtc, 115200, timeout=0)
            time.sleep(2)                 # the Uno restarts when the port opens
            rtc_last = "waiting..."
        buf, new, sent = deque(maxlen=BUF_LEN), 0, 0
        recent, shown = deque(maxlen=NEED), "REST"
        for a, b, c in SOURCE():
            if stop.is_set():
                return
            buf.append([a, b, c]); new += 1
            if len(buf) < BUF_LEN or new < STEP:
                continue
            new = 0
            raw = np.array(buf, dtype=float)
            problem = check_signal(raw[-WIN:, sensors])      # unplugged / stuck sensor?
            guess = conf = None
            if problem:
                recent.clear()
                message = "FAULT"
            else:
                sig = np.column_stack([clean(raw[:, k]) for k in range(3)])[-WIN:]
                f = np.array(window_features(sig))[cols].reshape(1, -1)
                p = model.predict_proba(f)[0]
                guess, conf = model.classes_[p.argmax()], float(p.max())
                recent.append(guess if conf >= THRESH else None)
                if len(recent) == NEED and len(set(recent)) == 1 and recent[0] is not None:
                    shown = recent[0]                          # 3 confident matches in a row
                message = shown
            if rtc:
                rtc.write((message + "\n").encode())           # the Uno stamps it if it changed
                sent += 1
                if sent % 10 == 0:
                    rtc.write(b"TIME?\n")                      # ask for the clock about once a second
                rtc_text += rtc.read(4096).decode(errors="ignore")
                *lines, rtc_text = rtc_text.split("\n")
                for ln in lines:
                    ln = ln.strip()
                    if ln.startswith("EVT,"):
                        parts = ln.split(",")
                        if len(parts) == 3:
                            log_event(parts[1], parts[2])
                            rtc_last = f"{parts[1]}  {parts[2]}"
                    elif ln.startswith("TIME "):
                        rtc_clock = ln[5:]
                    elif ln.startswith("RTC FAILED") or ln.startswith("ERR NO RTC"):
                        rtc_last = "RTC NOT FOUND - check wiring"
            q.put(dict(shown=shown, guess=guess, conf=conf, problem=problem,
                       clock=rtc_clock, last=rtc_last, t=time.time()))
    except Exception as e:                                     # e.g. USB cable pulled out
        q.put(dict(error=f"{type(e).__name__}: {e}"))


# ------------------------------------------------------------------ the window
HEADLESS = args.terminal  # use --terminal flag to force terminal mode; otherwise try GUI

q, stop = queue.Queue(), threading.Event()
threading.Thread(target=worker, args=(q, stop), daemon=True).start()

if HEADLESS:
    # ---- terminal mode (no display) ----
    import signal
    signal.signal(signal.SIGINT, lambda *_: (stop.set(), sys.exit(0)))
    print("live.py running in TERMINAL mode (no display detected)")
    if args.demo:
        print("DEMO - SIMULATED SIGNAL, NOT REAL MUSCLE DATA")
    print("Press Ctrl+C to stop.\n")
    last, last_msg, prev_shown = None, None, None
    try:
        t0 = time.time()
        while not stop.is_set():
            if args.seconds and (time.time() - t0) >= args.seconds:
                break
            while not q.empty():
                last = q.get()
            now = time.time()
            if last is None:
                pass
            elif "error" in last:
                print(f"[LINK LOST] {last['error'][:80]}", flush=True)
            elif now - last["t"] > 1.0:
                print("[NO DATA] nothing from the ESP32 for over 1 second", flush=True)
            elif last["problem"]:
                print(f"[SENSOR FAULT] {last['problem']}", flush=True)
            else:
                if last["shown"] != prev_shown:
                    c = "" if last["conf"] is None else f"{last['conf']:.0%}"
                    elapsed = round(now - t0, 1)
                    clock_str = f"  RTC: {last['clock']}" if last["clock"] else ""
                    print(f"[{elapsed:6.1f}s]  raw: {last['guess']} ({c})  ->  stable: {last['shown']}{clock_str}", flush=True)
                    prev_shown = last["shown"]
                    last_msg = last
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    stop.set()
    if last_msg:
        print(f"\nlast gesture: {last_msg['shown']} | RTC: {last_msg['clock']} | last event: {last_msg['last']}")

else:
    # ---- GUI mode (original tkinter window) ----
    import tkinter as tk
    root = tk.Tk()
    root.title("Muscle gesture display")
    root.geometry("720x500")
    big = tk.Label(root, text="starting...", font=("Helvetica", 80, "bold"))
    big.pack(expand=True, fill="both")
    line1 = tk.Label(root, font=("Helvetica", 16)); line1.pack()
    line2 = tk.Label(root, font=("Helvetica", 16)); line2.pack()
    line3 = tk.Label(root, font=("Helvetica", 12)); line3.pack()
    banner = tk.Label(root, font=("Helvetica", 12, "bold"), fg="#b00020",
                      text="DEMO - SIMULATED SIGNAL, NOT REAL MUSCLE DATA" if args.demo else "")
    banner.pack(pady=6)
    last, last_msg = None, None


    def paint(colour):
        for w in (root, big, line1, line2, line3, banner):
            w.configure(bg=colour)


    def update():
        global last, last_msg
        while not q.empty():
            last = q.get()
        now = time.time()
        if last is None:
            pass
        elif "error" in last:
            paint("#f8d7da"); big.config(text="LINK LOST", fg="#b00020")
            line1.config(text=last["error"][:80]); line2.config(text=""); line3.config(text="")
        elif now - last["t"] > 1.0:
            paint("#f8d7da"); big.config(text="NO DATA", fg="#b00020")
            line1.config(text="nothing from the ESP32 for over 1 second"); line2.config(text=""); line3.config(text="")
        elif last["problem"]:
            paint("#fff3cd"); big.config(text="SENSOR FAULT", fg="#8a6d00")
            line1.config(text=last["problem"])
            line2.config(text="RTC clock: " + (last["clock"] or "-"))
            line3.config(text="last stamped event: " + last["last"])
        else:
            paint("#d4edda"); big.config(text=last["shown"], fg="#14532d")
            c = "" if last["conf"] is None else f"{last['conf']:.0%}"
            line1.config(text=f"raw guess: {last['guess']} ({c})")
            line2.config(text="RTC clock: " + (last["clock"] or "-"))
            line3.config(text="last stamped event: " + last["last"])
            last_msg = last
        root.after(50, update)


    def close():
        stop.set(); root.destroy()


    root.protocol("WM_DELETE_WINDOW", close)
    if args.seconds:
        root.after(int(args.seconds * 1000), close)
    update()
    root.mainloop()
    if last_msg:
        print("last screen state:", last_msg["shown"], "| RTC:", last_msg["clock"], "| last event:", last_msg["last"])
