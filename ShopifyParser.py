import json
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any


REQUIRED_FIELDS = [
    "order_number", "theme", "product", "quantity",
    "name", "first_name", "arabic_name", "class", "school_name", "comments",
    "nickname", "initials",
    "phone_number", "main_sheet_choices", "subject_choices", "pencil_choice"
]

PROPERTY_MAPPING = {
    "name": ["name", "full_name", "full name", "fullname"],
    "first_name": ["first name", "first_name", "firstname"],
    "nickname": ["nickname", "nick", "call name"],
    "initials": ["initials", "initial"],
    "arabic_name": ["arabic name"],
    "class": ["class"],
    "school_name": ["school name"],
    "comments": ["comments"],
    "phone_number": ["text-5"],
    "main_sheet_choices": ["waterproof labels"],
    "subject_choices": ["subject sheet"],
    "pencil_choice": ["checkbox-16"],
}

IGNORED_ACCESSORIES = {
}

BAG_TAG_KEYWORDS = {
    "wooden tag",
    "wood tag",
    "laminated tag",
    "bag tag only",
    "bag tag",
}

TRACKED_MISSING_FIELDS = {
    "name": "Name",
    "arabic_name": "Arabic Name",
    "phone_number": "Phone Number"
}


class ShopifyLabelParser:

    def __init__(self):
        self.stats = {
            "orders_processed": 0,
            "line_items_found": 0,
            "accessories_ignored": 0,
            "items_exported": 0,
            "missing_fields": defaultdict(int)
        }

    @staticmethod
    def normalize_product_name(raw_product: str) -> str:
        if not raw_product:
            return ""
        
        pattern = r"(?i)(\b\d+\s*le\b|\s*\(\s*\d+\s*labels?\s*\)|\s*-\s*\d+\s*labels?\b)"
        
        clean_name = re.sub(pattern, "", raw_product)
        
        clean_name = " ".join(clean_name.split())
        return clean_name.capitalize()

    @staticmethod
    def normalize_properties(raw_properties: List[Dict[str, Any]]) -> Dict[str, str]:
        normalized = {}
        for prop in raw_properties or []:
            name = str(prop.get("name", "")).strip()
            value = prop.get("value", "")

            if not name or name.startswith("_"):
                continue

            normalized_key = name.lower()
            normalized[normalized_key] = str(value).strip() if value is not None else ""
            
        return normalized

    @staticmethod
    def extract_field(normalized_props: Dict[str, str], output_key: str) -> str:
        aliases = PROPERTY_MAPPING.get(output_key, [])
        for alias in aliases:
            if alias in normalized_props:
                return normalized_props[alias]
        return ""

    def is_accessory(self, title: str, variant_title: str) -> bool:
        combined_text = f"{title} {variant_title}".lower()
        for accessory in IGNORED_ACCESSORIES:
            if accessory in combined_text:
                return True
        return False

    @staticmethod
    def is_bag_tag(title: str, variant_title: str) -> bool:
        combined = f"{title} {variant_title}".lower()
        return any(kw in combined for kw in BAG_TAG_KEYWORDS)

    def process_order(self, order: Dict[str, Any]) -> List[Dict[str, Any]]:
        exported_items = []
        order_number = order.get("order_number", "")
        
        self.stats["orders_processed"] += 1

        for item in order.get("line_items", []):
            self.stats["line_items_found"] += 1
            
            theme = item.get("title", "")
            raw_product = item.get("variant_title", "")

            if self.is_accessory(theme, raw_product):
                self.stats["accessories_ignored"] += 1
                continue

            product = self.normalize_product_name(raw_product)

            if self.is_bag_tag(theme, raw_product):
                product = "Bag tag"
            quantity = item.get("quantity", 1)
            props = self.normalize_properties(item.get("properties", []))

            normalized_item = {
                "order_number": order_number,
                "theme": theme,
                "product": product,
                "quantity": quantity
            }

            for key in REQUIRED_FIELDS[4:]:
                extracted_val = self.extract_field(props, key)
                normalized_item[key] = extracted_val
                
                if not extracted_val and key in TRACKED_MISSING_FIELDS:
                    self.stats["missing_fields"][TRACKED_MISSING_FIELDS[key]] += 1

            exported_items.append(normalized_item)
            self.stats["items_exported"] += 1

        return exported_items

    def parse(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        normalized_data = []
        orders = raw_data.get("orders", [])
        
        for order in orders:
            normalized_data.extend(self.process_order(order))
            
        return normalized_data

    def print_statistics(self, output_file: str):
        print("\n====================================================")
        print("SHOPIFY LABEL PARSER")
        print("====================================================")
        print(f"Orders processed      : {self.stats['orders_processed']}")
        print(f"Line items found      : {self.stats['line_items_found']}")
        print(f"Accessories ignored   : {self.stats['accessories_ignored']}")
        print(f"Items exported        : {self.stats['items_exported']}")
        print("\nMissing Fields")
        
        for display_name in TRACKED_MISSING_FIELDS.values():
            count = self.stats["missing_fields"].get(display_name, 0)
            print(f"{display_name:<21}: {count}")
            
        print("\nOutput")
        print(f"{output_file}")
        print("====================================================\n")


def main():
    input_filepath = Path("raw_orders.json")
    output_filepath = Path("normalized_orders.json")

    if not input_filepath.exists():
        print(f"Error: Could not find input file '{input_filepath}'")
        return

    try:
        with open(input_filepath, "r", encoding="utf-8") as f:
            raw_shopify_data = json.load(f)
    except json.JSONDecodeError:
        print(f"Error: '{input_filepath}' contains invalid JSON.")
        return

    parser = ShopifyLabelParser()
    normalized_orders = parser.parse(raw_shopify_data)

    with open(output_filepath, "w", encoding="utf-8") as f:
        json.dump(
            normalized_orders,
            f,
            ensure_ascii=False,
            indent=4
        )

    parser.print_statistics(output_filepath.name)


if __name__ == "__main__":
    main()
