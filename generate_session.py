"""
一次性运行这个脚本，生成 Telethon Session String。
生成后把它存入 GitHub Secrets（TELETHON_SESSION）。
运行方式：pip install telethon && python generate_session.py
"""
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

print("=== Telethon Session 生成器 ===")
print("请先到 https://my.telegram.org 获取 API ID 和 API Hash\n")

api_id = int(input("输入 API ID: ").strip())
api_hash = input("输入 API Hash: ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as client:
    session_string = client.session.save()

print("\n✅ 你的 Session String（复制全部内容存入 GitHub Secrets）：")
print("-" * 60)
print(session_string)
print("-" * 60)
print("\n⚠️  请妥善保管，泄露相当于泄露你的 Telegram 账号！")
