import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from plugins.utils.admin_checker import co_owner
from connections.mongo_db import players_col, teams_col, get_tournament, get_player, get_user
from plugins.utils.helpers import resolve_user, send_sold_message, resolve_chat_id
from plugins.utils.templates import generate_card
from config import Config

# ===============================
# Auction State
# ===============================
@dataclass
class Auction:
    chat_id: int
    player_id: int
    base_price: int
    current_bid: int
    leading_team: Optional[str] = None
    leading_owner_id: Optional[int] = None
    last_bid_time: float = field(default_factory=time.time)
    active: bool = True
    message_id: Optional[int] = None
    bid_history: list = field(default_factory=list)
    end_time: Optional[float] = None
    timer_task: Optional[asyncio.Task] = None
    team_cooldowns: dict = field(default_factory=dict)
    announcement_message_id: Optional[int] = None


auction_state = {}  # {chat_id: Auction}


# ===============================
# Helper Functions
# ===============================
def get_increment(amount: int) -> int:
    """Calculate next bid increment based on current amount"""
    if amount < 1000:
        return 50
    elif amount < 5000:
        return 100
    else:
        return 250


def format_currency(amount: int) -> str:
    """Format currency with commas for better readability"""
    return f"{amount:,} ₪"


def format_time(seconds: int) -> str:
    """Format time in MM:SS format"""
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def create_bid_keyboard(current_bid: int) -> InlineKeyboardMarkup:
    """Create bidding keyboard with quick bid buttons"""
    quick_bids = [
        current_bid + get_increment(current_bid),
        current_bid + (get_increment(current_bid) * 2),
        current_bid + (get_increment(current_bid) * 5)
    ]
    
    buttons = []
    for bid in quick_bids:
        buttons.append(InlineKeyboardButton(f"💰 {format_currency(bid)}", callback_data=f"quickbid_{bid}"))
    
    return InlineKeyboardMarkup([
        buttons,
        [InlineKeyboardButton("📊 View Team Purses", callback_data="view_purses")],
        [InlineKeyboardButton("🛑 End Auction Now", callback_data="end_auction")]
    ])


# ===============================
# Auction Countdown Coroutine
# ===============================
async def auction_countdown(bot, chat_id: int):
    """Handle auction countdown with visual updates"""
    auction = auction_state.get(chat_id)
    if not auction:
        return

    last_update_time = time.time()
    
    while auction.active:
        try:
            current_time = time.time()
            remaining = int(auction.end_time - current_time)
            
            if remaining <= 0:
                await finalize_auction(bot, chat_id)
                return
            
            # Update announcement message every 10 seconds or when important time thresholds are reached
            if (current_time - last_update_time >= 10 or 
                remaining in [60, 30, 15, 10, 5, 4, 3, 2, 1]):
                
                await update_auction_announcement(bot, chat_id, remaining)
                last_update_time = current_time
                
                # Send warning messages at key intervals
                if remaining == 60:
                    await bot.send_message(chat_id, "⏰ **1 minute remaining!** Place your final bids!")
                elif remaining == 30:
                    await bot.send_message(chat_id, "⚡ **30 seconds left!** Bidding closing soon!")
                elif remaining == 10:
                    await bot.send_message(chat_id, "🔔 **10 seconds!** Final calls!")
                elif 1 <= remaining <= 5:
                    await bot.send_message(chat_id, f"‼️ **{remaining}**")
            
            await asyncio.sleep(1)
            
        except Exception as e:
            print(f"[COUNTDOWN ERROR] {e}")
            await asyncio.sleep(1)


async def update_auction_announcement(bot, chat_id: int, remaining_time: int):
    """Update the auction announcement message with current status"""
    auction = auction_state.get(chat_id)
    if not auction or not auction.announcement_message_id:
        return
    
    try:
        player = await bot.get_users(auction.player_id)
        time_emoji = "🔴" if remaining_time <= 10 else "🟡" if remaining_time <= 30 else "🟢"
        
        message_text = (
            f"🏏 **LIVE AUCTION** 🏏\n\n"
            f"**Player:** {player.mention}\n"
            f"**ID:** `{player.id}`\n\n"
            f"💰 **Current Bid:** {format_currency(auction.current_bid)}\n"
            f"👑 **Leading Team:** {auction.leading_team or 'None'}\n"
            f"⏰ **Time Left:** {time_emoji} {format_time(remaining_time)}\n\n"
            f"**Quick Bids:** `/bid` or use buttons below\n"
            f"💡 *Auto-extends by {Config.WAITTIME}s on new bid*"
        )
        
        keyboard = create_bid_keyboard(auction.current_bid)
        
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=auction.announcement_message_id,
            text=message_text,
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"[UPDATE ANNOUNCEMENT ERROR] {e}")


# ===============================
# Command: /auctionstart
# ===============================
@Client.on_message(filters.command("auctionstart", prefixes=["/", ".", "!"]) & filters.group)
@co_owner
async def auctionstart(bot, message):
    """Start a new auction for a player"""
    chat_id = resolve_chat_id(message.chat.id)
    args = message.text.split()

    # Check if auction already active
    if chat_id in auction_state and auction_state[chat_id].active:
        await message.reply("❌ **An auction is already running!**\nUse `/finalbid` to end it first.")
        return

    user = None
    base_price = None

    # Parse command arguments
    if len(args) >= 3:
        # Case 1: /auctionstart {userid/username} {base_price}
        identifier = args[1]
        user = await resolve_user(bot, identifier)
        if not user:
            await message.reply("❌ **Player not found!**\nPlease check the user ID/username and try again.")
            return
        try:
            base_price = int(args[2])
        except ValueError:
            await message.reply("❌ **Invalid base price!**\nPlease provide a valid number.")
            return

    elif len(args) == 2 and message.reply_to_message:
        # Case 2: Reply to user with /auctionstart {base_price}
        try:
            base_price = int(args[1])
        except ValueError:
            await message.reply("❌ **Invalid base price!**\nPlease provide a valid number.")
            return
        user = message.reply_to_message.from_user

    else:
        # Show help message
        help_text = (
            "🎯 **Auction Start Guide**\n\n"
            "**Method 1:**\n`/auctionstart username base_price`\n"
            "**Method 2:** Reply to a user\n`/auctionstart base_price`\n\n"
            "**Example:** `/auctionstart @username 500`"
        )
        await message.reply(help_text)
        return

    # Validate base price
    if base_price <= 0:
        await message.reply("❌ **Base price must be positive!**")
        return

    # Ensure player is registered
    try:
        players_col.update_one(
            {"user_id": user.id, "chat_id": chat_id},
            {
                "$setOnInsert": {
                    "user_id": user.id,
                    "chat_id": chat_id,
                    "fullname": getattr(user, "first_name", "") or "",
                    "username": getattr(user, "username", None),
                    "status": "unsold",
                    "base_price": 0,
                }
            },
            upsert=True
        )
    except Exception as e:
        print(f"[DB ERROR] {e}")
        await message.reply("❌ **Database error!** Could not register player.")
        return

    player = get_player(user.id, chat_id)
    if not player:
        await message.reply("❌ **Player not registered!**")
        return

    if player.get("status") != "unsold":
        status = player.get("status", "unknown")
        await message.reply(f"❌ **Player already {status}!**")
        return

    # Update base price in database
    try:
        players_col.update_one(
            {"user_id": user.id, "chat_id": chat_id},
            {"$set": {"base_price": base_price}}
        )
    except Exception as e:
        print(f"[DB UPDATE ERROR] {e}")
        await message.reply("❌ **Failed to update base price!**")
        return

    # Create auction
    auction = Auction(
        chat_id=chat_id,
        player_id=user.id,
        base_price=base_price,
        current_bid=base_price
    )
    auction.end_time = time.time() + Config.WAITTIME
    auction_state[chat_id] = auction

    # Create announcement message
    announcement_text = (
        f"🏏 **LIVE AUCTION STARTED** 🏏\n\n"
        f"**Player:** {user.mention}\n"
        f"**ID:** `{user.id}`\n\n"
        f"💰 **Base Price:** {format_currency(base_price)}\n"
        f"👑 **Leading Team:** None\n"
        f"⏰ **Time Left:** 🟢 {format_time(Config.WAITTIME)}\n\n"
        f"**Quick Bids:** `/bid` or use buttons below\n"
        f"💡 *Auto-extends by {Config.WAITTIME}s on new bid*"
    )

    keyboard = create_bid_keyboard(base_price)
    announcement_msg = await message.reply(announcement_text, reply_markup=keyboard)
    
    auction.announcement_message_id = announcement_msg.id
    auction.message_id = announcement_msg.id
    auction.timer_task = asyncio.create_task(auction_countdown(bot, chat_id))

    # Send confirmation
    await message.reply("✅ **Auction started successfully!**")


# ===============================
# Command: /next
# ===============================
@Client.on_message(filters.command("next", prefixes=["/", ".", "!"]) & filters.group)
@co_owner
async def next_auction(bot, message):
    """Start auction for the next unsold player"""
    chat_id = resolve_chat_id(message.chat.id)

    if chat_id in auction_state and auction_state[chat_id].active:
        await message.reply("❌ **An auction is already running!**\nUse `/finalbid` to end it first.")
        return

    # Find next unsold player
    next_player = players_col.find_one(
        {"chat_id": chat_id, "status": "unsold"},
        sort=[("base_price", -1)]  # Start with highest base price first
    )
    
    if not next_player:
        await message.reply("🎉 **All players have been sold!**\nTournament auction completed! 🏆")
        return

    user = await resolve_user(bot, next_player["user_id"])
    if not user:
        await message.reply("❌ **Could not find player details!**")
        return

    base_price = next_player.get("base_price", 100)

    # Create auction
    auction = Auction(
        chat_id=chat_id,
        player_id=user.id,
        base_price=base_price,
        current_bid=base_price
    )
    auction.end_time = time.time() + Config.WAITTIME
    auction_state[chat_id] = auction

    # Create announcement
    announcement_text = (
        f"🏏 **NEXT PLAYER AUCTION** 🏏\n\n"
        f"**Player:** {user.mention}\n"
        f"**ID:** `{user.id}`\n\n"
        f"💰 **Base Price:** {format_currency(base_price)}\n"
        f"👑 **Leading Team:** None\n"
        f"⏰ **Time Left:** 🟢 {format_time(Config.WAITTIME)}\n\n"
        f"**Quick Bids:** `/bid` or use buttons below\n"
        f"💡 *Auto-extends by {Config.WAITTIME}s on new bid*"
    )

    keyboard = create_bid_keyboard(base_price)
    announcement_msg = await message.reply(announcement_text, reply_markup=keyboard)
    
    auction.announcement_message_id = announcement_msg.id
    auction.message_id = announcement_msg.id
    auction.timer_task = asyncio.create_task(auction_countdown(bot, chat_id))

    await message.reply("✅ **Next auction started!**")


# ===============================
# Command: /bid
# ===============================
@Client.on_message(filters.command("bid") & filters.group)
async def place_bid(bot, message):
    """Place a bid in the ongoing auction"""
    chat_id = resolve_chat_id(message.chat.id)
    user = message.from_user
    auction = auction_state.get(chat_id)

    if not auction or not auction.active:
        await message.reply("❌ **No active auction!**\nWait for an auction to start.")
        return

    # Find bidder's team
    team = teams_col.find_one({"chat_id": chat_id, "bidder_list": user.id})
    if not team:
        await message.reply("❌ **You are not a registered bidder!**\nContact tournament admin.")
        return

    team_name = team["team_name"]
    team_purse = team.get("purse", 0)

    # Check team capacity
    players_count = len(team.get("sold_players", []))
    if players_count >= 11:  # Maximum 11 players per team
        await message.reply(f"❌ **{team_name} has reached maximum capacity!** (11/11 players)")
        return

    # Prevent same team consecutive bids
    if auction.leading_team == team_name:
        await message.reply("⚠️ **Your team is already leading!**\nWait for another team to bid.")
        return

    # Parse bid amount
    args = message.text.split()
    direct_bid = None
    
    if len(args) == 2:
        try:
            direct_bid = int(args[1])
            if direct_bid <= 0:
                await message.reply("❌ **Bid must be positive!**")
                return
        except ValueError:
            await message.reply("❌ **Invalid bid amount!** Use a number.")
            return

    # Calculate minimum next bid
    next_min = auction.current_bid + get_increment(auction.current_bid)

    # Determine bid amount and cooldown
    if direct_bid is not None:
        if direct_bid <= auction.current_bid:
            await message.reply(f"⚠️ **Bid too low!** Minimum bid is {format_currency(next_min)}")
            return
        if direct_bid % 100 != 0:
            await message.reply("⚠️ **Direct bids must be in multiples of 100!**")
            return
        cooldown = 15
        bid_amount = direct_bid
    else:
        bid_amount = next_min
        cooldown = 8

    # Check team cooldown
    last_bid_time = auction.team_cooldowns.get(team_name, 0)
    elapsed = time.time() - last_bid_time
    if elapsed < cooldown:
        wait_left = int(cooldown - elapsed)
        await message.reply(f"⏳ **Team cooldown!** Wait {wait_left}s before bidding again.")
        return

    # Check purse
    if bid_amount > team_purse:
        await message.reply(f"❌ **Insufficient purse!**\nYour purse: {format_currency(team_purse)}\nRequired: {format_currency(bid_amount)}")
        return

    # Accept the bid
    auction.current_bid = bid_amount
    auction.leading_team = team_name
    auction.leading_owner_id = user.id
    auction.last_bid_time = time.time()
    auction.bid_history.append({
        "user_id": user.id,
        "team_name": team_name,
        "bid": bid_amount,
        "ts": auction.last_bid_time
    })
    auction.team_cooldowns[team_name] = time.time()
    auction.end_time = time.time() + Config.WAITTIME

    # Restart countdown if needed
    if not auction.timer_task or auction.timer_task.done():
        auction.timer_task = asyncio.create_task(auction_countdown(bot, chat_id))

    # Update announcement
    await update_auction_announcement(bot, chat_id, Config.WAITTIME)

    # Send bid confirmation
    confirmation_msg = (
        f"✅ **BID ACCEPTED!**\n\n"
        f"💰 **Amount:** {format_currency(bid_amount)}\n"
        f"🏏 **Team:** {team_name}\n"
        f"👤 **Bidder:** {user.mention}\n"
        f"⏰ **Time Extended:** +{Config.WAITTIME}s"
    )
    
    await message.reply(confirmation_msg)


# ===============================
# Callback Query Handler
# ===============================
@Client.on_callback_query()
async def handle_callbacks(bot, callback_query):
    """Handle inline keyboard callbacks"""
    chat_id = callback_query.message.chat.id
    user = callback_query.from_user
    data = callback_query.data
    
    auction = auction_state.get(chat_id)
    
    if data == "view_purses":
        # Show all team purses
        teams = list(teams_col.find({"chat_id": chat_id}))
        purse_info = "💰 **Team Purses:**\n\n"
        
        for team in teams:
            team_name = team["team_name"]
            purse = team.get("purse", 0)
            players_count = len(team.get("sold_players", []))
            purse_info += f"🏏 **{team_name}:** {format_currency(purse)} | {players_count}/11 players\n"
        
        await callback_query.answer()
        await callback_query.message.reply(purse_info)
        return
    
    elif data == "end_auction":
        # Check if user is co-owner
        if not await co_owner(bot, callback_query.message):
            await callback_query.answer("❌ Admin access required!", show_alert=True)
            return
        
        await callback_query.answer("Ending auction...")
        await finalize_auction(bot, chat_id)
        return
    
    elif data.startswith("quickbid_"):
        if not auction or not auction.active:
            await callback_query.answer("❌ No active auction!", show_alert=True)
            return
        
        try:
            bid_amount = int(data.split("_")[1])
        except ValueError:
            await callback_query.answer("❌ Invalid bid!", show_alert=True)
            return
        
        # Simulate a bid using the quick bid amount
        team = teams_col.find_one({"chat_id": chat_id, "bidder_list": user.id})
        if not team:
            await callback_query.answer("❌ You're not a bidder!", show_alert=True)
            return
        
        # Process the quick bid
        if bid_amount <= auction.current_bid:
            await callback_query.answer(f"❌ Bid too low! Current: {format_currency(auction.current_bid)}", show_alert=True)
            return
        
        if bid_amount > team.get("purse", 0):
            await callback_query.answer("❌ Insufficient purse!", show_alert=True)
            return
        
        # Accept the quick bid
        team_name = team["team_name"]
        auction.current_bid = bid_amount
        auction.leading_team = team_name
        auction.leading_owner_id = user.id
        auction.last_bid_time = time.time()
        auction.bid_history.append({
            "user_id": user.id,
            "team_name": team_name,
            "bid": bid_amount,
            "ts": auction.last_bid_time
        })
        auction.team_cooldowns[team_name] = time.time()
        auction.end_time = time.time() + Config.WAITTIME
        
        await callback_query.answer(f"✅ Bid placed: {format_currency(bid_amount)}")
        await update_auction_announcement(bot, chat_id, Config.WAITTIME)
        
        # Send confirmation
        await bot.send_message(
            chat_id,
            f"💰 **Quick Bid Accepted!**\n"
            f"**Team:** {team_name}\n"
            f"**Amount:** {format_currency(bid_amount)}\n"
            f"**Bidder:** {user.mention}"
        )


# ===============================
# Command: /finalbid
# ===============================
@Client.on_message(filters.command("finalbid") & filters.group)
@co_owner
async def finalbid(bot, message):
    """Admin command to finalize auction immediately"""
    chat_id = resolve_chat_id(message.chat.id)
    
    if chat_id not in auction_state or not auction_state[chat_id].active:
        await message.reply("❌ **No active auction to finalize!**")
        return
    
    await message.reply("🛑 **Finalizing auction...**")
    await finalize_auction(bot, chat_id)


# ===============================
# Finalize Auction
# ===============================
async def finalize_auction(bot, chat_id: int):
    """Finalize the ongoing auction and process results"""
    auction = auction_state.get(chat_id)
    if not auction or not auction.active:
        return

    auction.active = False
    
    try:
        player = get_player(auction.player_id, chat_id)
        if not player:
            await bot.send_message(chat_id, "❌ **Player not found in database!**")
            return

        pusr = await bot.get_users(int(auction.player_id))
        pname = pusr.first_name

        if not auction.leading_team:
            # No bids received
            players_col.update_one(
                {"user_id": auction.player_id, "chat_id": chat_id},
                {"$set": {"status": "unsold"}}
            )
            
            unsold_msg = (
                f"📭 **AUCTION ENDED - UNSOLD**\n\n"
                f"**Player:** {pusr.mention}\n"
                f"**Base Price:** {format_currency(auction.base_price)}\n\n"
                f"❌ *No bids were placed*"
            )
            await bot.send_message(chat_id, unsold_msg)
            return

        # Process successful sale
        teams_col.update_one(
            {"chat_id": chat_id, "team_name": auction.leading_team},
            {
                "$inc": {"purse": -auction.current_bid},
                "$push": {
                    "sold_players": {
                        "player_id": auction.player_id,
                        "player_name": pname,
                        "sold_price": auction.current_bid,
                        "sold_at": datetime.now()
                    }
                }
            }
        )

        players_col.update_one(
            {"user_id": auction.player_id, "chat_id": chat_id},
            {
                "$set": {
                    "status": "sold",
                    "sold_to": auction.leading_team,
                    "sold_price": auction.current_bid,
                    "sold_at": datetime.now()
                }
            }
        )

        # Get updated team info
        team = teams_col.find_one({"chat_id": chat_id, "team_name": auction.leading_team})
        remaining_purse = team.get("purse", 0) if team else 0
        
        # Send sold message with enhanced UI
        sold_msg = (
            f"🏆 **SOLD!** 🏆\n\n"
            f"**Player:** {pusr.mention}\n"
            f"**Team:** {auction.leading_team}\n"
            f"**Price:** {format_currency(auction.current_bid)}\n"
            f"**Remaining Purse:** {format_currency(remaining_purse)}\n"
            f"**Players Bought:** {len(team.get('sold_players', []))}/11\n\n"
            f"🎉 *Congratulations to {auction.leading_team}!*"
        )
        
        await bot.send_message(chat_id, sold_msg)
        
        # Update announcement message to show final result
        try:
            if auction.announcement_message_id:
                final_announcement = (
                    f"🏁 **AUCTION COMPLETED** 🏁\n\n"
                    f"**Player:** {pusr.mention}\n"
                    f"**Sold To:** {auction.leading_team}\n"
                    f"**Final Price:** {format_currency(auction.current_bid)}\n\n"
                    f"✅ *Successfully sold!*"
                )
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=auction.announcement_message_id,
                    text=final_announcement,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Auction Completed", callback_data="completed")]])
                )
        except Exception as e:
            print(f"[FINAL ANNOUNCEMENT ERROR] {e}")

    except Exception as e:
        print(f"[FINALIZE AUCTION ERROR] {e}")
        await bot.send_message(chat_id, "❌ **Error finalizing auction!** Contact admin.")
    
    finally:
        # Clean up auction state
        if chat_id in auction_state:
            del auction_state[chat_id]


# ===============================
# Command: /auctioninfo
# ===============================
@Client.on_message(filters.command("auctioninfo") & filters.group)
async def auction_info(bot, message):
    """Show current auction information"""
    chat_id = resolve_chat_id(message.chat.id)
    auction = auction_state.get(chat_id)
    
    if not auction or not auction.active:
        await message.reply("ℹ️ **No active auction currently.**")
        return
    
    player = await bot.get_users(auction.player_id)
    remaining_time = int(auction.end_time - time.time())
    
    info_text = (
        f"📊 **Live Auction Info**\n\n"
        f"**Player:** {player.mention}\n"
        f"**Current Bid:** {format_currency(auction.current_bid)}\n"
        f"**Leading Team:** {auction.leading_team or 'None'}\n"
        f"**Time Left:** {format_time(remaining_time)}\n"
        f"**Total Bids:** {len(auction.bid_history)}\n"
        f"**Base Price:** {format_currency(auction.base_price)}\n\n"
        f"💡 Use `/bid` to place your bid!"
    )
    
    await message.reply(info_text)