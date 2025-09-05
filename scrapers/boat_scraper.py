import os
import csv
import time
import platform
import argparse
import logging
import tempfile
import shutil
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, WebDriverException

# Import only on Windows
if platform.system().lower() == 'windows':
    from webdriver_manager.chrome import ChromeDriverManager

# ========== Logging Setup ==========
logger = logging.getLogger("boat_scraper")
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

os.makedirs("logs", exist_ok=True)
file_handler = logging.FileHandler("logs/boat_scraper.log")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# ========== Zombie Chrome Killer ==========
def kill_zombie_chrome():
    """Force kill leftover Chrome/Chromedriver processes to prevent session errors."""
    try:
        logger.info("Killing leftover Chrome/Chromedriver processes...")
        subprocess.call(["pkill", "-9", "-f", "chrome"])
        subprocess.call(["pkill", "-9", "-f", "chromedriver"])
        time.sleep(2)
    except Exception as e:
        logger.warning(f"Failed to kill zombie Chrome processes: {e}")

# ========== WebDriver Setup ==========
def setup_driver():
    kill_zombie_chrome()

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-notifications")
    options.add_argument("--window-size=1920,1080")

    driver = None
    system_platform = platform.system().lower()

    try:
        if system_platform == 'linux':
            chrome_path = "/usr/bin/google-chrome"
            chromedriver_path = "/root/new_dataextraction/linux_browser/chromedriver/chromedriver"

            if not os.path.exists(chrome_path) or not os.path.exists(chromedriver_path):
                raise FileNotFoundError("Chrome or Chromedriver not found at expected paths.")

            os.chmod(chrome_path, 0o755)
            os.chmod(chromedriver_path, 0o755)

            options.binary_location = chrome_path

            # ✅ Temporary profile for Linux to prevent 'user data dir already in use'
            temp_profile = tempfile.mkdtemp()
            options.add_argument(f"--user-data-dir={temp_profile}")

            service = Service(executable_path=chromedriver_path)
            driver = webdriver.Chrome(service=service, options=options)
            driver.temp_profile_dir = temp_profile

        else:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)

        logger.info("WebDriver initialized")
        return driver

    except Exception as e:
        logger.exception("WebDriver initialization failed")
        raise

# ========== Scraper Utilities ==========
def scroll_to_load_all(driver, scroll_times=50, pause=3):
    try:
        height = driver.execute_script('return document.body.scrollHeight')
        scroll_height = 0
        for _ in range(scroll_times):
            scroll_height += height / 10
            driver.execute_script('window.scrollTo(0, arguments[0]);', scroll_height)
            time.sleep(pause)
        logger.info("Scrolling completed.")
    except Exception as e:
        logger.exception("Error while scrolling the page.")

def collect_product_links(driver, category_url):
    try:
        driver.get(category_url)
        scroll_to_load_all(driver)
        product_elements = driver.find_elements(By.CSS_SELECTOR, "a.product-item-meta__title")
        links = [el.get_attribute("href") for el in product_elements if el.get_attribute("href")]
        logger.info(f"{len(links)} product links collected.")
        return links
    except Exception as e:
        logger.exception("Failed to collect product links.")
        return []

def extract_specifications(driver):
    specs = {}
    try:
        spec_items = driver.find_elements(By.CLASS_NAME, "specs-item")
        for spec in spec_items:
            key = spec.find_element(By.CLASS_NAME, "spec-type").text.strip()
            value = spec.find_element(By.CLASS_NAME, "spec").text.strip()
            specs[key] = value
    except:
        try:
            spec_button = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.ID, "btn-specifications"))
            )
            driver.execute_script("arguments[0].click();", spec_button)
            time.sleep(2)
            rows = driver.find_element(By.ID, "specifications").find_elements(By.TAG_NAME, "tr")
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 2:
                    specs[cells[0].text.strip()] = cells[1].text.strip()
        except Exception:
            logger.debug("Specifications not found or clickable.")
    return specs

def extract_reviews(driver):
    reviews = []
    try:
        review_blocks = driver.find_elements(By.CLASS_NAME, "jdgm-rev")
        for block in review_blocks:
            try:
                reviews.append({
                    "author": block.find_element(By.CLASS_NAME, "jdgm-rev__author").text.strip(),
                    "rating": len(block.find_element(By.CLASS_NAME, "jdgm-rev__rating").find_elements(By.CLASS_NAME, "jdgm-star.jdgm--on")),
                    "title": block.find_element(By.CLASS_NAME, "jdgm-rev__title").text.strip(),
                    "body": block.find_element(By.CLASS_NAME, "jdgm-rev__body").text.strip()
                })
            except:
                continue
    except Exception:
        logger.debug("No reviews found.")
    return reviews

def extract_faqs(driver):
    faqs = []
    try:
        faq_blocks = driver.find_elements(By.CLASS_NAME, "ac-tab-new")
        for block in faq_blocks:
            try:
                try:
                    plus_icon = block.find_element(By.CLASS_NAME, "plus_icon")
                    driver.execute_script("arguments[0].click();", plus_icon)
                except:
                    question_elem = block.find_element(By.CLASS_NAME, "product-ques")
                    driver.execute_script("arguments[0].click();", question_elem)
                time.sleep(0.5)
                faqs.append({
                    "question": block.find_element(By.CLASS_NAME, "product-ques").text.strip(),
                    "answer": block.find_element(By.CLASS_NAME, "product-ans").text.strip()
                })
            except Exception:
                continue
    except Exception:
        logger.debug("FAQ extraction failed.")
    return faqs

def extract_product_details(driver, wait, links, brand, category_id):
    products, features, specifications, reviews, faqs = [], [], [], [], []

    for i, link in enumerate(links):
        try:
            driver.get(link)
            time.sleep(2)
            product_id = f"{category_id}_product_{i + 1}"

            title = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()
            sale_price = driver.find_element(By.CSS_SELECTOR, "span.price--highlight.price--large").get_attribute("innerText").strip()
            main_price = driver.find_element(By.CSS_SELECTOR, "span.price--compare.line-through").get_attribute("innerText").strip()
            discount = driver.find_element(By.CSS_SELECTOR, "p.custom-saved-price").text.strip()
            rating = driver.find_element(By.CLASS_NAME, "rating__stars").get_attribute("data-rating").strip() if driver.find_elements(By.CLASS_NAME, "rating__stars") else "Rating not found"
            features_text = driver.execute_script("return document.querySelector('.pdp-title-extra-info small')?.innerText || ''")
            feature_list = [f.strip() for f in features_text.split(",") if f.strip()]

            specs = extract_specifications(driver)
            revs = extract_reviews(driver)
            faq_list = extract_faqs(driver)

            products.append({
                "product_id": product_id, "title": title, "price": sale_price,
                "main_price": main_price, "discount": discount, "rating": rating,
                "link": link, "brand": brand, "category_id": category_id
            })

            features.extend({"product_id": product_id, "feature": f} for f in feature_list)
            specifications.extend({"product_id": product_id, "key": k, "value": v} for k, v in specs.items())
            reviews.extend({"product_id": product_id, **r} for r in revs)
            faqs.extend({"product_id": product_id, **f} for f in faq_list)

        except Exception as e:
            logger.error(f"Failed to extract product at {link} - {e}")
            continue

    return products, features, specifications, reviews, faqs

def save_to_csv(products, features, specifications, reviews, faqs, output_dir, prefix):
    try:
        def save(data, filename, fieldnames):
            with open(os.path.join(output_dir, filename), "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data)

        save(products, f"{prefix}_products.csv", ["brand", "category_id", "product_id", "title", "price", "main_price", "discount", "rating", "link"])
        save(features, f"{prefix}_features.csv", ["product_id", "feature"])
        save(specifications, f"{prefix}_specifications.csv", ["product_id", "key", "value"])
        save(reviews, f"{prefix}_reviews.csv", ["product_id", "author", "rating", "title", "body"])
        save(faqs, f"{prefix}_faqs.csv", ["product_id", "question", "answer"])
        logger.info("All CSV files saved successfully.")
    except Exception as e:
        logger.exception("Error saving CSV files.")

# ========== Main Entry ==========
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Category page URL to scrape")
    parser.add_argument("--category_id", required=True, help="Category ID for tracking")
    parser.add_argument("--brand", required=True, help="Brand name (e.g., boat)")

    args = parser.parse_args()
    brand = args.brand.lower()
    category_id = args.category_id
    url = args.url

    output_dir = os.path.join("data", brand)
    prefix = f"{brand}_{category_id}"
    os.makedirs(output_dir, exist_ok=True)

    driver = setup_driver()
    wait = WebDriverWait(driver, 30)

    try:
        logger.info(f"Started scraping for brand={brand}, category_id={category_id}, url={url}")

        logger.info("Collecting product links...")
        product_links = collect_product_links(driver, url)
        logger.info(f"Collected {len(product_links)} product links")

        logger.info("Extracting product details...")
        products, features, specifications, reviews, faqs = extract_product_details(
            driver, wait, product_links, brand, category_id
        )

        logger.info("Saving scraped data to CSV...")
        save_to_csv(products, features, specifications, reviews, faqs, output_dir, prefix)
        logger.info("Scraping and data saving completed successfully.")

    except Exception as e:
        logger.exception("Scraping failed due to an unexpected error.")

    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Browser closed.")
            except Exception as e:
                logger.warning(f"Error closing WebDriver: {e}")

            if hasattr(driver, "temp_profile_dir"):
                shutil.rmtree(driver.temp_profile_dir, ignore_errors=True)
                logger.info("Temporary Chrome profile directory cleaned up.")
