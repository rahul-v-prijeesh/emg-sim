"""sim_esp32.py - SIMULATED ESP32 + 3 EMG sensors. No hardware needed.

It behaves like arduino/esp32_emg: 1000 lines per second, each "micros,ch1,ch2,ch3", ADC range
0-4095. It listens on a local TCP port, so your normal scripts connect to it as if it were a COM port:

    Windows :  set EMG_PORT=socket://127.0.0.1:7001
    Linux/Mac: export EMG_PORT=socket://127.0.0.1:7001

(Real COM ports keep working: just leave EMG_PORT unset.)

USAGE
  python sim_esp32.py                     interactive: type a gesture to "perform" it
  python sim_esp32.py --auto 4            hands-free: cycle through all gestures, 4 s each
  python sim_esp32.py --run-record p1 1   runs record.py for you and "performs" every gesture it asks for
                                          (add --speed 20 to finish the 30-gesture session in ~25 s)

COMMANDS (interactive)
  rest open close pinch index   (or 0 1 2 3 4)   perform that gesture
  unplug N     sensor N (1-3) goes flat          -> live.py should show SENSOR FAULT
  stuck N      sensor N stuck at 4095            -> live.py should show SENSOR FAULT
  hum          toggle very strong 50 Hz mains hum on all sensors
  ok           clear all faults and hum
  status, help, quit

The signal is SIMULATED: band-limited noise (20-250 Hz) whose strength depends on the gesture, with
smooth transitions, random strength variation each time a gesture starts, cross-talk between the
sensors, 50 Hz hum, DC offset and ADC noise. It is more realistic than make_fake_csv.py but it is
still NOT real muscle data - never quote its accuracy as a result.
"""
import argparse, os, re, socket, subprocess, sys, threading, time
import numpy as np
from scipy.signal import butter, sosfilt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from emg_lib import GESTURES, FAKE_LEVEL, FS      # same gesture list / strength table as the project

HOST = "127.0.0.1"
TAU = 0.08                                         # seconds: how fast the muscle "ramps" between gestures
XTALK = 0.9 * np.eye(3) + 0.05 * (1 - np.eye(3))   # each sensor also picks up a little of the others
OFFSETS = np.array([0, 15, -10])                   # each channel has a slightly different DC level


class Sensors:
    def __init__(self, seed=None):
        self.rng = np.random.default_rng(seed)
        self.sos = butter(2, [20, 250], btype="bandpass", fs=FS, output="sos")
        probe = sosfilt(self.sos, self.rng.normal(size=200000))
        self.norm = 1.0 / probe[1000:].std()       # so the EMG RMS equals the table value
        self.lock = threading.RLock()
        self.events = []                           # (sample index, gesture): scripted changes
        self.limit = None                          # None = free running; else do not generate past this index
        self.gesture = "REST"
        self.fault = ["ok"] * 3
        self.hum = 3.0
        self.gain = np.ones(3)
        self.reset()

    def reset(self):
        """Like the ESP32 restarting: clock and filters start again."""
        self.zi = np.zeros((self.sos.shape[0], 2, 3))      # shape sosfilt wants for axis=0
        self.env = np.array(FAKE_LEVEL[self.gesture], float) * self.gain
        self.n = 0

    def set_gesture(self, g):
        with self.lock:
            if g != self.gesture:                  # a new contraction is never exactly as strong as the last
                self.gain = np.clip(self.rng.normal(1.0, 0.12, 3), 0.7, 1.3)
            self.gesture = g

    def schedule(self, idx, g):
        """Change to gesture g exactly at sample number idx (counted from the connection)."""
        with self.lock:
            self.events.append((idx, g))
            self.events.sort(key=lambda e: e[0])

    def chunk(self, n):
        """n samples; scripted gesture changes take effect at their exact sample."""
        parts = []
        while n > 0:
            with self.lock:
                while self.events and self.events[0][0] <= self.n:
                    self.set_gesture(self.events.pop(0)[1])
                nxt = self.events[0][0] if self.events else None
            m = n if nxt is None else min(n, nxt - self.n)
            parts.append(self._gen(m))
            n -= m
        return np.concatenate([p[0] for p in parts]), np.concatenate([p[1] for p in parts])

    def _gen(self, n):
        with self.lock:
            g, gain, fault, hum = self.gesture, self.gain.copy(), list(self.fault), self.hum
        emg, self.zi = sosfilt(self.sos, self.rng.normal(size=(n, 3)), axis=0, zi=self.zi)
        target = np.array(FAKE_LEVEL[g], float) * gain
        r = np.exp(-1.0 / (TAU * FS))
        k = np.arange(1, n + 1)[:, None]
        env = target + (self.env - target) * r ** k          # smooth ramp towards the new strength
        self.env = env[-1]
        sig = (emg * self.norm * env) @ XTALK
        idx = self.n + np.arange(n)
        t = idx / FS
        sig += hum * np.sin(2 * np.pi * 50 * t[:, None] + np.array([0.0, 1.0, 2.0]))
        sig += 2048 + OFFSETS + 5 * np.sin(2 * np.pi * 0.05 * t)[:, None]
        sig += self.rng.normal(0, 1.2, size=(n, 3))
        adc = np.clip(np.rint(sig), 0, 4095).astype(int)
        for ch, f in enumerate(fault):
            if f == "flat":
                adc[:, ch] = 2048
            elif f == "stuck":
                adc[:, ch] = 4095
        self.n += n
        micros = ((idx * 1_000_000) // FS) & 0xFFFFFFFF
        return micros, adc


def log(msg):
    print(f"[sim] {msg}", flush=True)


def serve(sim, port, speed, once, boot_delay=1.0):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, port))
    srv.listen(1)
    while True:
        conn, _ = srv.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        log("program connected - the ESP32 'restarts' (about 1 s, like the real board)")
        sim.reset()
        try:
            time.sleep(boot_delay)
            t0, sent, stall = time.perf_counter(), 0, None
            while True:
                due = int((time.perf_counter() - t0) * FS * speed) - sent
                if sim.limit is not None:              # flow control while record.py is being driven
                    room = sim.limit - sim.n
                    if room <= 0:
                        if stall is None:
                            stall = time.time()
                        elif time.time() - stall > 5:
                            log("no cue from record.py for 5 s - running free (gesture labels may be off)")
                            sim.limit = None
                        time.sleep(0.001)
                        continue
                    if stall is not None:              # leaving a stall: keep the real-time pacing
                        t0, stall = time.perf_counter() - sent / (FS * speed), None
                        due = int((time.perf_counter() - t0) * FS * speed) - sent
                    due = min(due, room)
                if due <= 0:
                    time.sleep(0.001)
                    continue
                n = min(due, 500)
                micros, adc = sim.chunk(n)
                data = "".join("%d,%d,%d,%d\n" % (m, a, b, c)
                               for m, (a, b, c) in zip(micros.tolist(), adc.tolist()))
                conn.sendall(data.encode())
                sent += n
        except OSError:
            log("program disconnected")
        finally:
            conn.close()
        if once:
            return


def command(sim, line):
    w = line.strip().lower().split()
    if not w:
        return True
    names = {g.lower(): g for g in GESTURES}
    if w[0] in names or (w[0].isdigit() and int(w[0]) < len(GESTURES)):
        g = names[w[0]] if w[0] in names else GESTURES[int(w[0])]
        sim.set_gesture(g)
        print(f"  performing {g}")
    elif w[0] in ("unplug", "stuck") and len(w) == 2 and w[1] in ("1", "2", "3"):
        sim.fault[int(w[1]) - 1] = "flat" if w[0] == "unplug" else "stuck"
        print(f"  sensor {w[1]}: {sim.fault[int(w[1]) - 1]}")
    elif w[0] == "hum":
        sim.hum = 40.0 if sim.hum < 10 else 3.0
        print(f"  mains hum amplitude now {sim.hum:g} counts")
    elif w[0] == "ok":
        sim.fault = ["ok"] * 3
        sim.hum = 3.0
        print("  all faults cleared")
    elif w[0] == "status":
        print(f"  gesture={sim.gesture} faults={sim.fault} hum={sim.hum:g}")
    elif w[0] in ("quit", "exit", "q"):
        return False
    else:
        print(__doc__.split("COMMANDS (interactive)")[1].split("The signal")[0])
    return True


def run_record(sim, person, day, speed, url):
    """Start record.py and perform each gesture it asks for.

    record.py counts samples, so the simulator does too: every cue it prints happens after an exactly
    known number of samples, and the simulator only generates samples up to the next cue. That keeps
    the gesture labels exact at any --speed."""
    rec = os.path.join(HERE, "record.py")
    m = re.search(r"REPS,\s*HOLD_S,\s*READY_S,\s*SETTLE_S\s*=\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)",
                  open(rec, encoding="utf-8").read())
    if m:
        _, hold, ready, settle = (float(x) for x in m.groups())
        ready_n, block = round(ready * FS), round((ready + settle + hold) * FS)
        react = round(0.3 * FS)                          # human reaction time after the cue
        sim.limit = 0
    else:
        log("could not read the timing constants of record.py - running without flow control "
            "(use --speed 1)")
    env = dict(os.environ, EMG_PORT=url, PYTHONUNBUFFERED="1")
    p = subprocess.Popen([sys.executable, "-u", rec, person, str(day)],
                         env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    b = -1
    for line in p.stdout:
        print(line, end="", flush=True)
        if re.search(r"next gesture = \w+", line):
            b += 1                                       # a new gesture block starts now
            if m:
                sim.schedule(b * block, "REST")          # relaxed while getting ready
                sim.limit = b * block + ready_n          # next cue: ">>> HOLD" after the ready time
        h = re.search(r">>> HOLD (\w+) NOW", line)
        if h and m:
            sim.schedule(b * block + ready_n + react, h.group(1))
            sim.limit = (b + 1) * block                  # next cue: the following block, or the end
    return p.wait()


def main():
    ap = argparse.ArgumentParser(description="Simulated ESP32 + 3 EMG sensors")
    ap.add_argument("--tcp-port", type=int, default=7001)
    ap.add_argument("--speed", type=float, default=1.0,
                    help="1 = real time. 20 = 20x faster (only for recording sessions, not live.py)")
    ap.add_argument("--auto", type=float, metavar="SEC", help="cycle through the gestures, SEC seconds each")
    ap.add_argument("--run-record", nargs=2, metavar=("PERSON", "DAY"), help="run record.py and perform for it")
    ap.add_argument("--seed", type=int)
    a = ap.parse_args()

    sim = Sensors(a.seed)
    url = f"socket://{HOST}:{a.tcp_port}"
    threading.Thread(target=serve, args=(sim, a.tcp_port, a.speed, bool(a.run_record),
                                          2.5 if a.run_record else 1.0), daemon=True).start()
    time.sleep(0.2)
    log(f"SIMULATED ESP32 ready at {url}   (NOT real muscle data)")

    if a.run_record:
        rc = run_record(sim, a.run_record[0], a.run_record[1], a.speed, url)
        log(f"record.py finished (exit code {rc})")
        sys.exit(rc)

    if a.auto:
        def cycle():
            k = 0
            while True:
                g = GESTURES[k % len(GESTURES)]
                sim.set_gesture(g)
                log(f"auto: performing {g}")
                time.sleep(a.auto)
                k += 1
        threading.Thread(target=cycle, daemon=True).start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return

    print("Type a gesture (rest open close pinch index), 'unplug 2', 'stuck 1', 'hum', 'ok', 'help', 'quit'.")
    try:
        while command(sim, input("sim> ")):
            pass
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
