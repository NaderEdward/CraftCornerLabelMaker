import json
import re
from pathlib import Path


INPUT_FILE = "normalized_orders.json"
CLEAN_OUTPUT_FILE = "clean_orders.json"
REVIEW_OUTPUT_FILE = "manual_review_orders.json"

REVIEW_PRODUCTS = [
    "Change the subjects", 
    "Clipart subjects", 
    "sticker sheet"
]

REVIEW_THEMES = [
    "caricature boys",
    "caricature girls",
    "name 3d spring",
    "name chromatix",
    "name creative handmade",
    "name fattem",
    "name frisia",
    "name neon",
    "name paint splashes",
    "name power of spring",
    "name smile",
    "name stitches",
    "name twinkle",
    "name white hope",
    "new theme",
]

VALUE_PACK_REVIEW_SUBJECTS = [
    "Clipart subject sheet",
    "Change the subjects"
]


def remove_extra_whitespace(text: str) -> str:
    if not isinstance(text, str):
        return str(text) if text is not None else ""
    return re.sub(r'\s+', ' ', text).strip()

def clean_phone_number(phone: str) -> str:
    if not phone:
        return ""
    return re.sub(r'[\s\-\(\)]+', '', str(phone))


def process_orders():
    input_path = Path(INPUT_FILE)
    
    if not input_path.exists():
        print(f"Error: Could not find '{INPUT_FILE}'. Please ensure the file exists.")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            print(f"Error: '{INPUT_FILE}' contains invalid JSON.")
            return

    clean_orders = []
    review_orders = []

    for item in data:
        
        for key, value in item.items():
            if isinstance(value, str):
                item[key] = remove_extra_whitespace(value)

        if "name" in item:
            item["name"] = item["name"].title() 

        phone_key = "text_5" if "text_5" in item else "phone_number"
        cleaned_phone = clean_phone_number(item.get(phone_key, ""))
        item[phone_key] = cleaned_phone

        
        needs_review = False
        reasons = []

        phone_length = len(cleaned_phone)
        if phone_length > 0 and phone_length not in [11, 13]:
            needs_review = True
            reasons.append(f"Invalid phone length ({phone_length} chars)")

        class_val = item.get("class", "")
        if len(class_val) > 9:
            needs_review = True
            reasons.append(f"Class length too long ({len(class_val)} chars)")

        product_val_lower = item.get("product", "").lower()
        if any(flag.lower() in product_val_lower for flag in REVIEW_PRODUCTS):
            needs_review = True
            reasons.append("Flagged product type detected")
            
        comments_val = item.get("comments", "")
        if comments_val:
            needs_review = True
            reasons.append("Contains custom comments")

        if "value pack" in product_val_lower:
            subject_choices_lower = item.get("subject_choices", "").lower()
            if any(trigger.lower() in subject_choices_lower for trigger in VALUE_PACK_REVIEW_SUBJECTS):
                needs_review = True
                reasons.append(f"Value pack contains custom subject choice ('{item.get('subject_choices')}')")


        theme_lower = item.get("theme", "").lower()
        if any(t in theme_lower for t in REVIEW_THEMES):
            needs_review = True
            reasons.append(f"Theme requires manual review ('{item.get('theme')}')")

        if theme_lower.startswith("name"):
            needs_review = True
            reasons.append(f"'Name' theme requires manual rendering ('{item.get('theme')}')")

        
        if needs_review:
            item["_review_reasons"] = reasons
            review_orders.append(item)
        else:
            clean_orders.append(item)


    with open(CLEAN_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(clean_orders, f, ensure_ascii=False, indent=4)

    with open(REVIEW_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(review_orders, f, ensure_ascii=False, indent=4)

    print("\n====================================================")
    print("ORDER FILTERING COMPLETE")
    print("====================================================")
    print(f"Total processed : {len(data)}")
    print(f"Clean orders    : {len(clean_orders)} -> Saved to {CLEAN_OUTPUT_FILE}")
    print(f"Manual review   : {len(review_orders)} -> Saved to {REVIEW_OUTPUT_FILE}")
    print("====================================================\n")


if __name__ == "__main__":
    process_orders()
