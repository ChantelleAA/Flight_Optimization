"""
Scraper reads the JSON above, visits each airline site with Selenium,
returns the three cheapest fares, number of stops, and total trip time.
Prices are stored in USD.  One CSV row per quote.
"""

import json, time, csv
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

JSON_PATH = "routes.json"
OUT_CSV  = "flight_quotes.csv"

AIRLINE_FUNCS = {} 

# --- airline-specific helpers ---------------------------------
def search_ethiopian(driver, r):
    """
    Submit a round-trip search on EthiopianAirlines.com and
    return list of dicts:
      [{price: 850, stops: 1, duration: "14h 25m"}, ... up to 3]
    Implementation uses driver to:
        1. open https://www.ethiopianairlines.com/booking
        2. fill origin, destination, dates, pax
        3. scrape the first three itinerary cards
    """
    quotes = []
    origin = r["origin"]
    dest   = r["dest"]
    dep    = r["depart"][0]        # first choice date
    ret    = r["return"]

    # Ethiopian’s booking engine accepts a direct query-string URL:
    # docs: https://book.ethiopianairlines.com (internal)
    url = (
        "https://book.ethiopianairlines.com/et/booking/flight-results"
        f"?tripType=RT&origin={origin}&destination={dest}"
        f"&departureDate={dep}&returnDate={ret}"
        f"&adults={r['pax']['adults']}&currency=USD"
    )
    driver.get(url)

    wait = WebDriverWait(driver, 30)
    # Wait for price cards to appear (--selector may change, verify in DevTools)
    cards = wait.until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "div.flight-result-card")
        )
    )

    for card in cards[:3]:   # three cheapest cards are listed first
        price_txt = card.find_element(By.CSS_SELECTOR, ".fare-total").text
        # e.g. "USD 850"
        price = float(price_txt.split()[-1].replace(",", ""))
        stops_txt = card.find_element(By.CSS_SELECTOR, ".stops-info").text
        # e.g. "1 Stop" → 1
        stops = int(stops_txt.split()[0])
        duration = card.find_element(By.CSS_SELECTOR, ".duration").text
        quotes.append(
            {"price": price, "stops": stops, "duration": duration}
        )

    return quotes


def search_kenya(driver, r):
    """
    Round-trip search on Kenya Airways.
    The site needs form interaction, so we fill the fields instead of a query-string.
    """
    quotes = []
    driver.get("https://www.kenya-airways.com/en-gh/book-a-flight")
    wait = WebDriverWait(driver, 20)

    # switch to round-trip, then fill From / To
    wait.until(
        EC.element_to_be_clickable((By.ID, "RoundTrip"))
    ).click()

    frm = wait.until(EC.element_to_be_clickable((By.ID, "fromInput")))
    frm.clear()
    frm.send_keys(r["origin"])
    time.sleep(1)
    frm.send_keys("\n")  # choose first suggestion

    to = driver.find_element(By.ID, "toInput")
    to.clear()
    to.send_keys(r["dest"])
    time.sleep(1)
    to.send_keys("\n")

    # dates
    dep_box = driver.find_element(By.ID, "departureDate")
    dep_box.clear()
    dep_box.send_keys(r["depart"][0])  # yyyy-mm-dd
    ret_box = driver.find_element(By.ID, "returnDate")
    ret_box.clear()
    ret_box.send_keys(r["return"])
    ret_box.send_keys("\n")

    # adults
    pax = driver.find_element(By.ID, "passengerSelector")
    pax.click()
    # default = 1, so skip unless >1

    driver.find_element(By.ID, "searchButton").click()

    # wait for results
    cards = wait.until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "div.result-card")
        )
    )
    for card in cards[:3]:
        price_txt = card.find_element(By.CSS_SELECTOR, ".price-total").text
        price = float(price_txt.replace("USD", "").replace(",", "").strip())
        stops = card.find_element(By.CSS_SELECTOR, ".stops").text
        stops = 0 if "Non-stop" in stops else int(stops.split()[0])
        duration = card.find_element(By.CSS_SELECTOR, ".duration").text
        quotes.append(
            {"price": price, "stops": stops, "duration": duration}
        )

    return quotes


# Placeholder stubs for other airlines — implement the same pattern
def search_asky(driver, r):          return []
def search_africaworld(driver, r):   return []
def search_turkish(driver, r):       return []
def search_qatar(driver, r):         return []
def search_delta(driver, r):         return []

AIRLINE_FUNCS.update(
    {
        "Kenya Airways":      search_kenya,
        "ASKY":               search_asky,
        "Africa World Airlines": search_africaworld,
        "Turkish Airlines":   search_turkish,
        "Qatar Airways":      search_qatar,
        "Delta Air Lines":    search_delta,
    }
)

# -----------------------------------------------------------------
# driver options (stealth user-agent, headless, etc.)
def make_driver():
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    opts.add_argument("--headless=new")          # Chrome 119+
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    return webdriver.Chrome(options=opts)


def run():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        routes = json.load(f)["routes"]

    Path(OUT_CSV).write_text(
        "route,airline,price_usd,stops,duration\n", encoding="utf-8"
    )

    driver = make_driver()

    for r in routes:
        for airline in r["airlines"]:
            func = AIRLINE_FUNCS.get(airline)
            if not func:
                print(f"[skip] {airline}: no parser yet")
                continue
            try:
                quotes = func(driver, r)
                for q in quotes[:3]:
                    csv_line = [
                        f"{r['origin']}-{r['dest']}",
                        airline,
                        q["price"],
                        q["stops"],
                        q["duration"],
                    ]
                    with open(OUT_CSV, "a", newline="", encoding="utf-8") as f:
                        csv.writer(f).writerow(csv_line)
                time.sleep(2)  # polite delay
            except Exception as e:
                print(f"[error] {airline} {r['id']} → {e}")

    driver.quit()


if __name__ == "__main__":
    run()

       
