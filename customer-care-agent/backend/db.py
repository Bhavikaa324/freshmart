import os
import logging
from datetime import datetime
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MONGO_URI       = os.getenv("MONGO_URI")
DB_NAME         = os.getenv("DB_NAME", "shopping_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "shopping_items")

client = None
collection = None
users_collection = None
_last_connect_attempt = None


def _connect_if_needed(force: bool = False):
    global client, collection, users_collection, _last_connect_attempt
    if not MONGO_URI:
        return

    if collection is not None and users_collection is not None and not force:
        return

    now = datetime.utcnow()
    if (
        not force
        and _last_connect_attempt is not None
        and (now - _last_connect_attempt).total_seconds() < 5
    ):
        return

    _last_connect_attempt = now
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        collection.create_index([("user_id", ASCENDING)])
        users_collection = db["users"]
        users_collection.create_index([("email", ASCENDING)], unique=True)
        client.server_info()
        logger.info("✅ MongoDB connected")
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {e}")
        collection = None
        users_collection = None


def get_db_client():
    _connect_if_needed()
    return client


def get_transcript_collection():
    _connect_if_needed()
    if client is None:
        return None
    try:
        return client[DB_NAME]["transcripts"]
    except Exception:
        return None


_connect_if_needed(force=True)



def save_shopping_list(user_id: str, items: list):
    _connect_if_needed()
    if collection is None:
        logger.error("MongoDB not connected")
        return
    try:
        collection.update_one(
            {"user_id": user_id},
            {"$set": {
                "user_id":    user_id,
                "items":      items,
                "updated_at": datetime.utcnow(),
            }},
            upsert=True,
        )
        logger.info(f"[{user_id}] ✅ Saved: {items}")
    except Exception as e:
        logger.error(f"[{user_id}] Save error: {e}")


def load_shopping_list(user_id: str) -> list:
    _connect_if_needed()
    if collection is None:
        return []
    try:
        doc = collection.find_one({"user_id": user_id})
        if doc and "items" in doc:
            return doc["items"]
        return []
    except Exception as e:
        logger.error(f"[{user_id}] Load error: {e}")
        return []


def archive_shopping_list(user_id: str):
    _connect_if_needed()
    if collection is None:
        return
    try:
        doc = collection.find_one({"user_id": user_id})
        if doc and doc.get("items"):
            # Only archive if the list actually has items
            history_entry = {
                "created_at": datetime.utcnow().isoformat(),
                "items": doc["items"]
            }
            collection.update_one(
                {"user_id": user_id},
                {
                    "$push": {"history": {"$each": [history_entry], "$position": 0}},
                    "$set": {"items": []}
                }
            )
            logger.info(f"[{user_id}] 🗄️ Archived shopping list.")
    except Exception as e:
        logger.error(f"[{user_id}] Archive error: {e}")


def get_all_users() -> list:
    _connect_if_needed()
    if collection is None:
        return []
    try:
        return [doc["user_id"] for doc in collection.find({}, {"user_id": 1})]
    except Exception as e:
        logger.error(f"get_all_users error: {e}")
        return []

def get_shopping_history(user_id: str) -> list:
    _connect_if_needed()
    if collection is None:
        return []
    try:
        doc = collection.find_one({"user_id": user_id})
        if doc and "history" in doc:
            return doc["history"]
        return []
    except Exception as e:
        logger.error(f"[{user_id}] History load error: {e}")
        return []


# ── User / Auth helpers ──────────────────────────────────────────────────────

def upsert_user(email: str, name: str, picture: str) -> dict:
    """Create or update a user profile. Returns the stored document."""
    _connect_if_needed()
    if users_collection is None:
        return {"email": email, "name": name, "picture": picture, "phone": None}
    try:
        users_collection.update_one(
            {"email": email},
            {
                "$set": {"name": name, "picture": picture, "updated_at": datetime.utcnow()},
                "$setOnInsert": {"email": email, "phone": None, "created_at": datetime.utcnow()},
            },
            upsert=True,
        )
        return get_user(email) or {"email": email, "name": name, "picture": picture, "phone": None}
    except Exception as e:
        logger.error(f"upsert_user error: {e}")
        return {"email": email, "name": name, "picture": picture, "phone": None}


def save_user_phone(email: str, phone: str):
    """Persist the user's phone number."""
    _connect_if_needed()
    if users_collection is None:
        return
    try:
        users_collection.update_one(
            {"email": email},
            {"$set": {"phone": phone, "updated_at": datetime.utcnow()}},
        )
        logger.info(f"[{email}] 📱 Phone saved.")
    except Exception as e:
        logger.error(f"save_user_phone error: {e}")


def get_user(email: str) -> dict | None:
    """Return the user document or None."""
    _connect_if_needed()
    if users_collection is None:
        return None
    try:
        doc = users_collection.find_one({"email": email}, {"_id": 0})
        return doc
    except Exception as e:
        logger.error(f"get_user error: {e}")
        return None