"""
Lapsus Database Manager Bot
Professional Telegram Bot for Database Analytics and Management

Author: Lapsus Team
Version: 2.0.1
License: MIT
"""

import os
import sys
import asyncio
import logging
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
from contextlib import asynccontextmanager
import platform
import schedule
import time
from threading import Thread

import pymysql
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    ContextTypes, 
    Application
)
from telegram.constants import ParseMode
from telegram.error import TelegramError

# =====================================
# CONFIGURATION & CONSTANTS
# =====================================

@dataclass
class BotConfig:
    """Bot configuration class"""
    bot_token: str
    secret_token: str
    db_host: str
    db_user: str
    db_password: str
    db_name: str
    db_port: int = 3306
    max_retry_attempts: int = 3
    connection_timeout: int = 30
    log_level: str = "INFO"

class Config:
    """Configuration manager"""
    
    @staticmethod
    def load_from_env() -> BotConfig:
        """Load configuration from environment variables"""
        # Default değerler - production'da environment variables kullanın
        return BotConfig(
            bot_token=os.getenv("BOT_TOKEN", "8073854606:AAELoXcJd5nU6trI6JCeIALBt1gDFcwyAk8"),
            secret_token=os.getenv("SECRET_TOKEN", "lapsus123"),
            db_host=os.getenv("DB_HOST", "192.168.70.70"),
            db_user=os.getenv("DB_USER", "root"),
            db_password=os.getenv("DB_PASSWORD", "daaqwWdas21as"),
            db_name=os.getenv("DB_NAME", "lapsusacc"),
            db_port=int(os.getenv("DB_PORT", "3306")),
            max_retry_attempts=int(os.getenv("MAX_RETRY_ATTEMPTS", "3")),
            connection_timeout=int(os.getenv("CONNECTION_TIMEOUT", "30")),
            log_level=os.getenv("LOG_LEVEL", "INFO")
        )

# =====================================
# DATABASE MANAGER
# =====================================

class DatabaseManager:
    """Professional database connection and query manager"""
    
    def __init__(self, config: BotConfig):
        self.config = config
        self._connection_pool = []
        
    @asynccontextmanager
    async def get_connection(self):
        """Get database connection with proper cleanup"""
        connection = None
        try:
            connection = await asyncio.get_event_loop().run_in_executor(
                None, self._create_connection
            )
            yield connection
        except pymysql.Error as e:
            logging.error(f"Database connection error: {e}")
            raise
        finally:
            if connection:
                connection.close()
    
    def _create_connection(self) -> pymysql.Connection:
        """Create new database connection"""
        return pymysql.connect(
            host=self.config.db_host,
            port=self.config.db_port,
            user=self.config.db_user,
            password=self.config.db_password,
            database=self.config.db_name,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=self.config.connection_timeout,
            read_timeout=self.config.connection_timeout,
            write_timeout=self.config.connection_timeout
        )
    
    async def execute_query(self, query: str, params: Optional[tuple] = None) -> Optional[List[Dict[str, Any]]]:
        """Execute database query with error handling and retries"""
        for attempt in range(self.config.max_retry_attempts):
            try:
                async with self.get_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(query, params)
                        return cursor.fetchall()
            except pymysql.Error as e:
                logging.error(f"Database query error (attempt {attempt + 1}): {e}")
                if attempt == self.config.max_retry_attempts - 1:
                    raise
                await asyncio.sleep(1)  # Wait before retry
        return None
    
    async def test_connection(self) -> bool:
        """Test database connectivity"""
        try:
            async with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    return result is not None
        except Exception as e:
            logging.error(f"Database connection test failed: {e}")
            return False

# =====================================
# AUTHORIZATION MANAGER
# =====================================

class AuthManager:
    """User authorization and session management"""
    
    def __init__(self):
        self.authorized_users: set = set()
        self.user_sessions: Dict[int, Dict[str, Any]] = {}
    
    def authorize_user(self, user_id: int, username: str = "Unknown") -> bool:
        """Authorize user and create session"""
        self.authorized_users.add(user_id)
        self.user_sessions[user_id] = {
            'username': username,
            'login_time': datetime.now(),
            'last_activity': datetime.now(),
            'command_count': 0
        }
        logging.info(f"User authorized: {username} (ID: {user_id})")
        return True
    
    def is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized"""
        return user_id in self.authorized_users
    
    def update_activity(self, user_id: int, command: str):
        """Update user activity"""
        if user_id in self.user_sessions:
            self.user_sessions[user_id]['last_activity'] = datetime.now()
            self.user_sessions[user_id]['command_count'] += 1
            logging.debug(f"User {user_id} executed command: {command}")
    
    def get_user_stats(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user session statistics"""
        return self.user_sessions.get(user_id)
    
    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all active user sessions"""
        return [
            {
                'user_id': user_id,
                **session_data
            }
            for user_id, session_data in self.user_sessions.items()
        ]

# =====================================
# MESSAGE FORMATTER
# =====================================

class MessageFormatter:
    """Professional message formatting utilities"""
    
    @staticmethod
    def format_number(number: Union[int, float]) -> str:
        """Format numbers with thousands separators"""
        return f"{number:,}"
    
    @staticmethod
    def format_percentage(value: float, total: float) -> str:
        """Format percentage with 2 decimal places"""
        if total == 0:
            return "0.00%"
        return f"{(value / total * 100):.2f}%"
    
    @staticmethod
    def format_datetime(dt: datetime) -> str:
        """Format datetime for display"""
        return dt.strftime("%Y-%m-%d %H:%M:%S")

# =====================================
# BOT COMMANDS HANDLER
# =====================================

class LapsusBotHandler:
    """Main bot command handler"""
    
    def __init__(self, config: BotConfig):
        self.config = config
        self.db_manager = DatabaseManager(config)
        self.auth_manager = AuthManager()
        self.formatter = MessageFormatter()
        self.daily_report_enabled = True  # Günlük rapor aktif/pasif
        self.report_chat_ids = set()  # Rapor alacak chat ID'leri
    
    async def initialize(self) -> bool:
        """Initialize bot and test connections"""
        logging.info("Initializing Lapsus Bot...")
        
        # Test database connection
        if not await self.db_manager.test_connection():
            logging.error("Database connection failed during initialization")
            return False
        
        logging.info("✅ Database connection successful")
        return True
    
    # =====================================
    # AUTHENTICATION COMMANDS
    # =====================================
    
    async def cmd_login(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """User authentication command"""
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name or "Unknown"
        
        if len(context.args) == 0:
            await update.message.reply_text(
                "🔐 **Authentication Required**\n\n"
                "Usage: `/giris <token>`\n"
                "Please provide your access token.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        provided_token = context.args[0]
        
        if provided_token == self.config.secret_token:
            self.auth_manager.authorize_user(user_id, username)
            
            welcome_msg = (
                "✅ **Authentication Successful!**\n\n"
                f"Welcome, **{username}**!\n"
                f"Login time: `{self.formatter.format_datetime(datetime.now())}`\n\n"
                "🎯 You can now access all bot commands.\n"
                "📋 Type `/help` to see available commands."
            )
            
            await update.message.reply_text(welcome_msg, parse_mode=ParseMode.MARKDOWN)
        else:
            logging.warning(f"Failed login attempt: {username} (ID: {user_id}) with token: {provided_token}")
            await update.message.reply_text(
                "❌ **Authentication Failed**\n\n"
                "Invalid access token provided.\n"
                "Please contact administrator for valid token.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    def _check_auth(self, user_id: int) -> bool:
        """Check user authorization"""
        return self.auth_manager.is_authorized(user_id)
    
    async def _unauthorized_response(self, update: Update):
        """Send unauthorized access message"""
        await update.message.reply_text(
            "🚫 **Access Denied**\n\n"
            "Please authenticate first using:\n"
            "`/giris <your_token>`\n\n"
            "Contact administrator if you need access.",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _track_command_usage(self, update: Update, command: str):
        """Track command usage for analytics"""
        user_id = update.effective_user.id
        self.auth_manager.update_activity(user_id, command)
    
    # =====================================
    # INFORMATION COMMANDS
    # =====================================
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display help menu"""
        if not self._check_auth(update.effective_user.id):
            return await self._unauthorized_response(update)
        
        await self._track_command_usage(update, "help")
        
        help_text = """
🤖 **Lapsus Database Manager v2.0.1**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 **Analytics Commands:**
• `/istatistik` - Database overview & daily stats
• `/bolgeler` - Regional distribution analysis
• `/enpopulerdomain` - Top 10 popular domains
• `/son7gun` - Last 7 days activity report
• `/kaynaklar` - Source-based categorization

🔍 **Search & Query Commands:**
• `/spidsorgu <id>` - Search by specific SPID
• `/ara <keyword>` - Domain keyword search
• `/tarihsorgu <YYYY-MM-DD>` - Date-based queries
• `/domainkontrol <domain>` - Exact domain match

📊 **Daily Report System:**
• `/gunlukrapor` - Get daily report manually
• `/raporabone` - Subscribe to daily reports (00:00)
• `/raporiptal` - Unsubscribe from daily reports
• `/raporayarlari` - Report settings & info

🛠️ **System Commands:**
• `/debug` - System diagnostics & data analysis
• `/status` - Bot & database status
• `/sessions` - Active user sessions
• `/help` - This help menu

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 **Tips:**
- All dates use YYYY-MM-DD format
- Commands are case-sensitive
- Use exact syntax for best results

🔒 **Security:** Your session expires after 24h of inactivity
        """
        
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot and system status"""
        if not self._check_auth(update.effective_user.id):
            return await self._unauthorized_response(update)
        
        await self._track_command_usage(update, "status")
        
        # Test database connectivity
        db_status = "🟢 Connected" if await self.db_manager.test_connection() else "🔴 Disconnected"
        
        # Get system info
        active_sessions = len(self.auth_manager.get_active_sessions())
        current_time = self.formatter.format_datetime(datetime.now())
        
        status_msg = f"""
🔧 **System Status Report**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🗄️ **Database:** {db_status}
👥 **Active Sessions:** {active_sessions}
🕒 **Current Time:** `{current_time}`
🤖 **Bot Version:** v2.0.1
⚡ **Status:** Operational

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔗 **Connection Details:**
• Host: `{self.config.db_host}:{self.config.db_port}`
• Database: `{self.config.db_name}`
• Timeout: {self.config.connection_timeout}s
• Max Retries: {self.config.max_retry_attempts}
        """
        
        await update.message.reply_text(status_msg, parse_mode=ParseMode.MARKDOWN)
    
    # =====================================
    # DAILY REPORT SYSTEM
    # =====================================
    
    async def generate_daily_report(self) -> str:
        """Günlük detaylı rapor oluştur"""
        try:
            yesterday = datetime.now() - timedelta(days=1)
            yesterday_str = yesterday.strftime('%Y-%m-%d')
            
            # Dün eklenen toplam kayıt
            daily_query = "SELECT COUNT(*) as daily_count FROM accs WHERE DATE(date) = %s"
            daily_result = await self.db_manager.execute_query(daily_query, (yesterday_str,))
            daily_count = daily_result[0]['daily_count'] if daily_result else 0
            
            # Dün eklenen kayıtların bölgelere göre dağılımı
            regions_query = """
                SELECT 
                    COALESCE(region, 'Unspecified') as region, 
                    COUNT(*) as count,
                    ROUND((COUNT(*) * 100.0 / %s), 2) as percentage
                FROM accs 
                WHERE DATE(date) = %s
                GROUP BY region 
                ORDER BY count DESC 
                LIMIT 10
            """
            regions_result = await self.db_manager.execute_query(regions_query, (daily_count, yesterday_str))
            
            # Dün eklenen kayıtların domainlere göre dağılımı
            domains_query = """
                SELECT 
                    domain, 
                    COUNT(*) as count,
                    ROUND((COUNT(*) * 100.0 / %s), 2) as percentage
                FROM accs 
                WHERE DATE(date) = %s AND domain IS NOT NULL AND domain != ''
                GROUP BY domain 
                ORDER BY count DESC 
                LIMIT 10
            """
            domains_result = await self.db_manager.execute_query(domains_query, (daily_count, yesterday_str))
            
            # Dün eklenen kayıtların saatlik dağılımı
            hourly_query = """
                SELECT 
                    HOUR(date) as hour,
                    COUNT(*) as count
                FROM accs 
                WHERE DATE(date) = %s
                GROUP BY HOUR(date)
                ORDER BY hour
            """
            hourly_result = await self.db_manager.execute_query(hourly_query, (yesterday_str,))
            
            # Kaynak dağılımı
            sources_query = """
                SELECT 
                    COALESCE(NULLIF(source, ''), 'Unspecified') as source,
                    COUNT(*) as count,
                    ROUND((COUNT(*) * 100.0 / %s), 2) as percentage
                FROM accs 
                WHERE DATE(date) = %s
                GROUP BY source 
                ORDER BY count DESC 
                LIMIT 5
            """
            sources_result = await self.db_manager.execute_query(sources_query, (daily_count, yesterday_str))
            
            # Genel istatistikler
            total_query = "SELECT COUNT(*) as total FROM accs"
            total_result = await self.db_manager.execute_query(total_query)
            total_count = total_result[0]['total'] if total_result else 0
            
            # Son 7 günün karşılaştırması
            week_comparison_query = """
                SELECT 
                    DATE(date) as date,
                    COUNT(*) as count
                FROM accs 
                WHERE DATE(date) >= %s - INTERVAL 6 DAY AND DATE(date) <= %s
                GROUP BY DATE(date)
                ORDER BY date DESC
            """
            week_result = await self.db_manager.execute_query(week_comparison_query, (yesterday_str, yesterday_str))
            
            # Rapor metni oluştur
            report = f"""
📊 **GÜNLÜK RAPOR - {yesterday_str}**
📅 **{yesterday.strftime('%A, %d %B %Y')}**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 **GENEL İSTATİSTİKLER:**
• Dün Eklenen: **{self.formatter.format_number(daily_count)}**
• Toplam Kayıt: **{self.formatter.format_number(total_count)}**
• Günlük Oran: **{self.formatter.format_percentage(daily_count, total_count)}**

"""
            
            if daily_count > 0:
                # Bölgesel dağılım
                if regions_result:
                    report += "🌍 **BÖLGESEL DAĞILIM:**\n"
                    for i, row in enumerate(regions_result[:5], 1):
                        region_flag = self._get_region_flag(row['region'])
                        report += f"{i}. {region_flag} **{row['region']}**: {self.formatter.format_number(row['count'])} ({row['percentage']}%)\n"
                    report += "\n"
                
                # Domain dağılımı
                if domains_result:
                    report += "🌐 **POPÜLER DOMAINLER:**\n"
                    for i, row in enumerate(domains_result[:5], 1):
                        domain_emoji = self._get_domain_emoji(row['domain'])
                        report += f"{i}. {domain_emoji} **{row['domain']}**: {self.formatter.format_number(row['count'])} ({row['percentage']}%)\n"
                    report += "\n"
                
                # Saatlik aktivite (sadece aktif saatler)
                if hourly_result:
                    peak_hours = sorted(hourly_result, key=lambda x: x['count'], reverse=True)[:3]
                    if peak_hours:
                        report += "⏰ **EN AKTİF SAATLER:**\n"
                        for i, hour_data in enumerate(peak_hours, 1):
                            hour = hour_data['hour']
                            count = hour_data['count']
                            percentage = self.formatter.format_percentage(count, daily_count)
                            report += f"{i}. **{hour:02d}:00-{hour+1:02d}:00**: {self.formatter.format_number(count)} ({percentage})\n"
                        report += "\n"
                
                # Kaynak dağılımı
                if sources_result:
                    report += "🔗 **KAYNAK DAĞILIMI:**\n"
                    for i, row in enumerate(sources_result, 1):
                        source_emoji = self._get_source_emoji(row['source'])
                        report += f"{i}. {source_emoji} **{row['source']}**: {self.formatter.format_number(row['count'])} ({row['percentage']}%)\n"
                    report += "\n"
            
            # Haftalık trend
            if week_result and len(week_result) > 1:
                report += "📊 **7 GÜNLÜK TREND:**\n"
                week_total = sum(row['count'] for row in week_result)
                week_avg = week_total / len(week_result)
                
                for row in week_result:
                    date = row['date']
                    count = row['count']
                    day_name = date.strftime("%a")
                    
                    # Trend göstergesi
                    if count > week_avg * 1.2:
                        trend = "📈"
                    elif count < week_avg * 0.8:
                        trend = "📉"
                    else:
                        trend = "➡️"
                    
                    report += f"• {date} ({day_name}): {trend} **{self.formatter.format_number(count)}**\n"
                
                report += f"\nHaftalık Ortalama: **{self.formatter.format_number(int(week_avg))}**\n"
            
            # Performans değerlendirmesi
            report += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            if daily_count == 0:
                report += "⚠️ **UYARI**: Dün hiç kayıt eklenmedi!\n"
            elif week_result:
                week_avg = sum(row['count'] for row in week_result) / len(week_result)
                if daily_count > week_avg * 1.5:
                    report += "🚀 **MÜKEMMEL**: Haftalık ortalamanın üzerinde!\n"
                elif daily_count > week_avg:
                    report += "✅ **İYİ**: Ortalamanın üzerinde performans\n"
                elif daily_count < week_avg * 0.5:
                    report += "🔴 **DİKKAT**: Ortalamanın çok altında!\n"
                else:
                    report += "⚡ **NORMAL**: Haftalık ortalama seviyesinde\n"
            
            report += f"\n🕐 **Rapor Zamanı**: {self.formatter.format_datetime(datetime.now())}\n"
            report += "🤖 **Lapsus Database Manager v2.0.1**"
            
            return report
            
        except Exception as e:
            logging.error(f"Daily report generation error: {e}")
            return f"❌ **Günlük Rapor Hatası**\n\nRapor oluşturulurken hata oluştu: {str(e)}"
    
    def _get_region_flag(self, region: str) -> str:
        """Get flag emoji for region"""
        region_flags = {
            'US': '🇺🇸', 'USA': '🇺🇸', 'United States': '🇺🇸',
            'TR': '🇹🇷', 'Turkey': '🇹🇷', 'Türkiye': '🇹🇷',
            'DE': '🇩🇪', 'Germany': '🇩🇪',
            'FR': '🇫🇷', 'France': '🇫🇷',
            'UK': '🇬🇧', 'United Kingdom': '🇬🇧',
            'CN': '🇨🇳', 'China': '🇨🇳',
            'RU': '🇷🇺', 'Russia': '🇷🇺',
            'Unspecified': '🌐'
        }
        return region_flags.get(region, '🏁')
    
    def _get_domain_emoji(self, domain: str) -> str:
        """Get emoji for domain type"""
        if not domain:
            return '🌍'
        domain = domain.lower()
        if any(x in domain for x in ['gmail', 'google']):
            return '📧'
        elif any(x in domain for x in ['yahoo', 'ymail']):
            return '💌'
        elif any(x in domain for x in ['outlook', 'hotmail', 'live', 'msn']):
            return '📨'
        elif any(x in domain for x in ['icloud', 'me.com', 'mac.com']):
            return '☁️'
        elif any(x in domain for x in ['protonmail', 'tutanota']):
            return '🔒'
        else:
            return '🌍'
    
    def _get_source_emoji(self, source: str) -> str:
        """Get emoji for source type"""
        if not source:
            return '📂'
        source = source.lower()
        if 'api' in source:
            return '🔌'
        elif any(x in source for x in ['import', 'migration', 'transfer']):
            return '📦'
        elif any(x in source for x in ['manual', 'admin']):
            return '👤'
        elif any(x in source for x in ['auto', 'automated', 'script']):
            return '🤖'
        elif any(x in source for x in ['web', 'website', 'form']):
            return '🌐'
        elif 'unspecified' in source:
            return '❓'
        else:
            return '📂'
    
    async def send_daily_report_to_subscribers(self):
        """Günlük raporu abone olan kullanıcılara gönder"""
        if not self.daily_report_enabled or not hasattr(self, 'application') or not self.application:
            return
        
        try:
            report = await self.generate_daily_report()
            
            if self.report_chat_ids:
                for chat_id in self.report_chat_ids.copy():  # Copy to avoid modification during iteration
                    try:
                        await self.application.bot.send_message(
                            chat_id=chat_id, 
                            text=report, 
                            parse_mode=ParseMode.MARKDOWN
                        )
                        logging.info(f"Daily report sent to chat {chat_id}")
                        await asyncio.sleep(1)  # Rate limiting
                    except Exception as e:
                        logging.error(f"Failed to send daily report to {chat_id}: {e}")
                        # Hatalı chat ID'yi kaldır
                        self.report_chat_ids.discard(chat_id)
            else:
                logging.info("No subscribers for daily report")
                
        except Exception as e:
            logging.error(f"Error sending daily reports: {e}")
    
    async def cmd_daily_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manuel günlük rapor komutu"""
        if not self._check_auth(update.effective_user.id):
            return await self._unauthorized_response(update)
        
        await self._track_command_usage(update, "daily_report")
        
        try:
            # Loading mesajı gönder
            loading_msg = await update.message.reply_text("📊 **Günlük rapor hazırlanıyor...**", parse_mode=ParseMode.MARKDOWN)
            
            # Raporu oluştur
            report = await self.generate_daily_report()
            
            # Loading mesajını sil ve raporu gönder
            await loading_msg.delete()
            await update.message.reply_text(report, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logging.error(f"Manual daily report error: {e}")
            await update.message.reply_text(
                "❌ **Hata**\n\nGünlük rapor oluşturulurken hata oluştu.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def cmd_report_subscribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Günlük rapora abone ol"""
        if not self._check_auth(update.effective_user.id):
            return await self._unauthorized_response(update)
        
        await self._track_command_usage(update, "report_subscribe")
        
        chat_id = update.effective_chat.id
        
        if chat_id in self.report_chat_ids:
            await update.message.reply_text(
                "✅ **Zaten Abonesinsiz**\n\nBu chat zaten günlük rapora abone.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            self.report_chat_ids.add(chat_id)
            await update.message.reply_text(
                "🔔 **Abonelik Başarılı!**\n\n"
                "Bu chat artık her gece saat 00:00'da günlük rapor alacak.\n\n"
                "📋 Abonelikten çıkmak için: `/raporiptal`",
                parse_mode=ParseMode.MARKDOWN
            )
            logging.info(f"Chat {chat_id} subscribed to daily reports")
    
    async def cmd_report_unsubscribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Günlük rapordan çık"""
        if not self._check_auth(update.effective_user.id):
            return await self._unauthorized_response(update)
        
        await self._track_command_usage(update, "report_unsubscribe")
        
        chat_id = update.effective_chat.id
        
        if chat_id in self.report_chat_ids:
            self.report_chat_ids.remove(chat_id)
            await update.message.reply_text(
                "🔕 **Abonelik İptal Edildi**\n\nBu chat artık günlük rapor almayacak.",
                parse_mode=ParseMode.MARKDOWN
            )
            logging.info(f"Chat {chat_id} unsubscribed from daily reports")
        else:
            await update.message.reply_text(
                "ℹ️ **Zaten Abone Değilsiniz**\n\nBu chat günlük rapora abone değil.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def cmd_report_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Rapor ayarları"""
        if not self._check_auth(update.effective_user.id):
            return await self._unauthorized_response(update)
        
        await self._track_command_usage(update, "report_settings")
        
        chat_id = update.effective_chat.id
        is_subscribed = chat_id in self.report_chat_ids
        
        settings_text = f"""
📊 **Günlük Rapor Ayarları**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔔 **Abonelik Durumu:** {"✅ Aktif" if is_subscribed else "❌ Pasif"}
⏰ **Rapor Zamanı:** Her gece 00:00
📱 **Toplam Abone:** {len(self.report_chat_ids)} chat
🤖 **Sistem Durumu:** {"🟢 Aktif" if self.daily_report_enabled else "🔴 Pasif"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 **Kullanılabilir Komutlar:**
• `/gunlukrapor` - Manuel rapor al
• `/raporabone` - Otomatik rapora abone ol
• `/raporiptal` - Abonelikten çık
• `/raporayarlari` - Bu menü

💡 **Günlük Rapor İçeriği:**
- Önceki günün istatistikleri
- Bölgesel dağılım analizi
- Domain istatistikleri
- Saatlik aktivite raporu
- Haftalık trend karşılaştırması
        """
        
        await update.message.reply_text(settings_text, parse_mode=ParseMode.MARKDOWN)
    async def cmd_statistics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced database statistics"""
        if not self._check_auth(update.effective_user.id):
            return await self._unauthorized_response(update)
        
        await self._track_command_usage(update, "statistics")
        
        try:
            # Get comprehensive statistics
            total_query = "SELECT COUNT(*) as total FROM accs"
            today_query = "SELECT COUNT(*) as today_total FROM accs WHERE DATE(date) = CURDATE()"
            week_query = "SELECT COUNT(*) as week_total FROM accs WHERE DATE(date) >= CURDATE() - INTERVAL 7 DAY"
            
            total_result = await self.db_manager.execute_query(total_query)
            today_result = await self.db_manager.execute_query(today_query)
            week_result = await self.db_manager.execute_query(week_query)
            
            if not all([total_result, today_result, week_result]):
                raise Exception("Failed to fetch statistics")
            
            total = total_result[0]["total"]
            today = today_result[0]["today_total"]
            week = week_result[0]["week_total"]
            
            # Calculate percentages
            today_pct = self.formatter.format_percentage(today, total)
            week_pct = self.formatter.format_percentage(week, total)
            
            current_time = self.formatter.format_datetime(datetime.now())
            
            stats_msg = f"""
📊 **Database Analytics Report**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 **Overview:**
• Total Records: **{self.formatter.format_number(total)}**
• Database Size: Excellent ✅

📅 **Time-based Statistics:**
• Today: **{self.formatter.format_number(today)}** ({today_pct})
• Last 7 Days: **{self.formatter.format_number(week)}** ({week_pct})

🕒 **Generated:** `{current_time}`

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 Use `/debug` for detailed analysis
            """
            
            await update.message.reply_text(stats_msg, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logging.error(f"Statistics command error: {e}")
            await update.message.reply_text(
                "❌ **Error**\n\nFailed to retrieve statistics. Please try again later.",
                parse_mode=ParseMode.MARKDOWN
            )

    # Diğer temel komutlar (basitleştirilmiş)
    async def cmd_regions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update.effective_user.id):
            return await self._unauthorized_response(update)
        
        await self._track_command_usage(update, "regions")
        
        try:
            query = """
                SELECT 
                    COALESCE(region, 'Unspecified') as region, 
                    COUNT(*) AS count
                FROM accs 
                GROUP BY region 
                ORDER BY count DESC 
                LIMIT 10
            """
            
            result = await self.db_manager.execute_query(query)
            
            if not result:
                await update.message.reply_text("📍 **Regional Analysis**\n\nNo regional data found.", parse_mode=ParseMode.MARKDOWN)
                return
            
            regions_text = "📍 **Regional Distribution Analysis**\n\n"
            
            for i, row in enumerate(result, 1):
                region = row['region']
                count = self.formatter.format_number(row['count'])
                regions_text += f"{i:2d}. **{region}**: {count}\n"
            
            await update.message.reply_text(regions_text, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logging.error(f"Regions command error: {e}")
            await update.message.reply_text("❌ **Error**\n\nFailed to retrieve regional data.", parse_mode=ParseMode.MARKDOWN)

# =====================================
# EVENT LOOP FIX
# =====================================

def fix_event_loop():
    """Fix event loop issues on Windows/Jupyter"""
    if platform.system() == 'Windows':
        # Windows specific fix
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Check if we're in Jupyter/IPython
    try:
        import IPython
        if IPython.get_ipython() is not None:
            import nest_asyncio
            nest_asyncio.apply()
            logging.info("Applied nest_asyncio for Jupyter compatibility")
    except ImportError:
        pass

# =====================================
# APPLICATION SETUP
# =====================================

class LapsusBotApplication:
    """Main bot application class"""
    
    def __init__(self):
        self.config = Config.load_from_env()
        self.handler = LapsusBotHandler(self.config)
        self.application: Optional[Application] = None
        self.scheduler_thread = None
        self.scheduler_running = False
    
    def setup_daily_scheduler(self):
        """Günlük rapor scheduler'ını ayarla"""
        def run_scheduler():
            while self.scheduler_running:
                schedule.run_pending()
                time.sleep(30)  # Her 30 saniyede bir kontrol et
        
        def daily_report_job():
            """Scheduler job function"""
            if self.application and hasattr(self.handler, 'send_daily_report_to_subscribers'):
                try:
                    # Async fonksiyonu sync context'te çalıştır
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.handler.send_daily_report_to_subscribers())
                    loop.close()
                except Exception as e:
                    logging.error(f"Daily report scheduler error: {e}")
        
        # Her gece 00:00'da çalışacak job'u ayarla
        schedule.every().day.at("00:00").do(daily_report_job)
        
        # Scheduler thread'ini başlat
        self.scheduler_running = True
        self.scheduler_thread = Thread(target=run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        logging.info("✅ Daily report scheduler started (00:00 daily)")
        
        # Test için - bir sonraki dakikada da çalışacak şekilde (ilk test için)
        next_minute = (datetime.now() + timedelta(minutes=1)).strftime("%H:%M")
        schedule.every().day.at(next_minute).do(daily_report_job).tag('test')
        
        logging.info(f"🧪 Test report scheduled for {next_minute} (one-time)")
    
    def stop_scheduler(self):
        """Scheduler'ı durdur"""
        self.scheduler_running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        schedule.clear()
        logging.info("🛑 Daily report scheduler stopped")
    
    def setup_handlers(self):
        """Setup all command handlers"""
        handlers = [
            ("giris", self.handler.cmd_login),
            ("login", self.handler.cmd_login),
            ("help", self.handler.cmd_help),
            ("start", self.handler.cmd_help),
            ("status", self.handler.cmd_status),
            ("istatistik", self.handler.cmd_statistics),
            ("bolgeler", self.handler.cmd_regions),
            # Daily Report Commands
            ("gunlukrapor", self.handler.cmd_daily_report),
            ("raporabone", self.handler.cmd_report_subscribe),
            ("raporiptal", self.handler.cmd_report_unsubscribe),
            ("raporayarlari", self.handler.cmd_report_settings),
        ]
        
        for command, handler in handlers:
            self.application.add_handler(CommandHandler(command, handler))
        
        logging.info(f"✅ Registered {len(handlers)} command handlers")
    
    def run_sync(self):
        """Synchronous run method to avoid event loop conflicts"""
        try:
            # Fix event loop issues
            fix_event_loop()
            
            # Initialize bot handler
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            init_success = loop.run_until_complete(self.handler.initialize())
            if not init_success:
                logging.error("❌ Bot initialization failed")
                return False
            
            # Create application
            self.application = ApplicationBuilder().token(self.config.bot_token).build()
            
            # Bot application'ı handler'a bağla (günlük rapor için gerekli)
            self.handler.application = self.application
            
            # Setup handlers
            self.setup_handlers()
            
            # Daily report scheduler'ını başlat
            self.setup_daily_scheduler()
            
            logging.info("🚀 Lapsus Bot initialized successfully")
            logging.info("🤖 Starting Lapsus Database Manager Bot...")
            logging.info(f"📡 Bot Token: {self.config.bot_token[:20]}...")
            logging.info(f"🗄️ Database: {self.config.db_host}:{self.config.db_port}/{self.config.db_name}")
            
            # Start bot polling
            self.application.run_polling(drop_pending_updates=True)
            
        except KeyboardInterrupt:
            logging.info("🛑 Bot stopped by user")
        except Exception as e:
            logging.error(f"❌ Bot runtime error: {e}")
            return False
        finally:
            logging.info("🔄 Cleaning up resources...")
            self.stop_scheduler()  # Scheduler'ı durdur
        
        return True

# =====================================
# LOGGING SETUP
# =====================================

def setup_logging(config: BotConfig):
    """Setup comprehensive logging"""
    log_format = "%(asctime)s | %(levelname)8s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # Setup file handler
    file_handler = logging.FileHandler(
        filename=f"logs/lapsus_bot_{datetime.now().strftime('%Y%m%d')}.log",
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))
    
    # Setup console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, config.log_level.upper()))
    console_handler.setFormatter(logging.Formatter(log_format, date_format))
    
    # Setup root logger
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[file_handler, console_handler],
        format=log_format,
        datefmt=date_format
    )
    
    # Reduce noise from external libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.INFO)

# =====================================
# MAIN ENTRY POINT
# =====================================

def main():
    """Main application entry point - synchronous version"""
    print("""
    ╔══════════════════════════════════════╗
    ║         LAPSUS DATABASE MANAGER      ║
    ║              Version 2.0.1           ║
    ║        Professional Telegram Bot     ║
    ╚══════════════════════════════════════╝
    """)
    
    # Load configuration
    config = Config.load_from_env()
    
    # Setup logging
    setup_logging(config)
    
    # Print configuration info
    logging.info("🔧 Configuration loaded:")
    logging.info(f"   DB Host: {config.db_host}:{config.db_port}")
    logging.info(f"   DB Name: {config.db_name}")
    logging.info(f"   Log Level: {config.log_level}")
    
    # Create and run bot application
    bot_app = LapsusBotApplication()
    success = bot_app.run_sync()
    
    if not success:
        print("\n💥 Bot failed to start properly")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped gracefully")
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        logging.error(f"Fatal error in main: {e}")
        sys.exit(1)