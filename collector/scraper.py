import re
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.nlb.lk"
LISTING_URL = f"{BASE}/pit/"
HEADERS = {
    "User-Agent": "GovisethaHistoricalResearch/1.0 (low-rate public results collector)",
    "Accept-Language": "en",
}

def get_page(url: str, retries: int = 2) -> str:
    last = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=(5,10))
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Unable to fetch {url}: {last}")

def discover_latest_draw() -> int:
    html = get_page(LISTING_URL)
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"/results/govisetha/\d+", href, re.I):
            m = re.search(r"/results/govisetha/(\d+)", href, re.I)
            if m:
                candidates.append(int(m.group(1)))
    if not candidates:
        # Fallback: listing markup may show the draw number as nearby text.
        text = soup.get_text(" ", strip=True)
        m = re.search(r"Govisetha\s+(\d{3,})", text, re.I)
        if m:
            candidates.append(int(m.group(1)))
    if not candidates:
        raise RuntimeError("Could not discover the latest Govisetha draw from NLB /pit/. NLB page structure may have changed.")
    return max(candidates)

def parse_draw(draw_no: int):
    url = f"{BASE}/results/govisetha/{draw_no}"
    html = get_page(url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # Confirm that the requested draw page really belongs to this draw.
    m_draw = re.search(r"Draw\s*No\.?\s*:\s*(\d+)", text, re.I)
    if not m_draw or int(m_draw.group(1)) != draw_no:
        raise ValueError(f"Draw {draw_no}: official page did not confirm the requested draw number.")

    m_date = re.search(r"Date\s*:\s*([A-Za-z]+\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})", text, re.I)
    if not m_date:
        raise ValueError(f"Draw {draw_no}: could not parse draw date.")
    parsed_date = datetime.strptime(m_date.group(1), "%A %B %d, %Y").date().isoformat()

    # NLB result pages expose the winning letter and four numbers in the first
    # ordered list. Use that structured section rather than guessing from prize text.
    values = []
    for ol in soup.find_all("ol"):
        candidate = [li.get_text(" ", strip=True) for li in ol.find_all("li", recursive=False)]
        if len(candidate) >= 5:
            first = candidate[:5]
            if re.fullmatch(r"[A-Za-z]", first[0]) and all(re.fullmatch(r"\d{1,2}", x) for x in first[1:5]):
                values = first
                break

    if not values:
        # Fallback for markup without ordered-list elements: parse the first
        # five numbered list entries from visible text, then still validate.
        match = re.search(
            r"1\.\s*([A-Z])\s+2\.\s*(\d{1,2})\s+3\.\s*(\d{1,2})\s+4\.\s*(\d{1,2})\s+5\.\s*(\d{1,2})",
            text, re.I
        )
        if match:
            values = list(match.groups())

    if len(values) != 5:
        raise ValueError(f"Draw {draw_no}: could not confidently parse letter and four winning numbers.")

    letter = values[0].upper()
    numbers = [int(x) for x in values[1:]]
    if not re.fullmatch(r"[A-Z]", letter):
        raise ValueError(f"Draw {draw_no}: invalid letter.")
    if len(numbers) != 4 or any(n < 1 or n > 80 for n in numbers):
        raise ValueError(f"Draw {draw_no}: number outside 1–80 or incorrect count.")

    return {
        "draw_no": draw_no,
        "draw_date": parsed_date,
        "letter": letter,
        "n1": numbers[0],
        "n2": numbers[1],
        "n3": numbers[2],
        "n4": numbers[3],
        "source_url": url,
        "source": "NLB",
    }
