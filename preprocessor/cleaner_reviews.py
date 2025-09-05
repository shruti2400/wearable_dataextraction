import pandas as pd
import nltk
import re
from nltk.tokenize import word_tokenize
from pathlib import Path

# --- NLTK Setup (cross-platform safe) ---
project_root = Path(__file__).resolve().parent.parent
nltk_data_dir = project_root / "nltk_data"
nltk.data.path.append(str(nltk_data_dir))

# Ensure punkt and punkt_tab are available
for resource in ["punkt", "punkt_tab"]:
    try:
        nltk.data.find(f"tokenizers/{resource}")
    except LookupError:
        nltk.download(resource, download_dir=nltk_data_dir, quiet=True)


# def preprocess_review_file(file_path: str) -> pd.DataFrame:
#     """
#     Universal review CSV preprocessor for boAt, Noise, and Boult review data.

#     Steps:
#     1. Remove emojis/special chars, lowercase, tokenize
#     2. Replace empty strings with NaN
#     3. Drop rows with empty body
#     4. Fill missing titles with mode
#     """

#     df = pd.read_csv(file_path)

#     # Ensure minimum expected columns
#     for col in ["title", "body", "author", "rating"]:
#         if col not in df.columns:
#             df[col] = pd.NA

#     # --- Emoji & special char removal ---
#     emoji_pattern = re.compile(
#         "["
#         u"\U0001F600-\U0001F64F"
#         u"\U0001F300-\U0001F5FF"
#         u"\U0001F680-\U0001F6FF"
#         u"\U0001F1E0-\U0001F1FF"
#         u"\U00002700-\U000027BF"
#         u"\U0001F900-\U0001F9FF"
#         u"\U0001FA70-\U0001FAFF"
#         u"\U00002600-\U000026FF"
#         u"\U00002B00-\U00002BFF"
#         u"\u200d"
#         u"\u2640-\u2642"
#         "]+",
#         flags=re.UNICODE
#     )

#     def clean_text(text: str) -> str:
#         if pd.isna(text):
#             return ""
#         text = str(text).lower()
#         text = emoji_pattern.sub("", text)  # remove emojis
#         text = re.sub(r"[^a-zA-Z0-9\s]", "", text)  # keep alphanumerics
#         words = word_tokenize(text)
#         return " ".join(words).strip()

#     # Apply cleaning
#     for col in ["title", "body", "author"]:
#         df[col] = df[col].astype(str).apply(clean_text)

#     # Replace empty strings with NaN
#     for col in ["title", "body"]:
#         df[col] = df[col].replace("", pd.NA)

#     # Drop rows with empty body
#     df = df[df["body"].notna()]

#     # Fill missing titles with mode
#     if df["title"].notna().any():
#         mode_title = df["title"].mode()
#         if not mode_title.empty:
#             df["title"] = df["title"].fillna(mode_title.iloc[0])
#     else:
#         df["title"] = df["title"].fillna("No Title")

#     # Reset index
#     return df.reset_index(drop=True)



def preprocess_review_file(file_path: str) -> pd.DataFrame:
    """
    Universal review CSV preprocessor for boAt, Noise, and Boult review data.

    Cleans and normalizes the review content:
    - Fills missing 'title' using mode
    - Removes emojis and special characters from text fields
    - Converts to lowercase and tokenizes using NLTK

    Args:
        file_path (str): Path to the review CSV file

    Returns:
        pd.DataFrame: Cleaned review DataFrame
    """
    df = pd.read_csv(file_path)

    # Fill missing 'title' with mode if available
    if 'title' in df.columns and df['title'].isnull().any():
        mode_title = df['title'].mode()
        if not mode_title.empty:
            df['title'] = df['title'].fillna(mode_title[0])

    # Compile emoji pattern for removal
    emoji_pattern = re.compile(
        "["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags
        u"\U00002700-\U000027BF"  # dingbats
        u"\U0001F900-\U0001F9FF"  # supplemental symbols
        u"\U0001FA70-\U0001FAFF"  # extended symbols
        u"\U00002600-\U000026FF"  # misc symbols
        u"\U00002B00-\U00002BFF"  # arrows
        u"\u200d"                  # zero width joiner
        u"\u2640-\u2642"          # gender symbols
        "]+", flags=re.UNICODE
    )

    def clean_text(text: str) -> str:
        if pd.isna(text):
            return ""
        text = text.lower()
        text = emoji_pattern.sub('', text)
        text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
        words = word_tokenize(text)
        return ' '.join(words)

    for col in ['title', 'body', 'author']:
        if col in df.columns:
            df[col] = df[col].apply(clean_text)

    # Drop empty or whitespace-only review bodies
    if 'body' in df.columns:
        df = df[df['body'].str.strip().ne('')].reset_index(drop=True)

    return df
