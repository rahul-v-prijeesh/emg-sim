# plot_check.py - draws your recording so you can SEE whether the data is good.
# Run: python plot_check.py emg_p1_day1.csv   -> creates emg_p1_day1_plot.png
import sys
import pandas as pd, matplotlib
matplotlib.use("Agg")  # draw to a PNG file (works everywhere)
import matplotlib.pyplot as plt
from emg_lib import clean, CH, GESTURES

path = sys.argv[1]
df = pd.read_csv(path)
rep = int(sys.argv[2]) if len(sys.argv) > 2 else 1   # which repetition to draw

fig, axes = plt.subplots(len(GESTURES), 1, figsize=(10, 9), sharex=True)
for ax, lab in zip(axes, GESTURES):
    g = df[(df.rep == rep) & (df.label == lab)]
    for c in CH:
        ax.plot(clean(g[c].values), lw=0.6, label=c)
    ax.set_ylabel(lab, rotation=0, labelpad=30)
axes[0].legend(loc="upper right", ncol=3)
axes[-1].set_xlabel("sample number (1000 = 1 second)")
fig.suptitle(f"{path} - repetition {rep}: you want BIG waves for gestures, small for REST")
fig.tight_layout()
out = path.replace(".csv", "_plot.png")
fig.savefig(out, dpi=110)
print("saved", out, "- open it and look at it")

print("\nAverage strength (RMS) per gesture and sensor, all repetitions:")
rows = []
for lab in GESTURES:
    g = df[df.label == lab]
    rows.append([lab] + [round((clean(g[c].values) ** 2).mean() ** 0.5, 1) for c in CH])
print(pd.DataFrame(rows, columns=["gesture"] + CH).to_string(index=False))
