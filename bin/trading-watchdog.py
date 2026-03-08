#!/usr/bin/env python3
"""Enterprise watchdog: 3-tier escalation (restart -> Telegram -> SMS), health JSON, heartbeat."""

import subprocess, time, urllib.request, urllib.parse, json, logging, os, socket, base64
from datetime import datetime, timezone

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', open(os.path.expanduser('~/.secrets/telegram-bot'), 'r').read().strip() if os.path.exists(os.path.expanduser('~/.secrets/telegram-bot')) else '')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '1486798034')
LOG = "/home/pai-server/trading/watchdog.log"
HEALTH_FILE = "/home/pai-server/trading/system-health.json"
HEARTBEAT_FILE = "/home/pai-server/trading/watchdog-heartbeat.json"
DB_PATH = "/home/pai-server/trading/rc-scanner.db"

_twilio = json.loads(open(os.path.expanduser('~/.secrets/twilio-config')).read()) if os.path.exists(os.path.expanduser('~/.secrets/twilio-config')) else {}
TWILIO_SID   = os.environ.get('TWILIO_SID', _twilio.get('account_sid',''))
TWILIO_TOKEN = os.environ.get('TWILIO_TOKEN', _twilio.get('auth_token',''))
TWILIO_FROM  = os.environ.get('TWILIO_FROM', _twilio.get('from_number','+447480821400'))
KELVIN_PHONE = os.environ.get('KELVIN_PHONE', '+447449986222')

logging.basicConfig(filename=LOG, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

SERVICES = [
    {"name": "rc-ws-bridge",       "label": "WebSocket Bridge",  "critical": True,  "port": 8765},
    {"name": "rc-research-server", "label": "Research Server",   "critical": True,  "port": 8767},
    {"name": "daytrade-dash",      "label": "Dashboard",         "critical": True,  "port": 3456},
    {"name": "trading-signals",    "label": "Trading Signals",   "critical": False, "port": 8085},
]

incident_state = {}
alerts_log = []

def tg(msg):
    try:
        data = json.dumps({"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        logging.error(f"Telegram send failed: {e}")

def send_sms(msg):
    try:
        auth = base64.b64encode(f"{TWILIO_SID}:{TWILIO_TOKEN}".encode()).decode()
        data = urllib.parse.urlencode({"From": TWILIO_FROM, "To": KELVIN_PHONE, "Body": msg}).encode()
        req = urllib.request.Request(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
            data=data,
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            ok = r.status == 201
            if ok: logging.info(f"SMS sent: {msg[:60]}")
            return ok
    except Exception as e:
        logging.error(f"SMS failed: {e}")
        return False

def is_systemd_active(service):
    r = subprocess.run(["systemctl", "--user", "is-active", service],
                       capture_output=True, text=True)
    return r.stdout.strip() == "active"

def get_uptime_mins(service):
    try:
        r = subprocess.run(["systemctl", "--user", "show", service, "-p", "ActiveEnterTimestamp", "--value"],
                           capture_output=True, text=True)
        val = r.stdout.strip()
        if not val: return 0
        # Parse: "Sun 2026-03-08 11:00:00 UTC"
        parts = val.split(" ", 1)
        if len(parts) > 1 and len(parts[0]) <= 3:
            val = parts[1]
        try:
            ts = datetime.strptime(val, "%Y-%m-%d %H:%M:%S %Z")
        except:
            ts = datetime.strptime(val.rsplit(" ", 1)[0], "%Y-%m-%d %H:%M:%S")
        diff = (datetime.utcnow() - ts).total_seconds()
        return max(0, diff / 60)
    except:
        return 0

def check_port(port):
    if not port: return True
    try:
        s = socket.create_connection(("localhost", port), timeout=2)
        s.close()
        return True
    except:
        return False

def check_eodhd():
    try:
        key = open(os.path.expanduser("~/.secrets/eodhd-api")).read().strip()
        url = f"https://eodhd.com/api/exchange-symbol-list/US?api_token={key}&fmt=json&type=common_stock"
        with urllib.request.urlopen(url, timeout=8) as r:
            return r.status == 200
    except:
        return False

def get_db_stats():
    try:
        import sqlite3
        size_mb = os.path.getsize(DB_PATH) / (1024 * 1024) if os.path.exists(DB_PATH) else 0
        c = sqlite3.connect(DB_PATH)
        candidates = c.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        trades = c.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        c.close()
        return {"status": "up", "size_mb": round(size_mb, 2), "candidates": candidates, "trades": trades}
    except Exception as e:
        return {"status": "error", "error": str(e)[:80]}

def add_alert(msg):
    alerts_log.append({"time": datetime.utcnow().isoformat() + "Z", "message": msg})
    if len(alerts_log) > 20:
        alerts_log.pop(0)

def build_health_snapshot():
    now = datetime.utcnow().isoformat() + "Z"
    services = {}
    any_critical_down = False
    any_down = False

    for svc in SERVICES:
        name = svc["name"]
        active = is_systemd_active(name)
        port_ok = check_port(svc["port"])
        is_up = active and port_ok
        uptime = get_uptime_mins(name) if active else 0
        services[name] = {
            "status": "up" if is_up else "down",
            "label": svc["label"],
            "port_ok": port_ok,
            "uptime_mins": round(uptime, 1),
        }
        if not is_up:
            any_down = True
            if svc["critical"]: any_critical_down = True

    h = datetime.utcnow().hour
    eodhd_status = "up"
    if 3 <= h <= 21:
        if not check_eodhd(): eodhd_status = "down"

    overall = "down" if any_critical_down else ("degraded" if any_down else "healthy")

    return {
        "timestamp": now,
        "overall": overall,
        "watchdog_ok": True,
        "services": services,
        "eodhd": {"status": eodhd_status, "last_check": now},
        "db": get_db_stats(),
        "alerts": alerts_log[-10:],
    }

def write_health(health):
    try:
        tmp = HEALTH_FILE + ".tmp"
        with open(tmp, 'w') as f:
            json.dump(health, f, indent=2)
        os.replace(tmp, HEALTH_FILE)
    except Exception as e:
        logging.error(f"Failed to write health: {e}")

def write_heartbeat():
    try:
        tmp = HEARTBEAT_FILE + ".tmp"
        with open(tmp, 'w') as f:
            json.dump({"timestamp": datetime.utcnow().isoformat() + "Z"}, f)
        os.replace(tmp, HEARTBEAT_FILE)
    except Exception as e:
        logging.error(f"Failed to write heartbeat: {e}")

heartbeat_counter = 0

def run():
    global heartbeat_counter
    logging.info("Watchdog v2 started - 3-tier escalation active")
    tg("\U0001f6e1\ufe0f <b>Trading Watchdog v2 Started</b>\n3-tier escalation: Restart \u2192 Telegram \u2192 SMS\nMonitoring: " + ", ".join(s["label"] for s in SERVICES))

    while True:
        try:
            health = build_health_snapshot()
            write_health(health)
            heartbeat_counter += 1
            if heartbeat_counter % 2 == 0:
                write_heartbeat()

            for svc in SERVICES:
                name = svc["name"]
                active = is_systemd_active(name)
                port_ok = check_port(svc["port"])
                is_up = active and port_ok

                if is_up:
                    if name in incident_state:
                        mins_down = (time.time() - incident_state[name]["start"]) / 60
                        tg(f"\u2705 <b>{svc['label']}</b> recovered after {mins_down:.0f} minutes")
                        add_alert(f"RECOVERED: {svc['label']} after {mins_down:.0f}m")
                        logging.info(f"{name} recovered after {mins_down:.0f}m")
                        del incident_state[name]
                else:
                    if name not in incident_state:
                        incident_state[name] = {"start": time.time(), "tier": 0, "restart_count": 0}
                    inc = incident_state[name]
                    mins_down = (time.time() - inc["start"]) / 60

                    if inc["tier"] == 0:
                        subprocess.run(["systemctl", "--user", "restart", name])
                        inc["restart_count"] += 1
                        inc["tier"] = 1
                        logging.warning(f"[T1] Auto-restarted {name}")
                        add_alert(f"T1 RESTART: {svc['label']}")
                    elif inc["tier"] == 1 and mins_down >= 2:
                        tg(f"\U0001f534 <b>ALERT: {svc['label']} DOWN</b>\nDown for {mins_down:.0f} mins. Restart attempted {inc['restart_count']}x.\nChecking again in 3 minutes...")
                        add_alert(f"T2 TELEGRAM: {svc['label']} down {mins_down:.0f}m")
                        logging.error(f"[T2] {name} still down after {mins_down:.0f}m")
                        inc["tier"] = 2
                    elif inc["tier"] == 2 and mins_down >= 5:
                        send_sms(f"TRADING ALERT: {svc['label']} has been down {mins_down:.0f} mins. Manual intervention needed. Check dashboard.")
                        tg(f"\U0001f6a8 <b>SMS SENT</b> \u2014 {svc['label']} still down after {mins_down:.0f} mins")
                        add_alert(f"T3 SMS: {svc['label']} down {mins_down:.0f}m")
                        logging.critical(f"[T3] SMS sent for {name} - down {mins_down:.0f}m")
                        inc["tier"] = 3

        except Exception as e:
            logging.error(f"Watchdog loop error: {e}")

        time.sleep(30)

if __name__ == "__main__":
    run()
