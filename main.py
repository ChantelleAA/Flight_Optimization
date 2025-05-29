import re, time, logging
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import config as config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.StreamHandler(),                      
        logging.FileHandler(config.LOG_FILE, mode="w")
    ]
)

def clean_code(city):
    """'Johannesburg (JNB)' → 'jnb'."""
    m = re.search(r"\((\w{3})\)", city)
    return m.group(1).lower() if m else None

def make_url(origin, dep_date, ret_date, pax):
    return (f"https://www.skyscanner.com/transport/flights/"
            f"{origin}/acc/{dep_date.replace('-','')}/{ret_date.replace('-','')}"
            f"/?adults={pax}&currency={config.CURRENCY}&preferdirects=false")

def launch_driver():
    opts = webdriver.ChromeOptions()
    # comment OUT the next line to see the browser
    # opts.add_argument("--headless=new")
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--no-sandbox")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    logging.info("Chrome driver launched")
    return driver

def fetch_price(driver, url):
    logging.info("Loading %s", url)
    driver.get(url)
    wait = WebDriverWait(driver, config.WAIT_PRICE)

    price_span = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'div[data-test-id="listing-card"] span[data-test-id="price-text"]')
        )
    )
    price_text = price_span.text
    price_val  = float(re.sub(r"[^\d\.]", "", price_text))

    airline = price_span.find_element(
        By.XPATH,
        '../../..//div[@data-test-id="airline-name"]'
    ).get_attribute("innerText").strip()

    logging.info(" → %s %s", airline, price_text)
    return airline, price_val

# --------------------------- main ---------------------------
def main():
    df_countries = pd.read_excel(config.WORKBOOK, sheet_name="countries", engine="openpyxl")
    unique_cities = df_countries[config.CITY_COL].unique()

    rows = []
    driver = launch_driver()

    try:
        for city in unique_cities:
            if "Accra" in city:
                continue        # locals
            code = clean_code(city)
            if not code:
                logging.warning("Could not parse IATA from %s – skipped", city)
                continue

            headcount = int(
                df_countries.loc[df_countries[config.CITY_COL] == city, config.HEADCOUNT_COL].iloc[0]
            )
            pax = min(headcount, 9)

            logging.info("=== %s | travellers: %d ===", city, headcount)

            for dep in config.DEPARTURE_DATES:
                try:
                    quote_url = make_url(code, dep, config.RETURN_DATE, pax)
                    airline, price = fetch_price(driver, quote_url)
                    rows.append(dict(
                        City=city, Airline=airline, ArriveDate=dep,
                        ReturnDate=config.RETURN_DATE, FareType="WebEco",
                        SeatsCapable=pax, RoundtripCost=price
                    ))
                except Exception as e:
                    logging.error("No price for %s on %s  (%s)", city, dep, e)

    finally:
        driver.quit()
        logging.info("Browser closed")

    if not rows:
        logging.error("No data fetched – aborting workbook write")
        return

    df_quotes = pd.DataFrame(rows)
    logging.info("Collected %d quote rows", len(df_quotes))

    with pd.ExcelWriter(config.WORKBOOK, mode="a", engine="openpyxl",
                        if_sheet_exists="replace") as xls:
        df_quotes.to_excel(xls, sheet_name="FlightQuotes", index=False)
        logging.info("FlightQuotes sheet overwritten in %s", config.WORKBOOK)

if __name__ == "__main__":
    main()