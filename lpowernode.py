#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль управления LPowerNode 2PDU по SNMP v1.
Чистый Python (только стандартная библиотека), без pysnmp.

Выход 1: 1.3.6.1.4.1.43672.1.1.1.3.1.1.3.0
Выход 2: 1.3.6.1.4.1.43672.1.1.1.3.1.1.3.1
Community: public
"""

import socket
import logging
import random

log = logging.getLogger(__name__)

OID_OUT1 = "1.3.6.1.4.1.43672.1.1.1.3.1.1.3.0"
OID_OUT2 = "1.3.6.1.4.1.43672.1.1.1.3.1.1.3.1"
COMMUNITY = "public"
SNMP_TIMEOUT = 1
SNMP_PORT = 161
OUTLETS = {"out1": OID_OUT1, "out2": OID_OUT2}

# совместимость с server.py
PYSNMP_AVAILABLE = True


# ------------------------------------------------------------------
# BER / ASN.1 — кодирование
# ------------------------------------------------------------------
def _ber_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    out = []
    while n > 0:
        out.insert(0, n & 0xFF)
        n >>= 8
    return bytes([0x80 | len(out)]) + bytes(out)


def _ber_int(n: int) -> bytes:
    if n == 0:
        body = b"\x00"
    else:
        body = []
        v = n
        while v > 0:
            body.insert(0, v & 0xFF)
            v >>= 8
        if body[0] & 0x80:
            body.insert(0, 0x00)
        body = bytes(body)
    return b"\x02" + _ber_len(len(body)) + body


def _ber_octet_string(s: bytes) -> bytes:
    return b"\x04" + _ber_len(len(s)) + s


def _ber_null() -> bytes:
    return b"\x05\x00"


def _ber_oid(oid_str: str) -> bytes:
    parts = [int(x) for x in oid_str.split(".")]
    first = parts[0] * 40 + parts[1]
    body = [first]
    for p in parts[2:]:
        if p < 0x80:
            body.append(p)
        else:
            stack = []
            v = p
            stack.insert(0, v & 0x7F)
            v >>= 7
            while v > 0:
                stack.insert(0, (v & 0x7F) | 0x80)
                v >>= 7
            body.extend(stack)
    body = bytes(body)
    return b"\x06" + _ber_len(len(body)) + body


def _ber_seq(*items: bytes) -> bytes:
    body = b"".join(items)
    return b"\x30" + _ber_len(len(body)) + body


# ------------------------------------------------------------------
# BER / ASN.1 — декодирование
# ------------------------------------------------------------------
class BERError(Exception):
    pass


def _read_tlv(data: bytes, i: int):
    """
    Читает один TLV по смещению i.
    Возвращает (tag, value_bytes, new_index).
    Бросает BERError при выходе за границы.
    """
    if i >= len(data):
        raise BERError(f"read past end at {i} (len={len(data)})")
    tag = data[i]
    i += 1
    if i >= len(data):
        raise BERError(f"missing length byte at {i}")
    first = data[i]
    i += 1
    if first < 0x80:
        length = first
    else:
        n = first & 0x7F
        if n == 0:
            raise BERError("indefinite length not supported")
        if i + n > len(data):
            raise BERError(f"length bytes exceed buffer at {i}")
        length = 0
        for _ in range(n):
            length = (length << 8) | data[i]
            i += 1
    if i + length > len(data):
        raise BERError(f"value exceeds buffer: need {length}, have {len(data) - i}")
    value = data[i:i + length]
    return tag, value, i + length


def _decode_int(b: bytes) -> int:
    if not b:
        return 0
    v = int.from_bytes(b, "big", signed=True)
    return v


# ------------------------------------------------------------------
# SNMP v1: одна операция GET или SET
# ------------------------------------------------------------------
def _snmp_request(ip: str, community: str, pdu_type: int, oid: str, value=None):
    """
    pdu_type: 0xA0 = GetRequest, 0xA3 = SetRequest
    value:    int для SetRequest, иначе None (GetRequest)
    Возвращает int (значение из ответа).
    """
    req_id = random.randint(1, 0x7FFFFFFF)

    varbind_parts = [_ber_oid(oid)]
    if value is None:
        varbind_parts.append(_ber_null())
    else:
        varbind_parts.append(_ber_int(int(value)))
    varbind = _ber_seq(*varbind_parts)
    varbind_list = _ber_seq(varbind)

    inner_pdu = _ber_int(req_id) + _ber_int(0) + _ber_int(0) + varbind_list
    pdu = bytes([pdu_type]) + _ber_len(len(inner_pdu)) + inner_pdu

    msg = _ber_seq(_ber_int(0), _ber_octet_string(community.encode("ascii")), pdu)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(SNMP_TIMEOUT)
    try:
        sock.sendto(msg, (ip, SNMP_PORT))
        data, _ = sock.recvfrom(65535)
    finally:
        sock.close()

    if len(data) < 10:
        raise BERError(f"response too short: {data!r}")

    # --- верхний уровень: SEQUENCE ---
    tag, body, _ = _read_tlv(data, 0)
    if tag != 0x30:
        raise BERError(f"expected SEQUENCE, got 0x{tag:02X}")

    # --- version ---
    tag, ver_b, i = _read_tlv(body, 0)
    if tag != 0x02:
        raise BERError(f"expected INTEGER (version), got 0x{tag:02X}")

    # --- community ---
    tag, comm_b, i = _read_tlv(body, i)
    if tag != 0x04:
        raise BERError(f"expected OCTET STRING (community), got 0x{tag:02X}")

    # --- PDU ---
    tag, pdu_body, i = _read_tlv(body, i)
    if tag == 0xA2:
        pass                                  # GetResponse
    elif tag == 0xA8:
        raise BERError("SNMP noSuchName (0xA8)")
    elif tag == 0xA9:
        raise BERError("SNMP badValue (0xA9)")
    elif tag == 0xA5:
        raise BERError("unexpected GetNext (0xA5)")
    elif tag == 0xA3:
        raise BERError("got SetRequest back (0xA3)")
    else:
        raise BERError(f"unexpected PDU tag 0x{tag:02X}")

    # --- внутри PDU: request-id, error-status, error-index, varbind-list ---
    tag, reqid_b, j = _read_tlv(pdu_body, 0)
    if tag != 0x02:
        raise BERError("expected INTEGER (request-id)")

    tag, err_status_b, j = _read_tlv(pdu_body, j)
    if tag != 0x02:
        raise BERError("expected INTEGER (error-status)")

    tag, err_index_b, j = _read_tlv(pdu_body, j)
    if tag != 0x02:
        raise BERError("expected INTEGER (error-index)")

    err_status = _decode_int(err_status_b)
    if err_status != 0:
        raise BERError(f"SNMP error-status={err_status}")

    # --- varbind-list ---
    tag, vbl_body, j = _read_tlv(pdu_body, j)
    if tag != 0x30:
        raise BERError("expected SEQUENCE (varbind-list)")

    # --- один varbind ---
    tag, vb_body, k = _read_tlv(vbl_body, 0)
    if tag != 0x30:
        raise BERError("expected SEQUENCE (varbind)")

    # OID внутри varbind
    tag, oid_b, k2 = _read_tlv(vb_body, 0)
    if tag != 0x06:
        raise BERError("expected OID in varbind")

    # value внутри varbind
    tag, val_b, _ = _read_tlv(vb_body, k2)

    if tag in (0x02, 0x41, 0x42, 0x43, 0x46):
        return _decode_int(val_b)
    if tag == 0x04:
        return val_b
    if tag == 0x05:
        return None
    raise BERError(f"unsupported value tag 0x{tag:02X}")


# ------------------------------------------------------------------
# Публичный API
# ------------------------------------------------------------------
def get_outlet_state(ip: str, outlet: str) -> dict:
    oid = OUTLETS.get(outlet)
    if not oid:
        return {"ok": False, "state": None, "error": f"unknown outlet '{outlet}'"}
    try:
        value = _snmp_request(ip, COMMUNITY, 0xA0, oid)
        return {"ok": True, "state": int(value), "error": None}
    except socket.timeout:
        return {"ok": False, "state": None, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "state": None, "error": f"{type(e).__name__}: {e}"}


def set_outlet_state(ip: str, outlet: str, state: int) -> dict:
    oid = OUTLETS.get(outlet)
    if not oid:
        return {"ok": False, "error": f"unknown outlet '{outlet}'"}
    state = 1 if int(state) else 0
    try:
        _snmp_request(ip, COMMUNITY, 0xA3, oid, value=state)
        return {"ok": True, "state": state, "error": None}
    except socket.timeout:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def get_all_states(ip: str) -> dict:
    result = {"ok": True, "out1": None, "out2": None, "error": None}
    for name in ("out1", "out2"):
        r = get_outlet_state(ip, name)
        if r["ok"]:
            result[name] = r["state"]
        else:
            result["ok"] = False
            result["error"] = r["error"]
    return result