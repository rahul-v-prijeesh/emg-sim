"""placement_study.py - where should the electrodes actually go?

The A/B test showed imputing missing channels adds zero information; the real lever
is WHICH electrode positions you keep. This sweeps candidate angles around the forearm
and greedily picks the most informative positions, then shows accuracy vs number of sensors.

Reuses the exact forearm physics from ab_test_sensors.py so results are comparable.

    python placement_study.py            # default 5-degree grid
    python placement_study.py 2          # 2-degree grid (finer, slower)
"""
import sys
import numpy as np
from ab_test_sensors import (K, FA, EA, DF, DE, PROTO, NAMES, window_features,
                             make_clf, POSE_SD, MEAS_SD, N_TRAIN)

N_VAL = 1500
N_TEST = 3000
SEEDS = [0, 1, 2]
K_MAX = 8
STEP = 5.0


def amp_at(v, rot, positions):
    f = np.maximum(0, (v - 0.35) / 0.65) + 0.03
    e = np.maximum(0, (0.35 - v) / 0.35) + 0.03
    out = np.zeros((v.shape[0], len(positions)))
    for i in range(5):
        out += (f[:, i:i+1] * DF[i] * K(FA[i] + rot - positions)) ** 2 \
             + (e[:, i:i+1] * DE[i] * K(EA[i] + rot - positions)) ** 2
    return np.sqrt(3600.0 * out + 9)


def gen_pose(n, rng):
    idx = rng.integers(0, len(NAMES), size=n)
    v = np.clip(PROTO[idx] + rng.normal(0, POSE_SD, size=(n, 5)), 0, 1)
    return v, idx


def features(v, rot, positions, rng):
    X = np.zeros((v.shape[0], len(positions), 5))
    for j in range(len(positions)):
        amp = amp_at(v, rot, np.array([positions[j]]))[:, 0]
        amp = amp * np.exp(MEAS_SD * rng.normal(size=amp.shape))
        X[:, j, :] = window_features(amp[:, None], rng)[:, 0, :]
    return X


def flat3(X, cols):
    return X[:, cols, :].reshape(X.shape[0], -1)


def build(seed, rot=0.0):
    rng = np.random.default_rng(seed)
    vtr, ytr = gen_pose(N_TRAIN, rng)
    vva, yva = gen_pose(N_VAL, rng)
    vte, yte = gen_pose(N_TEST, rng)
    return dict(ytr=ytr, yva=yva, yte=yte,
                Xtr=features(vtr, rot, candidates, rng),
                Xva=features(vva, rot, candidates, rng),
                Xte=features(vte, rot, candidates, rng))


candidates = np.arange(0, 360, STEP)


def greedy_selection(data):
    selected, curve = [], []
    for _ in range(K_MAX):
        best_c, best_acc = None, -1
        for c in range(len(candidates)):
            if c in selected:
                continue
            clf = make_clf('lda').fit(flat3(data['Xtr'], selected + [c]), data['ytr'])
            acc = clf.score(flat3(data['Xva'], selected + [c]), data['yva'])
            if acc > best_acc:
                best_acc, best_c = acc, c
        selected.append(best_c)
        clf = make_clf('lda').fit(flat3(data['Xtr'], selected), data['ytr'])
        curve.append(clf.score(flat3(data['Xte'], selected), data['yte']))
    return [int(candidates[c]) for c in selected], curve


def evenly(n):
    return [int(a) for a in np.linspace(0, 360, n, endpoint=False)]


def eval_set(data, positions):
    idx = [int(np.argmin(np.abs(candidates - p))) for p in positions]
    clf = make_clf('lda').fit(flat3(data['Xtr'], idx), data['ytr'])
    return clf.score(flat3(data['Xte'], idx), data['yte'])


def main():
    global STEP, candidates
    if len(sys.argv) > 1:
        STEP = float(sys.argv[1])
        candidates = np.arange(0, 360, STEP)
    print(f"candidate angles: {len(candidates)} (step {STEP} deg), seeds={SEEDS}\n")

    datas = [build(s) for s in SEEDS]

    # per-sensor solo accuracy (averaged over seeds / test)
    solo = np.zeros(len(candidates))
    for d in datas:
        for c in range(len(candidates)):
            clf = make_clf('lda').fit(flat3(d['Xtr'], [c]), d['ytr'])
            solo[c] += clf.score(flat3(d['Xte'], [c]), d['yte'])
    solo /= len(datas)
    order = np.argsort(solo)[::-1]
    print("best single electrode angles:")
    for c in order[:8]:
        print(f"   {int(candidates[c]):3d}deg  {100*solo[c]:5.1f}%")
    print()

    gs = [greedy_selection(d) for d in datas]
    picks = [g[0] for g in gs]
    curves = [g[1] for g in gs]

    print("k   optimal (greedy, acc over seeds)      evenly-spaced")
    for k in range(1, K_MAX + 1):
        opt = 100 * np.mean([c[k-1] for c in curves])
        even = 100 * np.mean([eval_set(d, evenly(k)) for d in datas])
        ang = picks[0][:k]
        print(f"{k}   {opt:5.1f}%   angles {ang}   {even:5.1f}%")

    print(f"\nchosen set consensus:")
    for i in range(K_MAX):
        print(f"  pick {i+1}: {[p[i] for p in picks]}")


if __name__ == "__main__":
    main()
