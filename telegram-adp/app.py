from telethon import TelegramClient, events
import os
from datetime import datetime
import asyncio
import mysql.connector
import re
import json

# Telegram API bilgileri
api_id = 1234567  # ← kendi api_id'ni yaz
api_hash = '3324c38be58520795478077fe6bea984'
client = TelegramClient('etem_logger', api_id, api_hash)

# Kanal etiketleri
TARGET_CHANNELS = {
    -1002636168605: "Kanal_ADP",
    -1001518255631: "Kanal_Log"
}

# Veritabanı bilgileri
DB_CONFIG = {
    'host': '192.168.70.70',
    'database': 'lapsusacc',
    'user': 'root',
    'password': 'daaqwWdas21as',
    'charset': 'utf8mb4',
    'port': 3306,
    'autocommit': True
}

# Dosya kilidi
file_lock = asyncio.Lock()

# Tarihi parse et
def parse_date(date_str):
    try:
        return datetime.strptime(date_str.strip(), "%d %b %Y").date()
    except:
        return datetime.now().date()

# Veritabanına kayıt fonksiyonu
def insert_log_to_db(chat_label, sender_name, message, timestamp):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # JSON varsa ayıkla
        json_match = re.search(r'\{[\s\S]*?\}', message)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
            except Exception as e:
                print(f"[!] JSON ayrıştırma hatası: {e}")
                data = {}

            if "ADP" in chat_label:
                cursor.execute("""
                    INSERT INTO vulnerabilities (channel, source, title, content, detection_date, type)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    chat_label,
                    data.get("Source", "UNKNOWN"),
                    data.get("Title", message[:100]),
                    data.get("Content", message),
                    parse_date(data.get("Detection Date")),
                    data.get("Type", "Vulnerability")
                ))
            else:
                cursor.execute("""
                    INSERT INTO leak_logs (channel, source, content, author, detection_date, type)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    chat_label,
                    data.get("Source", "UNKNOWN"),
                    data.get("Content", message),
                    data.get("author", sender_name),
                    parse_date(data.get("Detection Date")),
                    data.get("Type", "Data leak")
                ))
        else:
            # JSON yoksa düz content olarak gir
            cursor.execute("""
                INSERT INTO leak_logs (channel, source, content, author, detection_date, type)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                chat_label,
                "UNKNOWN",
                message,
                sender_name,
                timestamp.date(),
                "Data leak"
            ))

        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[!] Veritabanı hatası: {e}")

# Mesaj yakalama
@client.on(events.NewMessage(chats=list(TARGET_CHANNELS.keys())))
async def handler(event):
    async with file_lock:
        chat_id = event.chat_id
        chat_label = TARGET_CHANNELS.get(chat_id, f"Chat_{chat_id}")
        message = event.message.message or "<Boş mesaj>"
        now = datetime.now()
        timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')

        try:
            sender = await event.get_sender()
            sender_name = getattr(sender, 'first_name', 'Bilinmiyor')
        except:
            sender_name = "Bilinmiyor"

        log_line = f"[{timestamp_str}] ({chat_label}) {sender_name}: {message}"
        print(log_line)

        filename = f"telethon_{chat_label}.txt"
        with open(filename, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")

        insert_log_to_db(chat_label, sender_name, message, now)

# Başlat
print("✅ Etem logger aktif! Mesajlar kaydediliyor... 🧠")
client.start()
client.run_until_disconnected()
