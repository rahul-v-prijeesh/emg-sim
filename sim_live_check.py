"""sim_live_check.py - runs the REAL live.py without a window and prints what the screen would show.

Used by sim_selftest.py. It replaces tkinter with a stand-in, so live.py's own code (reading samples,
cleaning, features, model, FAULT detection, talking to the RTC unit, writing gesture_log.csv) runs
unchanged. Run from the folder that holds model.joblib.

    python sim_live_check.py --seconds 30 [--rtc socket://127.0.0.1:7002]
"""
import json, os, sys, time
from unittest.mock import MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

seconds = float(sys.argv[sys.argv.index("--seconds") + 1])
passthrough = [a for i, a in enumerate(sys.argv[1:], 1)
               if a != "--seconds" and sys.argv[i - 1] != "--seconds"]

tk = MagicMock()
sys.modules["tkinter"] = tk
root = MagicMock()
tk.Tk.return_value = root
callback = {}
root.after.side_effect = lambda ms, fn: callback.__setitem__("update", fn)
g = {"__name__": "live_under_test"}
timeline = []


def fake_mainloop():
    t0 = time.time()
    while time.time() - t0 < seconds:
        callback["update"]()                      # live.py's own screen-update function
        last = g.get("last")
        if last is not None:
            if "error" in last:
                screen = "LINK LOST"
            elif time.time() - last["t"] > 1.0:
                screen = "NO DATA"
            elif last["problem"]:
                screen = "SENSOR FAULT"
            else:
                screen = str(last["shown"])
            timeline.append((round(time.time() - t0, 2), screen))
        time.sleep(0.05)


root.mainloop.side_effect = fake_mainloop
sys.argv = ["live.py"] + passthrough
exec(compile(open(os.path.join(HERE, "live.py"), encoding="utf-8").read(), "live.py", "exec"), g)
print("TIMELINE " + json.dumps(timeline))
