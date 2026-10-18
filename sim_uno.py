"""sim_uno.py - SIMULATED Arduino Uno + DS3231 RTC unit. No hardware needed.

It follows arduino/rtc_uno/rtc_uno.ino line by line (same commands, same replies, same limits), but
listens on a local TCP port so your normal scripts can connect to it instead of COM6:

    python sim_uno.py
    python uno_test.py   socket://127.0.0.1:7002
    python set_rtc.py    socket://127.0.0.1:7002
    python live.py --rtc socket://127.0.0.1:7002

Options to rehearse things that go wrong on real hardware:
    --lost-power   the coin cell was empty: boots with "RTC LOST POWER" and a wrong date (2000-01-01)
    --no-rtc       the DS3231 is not wired: boots with "RTC FAILED", every command answers "ERR NO RTC"

Everything the program sends ("<-") and everything the Uno answers ("->") is printed, so you can
watch the protocol.
"""
import argparse, re, socket, threading, time
from datetime import datetime, timedelta

HOST = "127.0.0.1"
WORDS = ["REST", "OPEN", "CLOSE", "PINCH", "INDEX", "FAULT"]
BUF = 32                                   # char buf[32] in the sketch: 31 usable characters


class Uno:
    def __init__(self, lost_power, no_rtc):
        self.rtc_ok = not no_rtc
        self.lost = lost_power and self.rtc_ok
        # the DS3231 keeps its own time, even when the Uno restarts: keep an offset from the PC clock
        self.offset = (datetime(2000, 1, 1) - datetime.now()) if self.lost else timedelta(0)
        self.last = -1

    def stamp(self):
        return (datetime.now() + self.offset).strftime("%Y-%m-%d %H:%M:%S")

    def handle(self, s):
        """One complete line from the laptop -> list of reply lines (same logic as handleLine())."""
        if s == "TIME?":
            return ["TIME " + self.stamp()] if self.rtc_ok else ["ERR NO RTC"]
        if s.startswith("SET "):
            m = re.match(r"\s*(-?\d+)-(\d+)-(\d+)\s+(\d+):(\d+):(\d+)", s[4:])
            if self.rtc_ok and m:
                Y, M, D, h, mi, sec = map(int, m.groups())
                if 2000 <= Y <= 2099 and 1 <= M <= 12 and 1 <= D <= 31 and 0 <= h <= 23 \
                        and 0 <= mi <= 59 and 0 <= sec <= 59:
                    try:
                        self.offset = datetime(Y, M, D, h, mi, sec) - datetime.now()
                        self.lost = False
                        return ["OK SET"]
                    except ValueError:             # e.g. 31 February: the real chip would store nonsense
                        return ["ERR SET"]
            return ["ERR SET"]
        for i, w in enumerate(WORDS):
            if s == w:
                if i != self.last:                 # only CHANGES are reported
                    self.last = i
                    return [f"EVT,{self.stamp()},{w}"] if self.rtc_ok else ["ERR NO RTC"]
                return []
        return []                                  # anything else is ignored


def session(conn, uno):
    send = lambda t: (print("  ->", t, flush=True), conn.sendall((t + "\r\n").encode()))
    uno.last = -1                                  # the Uno restarts when the port opens
    print("[sim-uno] program connected (Uno 'restarts', boot message in 1 s)", flush=True)
    time.sleep(1.0)
    send("RTC OK" if uno.rtc_ok else "RTC FAILED")
    if uno.rtc_ok and uno.lost:
        send("RTC LOST POWER - set the time with set_rtc.py")
    buf = bytearray()
    while True:
        data = conn.recv(256)
        if not data:
            return
        for c in data:
            if c == 10:                            # '\n'
                line = buf.decode(errors="ignore")
                buf.clear()
                print("  <-", line, flush=True)
                for r in uno.handle(line):
                    send(r)
            elif c == 13:                          # '\r' ignored
                pass
            elif len(buf) < BUF - 1:
                buf.append(c)
            else:
                buf.clear()                        # too long = garbage, start over (as in the sketch)


def main():
    ap = argparse.ArgumentParser(description="Simulated Arduino RTC unit")
    ap.add_argument("--tcp-port", type=int, default=7002)
    ap.add_argument("--lost-power", action="store_true")
    ap.add_argument("--no-rtc", action="store_true")
    a = ap.parse_args()
    uno = Uno(a.lost_power, a.no_rtc)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, a.tcp_port))
    srv.listen(1)
    print(f"[sim-uno] SIMULATED Arduino RTC unit ready at socket://{HOST}:{a.tcp_port}", flush=True)
    try:
        while True:
            conn, _ = srv.accept()
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            try:
                session(conn, uno)
            except OSError:
                pass
            finally:
                conn.close()
                print("[sim-uno] program disconnected", flush=True)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
