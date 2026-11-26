import os
import requests
from bs4 import BeautifulSoup

TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = os.environ["TG_CHAT_ID"]
QUEUES = ["4.2", "5.2"]

URL = "https://svitlo.oe.if.ua/"
STATE_FILE = "last_schedule.txt"


def fetch_page():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://svitlo.oe.if.ua/",
    }
    resp = requests.get(URL, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.text


def get_queue_text(soup, queue):
    matches = []
    for el in soup.find_all(["div", "tr", "p", "li", "span", "td"]):
        text = el.get_text(" ", strip=True)
        if queue in text and len(text) < 600:
            if text not in matches:
                matches.append(text)
    return "\n".join(matches[:4]) if matches else "Даних у статичному HTML не знайдено"


def get_all_schedules():
    html = fetch_page()
    soup = BeautifulSoup(html, "html.parser")

    parts = []
    for q in QUEUES:
        info = get_queue_text(soup, q)
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
