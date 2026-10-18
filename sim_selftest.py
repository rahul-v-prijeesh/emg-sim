"""sim_selftest.py - one command that exercises the whole project against the simulators.

    python sim_selftest.py          (takes about 2 minutes; no hardware, no window)

It works in a temporary folder, so it never touches your own recordings or model.joblib. Steps:
  1. start the simulated Arduino RTC unit, run uno_test.py and set_rtc.py against it
  2. start the simulated ESP32 and let record.py record a full 5 gestures x 6 repetitions session
  3. plot_check.py, train_subsets.py, train_final.py on that recording
  4. run the real live.py (without a window) while gestures change, a sensor is unplugged and re-plugged,
     and check what it shows and what ends up in gesture_log.csv

The data is simulated, so PASS means "the software does what it should", not "EMG works on a human".
"""
import csv, datetime, json, os, re, shutil, socket, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
ESP_PORT, UNO_PORT = 7001, 7002
URL_E, URL_U = f"socket://127.0.0.1:{ESP_PORT}", f"socket://127.0.0.1:{UNO_PORT}"
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""), flush=True)


def run(args, cwd, env=None, timeout=300):
    e = dict(os.environ, PYTHONUNBUFFERED="1")
    e.pop("EMG_PORT", None)
    e.update(env or {})
    return subprocess.run([PY, "-u"] + args, cwd=cwd, env=e, capture_output=True, text=True, timeout=timeout)


def wait_port(port, seconds=15):
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            socket.create_connection(("127.0.0.1", port), 0.5).close()
            return True
        except OSError:
            time.sleep(0.2)
    return False


def is_subsequence(want, got):
    it = iter(got)
    return all(any(w == g for g in it) for w in want)


def main():
    tmp = tempfile.mkdtemp(prefix="emg_selftest_")
    procs = []
    print(f"working in {tmp}\n")
    try:
        # ------------------------------------------------------------ 1. RTC unit
        print("1) Arduino RTC unit (simulated)")
        uno = subprocess.Popen([PY, "-u", os.path.join(HERE, "sim_uno.py")], cwd=tmp,
                               stdout=open(os.path.join(tmp, "sim_uno.log"), "w"), stderr=subprocess.STDOUT)
        procs.append(uno)
        check("sim_uno.py started", wait_port(UNO_PORT))
        r = run([os.path.join(HERE, "uno_test.py"), URL_U], tmp)
        check("uno_test.py reports ALL OK", "ALL OK" in r.stdout, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:])
        r = run([os.path.join(HERE, "set_rtc.py"), URL_U], tmp)
        m = re.search(r"TIME (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", r.stdout)
        ok = False
        if m:
            got = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            ok = abs((datetime.datetime.now() - got).total_seconds()) < 10
        check("set_rtc.py sets the clock to the PC time", ok, m.group(1) if m else r.stdout[-200:] + r.stderr[-200:])

        # ------------------------------------------------------------ 2. recording
        print("\n2) Recording a full session with record.py (simulated ESP32, 20x speed)")
        r = run([os.path.join(HERE, "sim_esp32.py"), "--run-record", "simtest", "1", "--speed", "20", "--seed", "1"],
                tmp, timeout=400)
        check("record.py finished without error", r.returncode == 0, r.stderr[-200:])
        csvp = os.path.join(tmp, "emg_simtest_day1.csv")
        rows = labels = None
        if os.path.exists(csvp):
            with open(csvp) as f:
                data = list(csv.DictReader(f))
            rows = len(data)
            labels = sorted({d["label"] for d in data})
        check("CSV has 90000 rows (5 gestures x 6 reps x 3000 samples)", rows == 90000, f"{rows} rows")
        check("all 5 gestures present", labels == sorted(["REST", "OPEN", "CLOSE", "PINCH", "INDEX"]), str(labels))
        check("no sensor warnings during recording", "WARNING" not in r.stdout)

        # ------------------------------------------------------------ 3. analysis + training
        print("\n3) plot_check, train_subsets, train_final")
        r = run([os.path.join(HERE, "plot_check.py"), "emg_simtest_day1.csv"], tmp)
        check("plot_check.py made the PNG", os.path.exists(os.path.join(tmp, "emg_simtest_day1_plot.png")), r.stderr[-200:])
        r = run([os.path.join(HERE, "train_subsets.py"), "emg_simtest_day1.csv"], tmp)
        m = re.search(r"^S1\+S2\+S3\s+([\d.]+)\s+([\d.]+)", r.stdout, re.M)
        lda = float(m.group(1)) if m else -1
        check("train_subsets.py: LDA same-day accuracy with all 3 sensors >= 80%", lda >= 80, f"LDA {lda}%")
        rule = re.search(r"RULE:.*", r.stdout)
        if rule:
            print("      " + rule.group(0))
        r = run([os.path.join(HERE, "train_final.py"), "0,1,2", "emg_simtest_day1.csv"], tmp)
        check("train_final.py saved model.joblib", os.path.exists(os.path.join(tmp, "model.joblib")), r.stderr[-200:])

        # ------------------------------------------------------------ 4. live.py
        print("\n4) live.py (real code, no window) with gestures, a fault and the RTC unit - takes about 40 s")
        esp = subprocess.Popen([PY, "-u", os.path.join(HERE, "sim_esp32.py"), "--seed", "2"], cwd=tmp,
                               stdin=subprocess.PIPE, stdout=open(os.path.join(tmp, "sim_esp32.log"), "w"),
                               stderr=subprocess.STDOUT, text=True)
        procs.append(esp)
        check("sim_esp32.py started", wait_port(ESP_PORT))
        env = dict(os.environ, EMG_PORT=URL_E, PYTHONUNBUFFERED="1")
        live = subprocess.Popen([PY, "-u", os.path.join(HERE, "sim_live_check.py"), "--seconds", "36", "--rtc", URL_U],
                                cwd=tmp, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        send = lambda c: (esp.stdin.write(c + "\n"), esp.stdin.flush())
        time.sleep(7)                                   # start-up + a few seconds of REST
        for g in ("open", "close", "pinch", "index"):
            send(g); time.sleep(4)
        send("unplug 2"); time.sleep(4)
        send("ok"); time.sleep(4)
        out, err = live.communicate(timeout=60)
        m = re.search(r"^TIMELINE (.*)$", out, re.M)
        timeline = json.loads(m.group(1)) if m else []
        screens = [s for _, s in timeline]
        check("live.py ran and produced screen updates", len(timeline) > 100, f"{len(timeline)} updates" + (("; " + err[-300:]) if not m else ""))
        check("screen showed SENSOR FAULT when sensor 2 was unplugged", "SENSOR FAULT" in screens)
        check("screen never showed LINK LOST", "LINK LOST" not in screens)
        check("screen NO DATA for less than 1 s in total", screens.count("NO DATA") < 20, f"{screens.count('NO DATA')} updates")
        seen = [s for i, s in enumerate(screens) if i == 0 or s != screens[i - 1]]
        check("screen went REST -> OPEN -> CLOSE -> PINCH -> INDEX in order",
              is_subsequence(["REST", "OPEN", "CLOSE", "PINCH", "INDEX"], seen), " > ".join(seen))
        logp = os.path.join(tmp, "gesture_log.csv")
        events = []
        if os.path.exists(logp):
            with open(logp) as f:
                events = list(csv.DictReader(f))
        names = [e["gesture"] for e in events]
        check("gesture_log.csv has RTC-stamped changes in the right order",
              is_subsequence(["REST", "OPEN", "CLOSE", "PINCH", "INDEX", "FAULT", "INDEX"], names),
              " > ".join(names))
        stamped = bool(events) and all(re.match(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$", e["rtc_time"]) for e in events)
        check("every log row has a valid date-time stamp", stamped)
    finally:
        for p in procs:
            try:
                p.terminate()
            except OSError:
                pass
        time.sleep(0.5)
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
