import asyncio
import os
from collections import defaultdict
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION = os.environ["TELETHON_SESSION"]
SOURCE_CHANNEL = os.environ["SOURCE_CHANNEL"]   # 源频道 ID，如 -1001234567890
TARGET_CHANNEL = os.environ["TARGET_CHANNEL"]   # 你的频道 ID 或 @username
CUSTOM_URL = os.environ["CUSTOM_URL"]           # 你要附加的链接

LAST_ID_FILE = os.environ.get("LAST_ID_FILE", "last_message_id.txt")


def read_last_id():
    try:
        return int(open(LAST_ID_FILE).read().strip())
    except (FileNotFoundError, ValueError):
        return 0


def write_last_id(msg_id: int):
    with open(LAST_ID_FILE, "w") as f:
        f.write(str(msg_id))


def with_url(text: str) -> str:
    return f"{text}\n\n{CUSTOM_URL}" if text else CUSTOM_URL


async def send_messages(client, target, messages: list):
    # 按 grouped_id 分组，处理相册
    albums: dict = defaultdict(list)
    singles = []

    for msg in messages:
        if msg.grouped_id:
            albums[msg.grouped_id].append(msg)
        else:
            singles.append(msg)

    # 单条消息
    for msg in singles:
        if msg.media:
            await client.send_file(target, msg.media, caption=with_url(msg.message or ""))
        elif msg.message:
            await client.send_message(target, with_url(msg.message))
        await asyncio.sleep(1.5)

    # 相册（多图/多视频）
    for group_msgs in albums.values():
        group_msgs.sort(key=lambda m: m.id)
        files = [m.media for m in group_msgs if m.media]
        text_msg = next((m for m in reversed(group_msgs) if m.message), None)
        caption = with_url(text_msg.message if text_msg else "")
        if files:
            await client.send_file(target, files, caption=caption)
        await asyncio.sleep(1.5)


async def main():
    last_id = read_last_id()

    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        # 先加载对话列表，确保实体缓存已初始化
        await client.get_dialogs()
        source = await client.get_entity(int(SOURCE_CHANNEL))
        target = await client.get_entity(int(TARGET_CHANNEL) if TARGET_CHANNEL.lstrip("-").isdigit() else TARGET_CHANNEL)

        # 首次运行：只记录当前最新消息 ID，不转发历史
        if last_id == 0:
            async for msg in client.iter_messages(source, limit=1):
                write_last_id(msg.id)
                print(f"首次初始化完成，从消息 ID {msg.id} 之后开始监听。")
            return

        messages = []
        async for msg in client.iter_messages(source, min_id=last_id, reverse=True, limit=100):
            if not msg.action:  # 跳过入群/退群等服务消息
                messages.append(msg)

        if not messages:
            print("没有新消息。")
            return

        print(f"发现 {len(messages)} 条新消息，开始转发...")
        await send_messages(client, target, messages)
        write_last_id(messages[-1].id)
        print(f"转发完成，当前最新 ID：{messages[-1].id}")


if __name__ == "__main__":
    asyncio.run(main())
