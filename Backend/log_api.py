from flask import Blueprint, jsonify
import json
import os
import re
from datetime import datetime

log_bp = Blueprint("log_api", __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "notifier.log")

aggregated = {}
last_modified = 0


def parse_log_file():
    global aggregated, last_modified

    if not os.path.exists(LOG_FILE):
        return

    current_mtime = os.path.getmtime(LOG_FILE)
    if current_mtime == last_modified:
        return
    last_modified = current_mtime

    new_aggregated = {}

    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as handle:
        content = handle.read()

    for line in content.splitlines():
        match = re.search(r"payload='(\{.*?\})'", line)
        if not match:
            continue

        try:
            json_str = re.sub(r"\s*:\s*", ":", match.group(1))
            data = json.loads(json_str)

            src = data.get("src", "0.0.0.0:0")
            src_ip = src.split(":")[0] if ":" in src else src
            src_port = src.split(":")[1] if ":" in src else "?"

            dst = data.get("dst", "0.0.0.0:0")
            dst_ip = dst.split(":")[0] if ":" in dst else dst
            dst_port = dst.split(":")[1] if ":" in dst else "?"

            name = data.get("name", "Alerte inconnue")
            severity = data.get("severity", "low").lower()
            proto = data.get("proto", "TCP")
            alert_id = data.get("id", 0)

            ts_raw = data.get("timestamp", "")
            if ts_raw:
                timestamp = ts_raw.split(".")[0].split("+")[0]
            else:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            key = f"{src_ip}|||{name}"

            if key in new_aggregated:
                new_aggregated[key]["count"] += 1
                new_aggregated[key]["last_seen"] = timestamp
                if alert_id and alert_id not in new_aggregated[key]["ids"]:
                    new_aggregated[key]["ids"].append(alert_id)
            else:
                new_aggregated[key] = {
                    "name": name,
                    "severity": severity,
                    "src_ip": src_ip,
                    "src_port": src_port,
                    "dst_ip": dst_ip,
                    "dst_port": dst_port,
                    "proto": proto,
                    "count": 1,
                    "first_seen": timestamp,
                    "last_seen": timestamp,
                    "ids": [alert_id] if alert_id else [],
                }
        except Exception:
            continue

    aggregated = new_aggregated


@log_bp.route("/api/logs")
def get_logs():
    parse_log_file()
    logs = list(aggregated.values())
    logs.sort(key=lambda item: item["last_seen"], reverse=True)
    total_raw = sum(item["count"] for item in logs)

    return jsonify(
        {
            "success": True,
            "raw_count": total_raw,
            "aggregated_count": len(logs),
            "unique_ips": len(set(item["src_ip"] for item in logs)),
            "rate_per_minute": len(logs),
            "logs": logs,
        }
    )


@log_bp.route("/api/reset", methods=["POST"])
def reset():
    global aggregated
    aggregated = {}
    return jsonify({"success": True})


@log_bp.route("/api/status")
def status():
    return jsonify(
        {
            "success": True,
            "file_exists": os.path.exists(LOG_FILE),
            "file_path": LOG_FILE,
            "aggregated_count": len(aggregated),
        }
    )
