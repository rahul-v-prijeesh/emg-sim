"""run_live.py - start everything with ONE command.

Starts sim_esp32.py and sim_uno.py in the background, then runs the real live.py
against them. Works with a GUI (X11 / VcXsrv) or in the terminal.

    python run_live.py              # GUI window if a display is available
    python run_live.py --terminal   # force terminal output
    python run_live.py --auto       # sim cycles gestures by itself (hands-free)

Ctrl+C stops live.py and shuts the simulators down cleanly.
"""
import argparse, os, signal, socket, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
ESP32_PORT, UNO_PORT = 7001, 7002


def port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for(port, timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if port_open(port):
            return True
        time.sleep(0.2)
    return False


def free_port(port):
    """Kill whatever is listening on a local port (our own leftover simulators)."""
    try:
        out = subprocess.check_output(["ss", "-tlnp"], stderr=subprocess.DEVNULL).decode()
    except Exception:
        return
    for line in out.splitlines():
        if f":{port} " in line and "pid=" in line:
            pid = line.split("pid=")[1].split(",")[0]
            try:
                os.kill(int(pid), signal.SIGTERM)
                print(f"[run_live] freed port {port} (killed pid {pid})", flush=True)
                time.sleep(0.5)
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--terminal", action="store_true", help="force terminal (no GUI)")
    ap.add_argument("--auto", action="store_true", help="sim cycles through gestures by itself")
    ap.add_argument("--restart", action="store_true", help="kill any running simulators first")
    args = ap.parse_args()

    if args.restart:
        free_port(ESP32_PORT)
        free_port(UNO_PORT)

    procs = []

    def cleanup(*_):
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
        print("\n[run_live] stopped.", flush=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    if not port_open(ESP32_PORT):
        print(f"[run_live] starting sim_esp32.py on {ESP32_PORT}...", flush=True)
        esp = subprocess.Popen([PY, os.path.join(HERE, "sim_esp32.py")] +
                               (["--auto", "4"] if args.auto else []), cwd=HERE)
        procs.append(esp)
        if not wait_for(ESP32_PORT):
            print("[run_live] ERROR: sim_esp32 did not start", file=sys.stderr)
            cleanup()
    else:
        print(f"[run_live] sim_esp32 already running on {ESP32_PORT}", flush=True)

    if not port_open(UNO_PORT):
        print(f"[run_live] starting sim_uno.py on {UNO_PORT}...", flush=True)
        uno = subprocess.Popen([PY, os.path.join(HERE, "sim_uno.py")], cwd=HERE)
        procs.append(uno)
        if not wait_for(UNO_PORT):
            print("[run_live] ERROR: sim_uno did not start", file=sys.stderr)
            cleanup()
    else:
        print(f"[run_live] sim_uno already running on {UNO_PORT}", flush=True)

    env = dict(os.environ, EMG_PORT=f"socket://127.0.0.1:{ESP32_PORT}")
    cmd = [PY, os.path.join(HERE, "live.py"),
           "--rtc", f"socket://127.0.0.1:{UNO_PORT}"]
    if args.terminal or not os.environ.get("DISPLAY"):
        cmd.append("--terminal")
    print(f"[run_live] running: {' '.join(cmd)}\n", flush=True)

    live = subprocess.Popen(cmd, cwd=HERE, env=env)
    procs.append(live)
    try:
        live.wait()
    except KeyboardInterrupt:
        pass
    cleanup()


if __name__ == "__main__":
    main()
