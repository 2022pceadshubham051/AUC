from config import Config

class GroupLogger:
    def __init__(self, chat_id):
        self.chat_id = chat_id

    async def log(self, client, message):
        await client.send_message(self.chat_id, message)

group_logger = GroupLogger(Config.LOG_CHANNEL)
