from connections.mongo_db import admins_collection
from pyrogram.enums import ChatMemberStatus
from time import time
import asyncio

anti_spam_time = 0

def is_user_admin(mystic):
    async def wrapper(client, message):
        if message.sender_chat:
            return await message.reply("➣ An Anonymous User can't use this command")
        
        user_id = message.from_user.id
        admin = admins_collection.find_one({"user_id": user_id})
        if not admin:
            op = await message.reply("➣ Yᴏᴜ'ʀᴇ ɴᴏᴛ ᴀɴ ᴇʟғ ɪɴ ᴄʜᴀʀɢᴇ ᴏғ **Sᴏ̨ᴜᴀᴅ's Fʀᴏsᴛʏ Tʀᴇᴀsᴜʀʏ**. 🧝‍♂️❄️")
            await asyncio.sleep(5)
            await op.delete()
            return
        
        return await mystic(client, message)
    return wrapper

def is_user_admin_cq(mystic):
    async def wrapper(client, cq):
        user_id = cq.from_user.id
        admin = admins_collection.find_one({"user_id": user_id})
        if not admin:
            return await cq.answer("❌")
        return await mystic(client, cq)
    return wrapper

def AdminActual(mystic):
    async def wrapper(client, message):

        if message.sender_chat:
            return await message.reply("➣ An Anonymous User can't use this command")
        
        if message.from_user and message.from_user.id:
            user_id = message.from_user.id
            if user_id not in [5870107229, 1297990801, 5811312454, 5712544059, 6528829722, 6098821193, 5930803951]:
                return await message.reply("➣ You aren't eligible to use this command.")
        else:
            return await message.reply("➣ Unable to determine the User.")
        
        return await mystic(client, message)
    return wrapper

def AntiSpam(mystic):
    async def wrapper(client, message):

        global anti_spam_time

        if time() - anti_spam_time < 30 :
            ap = await message.reply("⛔️ 𝐀𝐍𝐓𝐈 𝐒𝐏𝐀𝐌 ⛔️")
            await asyncio.sleep(2)
            await ap.edit_text(f"⛔️ **Tʀʏ ᴛʜᴇ ᴄᴏᴍᴍᴀɴᴅ ᴀғᴛᴇʀ {round((28 - (time() - anti_spam_time)), 1)} sᴇᴄᴏɴᴅs**. ⛔️")
            return
        
        anti_spam_time = time()

        return await mystic(client, message)
    return wrapper

def reel_checker(mystic):
    async def wrapper(client, message):
        if message.sender_chat:
            return await message.reply("➣ An Anonymous User can't use this command")
        
        if message.chat.id == -1002055598229 :
            if not message.from_user.id in [7647274849, 7882775169, 6332677760, 5554963473, 7229884403, 7338522282, 6578485885, 7070603168, 6061864902, 1886114842, 5985223084, 1037945770, 1383237913, 6508598645, 888437633, 6098821193, 5870107229, 1297990801, 5811312454, 5712544059, 6528829722, 5894653420, 1156427827, 5894653420, 7093498297, 5918455847, 7064236997, 1577768729, 7375856965, 6772919857, 6056864030,7360982580, 7344789369] : 
                await message.delete()
                await message.reply(f"➣{message.from_user.mention}, You aren't approved to send reels here.")
                return
        
        return await mystic(client, message)
    return wrapper


def group_admin(mystic):
    async def wrapper(client, message):

        if message.sender_chat:
            await message.reply("➣ An Anonymous User can't use this command")
            return
        
        if message.from_user and message.from_user.id:
            chat_member = await client.get_chat_member(message.chat.id, message.from_user.id)
            if chat_member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
                pass
            elif message.from_user.id == 5930803951:
                pass
            else:
                return await message.reply("➣ You aren't eligible to use this command.")
        else:
            return
        
        return await mystic(client, message)
    return wrapper

def co_owner(mystic):
    async def wrapper(client, message):

        if message.sender_chat:
            await message.reply("➣ An Anonymous User can't use this command")
            return
        
        if message.from_user and message.from_user.id:
            chat_member = await client.get_chat_member(message.chat.id, message.from_user.id)
            if chat_member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
                pass
                # if message.from_user.id in [5930803951, 8391128611]:
                #     pass
                # elif chat_member.privileges.can_promote_members == True :
                #     pass
                # else :
                #     return
            elif message.from_user.id in [5930803951, 6098821193, 8391128611]:
                pass
            else:
                return await message.reply("➣ You aren't eligible to use this command.")
        else:
            return
        
        return await mystic(client, message)
    return wrapper


def group_admin_cq(mystic):
    async def wrapper(client, message):

        if message.from_user and message.from_user.id:
            chat_member = await client.get_chat_member(message.message.chat.id, message.from_user.id)
            if chat_member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
                pass
            elif message.from_user.id == 5930803951:
                pass
            else:
                return await message.answer("➣ You aren't eligible to use this command.")
        else:
            return
        
        return await mystic(client, message)
    return wrapper