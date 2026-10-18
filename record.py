# record.py - records one full session (5 gestures x 6 repetitions) into a CSV file.
# Run: python record.py p1 1   (person p1, day 1)
#      python record.py p2 1   (person p2, day 1) ... and so on
import sys, csv, os, random
import numpy as np
from emg_lib import samples_serial as SOURCE, GESTURES, check_signal, clean
# for WiFi later: from emg_lib import samples_udp as SOURCE

if len(sys.argv) != 3:
    sys.exit("usage: python record.py <person> <day>   e.g. python record.py p1 1")
PERSON, DAY = sys.argv[1], int(sys.argv[2])
REPS, HOLD_S, READY_S, SETTLE_S = 6, 3, 2, 0.5
FS = 1000
fname = f"emg_{PERSON}_day{DAY}.csv"
if os.path.exists(fname):
    sys.exit(f"{fname} already exists - I will not overwrite it. Rename or delete it first.")

src = SOURCE()


def take(seconds):
    """Read exactly seconds*1000 samples (the ESP32's own clock is the stopwatch)."""
    n = int(seconds * FS)
    out = []
    for s in src:
        out.append(s)
        if len(out) >= n:
            break
    return out


print(f"Recording {fname}. Keep the arm still, relaxed, same position every time.")
with open(fname, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["person", "day", "rep", "label", "ch1", "ch2", "ch3"])
    for rep in range(1, REPS + 1):
        order = GESTURES[:]
        random.shuffle(order)          # random order each repetition
        for g in order:
            print(f"\nRep {rep}/{REPS}: next gesture = {g}. Get ready...")
            take(READY_S)              # thrown away
            print(f">>> HOLD {g} NOW!")
            take(SETTLE_S)             # transition time, thrown away
            data = take(HOLD_S)
            for a, b, c in data:
                w.writerow([PERSON, DAY, rep, g, a, b, c])
            arr = np.array(data, dtype=float)
            rms = [np.sqrt(np.mean(clean(arr[:, k]) ** 2)) for k in range(3)]
            print(f"   saved {len(data)} samples | strength (RMS) S1={rms[0]:.1f} "
                  f"S2={rms[1]:.1f} S3={rms[2]:.1f}")
            problem = check_signal(arr)
            if problem:
                print(f"   !! WARNING: {problem}. Stop (Ctrl+C), fix it, delete the CSV, start again.")
print("\nDone:", fname)
