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
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# Import only on Windows
if platform.system().lower() == 'windows':
    from webdriver_manager.chrome import ChromeDriverManager

# ========== Logging Setup ==========
logger = logging.getLogger("boult_scraper")
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

os.makedirs("logs", exist_ok=True)
file_handler = logging.FileHandler("logs/boult_scraper.log")
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
    if platform.system().lower() == 'linux':
        try:
            logger.info("Killing leftover Chrome/Chromedriver processes...")
            subprocess.call(["pkill", "-9", "-f", "chrome"])
            subprocess.call(["pkill", "-9", "-f", "chromedriver"])
            time.sleep(2)  # Let the system settle
        except Exception as e:
            logger.warning(f"Failed to kill zombie Chrome processes: {e}")

# --- Setup WebDriver ---
def setup_driver():

    kill_zombie_chrome()

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-notifications")
    options.add_argument("--window-size=1920,1080")

    system_platform = platform.system().lower()
    driver = None

    try:
        if system_platform == 'linux':
            chrome_path = "/usr/bin/google-chrome"
            chromedriver_path = "/root/new_dataextraction/linux_browser/chromedriver/chromedriver"

            if not os.path.exists(chrome_path) or not os.path.exists(chromedriver_path):
                raise FileNotFoundError("Chrome or Chromedriver not found")

            os.chmod(chrome_path, 0o755)
            os.chmod(chromedriver_path, 0o755)

            options.binary_location = chrome_path

            # ✅ Temporary profile to avoid 'user data dir in use' issue
            temp_profile = tempfile.mkdtemp()
            options.add_argument(f"--user-data-dir={temp_profile}")

            service = Service(executable_path=chromedriver_path)
            driver = webdriver.Chrome(service=service, options=options)
            driver.temp_profile_dir = temp_profile

        else:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)

        logger.info("WebDriver initialized")
        return driver

    except Exception as e:
        logger.exception("WebDriver initialization failed")
        raise

# -------------------
# SCRAPER FUNCTIONS
# -------------------
def get_product_links(driver, category_url, scrolls=30):
    product_links = set()
    driver.get(category_url)
    last_height = driver.execute_script("return document.body.scrollHeight")

    for _ in range(scrolls):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    try:
        product_grid = driver.find_element(By.CLASS_NAME, "wizzy-search-results")
        for ul in product_grid.find_elements(By.CSS_SELECTOR, "ul.wizzy-search-results-list"):
            for li in ul.find_elements(By.TAG_NAME, "li"):
                try:
                    href = li.find_element(By.TAG_NAME, "a").get_attribute("href")
                    if href:
                        product_links.add(href)
                except Exception as e:
                    logger.warning(f"Error extracting product link: {e}")
    except Exception as e:
        logger.error(f"Error in product grid: {e}")

    return list(product_links)


def scrape_product_details(driver, wait, product_links, category_id, brand):
    products, features, specifications, reviews, faqs = [], [], [], [], []

    for idx, url in enumerate(product_links, start=1):
        product_id = f"{category_id}_product_{idx}"
        logger.info(f"Scraping {idx}/{len(product_links)}: {url}")
        info = {"product_id": product_id, "link": url, "category_id": category_id, "brand": brand}

        try:
            driver.get(url)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "h1")))

            info["title"] = driver.execute_script("return document.querySelector('h1.proTitle')?.innerText") or \
                             driver.find_element(By.TAG_NAME, "h1").text.strip()
            info["price"] = get_text_or_default(driver, By.ID, "priceChange")
            info["main_price"] = get_text_or_default(driver, By.CSS_SELECTOR, "span.comPrice")
            info["discount"] = get_text_or_default(driver, By.CSS_SELECTOR, "span.total-discount")

            products.append(info)
            extract_sections(driver, product_id, features, specifications)
            extract_reviews(driver, wait, product_id, reviews)
            extract_faqs(driver, product_id, faqs)

        except Exception as e:
            logger.error(f"Failed to scrape {url}: {e}")

    return products, features, specifications, reviews, faqs


def get_text_or_default(driver, by, selector, default="N/A"):
    try:
        return driver.find_element(by, selector).text.strip()
    except:
        return default


def extract_sections(driver, product_id, features, specifications):
    for section in driver.find_elements(By.CSS_SELECTOR, "div.WI_productDrop_con"):
        try:
            heading = section.find_element(By.CSS_SELECTOR, "p.WI_productDrop_heading").text
            points = [p.text.strip() or p.get_attribute("innerHTML").strip()
                      for p in section.find_elements(By.CSS_SELECTOR, "ul.WI_productDrop_info li p")]

            if "USP" in heading or "Feature" in heading:
                features.extend({"product_id": product_id, "feature": pt} for pt in points)
            elif "Specification" in heading:
                for i in range(0, len(points), 2):
                    key, value = points[i], points[i+1] if i + 1 < len(points) else ""
                    specifications.append({"product_id": product_id, "key": key, "value": value})
            else:
                specifications.extend({"product_id": product_id, "key": pt, "value": ""} for pt in points)

        except Exception as e:
            logger.warning(f"Error parsing section: {e}")


def extract_reviews(driver, wait, product_id, reviews):
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "jdgm-rev")))

        for block in driver.find_elements(By.CLASS_NAME, "jdgm-rev"):
            try:
                author = block.find_element(By.CLASS_NAME, "jdgm-rev__author").text.strip()
                rating = len(block.find_element(By.CLASS_NAME, "jdgm-rev__rating")
                              .find_elements(By.CLASS_NAME, "jdgm-star.jdgm--on"))
                title = block.find_element(By.CLASS_NAME, "jdgm-rev__title").text.strip()
                body = block.find_element(By.CLASS_NAME, "jdgm-rev__body").text.strip()
                reviews.append({"product_id": product_id, "author": author, "rating": rating,
                                "title": title, "body": body})
            except:
                continue

    except TimeoutException:
        logger.info(f"No reviews found for product {product_id}")


def extract_faqs(driver, product_id, faqs):
    for block in driver.find_elements(By.CLASS_NAME, "product-faq"):
        try:
            q = block.find_element(By.CLASS_NAME, "faq-title")
            question = q.text.strip()
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", q)
            time.sleep(0.5)
            try:
                driver.execute_script("arguments[0].click();", q)
            except:
                q.click()
            time.sleep(1.2)
            try:
                answer = block.find_element(By.CSS_SELECTOR, "div.faq-answer p").text.strip()
            except:
                answer = "Answer not available."

            faqs.append({"product_id": product_id, "question": question, "answer": answer})
        except:
            continue


def save_to_csv(products, features, specifications, reviews, faqs, brand, category_id):
    prefix = f"{brand.lower()}_{category_id}"
    output_dir = os.path.join("data", brand.lower())
    os.makedirs(output_dir, exist_ok=True)

    def save(filename, data, fields):
        with open(os.path.join(output_dir, filename), "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(data)

    save(f"{prefix}_products.csv", products,
         ["brand", "category_id", "product_id", "title", "price", "main_price", "discount", "link"])
    save(f"{prefix}_features.csv", features, ["product_id", "feature"])
    save(f"{prefix}_specifications.csv", specifications, ["product_id", "key", "value"])
    save(f"{prefix}_reviews.csv", reviews, ["product_id", "author", "rating", "title", "body"])
    save(f"{prefix}_faqs.csv", faqs, ["product_id", "question", "answer"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--category_id", required=True)
    parser.add_argument("--brand", required=True)
    args = parser.parse_args()

    logger.info("Starting Boult scraper...")
    driver = setup_driver()
    wait = WebDriverWait(driver, 20)

    try:
        logger.info("Collecting product links...")
        links = get_product_links(driver, args.url)
        logger.info(f"Found {len(links)} products.")

        logger.info("Scraping product details...")
        products, features, specs, reviews, faqs = scrape_product_details(driver, wait, links, args.category_id, args.brand)

        logger.info("Saving data to CSV...")
        save_to_csv(products, features, specs, reviews, faqs, args.brand, args.category_id)

    except Exception as e:
        logger.exception("Script failed")
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Browser closed.")
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")

            if hasattr(driver, "temp_profile_dir"):
                shutil.rmtree(driver.temp_profile_dir, ignore_errors=True)
                logger.info("Temporary Chrome profile directory cleaned up.")
