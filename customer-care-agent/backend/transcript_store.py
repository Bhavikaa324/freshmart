import logging
from backend.db import get_transcript_collection

logger = logging.getLogger(__name__)

def _collection():
    return get_transcript_collection()

def add_message(user_id: str, role: str, text: str):
    collection = _collection()
    if collection is None:
        return
    try:
        collection.update_one(
            {"user_id": user_id},
            {"$push": {"messages": {"role": role, "content": text}}},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Save transcript error: {e}")

def get_messages(user_id: str) -> list:
    collection = _collection()
    if collection is None:
        return []
    try:
        doc = collection.find_one({"user_id": user_id})
        if doc and "messages" in doc:
            return doc["messages"]
    except Exception as e:
        logger.error(f"Load transcript error: {e}")
    return []

def clear_messages(user_id: str):
    collection = _collection()
    if collection is None:
        return
    try:
        collection.delete_one({"user_id": user_id})
    except Exception as e:
        logger.error(f"Clear transcript error: {e}")