import os
import requests

TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = os.environ["TG_CHAT_ID"]
QUEUES = ["4.2", "5.2"]

API_URL = "https://be-svitlo.oe.if.ua/schedule-by-queue"
STATE_FILE = "last_schedule.txt"


def fetch_queue(queue):
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
        return "Графік відсутній або світло не вимикають"

    days = data if isinstance(data, list) else [data]
    lines = []

    for day in days:
        date = day.get("eventDate", "Дата невідома")
        q_items = day.get("queues", {}).get(queue, [])

        if not q_items:
            lines.append(f"📅 <b>{date}:</b> без відключень")
            continue

        slots = []
        for item in q_items:
            status = item.get("status")
            time_str = item.get("shutdownHours") or f"{item.get('from', '?')}–{item.get('to', '?')}"
            if status == 1:
                slots.append(f"🔴 {time_str}")
            elif status == 2:
                slots.append(f"🟡 {time_str} (можливо)")
            elif status is None:
                slots.append(f"🔴 {time_str}")

        if slots:
            lines.append(f"📅 <b>{date}:</b>\n" + "\n".join(slots))
        else:
            lines.append(f"📅 <b>{date}:</b> без відключень")

    return "\n\n".join(lines) if lines else str(data)[:400]


def get_all_schedules():
    parts = []
    for q in QUEUES:
        info = fetch_queue(q)
        parts.append(f"<b>Черга {q}:</b>\n{info}")
    return "\n\n──────────\n\n".join(parts)


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


def main():
    current_data = get_all_schedules().strip()
    if not current_data:
        return

    old_data = ""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            old_data = f.read().strip()

    if current_data != old_data:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write(current_data)
        send_telegram(f"⚡️ <b>Оновилися графіки (4.2 та 5.2):</b>\n\n{current_data}")


if __name__ == "__main__":
    main()
