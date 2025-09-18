import os
import csv
import time
import platform
import argparse
import logging
import tempfile
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# Logging setup
logger = logging.getLogger("noise_scraper")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

fh = logging.FileHandler("logs/noise_scraper.log")
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
logger.addHandler(fh)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
logger.addHandler(ch)

def setup_driver():
    """Setup Selenium Chrome WebDriver for Linux server with temporary profile."""
    system_platform = platform.system().lower()
    tmp_dir = tempfile.mkdtemp()
    driver = None

    try:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(f"--user-data-dir={tmp_dir}")

        if system_platform == 'linux':
            chrome_path = "/usr/bin/google-chrome"
            # chromedriver_path = "/root/new_dataextraction/linux_browser/chromedriver/chromedriver"
            chromedriver_path = "/usr/local/bin/chromedriver"
            if not os.path.exists(chrome_path) or not os.path.exists(chromedriver_path):
                raise FileNotFoundError("Chrome or Chromedriver not found in Linux paths.")
            options.binary_location = chrome_path
            service = Service(chromedriver_path)

            os.chmod(chrome_path, 0o755)
            os.chmod(chromedriver_path, 0o755)
            
        else:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())

        driver = webdriver.Chrome(service=service, options=options)
        driver.temp_profile_dir = tmp_dir
        logger.info("WebDriver initialized successfully")
        return driver

    except Exception as e:
        logger.exception("Failed to initialize WebDriver")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

def parse_price(text):
    try:
        return float(text.replace("₹", "").replace(",", "").strip())
    except:
        return 0.0
    
def scroll_to_end(driver):
    """Scroll to bottom until page fully loads."""
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def collect_product_links(driver, wait, url):
    logger.info(f"Scraping product links from {url}")
    driver.get(url)
    time.sleep(3)
    links = set()

    try:
        subcats = driver.find_elements(By.CSS_SELECTOR, "div.explore-categories a[href*='/collections/']")
        if subcats:
            logger.info(f"Found {len(subcats)} subcategories")
            sub_urls = list(set(a.get_attribute("href") for a in subcats))
            for sub_url in sub_urls:
                driver.get(sub_url)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)
                try:
                    products = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/products/']")))
                    links.update(p.get_attribute("href") for p in products if "/products/" in p.get_attribute("href"))
                except Exception as e:
                    logger.error(f"Error in {sub_url}: {e}")
        else:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            products = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/products/']")))
            links.update(p.get_attribute("href") for p in products if "/products/" in p.get_attribute("href"))

    except Exception as e:
        logger.exception(f"Failed to collect product links from {url}")

    return list(links)

def extract_product_details(driver, wait, links, category_id, brand):
    logger.info(f"Extracting product details for brand {brand}, category {category_id}")
    products = []

    for idx, link in enumerate(links):
        driver.get(link)
        pid = f"{category_id}_product_{idx+1}"
        try:
            title = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "product-title"))).text
            price = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "product-actual-price"))).text
            main_price = driver.find_element(By.CLASS_NAME, "product-compare-price").text if driver.find_elements(By.CLASS_NAME, "product-compare-price") else "N/A"
            rating = driver.find_elements(By.CLASS_NAME, "review-text")[0].text if driver.find_elements(By.CLASS_NAME, "review-text") else "N/A"
            
            discount = "N/A"
            price_val = parse_price(price)
            main_val = parse_price(main_price)
            if main_val > 0:
                discount = f"{round(((main_val - price_val) / main_val) * 100)}%"

            products.append({
                "product_id": pid,
                "title": title,
                "price": price,
                "main_price": main_price,
                "discount": discount,
                "rating": rating,
                "link": link,
                "brand": brand,
                "category_id": category_id,
                "features": [el.text for el in driver.find_elements(By.CLASS_NAME, "feature-name")],
                "specifications": extract_specifications(driver),
                "faqs": extract_faqs(driver),
                "reviews": extract_reviews(driver)
            })
        except Exception as e:
            logger.error(f"Failed for {link}: {e}")

    return products

def extract_specifications(driver):
    specs = {}
    try:
        for section in driver.find_elements(By.CLASS_NAME, "product-specification-accordion__header"):
            title = section.text.strip()
            section.click()
            time.sleep(1)
            content = section.find_element(By.XPATH, "./following-sibling::div").text.strip()
            specs[title] = content
    except:
        pass
    return specs

def extract_faqs(driver, wait_time=2):
    faqs = []
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "faq-panel"))
        )
        total_panels = len(driver.find_elements(By.CLASS_NAME, "faq-panel"))

        for i in range(total_panels):
            try:
                section = driver.find_elements(By.CLASS_NAME, "faq-panel")[i]
                ActionChains(driver).move_to_element(section).perform()
                time.sleep(0.5)
                section.click()
                time.sleep(wait_time)

                section = driver.find_elements(By.CLASS_NAME, "faq-panel")[i]
                title = section.find_element(By.CLASS_NAME, "ques-title").text.strip()
                answer_sec = section.find_element(By.CLASS_NAME, "answer")

                p_tags = answer_sec.find_elements(By.TAG_NAME, "p")
                q, a_parts = None, []
                for p in p_tags:
                    html = p.get_attribute("innerHTML").strip()
                    text = p.text.strip()
                    if not text:
                        continue
                    if "<strong>" in html:
                        if q:
                            faqs.append({"faq_title": title, "question": q, "answer": " ".join(a_parts)})
                        q = text
                        a_parts = []
                    else:
                        a_parts.append(text)
                if q:
                    faqs.append({"faq_title": title, "question": q, "answer": " ".join(a_parts)})

            except Exception as e:
                logger.warning(f"FAQ panel {i} failed: {e}")
    except Exception as e:
        logger.warning("No FAQ section found or timeout")

    return faqs

def extract_reviews(driver):
    reviews = []
    try:
        while True:
            load_more = driver.find_elements(By.CLASS_NAME, "jdgm-rev-widg__load-more")
            if not load_more:
                break
            driver.execute_script("arguments[0].click();", load_more[0])
            time.sleep(2)

        for review in driver.find_elements(By.CLASS_NAME, "jdgm-rev"):
            try:
                reviews.append({
                    "author": review.find_element(By.CLASS_NAME, "jdgm-rev__author").text.strip(),
                    "date": review.find_element(By.CLASS_NAME, "jdgm-rev__timestamp").get_attribute("data-content"),
                    "rating": review.find_element(By.CLASS_NAME, "jdgm-rev__rating").get_attribute("data-score"),
                    "title": review.find_element(By.CLASS_NAME, "jdgm-rev__title").text.strip(),
                    "body": review.find_element(By.CLASS_NAME, "jdgm-rev__body").text.strip(),
                })
            except Exception as e:
                logger.warning(f"Skipped a review due to: {e}")

    except Exception as e:
        logger.warning(f"Failed to load reviews: {e}")
    return reviews

def save_to_csv(products, brand, category_id):
    folder = os.path.join("data", brand.lower())
    os.makedirs(folder, exist_ok=True)
    prefix = f"{brand.lower()}_{category_id}"

    def write_csv(name, header, rows):
        with open(os.path.join(folder, f"{prefix}_{name}.csv"), "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)

    write_csv("products", ["brand", "category_id", "product_id", "title", "price", "main_price", "discount", "rating", "link"],
              [[p["brand"], p["category_id"], p["product_id"], p["title"], p["price"], p["main_price"], p["discount"], p["rating"], p["link"]] for p in products])

    write_csv("features", ["product_id", "feature"],
              [[p["product_id"], f] for p in products for f in p.get("features", [])])

    write_csv("reviews", ["product_id", "author", "rating", "title", "body"],
              [[p["product_id"], r["author"], r["rating"], r["title"], r["body"]] for p in products for r in p.get("reviews", [])])

    write_csv("specifications", ["product_id", "key", "value"],
              [[p["product_id"], k, v] for p in products for k, v in p.get("specifications", {}).items()])

    write_csv("faqs", ["product_id", "question", "answer"],
              [[p["product_id"], f["question"], f["answer"]] for p in products for f in p.get("faqs", [])])
    

# -------------------
# Main
# -------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--category_id", required=True)
    parser.add_argument("--brand", required=True)
    args = parser.parse_args()

    driver = setup_driver()
    wait = WebDriverWait(driver, 30)

    try:
        logger.info("Collecting product links...")
        links = collect_product_links(driver, wait, args.url)
        logger.info(f"Collected {len(links)} links")

        logger.info("Extracting product details...")
        products = extract_product_details(driver, wait, links, args.category_id, args.brand)

        logger.info("Saving data to CSV...")
        save_to_csv(products, args.brand, args.category_id)

    except Exception as e:
        logger.exception("Script failed")
    finally:
        if driver:
            driver.quit()
            logger.info("Browser closed.")
            if hasattr(driver, "temp_profile_dir"):
                shutil.rmtree(driver.temp_profile_dir, ignore_errors=True)
                logger.info("Temporary Chrome profile cleaned up.")