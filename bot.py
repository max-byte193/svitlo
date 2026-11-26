import os
import requests
from bs4 import BeautifulSoup

TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = os.environ["TG_CHAT_ID"]
QUEUES = ["4.2", "5.2"]  # Потрібні черги

URL = "https://pulse.if.ua/svitlo"
STATE_FILE = "last_schedule.txt"


def get_queue_text(soup, queue):
    text_blocks = [
        el.get_text(" ", strip=True)
        for el in soup.find_all(["div", "tr", "p", "li"])
        if f"Черга {queue}" in el.get_text() or queue in el.get_text()
    ]
    return "\n".join(text_blocks[:3]) if text_blocks else "Даних не знайдено"


def get_all_schedules():
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(URL, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    parts = []
    for q in QUEUES:
        info = get_queue_text(soup, q)
        parts.append(f"<b>Черга {q}:</b>\n{info}")
    return "\n\n──────────\n\n".join(parts)


def send_telegram(message):
    api_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(
        api_url,
        json={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        },
        timeout=10,
    )


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
