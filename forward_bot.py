import asyncio
import os
import re
from collections import defaultdict
from telethon import TelegramClient
from telethon.errors import MediaEmptyError
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaWebPage

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION = os.environ["TELETHON_SESSION"]
SOURCE_CHANNEL = os.environ["SOURCE_CHANNEL"]   # 源频道 ID，如 -1001234567890
TARGET_CHANNEL = os.environ["TARGET_CHANNEL"]   # 你的频道 ID 或 @username
CUSTOM_URL = os.environ["CUSTOM_URL"]           # 你的链接（追加 / 替换用）

# REPLACE_LINKS=1 时：把原文里的链接(http/https、t.me)替换成 CUSTOM_URL，
# 并把 @用户名 提及替换成你的频道用户名；否则只在末尾追加 CUSTOM_URL（旧行为）。
REPLACE_LINKS = os.environ.get("REPLACE_LINKS", "0") == "1"
# 用于替换原文 @提及 的频道用户名（用 MENTION_HANDLE 指定，例如你的主频道 @xrollofficial；
# 未设置时回退到目标频道的 @用户名）
MENTION_HANDLE = os.environ.get("MENTION_HANDLE", "").strip() or (TARGET_CHANNEL if TARGET_CHANNEL.startswith("@") else "")

LAST_ID_FILE = os.environ.get("LAST_ID_FILE", "last_message_id.txt")

URL_RE = re.compile(r'(?:https?://|www\.|t\.me/|telegram\.me/)\S+', re.IGNORECASE)
MENTION_RE = re.compile(r'@[A-Za-z][A-Za-z0-9_]{3,31}')


def read_last_id():
    try:
        return int(open(LAST_ID_FILE).read().strip())
    except (FileNotFoundError, ValueError):
        return 0


def write_last_id(msg_id: int):
    with open(LAST_ID_FILE, "w") as f:
        f.write(str(msg_id))


def with_url(text: str) -> str:
    text = text or ""
    if REPLACE_LINKS:
        had_link = bool(URL_RE.search(text))
        # 把原文里的链接换成你的链接
        text = URL_RE.sub(CUSTOM_URL, text)
        # 把 @别人的频道 换成你的频道用户名
        if MENTION_HANDLE:
            text = MENTION_RE.sub(MENTION_HANDLE, text)
        # 原文没有任何链接时，仍在末尾补上你的链接
        if not had_link:
            text = f"{text}\n\n{CUSTOM_URL}" if text else CUSTOM_URL
        return text
    # 旧行为：仅在末尾追加
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
        content = with_url(msg.message or "")
        try:
            # 网页链接预览(MessageMediaWebPage)不是真文件，当文字发；真媒体才 send_file
            if msg.media and not isinstance(msg.media, MessageMediaWebPage):
                try:
                    await client.send_file(target, msg.media, caption=content)
                except (MediaEmptyError, TypeError) as e:
                    print(f"消息 {msg.id} 媒体无法发送（{type(e).__name__}），改发文字。")
                    await client.send_message(target, content)
            else:
                await client.send_message(target, content)
        except Exception as e:
            # 单条消息出错不应中断整批转发（否则进度不保存、下一轮死循环重试）
            print(f"跳过消息 {msg.id}: {type(e).__name__}: {e}")
        await asyncio.sleep(1.5)

    # 相册（多图/多视频）
    for group_msgs in albums.values():
        try:
            group_msgs.sort(key=lambda m: m.id)
            files = [m.media for m in group_msgs
                     if m.media and not isinstance(m.media, MessageMediaWebPage)]
            text_msg = next((m for m in reversed(group_msgs) if m.message), None)
            caption = with_url(text_msg.message if text_msg else "")
            if files:
                try:
                    await client.send_file(target, files, caption=caption)
                except (MediaEmptyError, TypeError) as e:
                    print(f"相册媒体无法发送（{type(e).__name__}），改发文字。")
                    if caption:
                        await client.send_message(target, caption)
            elif caption:
                await client.send_message(target, caption)
        except Exception as e:
            print(f"跳过相册: {type(e).__name__}: {e}")
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
