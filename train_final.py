# train_final.py - trains the model you will use in the live demo and saves model.joblib
# Run: python train_final.py 0,1,2 emg_p1_day1.csv                    (all three sensors)
#      python train_final.py 1,2 emg_p1_day1.csv emg_p1_day2.csv      (S2+S3, two files)
# sensors: 0 = S1, 1 = S2, 2 = S3
import sys, joblib, numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from emg_lib import build_dataset, N_FEAT

if len(sys.argv) < 3:
    sys.exit("usage: python train_final.py 0,1,2 emg_p1_day1.csv [more.csv ...]")
sub = [int(a) for a in sys.argv[1].split(",")]
cols = [N_FEAT * k + j for k in sub for j in range(N_FEAT)]
parts = [build_dataset(p) for p in sys.argv[2:]]
X = np.vstack([p[0] for p in parts]); y = np.concatenate([p[1] for p in parts])
model = make_pipeline(StandardScaler(), LinearDiscriminantAnalysis()).fit(X[:, cols], y)
joblib.dump((model, cols), "model.joblib")
print(f"trained on {len(y)} windows, sensors {['S' + str(k + 1) for k in sub]} -> saved model.joblib")
print("accuracy on its own training data (will look high - that is NOT your result):",
      round(100 * model.score(X[:, cols], y), 1), "%")
