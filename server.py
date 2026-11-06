#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Пример HTTP-сервера для управления LPowerNode 2PDU через lpowernode.py.

Отдаёт статику из static/ и REST API для чтения/установки состояния
двух розеток одного или нескольких PDU.

Запуск: python server.py
Порт:   8081
"""

import time
import logging
from flask import Flask, jsonify, send_from_directory

from lpowernode import get_outlet_state, set_outlet_state, get_all_states

# ------------------------------------------------------------------
# Настройки
# ------------------------------------------------------------------
HTTP_PORT = 8081
STATIC_DIR = "static"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("server")

# ------------------------------------------------------------------
# Конфигурация PDU
# ------------------------------------------------------------------
PDUS = {
    "pdu1": {
        "title": "PDU 1",
        "ip": "192.168.12.12",
    },
    "pdu2": {
        "title": "PDU 2",
        "ip": "192.168.12.23",
    },
}

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")


# ------------------------------------------------------------------
# Статика
# ------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)


# ------------------------------------------------------------------
# API: конфигурация
# ------------------------------------------------------------------
@app.route("/api/config")
def api_config():
    payload = {
        key: {"title": p["title"], "ip": p["ip"]}
        for key, p in PDUS.items()
    }
    return jsonify({"ok": True, "pdus": payload})


# ------------------------------------------------------------------
# API: состояние всех розеток PDU
# ------------------------------------------------------------------
@app.route("/api/pdu/<pdu_id>/status")
def api_pdu_status(pdu_id):
    if pdu_id not in PDUS:
        return jsonify({"ok": False, "error": "unknown pdu"}), 404
    p = PDUS[pdu_id]

    log.info(f"[{pdu_id}] get_all_states {p['ip']}")
    t0 = time.time()
    res = get_all_states(p["ip"])
    dt = time.time() - t0
    log.info(f"[{pdu_id}] ← {res} за {dt*1000:.0f} мс")

    return jsonify({
        "ok": res["ok"],
        "pdu": pdu_id,
        "ip": p["ip"],
        "out1": res["out1"],
        "out2": res["out2"],
        "error": res["error"],
    })


# ------------------------------------------------------------------
# API: состояние одной розетки
# ------------------------------------------------------------------
@app.route("/api/pdu/<pdu_id>/outlet/<outlet>")
def api_outlet_state(pdu_id, outlet):
    if pdu_id not in PDUS:
        return jsonify({"ok": False, "error": "unknown pdu"}), 404
    if outlet not in ("out1", "out2"):
        return jsonify({"ok": False, "error": "outlet must be out1|out2"}), 400
    p = PDUS[pdu_id]

    log.info(f"[{pdu_id}/{outlet}] get_outlet_state {p['ip']}")
    t0 = time.time()
    res = get_outlet_state(p["ip"], outlet)
    dt = time.time() - t0
    log.info(f"[{pdu_id}/{outlet}] ← {res} за {dt*1000:.0f} мс")

    return jsonify({
        "ok": res["ok"],
        "pdu": pdu_id,
        "outlet": outlet,
        "state": res["state"],
        "error": res["error"],
    })


# ------------------------------------------------------------------
# API: установка состояния розетки
# ------------------------------------------------------------------
@app.route("/api/pdu/<pdu_id>/outlet/<outlet>/<action>", methods=["POST"])
def api_outlet_set(pdu_id, outlet, action):
    if pdu_id not in PDUS:
        return jsonify({"ok": False, "error": "unknown pdu"}), 404
    if outlet not in ("out1", "out2"):
        return jsonify({"ok": False, "error": "outlet must be out1|out2"}), 400
    if action not in ("on", "off"):
        return jsonify({"ok": False, "error": "action must be on|off"}), 400

    p = PDUS[pdu_id]
    state = 1 if action == "on" else 0

    log.info(f"[{pdu_id}/{outlet}] set_outlet_state {p['ip']} = {state}")
    t0 = time.time()
    res = set_outlet_state(p["ip"], outlet, state)
    dt = time.time() - t0
    log.info(f"[{pdu_id}/{outlet}] ← {res} за {dt*1000:.0f} мс")

    if not res["ok"]:
        return jsonify({
            "ok": False,
            "pdu": pdu_id,
            "outlet": outlet,
            "error": res.get("error"),
        }), 502

    return jsonify({
        "ok": True,
        "pdu": pdu_id,
        "outlet": outlet,
        "state": res.get("state"),
    })


# ------------------------------------------------------------------
if __name__ == "__main__":
    log.info(f"Сервер запущен: http://0.0.0.0:{HTTP_PORT}")
    for k, p in PDUS.items():
        log.info(f"  {k}: {p['title']} | PDU {p['ip']}")
    app.run(host="0.0.0.0", port=HTTP_PORT, debug=False, threaded=True)