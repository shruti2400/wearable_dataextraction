import pandas as pd
import logging
import re

logger = logging.getLogger(__name__)

def preprocess_feature_file(file_path: str) -> pd.DataFrame:
    """
    Universal features CSV preprocessor for boAt, Noise, and Boult brands.
    - Fixes encoding issues (e.g., Â°, &amp;)
    - Converts text to lowercase
    - Removes all punctuations (including °)
    - Strips whitespace
    - Drops duplicate features per product_id

    Args:
        file_path (str): Path to the CSV file

    Returns:
        pd.DataFrame: Cleaned feature data
    """
    try:
        df = pd.read_csv(file_path)
        df.columns = df.columns.str.strip()

        if 'feature' not in df.columns:
            logger.warning(f"Missing 'feature' column in {file_path}")
            return df

        df['feature'] = df['feature'].astype(str)
        df['feature'] = df['feature'].str.replace("Â°", "°", regex=False)
        df['feature'] = df['feature'].str.replace("&amp;", "&", regex=False)

        df['feature'] = (
            df['feature']
            .str.lower()
            .str.replace(r"[^\w\s]", "", regex=True)
            .str.strip()
        )

        if 'product_id' not in df.columns:
            logger.warning(f"Missing 'product_id' column in {file_path}")
            return df

        df.drop_duplicates(subset=['product_id', 'feature'], inplace=True)

        return df

    except Exception as e:
        logger.exception(f"Error processing file {file_path}: {e}")
        return pd.DataFrame()
