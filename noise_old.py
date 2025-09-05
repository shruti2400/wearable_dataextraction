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
from selenium.common.exceptions import NoSuchElementException,TimeoutException,WebDriverException,StaleElementReferenceException

# -------------------
# Logging setup
# -------------------
logger = logging.getLogger("noise_scraper")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

os.makedirs("logs", exist_ok=True)
fh = logging.FileHandler("logs/noise_scraper.log")
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
logger.addHandler(fh)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
logger.addHandler(ch)

# -------------------
# Helper functions
# -------------------

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
            chromedriver_path = "/root/new_dataextraction/linux_browser/chromedriver/chromedriver"  # adjust if custom path
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

# -------------------
# Scraper functions
# -------------------

def collect_product_links(driver, wait, url):
    logger.info(f"Scraping product links from {url}")
    driver.get(url)
    time.sleep(2)
    links = set()

    try:
        subcats = driver.find_elements(By.CSS_SELECTOR, "div.explore-categories a[href*='/collections/']")
        if subcats:
            logger.info(f"Found {len(subcats)} subcategories")
            sub_urls = list(set(a.get_attribute("href") for a in subcats))
            for sub_url in sub_urls:
                driver.get(sub_url)
                scroll_to_end(driver)
                try:
                    products = wait.until(EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, "a[href*='/products/']")))
                    links.update(p.get_attribute("href") for p in products if "/products/" in p.get_attribute("href"))
                except Exception as e:
                    logger.warning(f"Failed to load products on {sub_url}: {e}")
        else:
            scroll_to_end(driver)
            products = wait.until(EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, "a[href*='/products/']")))
            links.update(p.get_attribute("href") for p in products if "/products/" in p.get_attribute("href"))

    except Exception as e:
        logger.exception(f"Failed to collect product links from {url}")

    return list(links)

def extract_specifications(driver):
    specs = {}
    try:
        for section in driver.find_elements(By.CLASS_NAME, "product-specification-accordion__header"):
            title = section.text.strip()
            try:
                section.click()
                time.sleep(0.5)
                content = section.find_element(By.XPATH, "./following-sibling::div").text.strip()
                specs[title] = content
            except:
                continue
    except:
        pass
    return specs



def extract_faqs(driver, wait_time=1):
    faqs = []
    try:
        total_panels = len(driver.find_elements(By.CLASS_NAME, "faq-panel"))
        for i in range(total_panels):
            try:
                section = driver.find_elements(By.CLASS_NAME, "faq-panel")[i]
                ActionChains(driver).move_to_element(section).perform()
                time.sleep(0.2)
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
                logger.warning(f"FAQ panel {i} skipped: {e}")
    except Exception as e:
        logger.info("No FAQ section found or timeout")
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
            except:
                continue
    except:
        pass
    return reviews

def extract_product_details(driver, wait, links, category_id, brand):
    logger.info(f"Extracting product details for brand {brand}, category {category_id}")
    products = []

    for idx, link in enumerate(links):
        driver.get(link)
        pid = f"{category_id}_product_{idx+1}"
        try:
            title = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "product-title"))).text
            price = driver.find_element(By.CLASS_NAME, "product-actual-price").text
            main_price = driver.find_element(By.CLASS_NAME, "product-compare-price").text if driver.find_elements(By.CLASS_NAME, "product-compare-price") else price
            rating = driver.find_elements(By.CLASS_NAME, "review-text")[0].text if driver.find_elements(By.CLASS_NAME, "review-text") else "N/A"

            price_val = parse_price(price)
            main_val = parse_price(main_price)
            discount = f"{round((main_val - price_val)/main_val*100)}%" if main_val > 0 else "0%"

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
            logger.warning(f"Failed for {link}: {e}")

    return products


# -------------------
# CSV Saving
# -------------------
def save_to_csv(products, brand, category_id):
    folder = os.path.join("data", brand.lower())
    os.makedirs(folder, exist_ok=True)
    prefix = f"{brand.lower()}_{category_id}"

    def save(filename, rows, fieldnames):
        path = os.path.join(folder, filename)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"Saved {filename}")

    save(f"{prefix}_products.csv", [
        {
            "brand": p["brand"], "category_id": p["category_id"], "product_id": p["product_id"],
            "title": p["title"], "price": p["price"], "main_price": p["main_price"],
            "discount": p["discount"], "rating": p["rating"], "link": p["link"]
        }
        for p in products
    ], ["brand", "category_id", "product_id", "title", "price", "main_price", "discount", "rating", "link"])

    save(f"{prefix}_features.csv", [
        {"product_id": p["product_id"], "feature": f}
        for p in products for f in p.get("features", [])
    ], ["product_id", "feature"])

    save(f"{prefix}_reviews.csv", [
        {"product_id": p["product_id"], "author": r["author"], "rating": r["rating"], "title": r["title"], "body": r["body"]}
        for p in products for r in p.get("reviews", [])
    ], ["product_id", "author", "rating", "title", "body"])

    save(f"{prefix}_specifications.csv", [
        {"product_id": p["product_id"], "key": k, "value": v}
        for p in products for k, v in p.get("specifications", {}).items()
    ], ["product_id", "key", "value"])

    save(f"{prefix}_faqs.csv", [
        {"product_id": p["product_id"], "question": f["question"], "answer": f["answer"]}
        for p in products for f in p.get("faqs", [])
    ], ["product_id", "question", "answer"])

     

# -------------------
# Main
# -------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Category URL to scrape")
    parser.add_argument("--category_id", required=True, help="Category ID")
    parser.add_argument("--brand", required=True, help="Brand name")
    args = parser.parse_args()

    driver = setup_driver()
    wait = WebDriverWait(driver, 20)

    try:
        links = collect_product_links(driver, wait, args.url)
        products = extract_product_details(driver, wait, links, args.category_id, args.brand)
        save_to_csv(products, args.brand, args.category_id)
    except Exception as e:
        logger.exception("Scraper failed")
    finally:
        if driver:
            driver.quit()
            if hasattr(driver, "temp_profile_dir"):
                shutil.rmtree(driver.temp_profile_dir, ignore_errors=True)
