"""heldout_test.py - honest test: train on some reps, test on reps the model never saw."""
import sys
import numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.ensemble import RandomForestClassifier
from emg_lib import build_dataset, N_FEAT

csv = sys.argv[1] if len(sys.argv) > 1 else "emg_sim_day1.csv"
X, y, rep = build_dataset(csv)
cols = list(range(N_FEAT * 3))
print(f"{csv}: {X.shape[0]} windows, reps {sorted(set(rep))}\n")

print(f"{'held-out reps':>14} | {'train n':>7} {'test n':>6} | LDA % | RF %")
print("-" * 56)
for test_reps in ([6], [5, 6], [4, 5, 6], [2, 4, 6]):
    tr = ~np.isin(rep, test_reps)
    te = np.isin(rep, test_reps)
    lda = make_pipeline(StandardScaler(), LinearDiscriminantAnalysis()).fit(X[tr][:, cols], y[tr])
    rf = RandomForestClassifier(n_estimators=200, random_state=0).fit(X[tr][:, cols], y[tr])
    a_lda = 100 * lda.score(X[te][:, cols], y[te])
    a_rf = 100 * rf.score(X[te][:, cols], y[te])
    print(f"{str(test_reps):>14} | {tr.sum():>7} {te.sum():>6} | {a_lda:5.1f} | {a_rf:4.1f}")
