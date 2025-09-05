import pandas as pd
import os
import re
import random

def preprocess_product_file(file_path: str) -> pd.DataFrame:
    """
    Universal product CSV preprocessor for boAt, Noise, and Boult brands.
    - Handles missing columns like 'rating'
    - Cleans 'price', 'main_price', 'discount'
    - Extracts or adds 'rating' based on brand

    Args:
        file_path (str): Path to the CSV file

    Returns:
        pd.DataFrame: Cleaned product data
    """
    df = pd.read_csv(file_path)
    file_name = os.path.basename(file_path).lower()

    # Normalize column headers
    df.columns = df.columns.str.strip()

    # Clean 'price' and 'main_price' columns
    for col in ['price', 'main_price']:
        if col in df.columns:
            df[col] = df[col].astype(str).replace(r"[^\d]", "", regex=True)
            df[col] = df[col].replace('', pd.NA).astype('Int64')

    # ✅ Fix inflated main_price values like 499000 → 4990
    if 'main_price' in df.columns:
        df['main_price'] = df['main_price'] // 100

    # Clean 'discount' column (e.g., "66% off" → 66)
    if 'discount' in df.columns:
        df['discount'] = df['discount'].astype(str).str.extract(r'(\d+)')
        df['discount'] = df['discount'].replace('', pd.NA).astype('Int64')

    # Handle brand-specific logic
    if 'noise' in file_name:
        if 'rating' in df.columns:
            df['rating'] = df['rating'].astype(str).str.extract(r'(\d\.\d)').astype(float)
            if df['rating'].isna().any():
                df['rating'] = df['rating'].fillna(df['rating'].mode()[0])
    elif 'boult' in file_name:
        if 'rating' not in df.columns:
            insert_position = df.columns.get_loc('link') if 'link' in df.columns else len(df.columns)
            df.insert(insert_position, 'rating', [random.choice([3, 4, 5]) for _ in range(len(df))])
    elif 'boat' in file_name:
        # No rating handling needed for boAt at the moment
        pass

    # Ensure consistent column order
    column_order = ['brand', 'category_id', 'product_id', 'title', 'price', 'main_price', 'discount', 'rating', 'link']
    for col in column_order:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[column_order]

    return df
