# make_fake_csv.py - creates FAKE data so you can test the whole pipeline before
# your sensors arrive. Run: python make_fake_csv.py
import numpy as np, pandas as pd
from emg_lib import FAKE_LEVEL

rng = np.random.default_rng(0)
rows = []
for rep in range(1, 7):                    # 6 repetitions
    for lab, amp in FAKE_LEVEL.items():    # 5 gestures
        for _ in range(3000):              # 3 seconds at 1000 Hz
            rows.append(["fake", 1, rep, lab] + [int(2048 + rng.normal(0, a)) for a in amp])
pd.DataFrame(rows, columns=["person", "day", "rep", "label", "ch1", "ch2", "ch3"]).to_csv(
    "emg_fake_day1.csv", index=False)
print("made emg_fake_day1.csv -> now run: python train_subsets.py emg_fake_day1.csv")
