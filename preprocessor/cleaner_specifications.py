import pandas as pd
import re
import html

def preprocess_specification_file(file_path: str) -> pd.DataFrame:
    """
    Universal cleaner for boAt, Boult, and Noise specification CSVs.

    - Cleans 'key' and 'value' fields only
    - Lowercases all text
    - Decodes HTML entities like &nbsp;, &amp;
    - Replaces common separators (x, ×, +) with space
    - Inserts space between digits and letters
    - Removes special characters (preserving alphanumerics and spaces)
    - Normalizes whitespace

    Args:
        file_path (str): Path to the specification CSV

    Returns:
        pd.DataFrame: Cleaned specification data
    """
    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip().str.lower()

    # Standardize column names
    column_map = {
        'product id': 'product_id'
    }
    for col in df.columns:
        if 'key' in col and 'key' not in column_map:
            column_map[col] = 'key'
        if 'value' in col and 'value' not in column_map:
            column_map[col] = 'value'
    df.rename(columns=column_map, inplace=True)

    def clean_text(text: str) -> str:
        if pd.isna(text):
            return ''
        text = str(text).lower().strip()
        text = html.unescape(text)
        text = text.replace('\xa0', ' ').replace('\u200b', ' ')
        text = re.sub(r'\s*[xX\u00D7+]\s*', ' ', text)
        text = re.sub(r'(?<=\d)(?=[a-zA-Z])', ' ', text)
        text = re.sub(r'(?<=[a-zA-Z])(?=\d)', ' ', text)
        text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
        return re.sub(r'\s+', ' ', text).strip()

    for col in ['key', 'value']:
        if col in df.columns:
            df[col] = df[col].fillna('').apply(clean_text)

    return df
