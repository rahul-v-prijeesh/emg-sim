# train_subsets.py - accuracy for all 7 sensor subsets, LDA vs Random Forest.
# Run: python train_subsets.py emg_p1_day1.csv                    (same-day test only)
#      python train_subsets.py emg_p1_day1.csv emg_p1_day2.csv    (adds the day-2 test)
import sys, itertools, numpy as np, pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix
from emg_lib import build_dataset, N_FEAT, GESTURES

# The "fewest sensors" rule. DECIDE THIS BEFORE you look at any results and never change it.
RULE_POINTS = 5   # smallest subset within 5 percentage points of using all 3 sensors


def make_model(name):
    if name == "LDA":
        return make_pipeline(StandardScaler(), LinearDiscriminantAnalysis())
    return RandomForestClassifier(n_estimators=100, random_state=0)


if len(sys.argv) < 2:
    sys.exit("usage: python train_subsets.py day1.csv [day2.csv]")
day1 = sys.argv[1]
day2 = sys.argv[2] if len(sys.argv) > 2 else None

X, y, rep = build_dataset(day1)
print("day 1:", len(y), "windows | repetitions:", np.unique(rep))
if day2:
    X2, y2, _ = build_dataset(day2)
    print("day 2:", len(y2), "windows")

subsets = [c for n in (1, 2, 3) for c in itertools.combinations(range(3), n)]  # the 7 subsets
rows = []
for sub in subsets:
    cols = [N_FEAT * k + j for k in sub for j in range(N_FEAT)]  # feature columns of those sensors
    row = {"subset": "+".join(f"S{k + 1}" for k in sub), "n": len(sub)}
    for name in ("LDA", "RF"):
        accs = []
        for test_rep in np.unique(rep):              # leave-one-repetition-out (no cheating)
            tr, te = rep != test_rep, rep == test_rep
            m = make_model(name).fit(X[tr][:, cols], y[tr])
            accs.append(m.score(X[te][:, cols], y[te]))
        row[f"{name} same-day %"] = round(100 * np.mean(accs), 1)
        if day2:                                      # train on ALL of day 1, test on day 2
            m = make_model(name).fit(X[:, cols], y)
            row[f"{name} day-2 %"] = round(100 * m.score(X2[:, cols], y2), 1)
    rows.append(row)

res = pd.DataFrame(rows)
print("\n", res.drop(columns="n").to_string(index=False))
res.to_csv(day1.replace(".csv", "_results.csv"), index=False)

# ---- apply the pre-decided rule
best_all = res[res.n == 3]["LDA same-day %"].iloc[0]
ok = res[res["LDA same-day %"] >= best_all - RULE_POINTS].sort_values(
    ["n", "LDA same-day %"], ascending=[True, False])
pick = ok.iloc[0]
print(f"\nRULE: smallest subset within {RULE_POINTS} points of all 3 sensors ({best_all}%) -> "
      f"{pick['subset']} ({pick['LDA same-day %']}%)")

# ---- which gestures get confused? (LDA, all 3 sensors, leave-one-repetition-out)
pred = np.empty_like(y)
for test_rep in np.unique(rep):
    tr, te = rep != test_rep, rep == test_rep
    pred[te] = make_model("LDA").fit(X[tr], y[tr]).predict(X[te])
cm = pd.DataFrame(confusion_matrix(y, pred, labels=GESTURES),
                  index=[f"true {g}" for g in GESTURES], columns=GESTURES)
print("\nConfusion matrix (rows = what you did, columns = what the computer guessed):")
print(cm.to_string())
