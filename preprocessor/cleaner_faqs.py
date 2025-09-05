import pandas as pd
import re
import logging

# Setup module-level logger
logger = logging.getLogger(__name__)

def preprocess_faq_file(file_path: str) -> pd.DataFrame:
    """
    Universal FAQ CSV preprocessor for boAt, Noise, and Boult brands.
    - Drops rows where 'question' or 'answer' is null or empty
    - Fixes encoding issues (e.g., &amp;)
    - Removes leading 'q '
    - Converts text to lowercase
    - Removes all punctuations
    - Strips whitespace
    - Ensures no rows remain empty after cleaning
    """
    try:
        df = pd.read_csv(file_path)
        logger.info(f"Loaded FAQ file: {file_path} with {len(df)} rows")
    except Exception as e:
        logger.error(f"Failed to load FAQ file {file_path}: {e}")
        return pd.DataFrame()

    df.columns = df.columns.str.strip()

    if 'question' not in df.columns or 'answer' not in df.columns:
        logger.error(f"Missing required columns in {file_path}: {df.columns.tolist()}")
        return pd.DataFrame()

    # Drop rows with NaN
    original_len = len(df)
    df.dropna(subset=['question', 'answer'], inplace=True)

    # Clean text function
    def clean_text(text: str) -> str:
        text = str(text)
        text = text.replace("&amp;", "&")
        text = text.lower()
        text = re.sub(r'^q\s*', '', text)           # remove leading "q "
        text = re.sub(r"[^a-zA-Z0-9\s]", "", text)  # remove punctuations
        text = re.sub(r"\s+", " ", text).strip()    # normalize whitespace
        return text

    df['question'] = df['question'].apply(clean_text)
    df['answer']   = df['answer'].apply(clean_text)

    # Drop rows that became empty after cleaning
    cleaned_len_before = len(df)
    df = df[(df['question'] != "") & (df['answer'] != "")]
    logger.info(f"Removed {cleaned_len_before - len(df)} rows that became empty after cleaning")

    logger.info(f"Finished cleaning FAQ file: {file_path} → {len(df)} cleaned rows")
    return df
