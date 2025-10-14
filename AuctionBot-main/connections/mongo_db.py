from pymongo import MongoClient
from config import Config

client = MongoClient(Config.MONGO_URI)
db = client['AuctionBot']

# Collections
tournaments_col = db["tournaments"]
players_col = db["players"]
teams_col = db["teams"]
users_col = db["users"]
bids_col = db["bids"]
admins_collection = db["admins"]

# Indexes
tournaments_col.create_index("chat_id", unique=True)
players_col.create_index([("user_id", 1), ("chat_id", 1)], unique=True)
teams_col.create_index([("team_name", 1), ("chat_id", 1)], unique=True)
teams_col.create_index([("owner_id", 1), ("chat_id", 1)], unique=True)


# def add_served_user(user_id, fullname):
#     is_served = is_served_user(user_id)
#     if is_served:
#         return
#     return usersdb.insert_one({"user_id": user_id, "full_name": fullname})


# def is_served_user(user_id: int) -> bool:
#     user = usersdb.find_one({"user_id": user_id})
#     if not user:
#         return False
#     return True

def get_tournament(chat_id: int):
    """Fetch tournament by chat_id, return None if not exists"""
    return tournaments_col.find_one({"chat_id": chat_id})

# --- User & Player Helpers ---

def get_user(user_id: int):
    return users_col.find_one({"user_id": user_id})

def add_user(user_id: int, username: str, full_name: str):
    user = {
        "user_id": user_id,
        "username": username,
        "full_name": full_name,
        "stats": {
            "tournaments_played": 0,
            "total_sold_value": 0,
            "highest_bid": 0
        }
    }
    users_col.insert_one(user)
    return user


def get_player(user_id: int, chat_id: int):
    return players_col.find_one({"user_id": user_id, "chat_id": chat_id})

def add_player(user_id: int, chat_id: int, base_price: int = 0):
    player = {
        "user_id": user_id,
        "chat_id": chat_id,
        "base_price": base_price,
        "status": "unsold",
        "sold_to": None,
        "sold_price": None
    }
    players_col.insert_one(player)
    return player

def remove_player(user_id: int, chat_id: int):
    """Remove player entry from a specific tournament"""
    players_col.delete_one({"user_id": user_id, "chat_id": chat_id})