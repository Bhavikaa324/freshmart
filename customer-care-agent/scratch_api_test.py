import requests
import json
import urllib.parse

def test_api(item):
    url = f"https://world.openfoodfacts.org/cgi/search.pl?search_terms={urllib.parse.quote(item)}&search_simple=1&action=process&json=1&page_size=3"
    headers = {"User-Agent": "FreshMartAI/1.0"}
    res = requests.get(url, headers=headers)
    data = res.json()
    products = data.get("products", [])
    
    print(f"Results for '{item}':")
    for p in products:
        name = p.get("product_name", "Unknown")
        qty = p.get("quantity", "")
        unit = p.get("product_quantity_unit", "")
        cats = p.get("categories_tags", [])
        print(f" - {name} | Qty: {qty} | Unit: {unit} | Cats: {cats[:3]}")

if __name__ == "__main__":
    test_api("dahi")
    test_api("maggi")
    test_api("onion")
