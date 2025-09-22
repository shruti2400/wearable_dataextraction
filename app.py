import os
import glob
import subprocess
import logging
from datetime import datetime
from flask import Flask, request, jsonify
import pandas as pd
import sys

from preprocessor.cleaner_products import preprocess_product_file
from preprocessor.cleaner_features import preprocess_feature_file
from preprocessor.cleaner_faqs import preprocess_faq_file
from preprocessor.cleaner_specifications import preprocess_specification_file
from preprocessor.cleaner_reviews import preprocess_review_file

# ----- Flask App -----
app = Flask(__name__)

# ----- Config -----
LOG_FILE = 'app.log'
CATEGORIES_CSV = 'categories.csv'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FOLDER = os.path.join(BASE_DIR, 'data')
MERGED_FOLDER = os.path.join(BASE_DIR, 'merged_data')

PYTHON_PATH = sys.executable

SCRIPTS = {
    "boat": os.path.join(BASE_DIR, "scrapers/boat_scraper.py"),
    "boult": os.path.join(BASE_DIR, "scrapers/boult_scraper.py"),
    "noise": os.path.join(BASE_DIR, "scrapers/noise_scraper.py")
}

# ----- Logging -----
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s'
)

# ----- Utility: Merge Data -----
def append_to_merged(file_path, brand):
    """Append cleaned data to merged CSV, drop duplicates, and sort by category_id."""
    try:
        filename = os.path.basename(file_path)
        file_type = filename.split('_')[-1]  # e.g., products.csv
        merged_dir = os.path.join(MERGED_FOLDER, f"{brand}_merged")
        os.makedirs(merged_dir, exist_ok=True)
        merged_path = os.path.join(merged_dir, f"{brand}_{file_type}")

        new_df = pd.read_csv(file_path)

        if os.path.exists(merged_path):
            existing_df = pd.read_csv(merged_path)
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined_df = new_df

        combined_df.drop_duplicates(inplace=True)
        if 'category_id' in combined_df.columns:
            combined_df.sort_values(by='category_id', inplace=True)

        combined_df.to_csv(merged_path, index=False)
        logging.info(f"[MERGE] Successfully merged into {merged_path}")

    except Exception:
        logging.exception(f"[MERGE ERROR] Failed to merge {file_path}")

# ----- Utility: Clean & Merge Files -----
def clean_and_merge(brand, cleaner_fn, pattern):
    """Clean files using provided cleaner function and append to merged file."""
    cleaned_files = []
    brand_path = os.path.join(DATA_FOLDER, brand)
    files = glob.glob(os.path.join(brand_path, pattern))

    logging.debug(f"[{brand}] Found files: {files}")

    for file_path in files:
        try:
            df = cleaner_fn(file_path)
            if df is None:
                logging.warning(f"[{brand}] Cleaner returned None for {file_path}")
                continue

            df.to_csv(file_path, index=False)
            cleaned_files.append(os.path.basename(file_path))
            append_to_merged(file_path, brand)

            logging.info(f"[{brand}] Cleaned & merged {file_path}")

        except Exception:
            logging.exception(f"[{brand}] Failed to clean or merge {file_path}")

    return cleaned_files

# ----- Endpoint: Scrape Specific -----
@app.route("/scrape", methods=["POST"])
def scrape():
    data = request.get_json()
    brand = data.get("brand", "").lower()
    url = data.get("url")
    category_id = data.get("category_id")

    logging.info(f"Scrape request: brand={brand}, category_id={category_id}, url={url}")

    if not brand or not url or not category_id:
        return jsonify({"error": "Missing required fields: brand, url, category_id"}), 400

    script_path = SCRIPTS.get(brand)
    if not script_path:
        return jsonify({"error": f"Invalid brand '{brand}'"}), 400

    os.makedirs(os.path.join(DATA_FOLDER, brand), exist_ok=True)

    try:
        # Run scraper subprocess
        result = subprocess.run(
            [PYTHON_PATH, script_path, "--url", url, "--category_id", str(category_id), "--brand", brand],
            capture_output=True,
            text=True,
            check=True
        )

        logging.info(f"Scraping completed for {brand}")

        response_data = {
            "status": "success",
            "message": f"Scraping for '{brand}' completed.",
            "cleaned_product_files": clean_and_merge(brand, preprocess_product_file, "*_products.csv"),
            "cleaned_feature_files": clean_and_merge(brand, preprocess_feature_file, "*_features.csv"),
            "cleaned_faq_files": clean_and_merge(brand, preprocess_faq_file, "*_faqs.csv"),
            "cleaned_specification_files": clean_and_merge(brand, preprocess_specification_file, "*_specifications.csv"),
            "cleaned_review_files": clean_and_merge(brand, preprocess_review_file, "*_reviews.csv"),
            "script_output": result.stdout.strip()
        }
        return jsonify(response_data), 200

    except subprocess.CalledProcessError as e:
        logging.error(f"Scraping failed for {brand}: {e.stderr.strip()}")
        return jsonify({"status": "error", "error": e.stderr.strip()}), 500

# ----- Endpoint: Scrape Next Row -----
@app.route("/scrape-next", methods=["POST"])
def scrape_next():
    if not os.path.exists(CATEGORIES_CSV):
        return jsonify({"error": "categories.csv not found"}), 500

    df = pd.read_csv(CATEGORIES_CSV)
    df['last_scraped'] = pd.to_datetime(df.get('last_scraped', pd.NaT), errors='coerce')
    today = pd.Timestamp(datetime.today().date())

    next_row = df[df['last_scraped'] != today].head(1)
    if next_row.empty:
        return '', 204

    row = next_row.iloc[0]
    request_data = {"brand": row['brand'], "url": row['url'], "category_id": row['category_id']}

    logging.info(f"Dispatching next scrape: {request_data}")

    with app.test_request_context(json=request_data):
        scrape_response = scrape()

    try:
        response_data, status_code = scrape_response
    except Exception:
        logging.exception("Failed to parse scrape response.")
        return jsonify({"error": "Internal scraping error"}), 500

    if status_code == 200:
        df.at[next_row.index[0], 'last_scraped'] = today
        df.to_csv(CATEGORIES_CSV, index=False)
        logging.info(f"Updated last_scraped for {row['url']}")
        return response_data, 200
    else:
        logging.error(f"Scrape failed: {response_data.get_json()}")
        return jsonify({"error": "Scrape failed", "details": response_data.get_json()}), 500

# ----- Health Check -----
@app.route("/")
def home():
    return "<h2>Web Scraping API is live</h2><p>Use POST /scrape or /scrape-next</p>"

# ----- Run App -----
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
