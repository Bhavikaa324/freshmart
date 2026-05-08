import os
import json
import logging
import urllib.parse
import aiohttp
from openai import AsyncOpenAI
from dotenv import load_dotenv
from backend.db import save_shopping_list, load_shopping_list, get_user
from backend.twilio_client import send_whatsapp_list

load_dotenv()

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

MODEL = "llama-3.3-70b-versatile"
MAX_HISTORY_TURNS = 10

_user_state: dict = {}

LANGUAGE_NAMES = {
    "en-IN": "English",
    "hi-IN": "Hindi",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "mr-IN": "Marathi",
    "gu-IN": "Gujarati",
    "bn-IN": "Bengali",
    "pa-IN": "Punjabi",
    "od-IN": "Odia",
}


def _get_state(user_id: str) -> dict:
    if user_id not in _user_state:
        existing = load_shopping_list(user_id)
        user_info = get_user(user_id) or {}
        _user_state[user_id] = {
            "history": [],
            "shopping_list": existing,
            "language": "en-IN",
            "name": user_info.get("name", "Customer"),
        }
    return _user_state[user_id]


def set_user_language(user_id: str, language: str):
    _get_state(user_id)["language"] = language
    logger.info(f"[{user_id}] Language: {language}")


def get_shopping_list(user_id: str) -> list:
    return _get_state(user_id)["shopping_list"]


def clear_user_memory(user_id: str):
    if user_id in _user_state:
        save_shopping_list(user_id, _user_state[user_id]["shopping_list"])
        logger.info(f"[{user_id}] Saved to MongoDB on disconnect")
    _user_state.pop(user_id, None)


def _format_list_for_prompt(shopping_list: list) -> str:
    if not shopping_list:
        return "empty"
    return ", ".join(
        f"{item['name']} ({item['quantity']})" for item in shopping_list
    )


OFF_CACHE = {}
GOOGLE_IMAGE_CACHE = {}


async def fetch_google_image(item: str) -> str:
    item_lower = item.lower()
    if item_lower in GOOGLE_IMAGE_CACHE:
        return GOOGLE_IMAGE_CACHE[item_lower]

    api_key = os.getenv("GOOGLE_SEARCH_API_KEY", "").strip()
    search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID", "").strip()
    if not api_key or not search_engine_id:
        GOOGLE_IMAGE_CACHE[item_lower] = ""
        return ""

    image_url = ""
    try:
        query = f"{item} grocery product"
        params = {
            "key": api_key,
            "cx": search_engine_id,
            "q": query,
            "searchType": "image",
            "num": 1,
            "safe": "active",
        }
        url = "https://www.googleapis.com/customsearch/v1"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=4) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    items = data.get("items", [])
                    if items:
                        image_url = items[0].get("link", "")
                else:
                    body = await resp.text()
                    logger.warning(
                        f"Google Image Search returned status={resp.status} for {item}. Body={body[:300]!r}"
                    )
    except Exception as e:
        logger.error(f"Google Image Search API error for {item}: {e!r}")

    GOOGLE_IMAGE_CACHE[item_lower] = image_url
    return image_url

PLACEHOLDERS = {
    "vegetable": "vegetable-placeholder.png",
    "fruit": "fruit-placeholder.png",
    "dairy": "dairy-placeholder.png",
    "liquid": "liquid-placeholder.png",
    "grains": "grains-placeholder.png",
    "spices": "spices-placeholder.png",
    "packaged": "default-placeholder.png",
    "default": "default-placeholder.png",
}


def infer_category(item: str) -> str:
    item_lower = item.lower()
    if any(x in item_lower for x in ["water", "oil", "juice", "liquid", "beverage", "soda", "drink"]):
        return "liquid"
    if any(x in item_lower for x in ["cheese", "butter", "paneer", "dahi", "curd", "yogurt", "cream", "ghee","milk"]):
        return "dairy"
    if any(x in item_lower for x in ["apple", "banana", "mango", "orange", "grape", "berry", "fruit", "strawberry"]):
        return "fruit"
    if any(x in item_lower for x in ["tomato", "potato", "onion", "vegetable", "carrot", "garlic", "ginger", "spinach", "cabbage", "cauliflower"]):
        return "vegetable"
    if any(x in item_lower for x in ["rice", "flour", "sugar", "wheat", "dal", "lentil", "grain"]):
        return "grains"
    if any(x in item_lower for x in ["spice", "pepper", "salt", "cumin", "powder", "turmeric", "masala"]):
        return "spices"
    if any(x in item_lower for x in ["biscuit", "bread", "maggi", "cookie", "packet", "snack", "pav", "chips", "chocolate"]):
        return "packaged"
    return "default"


async def fetch_openfoodfacts(item: str, category: str = None) -> dict:
    item_lower = item.lower()
    if item_lower in OFF_CACHE:
        res = OFF_CACHE[item_lower]
        cat = category or infer_category(item)
        res["image_url"] = PLACEHOLDERS.get(cat.lower(), PLACEHOLDERS["default"])
        return res
    
    res_data = {}
    try:
        url = f"https://world.openfoodfacts.org/cgi/search.pl?search_terms={urllib.parse.quote(item)}&search_simple=1&action=process&json=1&page_size=1"
        headers = {"User-Agent": "FreshMartAI/1.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=8) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    products = data.get("products", [])
                    if products:
                        p = products[0]
                        unit = p.get("product_quantity_unit", "").lower()
                        qty = p.get("product_quantity")
                        if not unit and p.get("quantity"):
                            q_str = p.get("quantity").lower()
                            if "g" in q_str: unit = "g"
                            elif "ml" in q_str: unit = "ml"
                            elif "kg" in q_str: unit = "kg"
                            elif "l" in q_str: unit = "liters"
                        if unit == "l": unit = "liters"
                        
                        if unit in ["g", "kg", "ml", "liters", "packets", "unit", "packs"]:
                            res_data["unit"] = unit
                        if qty:
                            res_data["quantity"] = float(qty)

        # Do not fetch any image URLs from Open Food Facts or online search APIs.
        # Always use the corresponding category placeholder.
        cat = category or infer_category(item)
        res_data["image_url"] = PLACEHOLDERS.get(cat.lower(), PLACEHOLDERS["default"])
    except Exception as e:
        logger.error(f"OpenFoodFacts API error for {item}: {e!r}")
        
    OFF_CACHE[item_lower] = res_data
    return res_data

async def infer_unit(item: str) -> str:
    item_lower = item.lower()
    if any(x in item_lower for x in ["milk", "water", "oil", "juice", "liquid"]):
        return "liters"
    if any(x in item_lower for x in ["ice cream", "icecream", "dahi", "curd", "yogurt"]):
        return "ml"
    if any(x in item_lower for x in ["rice", "flour", "sugar", "wheat", "dal", "lentil"]):
        return "kg"
    if any(x in item_lower for x in ["spice", "pepper", "salt", "cumin", "powder", "turmeric"]):
        return "g"
    if any(x in item_lower for x in ["apple", "banana", "tomato", "potato", "onion", "vegetable", "fruit", "carrot"]):
        return "kg"
    if any(x in item_lower for x in ["cheese", "butter", "paneer"]):
        return "g"
    if any(x in item_lower for x in ["biscuit", "bread", "maggi", "cookie", "packet", "snack", "pav"]):
        return "packets"
        
    api_data = await fetch_openfoodfacts(item)
    if api_data.get("unit"):
        return api_data["unit"]
        
    return "unit"

async def default_value(item: str) -> int:
    api_data = await fetch_openfoodfacts(item)
    if api_data.get("quantity"):
        return int(api_data["quantity"])
        
    unit = await infer_unit(item)
    if unit == "g":
        return 250
    if unit == "ml":
        return 500
    return 1


def format_item_quantity(qty_num, unit_str) -> str:
    if not isinstance(qty_num, (int, float)):
        return f"{qty_num} {unit_str}"
        
    if unit_str in ["g", "grams"] and qty_num >= 1000:
        if qty_num % 1000 == 0:
            qty_num = int(qty_num // 1000)
        else:
            qty_num = qty_num / 1000
        unit_str = "kg"
    elif unit_str in ["ml", "milliliters"] and qty_num >= 1000:
        if qty_num % 1000 == 0:
            qty_num = int(qty_num // 1000)
        else:
            qty_num = qty_num / 1000
        unit_str = "liters"

    if isinstance(qty_num, float) and qty_num.is_integer():
        qty_num = int(qty_num)

    if qty_num == 1:
        if unit_str == "liters": unit_str = "liter"
        elif unit_str == "packets": unit_str = "packet"
        elif unit_str == "bars": unit_str = "bar"
        elif unit_str == "pieces": unit_str = "piece"
        elif unit_str == "units": unit_str = "unit"
        elif unit_str == "packs": unit_str = "pack"
    elif isinstance(qty_num, (int, float)) and qty_num > 1:
        if unit_str == "liter": unit_str = "liters"
        elif unit_str == "packet": unit_str = "packets"
        elif unit_str == "bar": unit_str = "bars"
        elif unit_str == "piece": unit_str = "pieces"
        elif unit_str == "unit": unit_str = "units"
        elif unit_str == "pack": unit_str = "packs"

    return f"{qty_num} {unit_str}"


def _build_system_prompt(user_id: str, shopping_list: list, language: str, user_name: str) -> str:
    list_str = _format_list_for_prompt(shopping_list)
    lang_name = LANGUAGE_NAMES.get(language, "English")
    return f"""You are Priya, a polite professional AI grocery assistant at FreshMart.
You are on a voice call with {user_name}.

YOUR CURRENT SHOPPING LIST MEMORY:
[{list_str}]

CRITICAL INSTRUCTIONS:
1. You MUST output a strictly valid JSON object. Do not output anything outside of the JSON format.
2. Structure your JSON exactly like this example:
{{
  "adds": [
    {{
      "item": "Tomato",
      "category": "vegetable",
      "quantity": 500,
      "unit": "g"
    }},
    {{
      "item": "Milk",
      "category": "liquid",
      "quantity": 2,
      "unit": "liters"
    }}
  ],
  "removes": [
    "Name of the item to remove, MUST be written purely in {lang_name}"
  ],
  "updates": [
    {{
      "item": "Name of the existing item to update, MUST be written purely in {lang_name}",
      "new_quantity": 3,
      "new_unit": "liters"
    }}
  ],
  "is_confirmed": false,
  "reply": "Your conversational reply to the user spoken aloud"
}}

STRICT RULES FOR ITEMS:
1. NEVER return null or empty values for quantity. DO NOT use "1" without a unit.
2. Choose units based on item type:
   - Vegetables & fruits -> grams (g) or kilograms (kg)
   - Liquids (milk, oil) -> ml or liters
   - Frozen/Ice Cream/Dahi/Curd/Yogurt -> ml or liters
   - Grains (rice, flour) -> grams or kg
   - Dairy (cheese, butter) -> grams
   - Packaged items (biscuits, bread, maggi, pav) -> packets or pieces (e.g., pav is sold in packets)
   - Spices -> grams
3. If quantity is missing, estimate a reasonable default based on real shopping. NEVER return null.
4. Normalize values: e.g. 1000g -> 1kg (convert any quantity above 1000g to kgs, for e.g 1200g -> 1.2kg or 1kg 200g and same for ml and litres), 240g -> 250g. Combine duplicate items e.g., milk (null), milk (2 liters) -> milk (2 liters).
5. If the input is a recipe:
   - Generate ingredients with quantities per person
   - Multiply by number of people
   - Convert all quantities into practical shopping units
   - Prefer grams/kg over pieces for vegetables

RULES FOR ACTIONS:
- "adds": List items to add. Follow the STRICT RULES FOR ITEMS.
- "removes": List items to remove. Leave empty if none.
- "updates": List items to change quantity of. Follow the STRICT RULES FOR ITEMS.
- "is_confirmed": Set to true ONLY when the user explicitly confirms the order.
- "reply": Your spoken reply in {lang_name}. Keep it plain spoken (no symbols, markdown, acronyms), 1-2 short sentences. If is_confirmed is true, completely translate the final itemized order summary into {lang_name}.
"""


async def run_llm(user_id: str, user_message: str) -> tuple:
    state         = _get_state(user_id)
    shopping_list = state["shopping_list"]
    language      = state.get("language", "en-IN")
    
    # Track the conversational history context
    history = state["history"]
    trimmed = history[-(MAX_HISTORY_TURNS * 2):]
    
    # Note: We must NOT pass the assistant's previous raw JSON into history as "assistant",
    # otherwise it confuses the context window. We only track what they actually "said".
    
    messages = [{"role": "system", "content": _build_system_prompt(user_id, shopping_list, language, state.get("name", "Customer"))}]
    for h in trimmed:
        messages.append(h)
    messages.append({"role": "user", "content": user_message})

    try:
        response = await _client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=250,
            response_format={"type": "json_object"},
        )
        raw_output = response.choices[0].message.content.strip()
        data = json.loads(raw_output)
    except Exception as e:
        logger.error(f"LLM JSON extraction error: {e}")
        # Fallback if parsing completely fails
        return "I'm sorry, I encountered an issue making sense of that. Could you repeat?", False

    adds   = data.get("adds", [])
    removes = data.get("removes", [])
    updates = data.get("updates", [])
    reply  = data.get("reply", "Okay.")
    is_confirmed = data.get("is_confirmed", False)

    logger.info(f"[{user_id}] Adds={adds}, Removes={removes}, Updates={updates}, Confirmed={is_confirmed} | LLM Reply: {reply!r}")

    list_changed = False

    # Process Actions Locally
    if adds:
        for i in adds:
            item = i.get("item")
            quantity = i.get("quantity")
            unit = i.get("unit")
            cat = i.get("category", "")
            if item:
                if quantity is None:
                    quantity = await default_value(item)
                if unit is None or unit == "":
                    unit = await infer_unit(item)
                
                api_data = await fetch_openfoodfacts(item, category=cat)
                img_url = api_data.get("image_url", "")
                
                qty_str = format_item_quantity(quantity, unit)
                
                existing = next((x for x in shopping_list if x["name"].lower() == item.lower()), None)
                if existing:
                    existing["quantity"] = qty_str
                    if cat:
                        existing["category"] = cat
                    if img_url and not existing.get("image_url"):
                        existing["image_url"] = img_url
                    logger.info(f"[{user_id}] 🔄 OVERWROTE DUPLICATE: {existing}")
                else:
                    entry = {"name": item, "quantity": qty_str, "category": cat}
                    if img_url:
                        entry["image_url"] = img_url
                    shopping_list.append(entry)
                    logger.info(f"[{user_id}] ✅ ADDED: {entry}")
                list_changed = True

    if removes:
        missing_items = []
        for item in removes:
            if isinstance(item, dict):
                item = item.get("item") or item.get("name")
            
            if not item or not isinstance(item, str):
                continue
            
            removed = None
            for entry in shopping_list:
                if item.lower() in entry["name"].lower() or entry["name"].lower() in item.lower():
                    removed = entry
                    break
            
            if removed:
                shopping_list.remove(removed)
                logger.info(f"[{user_id}] ❌ REMOVED: {removed}")
                list_changed = True
            else:
                logger.info(f"[{user_id}] Requested item {item!r} to remove but not found in list.")
                missing_items.append(item)
                
        if missing_items:
            reply = f"I am sorry, but I could not find {', '.join(missing_items)} on your list to remove. " + reply

    if updates:
        missing_updates = []
        for upd in updates:
            if not upd or not isinstance(upd, dict):
                continue
            item = upd.get("item")
            quantity = upd.get("new_quantity")
            unit = upd.get("new_unit")
            
            if not item:
                continue
                
            if quantity is None:
                quantity = await default_value(item)
            if unit is None or unit == "":
                unit = await infer_unit(item)
                
            new_qty = format_item_quantity(quantity, unit)
            
            # Fuzzy match to update
            updated = None
            for entry in shopping_list:
                if item.lower() in entry["name"].lower() or entry["name"].lower() in item.lower():
                    entry["quantity"] = new_qty
                    updated = entry
                    break
            
            if updated:
                logger.info(f"[{user_id}] 🔄 UPDATED: {updated}")
                list_changed = True
            else:
                logger.info(f"[{user_id}] Requested item {item!r} to update but not found.")
                missing_updates.append(item)
                
        if missing_updates:
            reply = f"I could not find {', '.join(missing_updates)} on your list to update. " + reply

    if list_changed:
        save_shopping_list(user_id, shopping_list)

    # Record ONLY the spoken conversation string to history, not the JSON block
    state["history"].append({"role": "user", "content": user_message})
    state["history"].append({"role": "assistant", "content": reply})

    if is_confirmed:
        user = get_user(user_id)
        if user and user.get("phone"):
            logger.info(f"[{user_id}] 🟢 Order confirmed! Sending WhatsApp to {user['phone']}...")
            import asyncio
            asyncio.create_task(asyncio.to_thread(send_whatsapp_list, user["phone"], shopping_list))
        else:
            logger.warning(f"[{user_id}] ⚠️ Order confirmed but no phone number found to send WhatsApp.")

    return reply, is_confirmed


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        user_id = "test_user_json"
        print("FreshMart JSON Intelligence Shell (type 'quit' to exit)")
        print("Say something conversational like: 'remove the sugar that is in it'")
        while True:
            try:
                user_msg = input("\nYou: ")
                if user_msg.lower().strip() in ('quit', 'exit'):
                    break
                reply, is_confirmed = await run_llm(user_id, user_msg)
                print(f"Priya: {reply}")
                if is_confirmed:
                    print("[System: Order Confirmed!]")
            except EOFError:
                break

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass