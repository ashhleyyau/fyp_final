import pandas as pd
import re
import os

# Map recipe category to food type
def map_category(category):
    cat = str(category).lower()
    if 'cake' in cat or 'dessert' in cat:
        return 'cake'
    if 'bread' in cat:
        return 'bread'
    if 'fruit' in cat:
        return 'fruit'
    if 'vegetable' in cat or 'salad' in cat:
        return 'vegetable'
    if 'meal' in cat or 'main' in cat or 'dinner' in cat or 'lunch' in cat:
        return 'meal'
    return None

# Validate food name
def is_valid_name(name):
    name = str(name)
    if len(name) < 3 or len(name) > 50:
        return False
    if re.search(r'\d', name):
        return False
    if re.search(r'\b[IVXLCDM]{2,}\b', name.upper()):
        return False
    if name.count('/') > 1 or name.count('&') > 1:
        return False
    return True

# Clean Excel data and save to CSV
def clean_and_save_seed_data(excel_path='foodtype_dataset.xlsx', csv_path='cleaned_seed_foods.csv'):
    if not os.path.exists(excel_path):
        print(f"Warning: {excel_path} not found. Using fallback seed data.")
        return 0

    df = pd.read_excel(excel_path)
    title_col = 'recipe_title'
    category_col = 'category'
    
    seen = set()
    cleaned = []
    for _, row in df.iterrows():
        title = row[title_col]
        category = row[category_col]
        ftype = map_category(category)
        if not ftype:
            continue
        if not is_valid_name(title):
            continue
        if title in seen:
            continue
        seen.add(title)
        cleaned.append((title, ftype))
    
    out_df = pd.DataFrame(cleaned, columns=['food_name', 'food_type'])
    out_df.to_csv(csv_path, index=False)
    print(f"Saved {len(cleaned)} cleaned seed foods to {csv_path}")
    return len(cleaned)

# Run manually
if __name__ == '__main__':
    clean_and_save_seed_data()