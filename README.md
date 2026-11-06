# LPowerNode 2PDU — веб-панель управления

Веб-интерфейс для управления двумя розетками PDU **LPowerNode 2PDU** по SNMP v1.
Реализован на чистом Python (стандартная библиотека + Flask), без внешних SNMP-библиотек —
BER/ASN.1 кодирование и декодирование SNMP написано вручную.

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/flask-2.x-green)
![SNMP](https://img.shields.io/badge/SNMP-v1-orange)

---

## Возможности

- Чтение состояния двух розеток (`out1`, `out2`) каждого PDU.
- Включение / выключение розеток.
- Поддержка нескольких PDU (список задаётся в `server.py`).
- REST API + простая веб-страница.
- Логирование всех SNMP-запросов с замером времени.
- Чистый Python: только `socket`, `logging`, `random` + Flask.

---

## Структура проекта
```bash
.
├── server.py # HTTP-сервер (Flask) + REST API
├── lpowernode.py # SNMP-клиент (BER/ASN.1, GET/SET)
├── static/
│ └── index.html # Веб-интерфейс
└── README.md
```
text

---

## Требования

- Python 3.8+
- Flask
- Сетевой доступ к PDU по SNMP (UDP/161)
- Community: `public` (по умолчанию)

Установка зависимостей:

```bash
pip install flask
```
Настройка
PDU
Отредактируйте словарь PDUS в server.py:
```bash
python
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
Ключи (pdu1, pdu2, …) используются в URL API и на странице.

SNMP
Параметры в lpowernode.py:

python
COMMUNITY    = "public"
SNMP_TIMEOUT = 1       # секунды
SNMP_PORT    = 161

OID_OUT1 = "1.3.6.1.4.1.43672.1.1.1.3.1.1.3.0"
OID_OUT2 = "1.3.6.1.4.1.43672.1.1.1.3.1.1.3.1"
HTTP
python
HTTP_PORT = 8081
Запуск
bash
python server.py
Вывод:

text
16:49:08 [INFO] server: Сервер запущен: http://0.0.0.0:8081
16:49:08 [INFO] server:   pdu1: PDU 1 | PDU 192.168.12.12
16:49:08 [INFO] server:   pdu2: PDU 2 | PDU 192.168.12.23
Откройте в браузере:

text
http://<ip-сервера>:8081/
REST API
GET /api/config
Список PDU.

json
{
  "ok": true,
  "pdus": {
    "pdu1": { "title": "PDU 1", "ip": "192.168.12.12" },
    "pdu2": { "title": "PDU 2", "ip": "192.168.12.23" }
  }
}
GET /api/pdu/<pdu_id>/status
Состояние обеих розеток PDU.

json
{
  "ok": true,
  "pdu": "pdu1",
  "ip": "192.168.12.12",
  "out1": 1,
  "out2": 0,
  "error": null
}
GET /api/pdu/<pdu_id>/outlet/<outlet>
Состояние одной розетки. <outlet> — out1 или out2.

json
{
  "ok": true,
  "pdu": "pdu1",
  "outlet": "out1",
  "state": 1,
  "error": null
}
POST /api/pdu/<pdu_id>/outlet/<outlet>/<action>
Управление розеткой. <action> — on или off.

json
{
  "ok": true,
  "pdu": "pdu1",
  "outlet": "out1",
  "state": 1
}
Коды ответа:

Код	Причина
200	успех
400	неверный outlet или action
404	неизвестный pdu_id
502	ошибка SNMP (timeout, noSuchName и т.п.)
Значения состояний
state	Значение
1	розетка включена
0	розетка выключена
null	состояние неизвестно (ошибка)
Примеры (curl)
bash
# Конфигурация
curl http://localhost:8081/api/config

# Состояние всех розеток PDU
curl http://localhost:8081/api/pdu/pdu1/status

# Состояние одной розетки
curl http://localhost:8081/api/pdu/pdu1/outlet/out1

# Включить розетку
curl -X POST http://localhost:8081/api/pdu/pdu1/outlet/out1/on

# Выключить розетку
curl -X POST http://localhost:8081/api/pdu/pdu1/outlet/out2/off
Модуль lpowernode.py
Публичное API:

python
from lpowernode import (
    get_outlet_state,
    set_outlet_state,
    get_all_states,
)

get_outlet_state("192.168.12.12", "out1")
# {'ok': True, 'state': 1, 'error': None}

set_outlet_state("192.168.12.12", "out1", 0)
# {'ok': True, 'state': 0, 'error': None}

get_all_states("192.168.12.12")
# {'ok': True, 'out1': 1, 'out2': 0, 'error': None}
Все функции возвращают словарь с полем ok. При ошибке — ok: False и текст в error.
```
Как это работает
lpowernode.py формирует SNMP-пакеты вручную:

BER/ASN.1 — кодирование длины, целых, OCTET STRING, OID, SEQUENCE.

SNMP v1 — сообщение = SEQUENCE { version, community, PDU }.

GetRequest (тег 0xA0) — чтение.

SetRequest (тег 0xA3) — запись (значение INTEGER 0/1).

Ответ разбирается тем же BER-декодером; при error-status != 0 выбрасывается BERError.

Это позволяет работать без pysnmp и прочих зависимостей, кроме Flask на уровне HTTP-сервера.


Логи с временем отклика каждого SNMP-запроса пишутся в stdout server.py.

Ограничения
Только SNMP v1 (не v2c/v3).

Community жёстко задан в lpowernode.py.

Один OID на розетку (состояние = INTEGER 0/1).

Один запрос = один varbind (без батчинга).

threaded=True у Flask — параллельные запросы к разным PDU работают, но каждый SNMP-запрос создаёт новый сокет.
