import os
import csv
import logging
import urllib.request

import chromedriver_autoinstaller

from urllib.parse import urlparse
from urllib.error import HTTPError
from selenium import webdriver

from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, WebDriverException


# Config
EXPLICIT_WAIT = 10
IMAGES_DIR = "images"
CSV_FILE = "watch_data.csv"
LOG_FILE = "logs.log"

# Check if the current version of chromedriver exists
# and if it doesn't exist, download it automatically,
# then add chromedriver to path
chromedriver_autoinstaller.install()

# Setup logging
logging.root.handlers = []
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE, mode="w"), logging.StreamHandler()],
)


# Keep track of scraped items
count = 0


def init_chrome_driver():
    options = Options()
    options.add_argument("--headless=new")  # run in headless mode
    options.add_argument("--disable-dev-shm-usage")  # disable shared memory usage
    options.add_argument("--window-size=1920,1080")  # window size 1920x1080
    options.add_argument("--enable-automation")  # enable automation

    # Initialize the ChromeDriver instance with the given options and proxy settings
    driver = webdriver.Chrome(options=options)

    # Return both the ChromeDriver instance and the ActionChains instance
    return driver


def close_region_selector_modal(driver):
    # Wait for the modal to appear and check if it's open
    try:
        modal = WebDriverWait(driver, EXPLICIT_WAIT).until(
            EC.visibility_of_element_located((By.ID, "modal_region-selector"))
        )
        if modal.is_displayed():
            # If the modal is open, close it
            close_button = modal.find_element(By.CLASS_NAME, "btn-modal-close")
            close_button.click()
    except:
        # If the modal doesn't appear, do nothing
        pass


def get_watch_brands(driver):
    driver.get("https://www.watchfinder.co.uk/sell-your-watch/brands")
    close_region_selector_modal(driver)

    all_brand_links = driver.find_elements(
        By.CSS_SELECTOR, "a[data-sellaction='brand-click-normal']"
    )
    all_brand_hrefs = [link.get_attribute("href") for link in all_brand_links]

    return all_brand_hrefs


def scrape_watch_series(driver, csv_writer):
    try:
        driver.find_element(
            By.XPATH,
            "//p[contains(text(), 'Alternatively, select your watch by series:')]",
        )
    except NoSuchElementException:
        return

    series = driver.find_elements(By.CSS_SELECTOR, "a[data-sellaction='series_item']")
    series_links = [link.get_attribute("href") for link in series]

    for series_href in series_links:
        driver.get(series_href)
        scrape_watch_series(driver, csv_writer)
        scrape_watches(driver, csv_writer)


def scrape_watches(driver, csv_writer):
    next_page_url = None
    try:
        next_page_url = driver.find_element(
            By.CSS_SELECTOR, "div.search_options-footer a.pager_next"
        ).get_attribute("href")
    except NoSuchElementException:
        pass

    watches = driver.find_elements(
        By.CSS_SELECTOR, "div.group div.prods_item a.prods_name"
    )
    watch_links = [link.get_attribute("href") for link in watches]

    for watch_link in watch_links:
        driver.get(watch_link)
        try:
            watch_data = extract_watch_details(driver)
            csv_writer.writerow(watch_data)
            global count
            count += 1
            logging.info(
                f"Successfully extracted watch details at {driver.current_url}"
            )
            logging.info(f"Total number of watches extracted: {count}")
        except (WebDriverException, HTTPError):
            logging.error(
                f"Exception occurred extracting watch details at {driver.current_url}"
            )

    if next_page_url:
        driver.get(next_page_url)
        scrape_watches(driver, csv_writer)


def extract_watch_details(driver):
    WebDriverWait(driver, EXPLICIT_WAIT).until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "a.watch-details-name-specs[data-modal='prod_zoom_sell']")
        )
    )

    driver.find_element(
        By.CSS_SELECTOR, "a.watch-details-name-specs[data-modal='prod_zoom_sell']"
    ).click()

    WebDriverWait(driver, EXPLICIT_WAIT).until(
        EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "div#prod_zoom_sell .modal_frame")
        )
    )

    brand = driver.find_element(By.CSS_SELECTOR, "span.prod_brand").text
    series = driver.find_element(By.CSS_SELECTOR, "span.prod_series").text
    model = driver.find_element(By.CSS_SELECTOR, "span.prod_model").text
    description = {}

    description_table = driver.find_element(By.CSS_SELECTOR, "table.prod_info-table")
    rows = description_table.find_elements(By.TAG_NAME, "tr")
    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) == 2:
            label = cells[0].text
            value = cells[1].text
            description[label] = value

    img_url = (
        driver.find_element(By.CSS_SELECTOR, "div.zoomHolder img")
        .get_attribute("data-src")
        .split(",")[0]
    )

    if is_url(img_url):
        img_download_path = f"{IMAGES_DIR}/{brand}_{series}_{model}.jpg"
        # download_img(img_url, img_download_path) # Uncomment this to enable image downloading
    else:
        img_url = ""
        img_download_path = ""

    watch_info = {
        "Brand": brand,
        "Series": series,
        "Model": model,
        "Image URL": img_url,
        "Image Path": img_download_path,
        "URL": driver.current_url,
    }

    watch_info.update(description)

    return watch_info


def download_img(image_url, img_download_path):
    local_filename, _ = urllib.request.urlretrieve(image_url, img_download_path)
    return local_filename


def is_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def main():
    if not os.path.exists(IMAGES_DIR):
        logging.warning(f"Folder '{IMAGES_DIR}' doesn't exist")
        os.makedirs(IMAGES_DIR)
        logging.info(f"Folder '{IMAGES_DIR}' created successfully")

    driver = init_chrome_driver()
    brand_pages = get_watch_brands(driver)

    with open(CSV_FILE, mode="w", newline="\n", encoding="utf-8") as results_file:
        writer = csv.writer(results_file)
        fieldnames = [
            "Brand",
            "Series",
            "Model",
            "Image URL",
            "Image Path",
            "URL",
            "Movement",
            "Case material",
            "Bracelet material",
            "Dial type",
            "Water resistance",
            "Case size",
        ]
        writer = csv.DictWriter(results_file, fieldnames=fieldnames)
        writer.writeheader()

        for brand_href in brand_pages:
            driver.get(brand_href)
            scrape_watch_series(driver, writer)

    driver.quit()


if __name__ == "__main__":
    main()
