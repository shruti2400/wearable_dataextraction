
# import os
# import re
# import random
# import pandas as pd

# def preprocess_product_file(file_path: str) -> pd.DataFrame:
#     """
#     Universal product CSV preprocessor for boAt, Noise, and Boult brands.
#     - Handles missing columns like 'rating'
#     - Cleans 'price', 'main_price', 'discount'
#     - Extracts or adds 'rating' based on brand

#     Args:
#         file_path (str): Path to the CSV file

#     Returns:
#         pd.DataFrame: Cleaned product data
#     """
#     df = pd.read_csv(file_path)
#     file_name = os.path.basename(file_path).lower()

#     df.columns = df.columns.str.strip()

#     # Clean pricing columns
#     for col in ["price", "main_price"]:
#         if col in df.columns:
#             df[col] = (
#                 df[col]
#                 .astype(str)
#                 .str.replace(r"[^\d.]", "", regex=True)
#                 .replace("", pd.NA)  # Convert empty string to NA
#             )
#             df[col] = pd.to_numeric(df[col], errors="coerce")
#             df[col] = df[col].apply(lambda x: x // 10 if pd.notna(x) and x > 100000 else x)
#             df[col] = df[col].astype("Int64")

#     # ✅ Fill null main_price with price if missing
#     if "main_price" in df.columns and "price" in df.columns:
#         df["main_price"] = df["main_price"].fillna(df["price"])

#     # Clean discount column
#     if "discount" in df.columns:
#         df["discount"] = (
#             df["discount"]
#             .astype(str)
#             .str.extract(r"(\d+)")[0]
#             .replace("", pd.NA)
#         )
#         df["discount"] = pd.to_numeric(df["discount"], errors="coerce")

#         # ✅ Fill blank or null discount with mode or 0
#         if df["discount"].notna().any():
#             df["discount"] = df["discount"].fillna(df["discount"].mode()[0])
#         else:
#             df["discount"] = 0

#         df["discount"] = df["discount"].astype("Int64")

#     # Brand-specific logic
#     if "noise" in file_name:
#         if "rating" in df.columns:
#             df["rating"] = (
#                 df["rating"]
#                 .astype(str)
#                 .str.extract(r"(\d\.\d)")[0]
#             )
#             df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
#             if df["rating"].notna().any():
#                 df["rating"] = df["rating"].fillna(df["rating"].mode()[0])
#             else:
#                 df["rating"] = 4.0

#     elif "boult" in file_name:
#         random_ratings = [random.choice([3, 4, 5]) for _ in range(len(df))]
#         if "rating" in df.columns:
#             df["rating"] = random_ratings
#         else:
#             insert_at = df.columns.get_loc("link") if "link" in df.columns else len(df.columns)
#             df.insert(insert_at, "rating", random_ratings)

#     elif "boat" in file_name:
#         if "rating" in df.columns:
#             df["rating"] = (
#                 df["rating"]
#                 .astype(str)
#                 .str.extract(r"(\d\.\d)")[0]
#             )
#             df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
#             fallback = 4.0 if df["rating"].mode().empty else df["rating"].mode()[0]
#             df["rating"] = df["rating"].fillna(fallback)

#     # Ensure column order
#     desired_order = [
#         "brand", "category_id", "product_id", "title",
#         "price", "main_price", "discount", "rating", "link"
#     ]
#     for col in desired_order:
#         if col not in df.columns:
#             df[col] = pd.NA

#     return df[desired_order]

import random
import pandas as pd
from pathlib import Path

def preprocess_product_file(file_path: str) -> pd.DataFrame:
    """
    Universal product CSV preprocessor for boAt, Noise, and Boult brands.
    - Handles missing columns like 'rating'
    - Cleans 'price', 'main_price', 'discount'
    - Extracts or adds 'rating' based on brand
    - Removes invalid rows for Boult if both price columns are missing
    """
    file_path = Path(file_path)  # ensures cross-platform compatibility
    df = pd.read_csv(file_path)
    file_name = file_path.name.lower()

    # Normalize column names
    df.columns = df.columns.str.strip()

    # --- Clean pricing columns ---
    for col in ["price", "main_price"]:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(r"[^\d.]", "", regex=True)
                .replace("", pd.NA)
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df[col] = df[col].apply(
                lambda x: x // 10 if pd.notna(x) and x > 100000 else x
            )
            df[col] = df[col].astype("Int64")

    # ✅ Fill null main_price with price
    if "main_price" in df.columns and "price" in df.columns:
        df["main_price"] = df["main_price"].fillna(df["price"])

    # --- Clean discount ---
    if "discount" in df.columns:
        df["discount"] = (
            df["discount"].astype(str).str.extract(r"(\d+)")[0].replace("", pd.NA)
        )
        df["discount"] = pd.to_numeric(df["discount"], errors="coerce")

        if df["discount"].notna().any():
            df["discount"] = df["discount"].fillna(df["discount"].mode().iloc[0])
        else:
            df["discount"] = 0

        df["discount"] = df["discount"].astype("Int64")

    # --- Brand-specific rating logic ---
    if "noise" in file_name:
        if "rating" in df.columns:
            df["rating"] = (
                df["rating"].astype(str).str.extract(r"(\d\.\d)")[0]
            )
            df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
            if df["rating"].notna().any():
                df["rating"] = df["rating"].fillna(df["rating"].mode().iloc[0])
            else:
                df["rating"] = 4.0

    elif "boult" in file_name:
        random_ratings = [random.choice([3, 4, 5]) for _ in range(len(df))]
        if "rating" in df.columns:
            df["rating"] = random_ratings
        else:
            insert_at = df.columns.get_loc("link") if "link" in df.columns else len(df.columns)
            df.insert(insert_at, "rating", random_ratings)

        # ✅ Drop rows where both price and main_price are missing
        if "price" in df.columns and "main_price" in df.columns:
            df = df.dropna(subset=["price", "main_price"], how="all")

    elif "boat" in file_name:
        if "rating" in df.columns:
            df["rating"] = (
                df["rating"].astype(str).str.extract(r"(\d\.\d)")[0]
            )
            df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
            if not df["rating"].mode().empty:
                fallback = df["rating"].mode().iloc[0]
            else:
                fallback = 4.0
            df["rating"] = df["rating"].fillna(fallback)

    # --- Ensure column order ---
    desired_order = [
        "brand", "category_id", "product_id", "title",
        "price", "main_price", "discount", "rating", "link"
    ]
    for col in desired_order:
        if col not in df.columns:
            df[col] = pd.NA

    return df[desired_order]
