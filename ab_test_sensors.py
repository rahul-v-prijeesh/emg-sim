"""ab_test_sensors.py - does "impute the missing sensors, then classify" actually beat
classifying directly from the same few sensors?

Three setups, evaluated on identical test poses:
  1. DIRECT-4      : classifier trained and tested on 4 real sensors
  2. IMPUTE-6      : 4 real sensors -> impute the other 2 -> 6-sensor classifier
  3. REAL-6        : classifier trained and tested on all 6 real sensors (upper bound)

If IMPUTE-6 only matches DIRECT-4, the imputation step adds no information (as theory says).
If IMPUTE-6 approaches REAL-6, it recovers useful information.

Runs on the same forearm physics as arm_lab.html, over every choice of which 4 of 6 sensors
are "given", and several random seeds. Run with the project venv:
    python ab_test_sensors.py
"""
import itertools, sys
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.neighbors import KNeighborsRegressor
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

# ------------------------------------------------------------------ knobs
N_TOTAL   = 6        # size of the full ("real 6") rig
GIVEN_K   = 4        # sensors you actually own in the reduced rig
N_TRAIN   = 3000
N_TEST    = 1500
SEEDS     = [0, 1, 2]
WIN       = 200
POSE_SD   = 0.06     # how much a real repetition wobbles around the ideal pose
MEAS_SD   = 0.12     # per-sensor multiplicative measurement noise (log units)
TRAIN_ROT = 0.0
TEST_ROTS = [-30.0, 0.0, 30.0]

# ------------------------------------------------------------------ arm physics (from arm_lab.html)
FA = np.array([-55, -25, 5, 30, 55]); EA = np.array([235, 205, 180, 155, 130])
DF = np.array([.7, .9, 1, .9, .6]);   DE = np.array([.8, .9, 1, .9, .8])
GEST = {'REST': [.35]*5, 'OPEN': [0]*5, 'CLOSE': [1]*5, 'PINCH': [.8, .8, .35, .35, .35],
        'INDEX': [1, 0, 1, 1, 1], 'THUMB': [0, 1, 1, 1, 1], 'PEACE': [1, 0, 0, 1, 1]}
NAMES = list(GEST)
PROTO = np.array([GEST[n] for n in NAMES])


def K(d):
    d = ((d % 360) + 540) % 360 - 180
    return 1.0 / (1.0 + (d / 40.0) ** 2)


def sense_amp(v, rot, wr, g, N):
    f = np.maximum(0, (v - 0.35) / 0.65) * (1 + 0.5 * wr) + 0.03
    e = np.maximum(0, (0.35 - v) / 0.35) * (1 - 0.5 * wr) + 0.03
    ph = 360.0 * np.arange(N) / N
    out = np.zeros(v.shape[:-1] + (N,))
    for i in range(5):
        out += (f[..., i:i+1] * DF[i] * K(FA[i] + rot - ph)) ** 2 \
             + (e[..., i:i+1] * DE[i] * K(EA[i] + rot - ph)) ** 2
    return np.sqrt((60 * g) ** 2 * out + 9)


def window_features(rms, rng, win=WIN, thr=5):
    M, N = rms.shape
    x = rng.normal(size=(M, N, win)) * rms[..., None]
    d = np.diff(x, axis=2)
    RMS = np.sqrt(np.mean(x ** 2, axis=2))
    MAV = np.mean(np.abs(x), axis=2)
    WL = np.sum(np.abs(d), axis=2)
    ZC = np.sum((x[:, :, :-1] * x[:, :, 1:] < 0) & (np.abs(d) > thr), axis=2)
    SSC = np.sum((d[:, :, :-1] * d[:, :, 1:] < 0) &
                 ((np.abs(d[:, :, :-1]) > thr) | (np.abs(d[:, :, 1:]) > thr)), axis=2)
    return np.stack([RMS, MAV, WL, ZC, SSC], axis=2)      # (M, N, 5)


def make_data(n, rot, rng, N=N_TOTAL):
    idx = rng.integers(0, len(NAMES), size=n)
    v = np.clip(PROTO[idx] + rng.normal(0, POSE_SD, size=(n, 5)), 0, 1)
    amp = sense_amp(v, rot, 0.0, 1.0, N) * np.exp(MEAS_SD * rng.normal(size=(n, N)))
    return window_features(amp, rng), idx                    # (n,N,5), (n,)


def make_clf(kind):
    if kind == 'lda':
        return make_pipeline(StandardScaler(), LinearDiscriminantAnalysis())
    return make_pipeline(StandardScaler(), RandomForestClassifier(n_estimators=200, random_state=0, n_jobs=-1))


def make_imp(kind):
    if kind == 'ridge':
        return make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    if kind == 'rf':
        from sklearn.ensemble import RandomForestRegressor
        return make_pipeline(StandardScaler(),
                             RandomForestRegressor(n_estimators=300, random_state=0, n_jobs=-1))
    return make_pipeline(StandardScaler(), KNeighborsRegressor(n_neighbors=15, weights='distance', n_jobs=-1))


def flat(F, sensors):
    return F[:, sensors, :].reshape(F.shape[0], -1)


def one_split(seed, train_rot, test_rot, given, hid, clf_kind='lda', imp_kind='ridge'):
    rng = np.random.default_rng(seed)
    Ftr, ytr = make_data(N_TRAIN, train_rot, rng)
    Fte, yte = make_data(N_TEST, test_rot, rng)

    g_tr, g_te = flat(Ftr, given), flat(Fte, given)
    h_tr, h_te = flat(Ftr, hid), flat(Fte, hid)
    a_tr, a_te = flat(Ftr, list(range(N_TOTAL))), flat(Fte, list(range(N_TOTAL)))

    acc_direct = make_clf(clf_kind).fit(g_tr, ytr).score(g_te, yte)          # 4 real sensors
    acc_real6 = make_clf(clf_kind).fit(a_tr, ytr).score(a_te, yte)           # 6 real sensors

    imp = make_imp(imp_kind).fit(g_tr, h_tr)

    # (a) naive: classifier trained on REAL hidden, tested with IMPUTED hidden (train/test mismatch)
    clf6 = make_clf(clf_kind).fit(np.hstack([g_tr, h_tr]), ytr)
    acc_impute_raw = clf6.score(np.hstack([g_te, imp.predict(g_te)]), yte)

    # (b) matched: classifier also trained on IMPUTED hidden, so train and test agree
    clf6m = make_clf(clf_kind).fit(np.hstack([g_tr, imp.predict(g_tr)]), ytr)
    acc_impute_match = clf6m.score(np.hstack([g_te, imp.predict(g_te)]), yte)

    # reconstruction quality of the hidden sensors (log-scale, normalised error)
    eps = 1e-6
    h_hat = imp.predict(g_te)
    nrmse = np.mean(np.abs(np.log(np.abs(h_hat) + eps) - np.log(np.abs(h_te) + eps)))
    return acc_direct, acc_impute_raw, acc_impute_match, acc_real6, nrmse


def main():
    clf_kind = sys.argv[1] if len(sys.argv) > 1 else 'lda'
    imp_kind = sys.argv[2] if len(sys.argv) > 2 else 'ridge'
    subsets = list(itertools.combinations(range(N_TOTAL), GIVEN_K))
    print(f"classifier={clf_kind}  imputer={imp_kind}  N_total={N_TOTAL}  given={GIVEN_K}  "
          f"gestures={len(NAMES)}  subsets={len(subsets)}  seeds={SEEDS}")
    print(f"train_rot={TRAIN_ROT}  test_rots={TEST_ROTS}\n")
    for test_rot in TEST_ROTS:
        d, ir, im, r6, nr = [], [], [], [], []
        for given in subsets:
            hid = [s for s in range(N_TOTAL) if s not in given]
            for seed in SEEDS:
                a, b, c, e, f_ = one_split(seed, TRAIN_ROT, test_rot, list(given), hid, clf_kind, imp_kind)
                d.append(a); ir.append(b); im.append(c); r6.append(e); nr.append(f_)
        m = lambda x: 100 * np.mean(x)
        print(f"test rot {test_rot:+.0f}deg | "
              f"DIRECT-{GIVEN_K} {m(d):5.1f}%   "
              f"IMPUTE naive {m(ir):5.1f}%   IMPUTE matched {m(im):5.1f}%   "
              f"REAL-{N_TOTAL} {m(r6):5.1f}%   | hidden nrmse {np.mean(nr):.2f}")


if __name__ == "__main__":
    main()
