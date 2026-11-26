import json
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests

TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = str(os.environ["TG_CHAT_ID"]).strip()
QUEUES = ["4.2", "5.2"]

API_URL = "https://be-svitlo.oe.if.ua/schedule-by-queue"
STATE_FILE = "state.json"

try:
    KYIV_TZ = ZoneInfo("Europe/Kyiv")
except Exception:
    KYIV_TZ = timezone(timedelta(hours=2))


def load_state():
    default = {
        "last_update_id": 0,
        "quiet_start": "23:00",
        "quiet_end": "07:00",
        "schedules": {},
    }
    if not os.path.exists(STATE_FILE):
        return default
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            default.update(data)
            return default
    except Exception:
        return default


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send_telegram(message):
    api_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    resp = requests.post(
        api_url,
        json={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        },
        timeout=15,
    )
    resp.raise_for_status()


def normalize_time(raw):
    if ":" in raw:
        h_str, m_str = raw.split(":", 1)
        h, m = int(h_str), int(m_str)
    else:
        h, m = int(raw), 0
    if h == 24 and m == 0:
        h = 0
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return f"{h:02d}:{m:02d}"


def to_minutes(hhmm):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def is_quiet_now(state):
    start = state.get("quiet_start")
    end = state.get("quiet_end")
    if not start or not end or start == end:
        return False

    now = datetime.now(KYIV_TZ)
    now_m = now.hour * 60 + now.minute
    start_m = to_minutes(start)
    end_m = to_minutes(end)

    if start_m < end_m:
        return start_m <= now_m < end_m
    return now_m >= start_m or now_m < end_m


def fetch_queue_by_date(queue):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://svitlo.oe.if.ua",
        "Referer": "https://svitlo.oe.if.ua/",
    }
    resp = requests.get(API_URL, params={"queue": queue}, headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    if not data:
        return {"__empty__": "Графік відсутній або світло не вимикають"}

    days = data if isinstance(data, list) else [data]
    result = {}

    for day in days:
        date = str(day.get("eventDate", "Дата невідома"))
        q_items = day.get("queues", {}).get(queue, [])

        if not q_items:
            result[date] = "без відключень"
            continue

        slots = []
        for item in q_items:
            status = item.get("status")
            time_str = item.get("shutdownHours") or f"{item.get('from', '?')}–{item.get('to', '?')}"
            if status == 1 or status is None:
                slots.append(f"🔴 {time_str}")
            elif status == 2:
                slots.append(f"🟡 {time_str} (можливо)")

        result[date] = "\n".join(slots) if slots else "без відключень"

    return result or {"__empty__": str(data)[:400]}


def format_schedules(schedules):
    parts = []
    for q in QUEUES:
        days_map = schedules.get(q, {})
        lines = []
        for date, info in days_map.items():
            if date == "__empty__":
                lines.append(info)
            elif info == "без відключень":
                lines.append(f"📅 <b>{date}:</b> без відключень")
            else:
                lines.append(f"📅 <b>{date}:</b>\n{info}")
        parts.append(f"<b>Черга {q}:</b>\n" + "\n\n".join(lines))
    return "\n\n──────────\n\n".join(parts)


def process_commands(state):
    changed = False
    force_send = False
    api_url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

    try:
        resp = requests.get(
            api_url,
            params={"offset": state.get("last_update_id", 0) + 1, "timeout": 1},
            timeout=15,
        )
        resp.raise_for_status()
        updates = resp.json().get("result", [])
    except Exception:
        return False, False

    for upd in updates:
        upd_id = upd.get("update_id", 0)
        if upd_id > state.get("last_update_id", 0):
            state["last_update_id"] = upd_id
            changed = True

        msg = upd.get("message") or {}
        if str(msg.get("chat", {}).get("id", "")) != CHAT_ID:
            continue

        text = (msg.get("text") or "").strip()
        low = text.lower()

        if low.startswith("/quiet off") or low in ("/off", "off", "вимкнути"):
            state["quiet_start"] = None
            state["quiet_end"] = None
            changed = True
            send_telegram("🔔 Тихий режим вимкнено — графіки приходитимуть цілодобово.")
        elif low.startswith("/now"):
            force_send = True
        elif low.startswith("/status"):
            now_str = datetime.now(KYIV_TZ).strftime("%H:%M")
            qs, qe = state.get("quiet_start"), state.get("quiet_end")
            mode = f"з <b>{qs}</b> до <b>{qe}</b>" if qs and qe else "вимкнено"
            send_telegram(
                f"⚙️ <b>Налаштування:</b>\n"
                f"Зараз (Київ): {now_str}\n"
                f"Тихий режим: {mode}\n\n"
                f"Команди:\n"
                f"• <code>23-7</code> або <code>23:30-07:30</code> — задати тихі години\n"
                f"• <code>/quiet off</code> — вимкнути тихий режим\n"
                f"• <code>/now</code> — надіслати графік зараз"
            )
        else:
            match = re.search(r"(\d{1,2}(?::\d{2})?)\s*[-–—]\s*(\d{1,2}(?::\d{2})?)", text)
            if match:
                t_start = normalize_time(match.group(1))
                t_end = normalize_time(match.group(2))
                if t_start and t_end:
                    state["quiet_start"] = t_start
                    state["quiet_end"] = t_end
                    changed = True
                    send_telegram(
                        f"🌙 Тихий режим збережено: з <b>{t_start}</b> до <b>{t_end}</b>.\n"
                        f"У цей час бот мовчатиме, а якщо графік оновиться за ніч — пришле одразу після {t_end}."
                    )
                else:
                    send_telegram("❌ Некоректний час. Приклад: <code>23-7</code> або <code>22:30-08:00</code>")

    return changed, force_send


def has_schedule_updates(old_schedules, new_schedules):
    for q in QUEUES:
        old_q = old_schedules.get(q, {})
        new_q = new_schedules.get(q, {})
        for date, val in new_q.items():
            if old_q.get(date) != val:
                return True
    return False


def main():
    state = load_state()
    state_changed, force_send = process_commands(state)

    current_schedules = {q: fetch_queue_by_date(q) for q in QUEUES}
    updated = has_schedule_updates(state.get("schedules", {}), current_schedules)

    if force_send:
        send_telegram(f"⚡️ <b>Актуальні графіки (4.2 та 5.2):</b>\n\n{format_schedules(current_schedules)}")
        state["schedules"] = current_schedules
        state_changed = True
    elif updated and not is_quiet_now(state):
        send_telegram(f"⚡️ <b>Оновилися графіки (4.2 та 5.2):</b>\n\n{format_schedules(current_schedules)}")
        state["schedules"] = current_schedules
        state_changed = True

    if state_changed:
        save_state(state)


if __name__ == "__main__":
    main()
