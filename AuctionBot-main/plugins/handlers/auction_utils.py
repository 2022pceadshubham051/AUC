from pyrogram import Client, filters
from plugins.utils.admin_checker import co_owner, group_admin
from connections.mongo_db import players_col, get_tournament, get_user, get_player, add_user, teams_col
from plugins.utils.helpers import resolve_user, resolve_chat_id
from config import Config
from plugins.handlers.auction import auction_state
import time

def split_message(text, limit=4000):
    if len(text) > limit:
        for i in range(0, len(text), limit):
            yield text[i:i+limit]
    else:
        yield text

@Client.on_message(filters.command("list") & filters.group)
@co_owner
async def list_players(bot, message):
    chat_id = resolve_chat_id(message.chat.id)
    tournament = get_tournament(chat_id)

    if not tournament:
        return await message.reply("⚠️ No active tournament here.")

    players = list(players_col.find({"chat_id": chat_id}))
    if not players:
        return await message.reply("⚠️ No players have registered yet.")

    text = f"**📋 Players in {tournament['title']}**\n\n"
    for idx, p in enumerate(players, start=1):
        user_info = get_user(p["user_id"])
        name = user_info["full_name"] if user_info and user_info.get("full_name") else "Unknown"
        status = p.get("status", "unsold").capitalize()

        if status.lower() == "sold":
            sold_price = p.get("sold_price", "N/A")
            sold_to = p.get("sold_to", "N/A")
            text += f"**{idx}. {name}** (`{p['user_id']}`) — Status: {status} (Sold for {sold_price} ₪ to {sold_to})\n"
        else:
            base_price = p.get("base_price", "N/A")
            text += f"**{idx}. {name}** (`{p['user_id']}`) — Base: {base_price} ₪ — Status: {status}\n"

    for chunk in split_message(text):
        await message.reply(chunk)


@Client.on_message(filters.command("unsold") & filters.group)
@co_owner
async def unsold_players(bot, message):
    chat_id = resolve_chat_id(message.chat.id)
    tournament = get_tournament(chat_id)

    if not tournament:
        return await message.reply("⚠️ No active tournament here.")

    players = list(players_col.find({"chat_id": chat_id, "status": "unsold"}))
    if not players:
        return await message.reply("🎉 All players have been sold!")

    text = f"**❌ Unsold Players in {tournament['title']}**\n\n"
    for idx, p in enumerate(players, start=1):
        user_info = get_user(p["user_id"])
        name = user_info["full_name"] if user_info and user_info.get("full_name") else "Unknown"
        base_price = p.get('base_price', 'N/A')
        text += f"**{idx}. {name}** (`{p['user_id']}`) — Base Price: {base_price} ₪\n"

    for chunk in split_message(text):
        await message.reply(chunk)


@Client.on_message(filters.command("add_player") & filters.group)
@co_owner
async def add_player_cmd(bot, message):
    chat_id = resolve_chat_id(message.chat.id)
    if not get_tournament(chat_id):
        return await message.reply("⚠️ No active tournament here.")

    if message.reply_to_message:
        if len(message.command) < 2:
            return await message.reply("⚠️ Usage: Reply to a user with `/add_player {base_price}`")
        try:
            base_price = int(message.command[1])
        except ValueError:
            return await message.reply("❌ Invalid base price.")
        user = message.reply_to_message.from_user
    else:
        if len(message.command) < 3:
            return await message.reply("⚠️ Usage: `/add_player {user_id/username} {base_price}`")
        identifier = message.command[1]
        try:
            base_price = int(message.command[2])
        except ValueError:
            return await message.reply("❌ Invalid base price.")
        user = await resolve_user(bot, identifier)
        if not user:
            return await message.reply("❌ Could not find the specified user.")

    if get_player(user.id, chat_id):
        return await message.reply("⚠️ This player is already registered.")

    if not get_user(user.id):
        add_user(user.id, user.username, user.first_name)

    players_col.insert_one({
        "user_id": user.id, "chat_id": chat_id, "base_price": base_price,
        "status": "unsold", "sold_to": None, "sold_price": None
    })

    await message.reply(f"✅ Player {user.first_name} added with a base price of {base_price} ₪.")


@Client.on_message(filters.command("remove_player") & filters.group)
@co_owner
async def remove_player_cmd(bot, message):
    chat_id = resolve_chat_id(message.chat.id)
    if not get_tournament(chat_id):
        return await message.reply("⚠️ No active tournament here.")

    if message.reply_to_message:
        user = message.reply_to_message.from_user
    else:
        if len(message.command) < 2:
            return await message.reply("⚠️ Usage: `/remove_player {user_id/username}` or reply to a user.")
        user = await resolve_user(bot, message.command[1])
        if not user:
            return await message.reply("❌ Could not find the specified user.")

    if not get_player(user.id, chat_id):
        return await message.reply("⚠️ This player is not in this tournament.")

    players_col.delete_one({"user_id": user.id, "chat_id": chat_id})
    await message.reply(f"🗑 Player {user.first_name} has been removed.")


@Client.on_message(filters.command("reset") & filters.group)
@co_owner
async def reset_player_cmd(bot, message):
    chat_id = resolve_chat_id(message.chat.id)
    args = message.text.split()

    if message.reply_to_message:
        user = message.reply_to_message.from_user
    elif len(args) >= 2:
        user = await resolve_user(bot, args[1])
    else:
        return await message.reply("⚠️ Usage: `/reset {user_id/username}` or reply to a user.")

    if not user:
        return await message.reply("❌ Could not find the specified user.")

    player = get_player(user.id, chat_id)
    if not player or player.get("status") != "sold":
        return await message.reply("⚠️ This player has not been sold yet.")

    team_name = player.get("sold_to")
    sold_price = player.get("sold_price", 0)

    teams_col.update_one(
        {"chat_id": chat_id, "team_name": team_name},
        {"$inc": {"purse": sold_price}, "$pull": {"sold_players": {"player_id": user.id}}}
    )
    players_col.update_one(
        {"user_id": user.id, "chat_id": chat_id},
        {"$set": {"status": "unsold", "sold_to": None, "sold_price": None}}
    )
    await message.reply(f"🔄 Player {user.first_name} has been reset to unsold. {sold_price} ₪ refunded to {team_name}.")


@Client.on_message(filters.command("add_team") & filters.group)
@co_owner
async def add_team(bot, message):
    chat_id = resolve_chat_id(message.chat.id)
    tournament = get_tournament(chat_id)
    if not tournament:
        return await message.reply("⚠️ No active tournament here.")

    if message.reply_to_message:
        user = message.reply_to_message.from_user
        if len(message.command) < 2:
            return await message.reply("⚠️ Usage: Reply to a user with `/add_team {team_name}`")
        team_name = " ".join(message.command[1:])
    else:
        if len(message.command) < 3:
            return await message.reply("⚠️ Usage: `/add_team {user_id/username} {team_name}`")
        user = await resolve_user(bot, message.command[1])
        if not user:
            return await message.reply("❌ Could not find the specified user.")
        team_name = " ".join(message.command[2:])

    if teams_col.find_one({"chat_id": chat_id, "$or": [{"team_name": team_name}, {"owner_id": user.id}]}):
        return await message.reply("⚠️ A team with this name or owner already exists.")

    teams_col.insert_one({
        "chat_id": chat_id, "team_name": team_name, "owner_id": user.id,
        "bidder_list": [user.id], "purse": tournament["purse"], "sold_players": []
    })
    await message.reply(f"✅ Team **{team_name}** registered for {user.mention} with {tournament['purse']} ₪.")


@Client.on_message(filters.command("team") & filters.group)
async def fetch_team_players(bot, message):
    if len(message.command) < 2:
        return await message.reply("⚠️ Usage: `/team <team_name>`")

    team_name = " ".join(message.command[1:])
    team_data = teams_col.find_one({"chat_id": resolve_chat_id(message.chat.id), "team_name": {"$regex": f"^{team_name}$", "$options": "i"}})

    if not team_data:
        return await message.reply(f"⚠️ Team '{team_name}' not found.")

    bidders_text = ""
    for uid in team_data.get("bidder_list", []):
        try:
            user = await bot.get_users(uid)
            bidders_text += f"- {user.mention}\n"
        except:
            bidders_text += f"- `{uid}`\n"

    sold_players = team_data.get("sold_players", [])
    total_cost = sum(p.get("sold_price", 0) for p in sold_players)

    response = (
        f"**📜 Team Details: {team_data['team_name']}**\n\n"
        f"**👑 Owner ID:** `{team_data['owner_id']}`\n"
        f"**💼 Bidders:**\n{bidders_text or 'None'}\n"
        f"**🛒 Players Bought:** {len(sold_players)}\n"
        f"**💰 Total Cost:** {total_cost:,} ₪\n"
        f"**💵 Shards Left:** {team_data.get('purse', 0):,} ₪\n\n"
    )

    if sold_players:
        response += "**📌 Sold Players:**\n"
        for idx, player in enumerate(sold_players, start=1):
            response += f"**{idx}. {player['player_name']}** (`{player['player_id']}`) - {player.get('sold_price', 0):,} ₪\n"
    else:
        response += "No players bought yet."

    await message.reply(response)


@Client.on_message(filters.command("add_bidder") & filters.group)
@co_owner
async def add_bidder(bot, message):
    chat_id = resolve_chat_id(message.chat.id)
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        team_name = " ".join(message.command[1:])
    elif len(message.command) > 2:
        target_user = await resolve_user(bot, message.command[1])
        team_name = " ".join(message.command[2:])
    else:
        return await message.reply("⚠️ Usage: `/add_bidder {user_id/username} {team_name}` or reply to a user.")

    if not team_name or not target_user:
        return await message.reply("⚠️ Invalid input.")

    team = teams_col.find_one({"chat_id": chat_id, "team_name": {"$regex": f"^{team_name}$", "$options": "i"}})
    if not team:
        return await message.reply(f"⚠️ Team '{team_name}' not found.")

    if target_user.id in team.get("bidder_list", []):
        return await message.reply(f"⚠️ {target_user.mention} is already a bidder for **{team['team_name']}**.")

    teams_col.update_one({"_id": team["_id"]}, {"$push": {"bidder_list": target_user.id}})
    await message.reply(f"✅ {target_user.mention} is now a bidder for **{team['team_name']}**.")


@Client.on_message(filters.command("rm_bidder") & filters.group)
@co_owner
async def remove_bidder(bot, message):
    chat_id = resolve_chat_id(message.chat.id)
    args = message.text.split(maxsplit=2)

    if message.reply_to_message and len(args) >= 2:
        target_user = message.reply_to_message.from_user
        team_name = args[1]
    elif len(args) >= 3:
        target_user = await resolve_user(bot, args[1])
        team_name = args[2]
    else:
        return await message.reply("⚠️ Usage: `/rm_bidder {user_id/username} {team_name}` or reply to a user.")

    if not target_user:
        return await message.reply("❌ Could not find the specified user.")

    team = teams_col.find_one({"chat_id": chat_id, "team_name": {"$regex": f"^{team_name}$", "$options": "i"}})
    if not team:
        return await message.reply(f"⚠️ Team '{team_name}' not found.")

    if target_user.id not in team.get("bidder_list", []):
        return await message.reply(f"⚠️ {target_user.mention} is not a bidder for **{team_name}**.")

    teams_col.update_one(
        {"chat_id": chat_id, "team_name": team['team_name']},
        {"$pull": {"bidder_list": target_user.id}}
    )
    await message.reply(f"🗑 {target_user.mention} is no longer a bidder for **{team_name}**.")


@Client.on_message(filters.command("info") & filters.group)
@group_admin
async def get_player_info(bot, message):
    args = message.text.split()
    chat_id = resolve_chat_id(message.chat.id)

    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
    elif len(args) == 2:
        target_user = await resolve_user(bot, args[1])
        if not target_user:
            return await message.reply("❌ Unable to fetch user details.")
    else:
        return await message.reply("⚠️ Usage: Reply to a user with `/info` or use `/info {userid/username}`")

    player = players_col.find_one({"user_id": target_user.id, "chat_id": chat_id})
    if not player:
        return await message.reply("⚠️ This player is not found in the tournament database.")

    status = player.get("status", "unsold").capitalize()
    sold_price = player.get("sold_price", "N/A")
    team_name = player.get("sold_to") or "N/A"
    base_price = player.get("base_price", "N/A")

    await message.reply(
        f"**📊 Player Information**\n\n"
        f"**👤 Name:** {target_user.mention}\n"
        f"**🆔 User ID:** `{target_user.id}`\n"
        f"**💵 Base Price:** {base_price} ₪\n"
        f"**📈 Status:** {status}\n"
        f"**💰 Sold Price:** {sold_price} ₪\n"
        f"**🏏 Team:** {team_name}\n"
    )


@Client.on_message(filters.command("purse") & filters.group)
@co_owner
async def show_team_purses(bot, message):
    chat_id = resolve_chat_id(message.chat.id)
    tournament = get_tournament(chat_id)
    if not tournament:
        return await message.reply("⚠️ No active tournament here.")

    teams = list(teams_col.find({"chat_id": chat_id}))
    if not teams:
        return await message.reply("⚠️ No teams are registered in this tournament.")

    text = f"**💼 Team Purses in {tournament['title']}**\n\n"
    for idx, team in enumerate(teams, start=1):
        text += (
            f"**{idx}. {team['team_name']}**\n"
            f"   **💰 Shards Left:** {team.get('purse', 0):,} ₪\n"
            f"   **👥 Players Bought:** {len(team.get('sold_players', []))}\n\n"
        )
    for chunk in split_message(text):
        await message.reply(chunk)

@Client.on_message(filters.command("status") & filters.group)
async def auction_status(bot, message):
    chat_id = resolve_chat_id(message.chat.id)
    auction = auction_state.get(chat_id)

    if not auction or not auction.active:
        return await message.reply("ℹ️ No auction is currently active.")

    user = await resolve_user(bot, auction.player_id)
    status_msg = (
        f"**🕒 AUCTION STATUS**\n\n"
        f"**👤 Player:** {user.mention}\n"
        f"**💰 Current Bid:** {auction.current_bid} ₪\n"
        f"**🏏 Leading Team:** {auction.leading_team or 'None'}\n"
        f"**⏳ Time Left:** {int(auction.end_time - time.time())}s"
    )
    await message.reply(status_msg)

@Client.on_message(filters.command("myteam") & filters.group)
async def my_team(bot, message):
    chat_id = resolve_chat_id(message.chat.id)
    team = teams_col.find_one({"chat_id": chat_id, "bidder_list": message.from_user.id})

    if not team:
        return await message.reply("⚠️ You are not part of any team in this tournament.")

    sold_players = team.get("sold_players", [])
    total_spent = sum(p['sold_price'] for p in sold_players)
    
    response = (
        f"**🛡️ My Team: {team['team_name']}**\n\n"
        f"**💰 Total Spent:** {total_spent:,} ₪\n"
        f"**💵 Purse Left:** {team.get('purse', 0):,} ₪\n\n"
    )

    if sold_players:
        response += "**🛒 Purchased Players:**\n"
        for p in sold_players:
            response += f"- **{p['player_name']}**: {p['sold_price']:,} ₪\n"
    else:
        response += "You haven't purchased any players yet."

    await message.reply(response)

@Client.on_message(filters.command("team_stats") & filters.group)
@co_owner
async def team_stats(bot, message):
    chat_id = resolve_chat_id(message.chat.id)
    teams = list(teams_col.find({"chat_id": chat_id}))
    if not teams:
        return await message.reply("⚠️ No teams have been registered yet.")

    stats_msg = "**📊 Team Statistics**\n\n"
    for team in teams:
        sold_players = team.get("sold_players", [])
        total_spent = sum(p['sold_price'] for p in sold_players)
        stats_msg += (
            f"**🛡️ {team['team_name']}**\n"
            f"- **Players Bought:** {len(sold_players)}\n"
            f"- **Total Spent:** {total_spent:,} ₪\n"
            f"- **Balance:** {team.get('purse', 0):,} ₪\n\n"
        )
    await message.reply(stats_msg)

@Client.on_message(filters.command("auction_stats") & filters.group)
@co_owner
async def auction_stats(bot, message):
    chat_id = resolve_chat_id(message.chat.id)
    sold_players = list(players_col.find({"chat_id": chat_id, "status": "sold"}))

    if not sold_players:
        return await message.reply("ℹ️ No players have been sold yet.")

    stats_msg = "**📈 Auction Statistics (All Sold Players)**\n\n"
    for player in sold_players:
        user = await resolve_user(bot, player['user_id'])
        stats_msg += (
            f"**👤 {user.first_name}** sold to **{player['sold_to']}** for **{player['sold_price']:,} ₪**\n"
        )
    await message.reply(stats_msg)

@Client.on_message(filters.command("history") & filters.group)
async def bid_history(bot, message):
    chat_id = resolve_chat_id(message.chat.id)
    auction = auction_state.get(chat_id)

    if not auction or not auction.bid_history:
        return await message.reply("ℹ️ No bid history available for the current auction.")

    history_msg = "**📜 Bid History (Last 10 Bids)**\n\n"
    for bid in reversed(auction.bid_history[-10:]):
        user = await resolve_user(bot, bid['user_id'])
        history_msg += f"- **{bid['bid']:,} ₪** by {user.mention} for **{bid['team_name']}**\n"

    await message.reply(history_msg)

@Client.on_message(filters.command("top_bidders") & filters.group)
@co_owner
async def top_bidders(bot, message):
    chat_id = resolve_chat_id(message.chat.id)
    teams = list(teams_col.find({"chat_id": chat_id}))
    if not teams:
        return await message.reply("⚠️ No teams available to rank.")

    team_spending = []
    for team in teams:
        total_spent = sum(p['sold_price'] for p in team.get("sold_players", []))
        team_spending.append((team['team_name'], total_spent))

    top_10 = sorted(team_spending, key=lambda x: x[1], reverse=True)[:10]

    top_bidders_msg = "**🏆 Top 10 Bidders**\n\n"
    for i, (team, spent) in enumerate(top_10, 1):
        top_bidders_msg += f"**{i}. {team}** - {spent:,} ₪\n"

    await message.reply(top_bidders_msg)