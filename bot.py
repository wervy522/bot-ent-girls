import os
import asyncio
import gspread
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from oauth2client.service_account import ServiceAccountCredentials
from pyrogram import Client, filters
from pyrogram.types import Message

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")
FORM_URL = os.getenv("FORM_URL")
TRIBUTE_LINK = os.getenv("TRIBUTE_LINK")

app = Client("entourage_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
scheduler = AsyncIOScheduler()

scope = ["https://spreadsheets.google.com/feeds",'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
gs_client = gspread.authorize(creds)
sheet = gs_client.open(GOOGLE_SHEET_NAME).sheet1

user_timers = {}

def check_form_submission(username):
    records = sheet.get_all_records()
    for record in records:
        tg = record.get("Как с тобой лучше связаться?", "").strip().replace("@", "")
        if tg.lower() == username.lower():
            return True
    return False

def check_form_approved(username):
    records = sheet.get_all_records()
    for record in records:
        tg = record.get("Как с тобой лучше связаться?", "").strip().replace("@", "")
        status = record.get("Статус", "").lower()
        if tg.lower() == username.lower() and "одобр" in status:
            return True
    return False

async def send_reminder(client, chat_id, level):
    if level == 1:
        await client.send_message(chat_id, f"💌 Милая, напоминаем: вступление в Entourage Girls начинается с короткой анкеты. Это займёт 3 минуты. Вот форма: {FORM_URL}")
    elif level == 2:
        await client.send_message(chat_id, f"✨ Привет! Мы пока не получили твою анкету. Entourage — это стиль жизни. Если откликается — анкета всё ещё открыта: {FORM_URL}")

async def send_invite(client, chat_id):
    await client.send_message(chat_id, f"""
Привет, дорогая! ♥
Мы приглашаем тебя в Entourage Girls!
Твоя анкета одобрена. 💖

Ссылка на оплату участия: {TRIBUTE_LINK}

Приглашение действительно 24 часа ✨
""")
    scheduler.add_job(lambda: asyncio.create_task(
        client.send_message(chat_id, f"🔔 Напоминаем: твоё приглашение в Entourage всё ещё активно. {TRIBUTE_LINK}")
    ), 'date', run_date=datetime.now() + timedelta(hours=24))

    scheduler.add_job(lambda: asyncio.create_task(
        client.send_message(chat_id, f"❗️Это финальное напоминание: твоё приглашение скоро истекает. Успей присоединиться: {TRIBUTE_LINK}")
    ), 'date', run_date=datetime.now() + timedelta(hours=48))

@app.on_message(filters.command("start") | filters.text)
async def welcome(client, message: Message):
    username = message.from_user.username
    chat_id = message.chat.id

    if check_form_approved(username):
        await send_invite(client, chat_id)
        return

    if check_form_submission(username):
        await message.reply("Спасибо, мы получили твою анкету! 💌 В течение 24 часов ты получишь ответ.")
    else:
        await message.reply(f"""Привет, милая! ✨

Спасибо за интерес к Entourage Girls — закрытому клубу девушек, которые хотят большего от жизни.

Если хочешь получить личное приглашение — заполни короткую форму, она займёт 3 минуты:
{FORM_URL}

С любовью, команда Entourage 💖
""")
        # Запланировать напоминания
        scheduler.add_job(send_reminder, 'date', run_date=datetime.now() + timedelta(hours=12), args=[client, chat_id, 1])
        scheduler.add_job(send_reminder, 'date', run_date=datetime.now() + timedelta(hours=24), args=[client, chat_id, 2])

if __name__ == "__main__":
    scheduler.start()
    app.run()