from pyrogram import Client, filters
from pyrogram.types import Message, ChatJoinRequest
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from plugins.utils.admin_checker import is_user_admin_cq
from pyrogram.enums import ParseMode
import asyncio
from plugins.utils.templates import generate_card
from connections.logger import group_logger

START_KEYBOARD_BUTTON = [
    [
        InlineKeyboardButton('GROUP', url='https://t.me/CLG_fun_zone'),
    ],
    [
        InlineKeyboardButton('HELP', callback_data="DEVS")
    ]
]

BACK = [
    [
        InlineKeyboardButton('BACK', callback_data="START")
    ]
]


CLOSE = [
    [
        InlineKeyboardButton('CLOSE', callback_data='CLOSE')
    ]
]

ACLOSE = [
    [
        InlineKeyboardButton(' ᴄʟᴏsᴇ ', callback_data='ACLOSE')
    ]
]


start_replymarkup = InlineKeyboardMarkup(START_KEYBOARD_BUTTON)
back_replymarkup = InlineKeyboardMarkup(BACK)
close_replymarkup = InlineKeyboardMarkup(CLOSE)
aclose_replymarkup = InlineKeyboardMarkup(ACLOSE)

START_MESSAGE = '''

⚡ **Welcome to the Auction Bot of 𝐅ᴜɴ•𝐙ᴏɴᴇ™!** ⚡

Get ready for an exciting bidding experience.

🌲 **Create the auctions** for fellow members.
❄️ **Manage bids** and reward winners.
🏆 Climb the **leaderboard of top bidders**.

🔥 **Bot Owner:** SHUBH ☄ (@ASTRO_SHUBH)

-------------------------------------------
'''

creator_names = '''

📖 **Auction Bot Help Menu**

**🏆 Tournament Commands**
/start_tour - Start a new tournament in your group.
/stop_tour - Stop the current tournament.
/clear - Clear all players and teams from the tournament.

**👥 Team Commands**
/add_team {user} {team_name} - Register a new team.
/team {team_name} - Get details of a specific team.

**👤 Player Commands**
/register - Join a tournament.
/deregister - Leave a tournament.
/add_player {user} {base_price} - Manually add a player.
/remove_player {user} - Remove a player from the tournament.
/reset {user} - Reset a sold player to unsold status.

**⚡ Auction Commands**
/auctionstart {player} {base_price} - Start an auction for a player.
/bid [amount] - Place a bid.
/finalbid - Forcefully finalize the current auction (admin only).
/next - Bring up the next unsold player for auction (coming soon).

**ℹ️ Info Commands**
/list - List all registered players.
/unsold - List all unsold players.
/info {user} - Get information about a specific player.
/purse - Show the remaining Shards for all teams.

'''



@Client.on_message(filters.media & filters.private & filters.user(5930803951))
async def media_id_handler(client, message):
        media = getattr(message, message.media.value)
        await message.reply_text(
            f"<code> {media.file_id} </code>", parse_mode=ParseMode.HTML, quote=True
        )

@Client.on_callback_query(filters.regex(pattern="^(DEVS|START|CLOSE)$"))
async def call_back_func(bot, CallbackQuery):

    if CallbackQuery.data == "DEVS":
        await CallbackQuery.edit_message_caption(
            caption = creator_names,
            reply_markup = back_replymarkup
        )

    if CallbackQuery.data == "START":
        await CallbackQuery.edit_message_caption(
            caption = START_MESSAGE,
            reply_markup = start_replymarkup
        )

    if CallbackQuery.data == "CLOSE":
        try:
            await CallbackQuery.answer()
            await CallbackQuery.message.delete()
            umm = await CallbackQuery.message.reply_text(
            f"Cʟᴏsᴇᴅ ʙʏ : {CallbackQuery.from_user.mention}"
            )
            await asyncio.sleep(7)
            await umm.delete()
        except:
            pass

@Client.on_callback_query(filters.regex(pattern="^ACLOSE$"))
@is_user_admin_cq
async def admincall_back_func(bot, CallbackQuery):
    try:
        await CallbackQuery.answer()
        await CallbackQuery.message.delete()
        umm = await CallbackQuery.message.reply_text(
        f"Cʟᴏsᴇᴅ ʙʏ : {CallbackQuery.from_user.mention}"
            )
        await asyncio.sleep(7)
        await umm.delete()
    except:
        pass

async def resolve_user(bot, identifier: str):
    """
    Resolve user by ID or username.
    Returns a pyrogram User object or None.
    """
    try:
        return await bot.get_users(identifier)
    except Exception:
        return None

def resolve_chat_id(incoming_chat_id: int) -> int:
    """
    If incoming_chat_id is one of the alias groups, return the canonical chat id.
    Otherwise return incoming_chat_id unchanged.
    """
    # You can add your group IDs here if you have multiple groups for the same tournament
    if incoming_chat_id in [-1003067082800]:
        return -1003067082800
    return incoming_chat_id

async def send_sold_message(bot, chat_id: int, auction):
        user = await resolve_user(bot, auction.player_id)
        try:
            pfp_path = await bot.download_media(user.photo.big_file_id, file_name=f"{user.id}.jpg")
        except:
            pfp_path = None


        sold_message = (
            f"<b><u>Sold Player!!</u></b>\n\n"
            f"<b>-> Player Name :</b> {user.mention}\n"
            f"<b>-> Base Price :</b> {auction.base_price} ₪\n"
            f"<b>-> Amount :</b> {auction.current_bid} ₪\n"
            f"<b>-> Sold to : </b>: {auction.leading_team} \n\n"
            f"<b>Congratulations to the winning team! \n\n"
            f"⚡ **<u>Bot Owner:</u>** SHUBH ☄ (@ASTRO_SHUBH)"
        )
        await bot.send_message(
            chat_id=chat_id,
            text = sold_message)

        try:
            card = generate_card("auctionsold", user_pfp=pfp_path)
            await bot.send_photo(
            chat_id=chat_id,
            photo=card,
            caption=sold_message
        )
        except:
            pass