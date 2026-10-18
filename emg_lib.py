"""emg_lib.py - shared helpers used by every other Python file.
Put this file in the same folder as record.py, train_subsets.py, live.py ...
"""
import os, time, socket
import numpy as np, pandas as pd, serial
from scipy.signal import butter, sosfilt, iirnotch, lfilter

# ---------------------------------------------------------------- settings
ESP32_PORT = os.environ.get("EMG_PORT", "COM5")   # EDIT: Windows "COM5" / Linux "/dev/ttyUSB0" / Mac "/dev/cu.usbserial-0001"
                                                  # (env var EMG_PORT overrides it, e.g. socket://127.0.0.1:7001 for the simulator)
UDP_PORT = 5005       # only used for the optional WiFi mode
FS = 1000             # samples per second (must match PERIOD_US in the ESP32 sketch)
WIN = 200             # one window = 200 samples = 0.2 seconds
STEP = 100            # a new window every 100 samples (windows overlap by half)
CH = ["ch1", "ch2", "ch3"]
N_FEAT = 5            # features per sensor: RMS, MAV, WL, ZC, SSC
GESTURES = ["REST", "OPEN", "CLOSE", "PINCH", "INDEX"]
MAINS_HZ = 50         # India = 50 Hz (USA = 60)

# Only for fake / demo data: how "strong" each sensor looks for each gesture.
FAKE_LEVEL = {"REST": (5, 5, 5), "OPEN": (60, 20, 10), "CLOSE": (15, 70, 30),
              "PINCH": (30, 40, 60), "INDEX": (45, 15, 50)}

# ---------------------------------------------------------------- cleaning
_sos = butter(4, [20, 400], btype="bandpass", fs=FS, output="sos")  # keep 20-400 Hz
_nb, _na = iirnotch(MAINS_HZ, 30, fs=FS)                            # cut mains hum


def clean(x):
    """Raw ADC numbers -> cleaned signal centred on zero."""
    x = np.asarray(x, dtype=float)
    x = x - x.mean()            # 1) remove the DC level (about 2048)
    x = sosfilt(_sos, x)        # 2) band-pass filter
    return lfilter(_nb, _na, x) # 3) notch filter for mains hum


def check_signal(raw, edge=40, flat=0.5):
    """Is the RAW signal healthy? raw has shape (n_samples, n_channels).
    Returns None if fine, or a text reason. Used by record.py and live.py."""
    raw = np.asarray(raw, dtype=float)
    for k in range(raw.shape[1]):
        x = raw[:, k]
        if np.mean((x <= edge) | (x >= 4095 - edge)) > 0.2:
            return f"sensor {k + 1} stuck near 0 or 4095"
        if x.std() < flat:
            return f"sensor {k + 1} flat (unplugged?)"
    return None


# ---------------------------------------------------------------- features
def features(w, thr=5):
    """One window of ONE sensor -> 5 numbers."""
    d = np.diff(w)
    rms = np.sqrt(np.mean(w ** 2))                          # RMS: signal strength
    mav = np.mean(np.abs(w))                                # MAV: average size
    wl = np.sum(np.abs(d))                                  # WL: waveform length
    zc = np.sum((w[:-1] * w[1:] < 0) & (np.abs(d) > thr))   # zero crossings
    ssc = np.sum((d[:-1] * d[1:] < 0) &
                 ((np.abs(d[:-1]) > thr) | (np.abs(d[1:]) > thr)))  # slope sign changes
    return [rms, mav, wl, zc, ssc]


def window_features(sig):
    """sig has shape (WIN, 3) -> 15 numbers (5 per sensor)."""
    f = []
    for k in range(sig.shape[1]):
        f += features(sig[:, k])
    return f


def build_dataset(csv_path):
    """CSV file -> X (features), y (labels), rep (which repetition each row came from)."""
    df = pd.read_csv(csv_path)
    X, y, rep = [], [], []
    for (r, lab), g in df.groupby(["rep", "label"]):
        sig = np.column_stack([clean(g[c].values) for c in CH])[100:]  # skip filter start-up
        for s in range(0, len(sig) - WIN + 1, STEP):
            X.append(window_features(sig[s:s + WIN])); y.append(lab); rep.append(r)
    return np.array(X), np.array(y), np.array(rep)


# ---------------------------------------------------------------- data sources
def _parse(line):
    parts = line.strip().split(",")
    if len(parts) == 4:
        try:
            v = [int(p) for p in parts[1:]]
        except ValueError:
            return None
        if all(0 <= q <= 4095 for q in v):
            return v
    return None


def samples_serial(port=None, baud=921600):
    """USB source: yields [ch1, ch2, ch3] forever."""
    ser = serial.serial_for_url(port or ESP32_PORT, baud, timeout=1)  # COM5 or socket://...
    time.sleep(2)  # the ESP32 restarts when the port opens
    ser.reset_input_buffer()
    while True:
        s = _parse(ser.readline().decode(errors="ignore"))
        if s:
            yield s


def samples_udp(port=UDP_PORT):
    """WiFi source (optional, last): yields [ch1, ch2, ch3] forever."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    while True:
        data, _ = sock.recvfrom(2048)
        for line in data.decode(errors="ignore").splitlines():
            s = _parse(line)
            if s:
                yield s


def samples_demo():
    """SIMULATED source (no hardware). Cycles through the gestures, 3 s each.
    Only for testing the software. Never present it as real muscle data."""
    rng = np.random.default_rng()
    t0, k = time.perf_counter(), 0
    while True:
        amp = FAKE_LEVEL[GESTURES[(k // (3 * FS)) % len(GESTURES)]]
        for _ in range(10):
            yield [int(2048 + rng.normal(0, a)) for a in amp]
            k += 1
        wait = t0 + k / FS - time.perf_counter()
        if wait > 0:
            time.sleep(wait)
