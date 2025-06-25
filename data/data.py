#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import mysql.connector
from mysql.connector import Error
from datetime import datetime

# Database bağlantı bilgileri
DB_CONFIG = {
    'host': '192.168.70.70',
    'database': 'lapsusacc',
    'user': 'root',
    'password': 'daaqwWdas21as',
    'charset': 'utf8mb4',
    'port': 3306
}

# Hedef domain listesi - Kapsamlı tarama
TARGET_DOMAINS = {
    "banks": [
        "ziraatbank.com.tr",
        "vakifbank.com.tr",
        "halkbank.com.tr",
        "isbank.com.tr",
        "akbank.com",
        "yapikredi.com.tr",
        "garantibbva.com.tr",
        "qnbfinansbank.com",
        "denizbank.com",
        "teb.com.tr"
    ],
    "turkish_extensions": [
        ".gov.tr",
        ".edu.tr",
        ".org.tr",
        ".bel.tr",
        ".k12.tr",
        ".tsk.tr"
    ],
    "popular_turkish": [
        "turkcell.com.tr",
        "vodafone.com.tr",
        "turktelekom.com.tr",
        "sahibinden.com",
        "hepsiburada.com",
        "trendyol.com",
        "n11.com",
        "eksiup.com",
        "milliyet.com.tr",
        "hurriyet.com.tr"
    ],
    "government": [
        "tckb.gov.tr",
        "icisleri.gov.tr",
        "sgk.gov.tr",
        "mhk.gov.tr",
        "turkiye.gov.tr",
        "gelirler.gov.tr",
        "meb.gov.tr",
        "ticaret.gov.tr",
        "cumhurbaskanligi.gov.tr",
        "msb.gov.tr"
    ],
    "universities": [
        "istanbul.edu.tr",
        "ankara.edu.tr",
        "ege.edu.tr",
        "hacettepe.edu.tr",
        "odtu.edu.tr",
        "bilkent.edu.tr",
        "itu.edu.tr",
        "yildiz.edu.tr",
        "selcuk.edu.tr",
        "uludag.edu.tr"
    ]
}


# Tüm domainleri birleştir
ALL_DOMAINS = []
for category, domains in TARGET_DOMAINS.items():
    ALL_DOMAINS.extend(domains)

# Domain uzantıları için ayrı liste
DOMAIN_EXTENSIONS = TARGET_DOMAINS["turkish_extensions"]

class DataFetcher:
    def __init__(self):
        self.connection = None
        self.all_accounts = []
        self.stats = {
            'total_found': 0,
            'by_category': {},
            'total_added': 0,
            'total_skipped': 0,
            'start_time': datetime.now(),
            'end_time': None
        }
    
    def log(self, message):
        """Log mesajı yazdır"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
    
    def connect_db(self):
        """Veritabanına bağlan"""
        try:
            self.connection = mysql.connector.connect(**DB_CONFIG)
            if self.connection.is_connected():
                db_info = self.connection.get_server_info()
                cursor = self.connection.cursor()
                cursor.execute("SELECT database();")
                db_name = cursor.fetchone()[0]
                self.log(f"✅ MySQL Server {db_info} bağlantısı başarılı")
                self.log(f"📊 Veritabanı: {db_name}")
                return True
        except Error as e:
            self.log(f"❌ Database bağlantı hatası: {e}")
            return False
    
    def disconnect_db(self):
        """Veritabanı bağlantısını kapat"""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            self.log("🔐 Database bağlantısı kapatıldı")
    
    def create_fetched_accounts_table(self):
        """Fetched accounts için yeni tablo oluştur"""
        try:
            cursor = self.connection.cursor()
            create_table_query = """
            CREATE TABLE IF NOT EXISTS `fetched_accounts` (
                `id` int(11) NOT NULL AUTO_INCREMENT,
                `spid` int(11) DEFAULT 0,
                `domain` varchar(255) NOT NULL,
                `region` varchar(100) DEFAULT '',
                `source` varchar(100) DEFAULT '',
                `category` varchar(50) DEFAULT '',
                `fetch_date` datetime DEFAULT CURRENT_TIMESTAMP,
                `added_date` date DEFAULT (CURDATE()),
                PRIMARY KEY (`id`),
                INDEX `idx_domain` (`domain`),
                INDEX `idx_category` (`category`),
                INDEX `idx_fetch_date` (`fetch_date`),
                INDEX `idx_added_date` (`added_date`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
            """
            cursor.execute(create_table_query)
            self.connection.commit()
            self.log("📋 'fetched_accounts' tablosu kontrol edildi/oluşturuldu")
            return True
        except Error as e:
            self.log(f"❌ Fetched accounts tablosu oluşturma hatası: {e}")
            return False
    
    def clear_fetched_accounts_table(self):
        """fetched_accounts tablosundaki tüm verileri sil"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("TRUNCATE TABLE fetched_accounts")
            self.connection.commit()
            self.log("🗑️ fetched_accounts tablosu temizlendi")
            return True
        except Error as e:
            self.log(f"❌ fetched_accounts tablosunu temizleme hatası: {e}")
            return False
    
    def test_table(self):
        """Tabloları test et"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SHOW TABLES LIKE 'accs'")
            result = cursor.fetchone()
            if result:
                cursor.execute("SELECT COUNT(*) FROM accs")
                total_count = cursor.fetchone()[0]
                self.log(f"📋 'accs' tablosu bulundu - Toplam kayıt: {total_count}")
            else:
                self.log("❌ 'accs' tablosu bulunamadı!")
                return False
            
            if not self.create_fetched_accounts_table():
                return False
                
            cursor.execute("SELECT COUNT(*) FROM fetched_accounts")
            fetched_count = cursor.fetchone()[0]
            self.log(f"📋 'fetched_accounts' tablosu - Mevcut kayıt: {fetched_count}")
            
            return True
        except Error as e:
            self.log(f"❌ Tablo test hatası: {e}")
            return False
    
    def bulk_insert_accounts(self, accounts_batch, category):
        """Toplu hesap ekleme - FETCHED_ACCOUNTS tablosuna"""
        try:
            cursor = self.connection.cursor()
            
            insert_query = """
                INSERT IGNORE INTO fetched_accounts 
                (spid, domain, region, source, category, fetch_date, added_date)
                VALUES (%s, %s, %s, %s, %s, NOW(), CURDATE())
            """
            
            batch_data = []
            for account in accounts_batch:
                values = (
                    account.get('spid', 0),
                    account['domain'],
                    account.get('region', ''),
                    f"AUTO-FETCH-{datetime.now().strftime('%Y%m%d')}",
                    category
                )
                batch_data.append(values)
            
            cursor.executemany(insert_query, batch_data)
            self.connection.commit()
            
            return cursor.rowcount
            
        except Error as e:
            self.log(f"❌ Toplu ekleme hatası: {e}")
            return 0
    
    def fetch_external_data(self, domain_or_extension, is_extension=False):
        """External kaynaklardan veri çek"""
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            if is_extension:
                query = """
                    SELECT domain, region
                    FROM accs 
                    WHERE domain LIKE %s 
                    AND source NOT LIKE 'AUTO-FETCH%'
                    ORDER BY id DESC
                """
                search_term = f"%{domain_or_extension}"
                log_name = f"*{domain_or_extension} uzantısı"
            else:
                query = """
                    SELECT domain, region
                    FROM accs 
                    WHERE domain LIKE %s 
                    AND source NOT LIKE 'AUTO-FETCH%'
                    ORDER BY id DESC  
                """
                search_term = f"%{domain_or_extension}%"
                log_name = domain_or_extension
            
            cursor.execute(query, (search_term,))
            results = cursor.fetchall()
            
            external_accounts = []
            for row in results:
                if 'id' in row:
                    del row['id']
                if 'date' in row:
                    del row['date']
                external_accounts.append(row)
            
            if external_accounts:
                self.log(f"🌐 {log_name}: {len(external_accounts)} kayıt bulundu")
            else:
                self.log(f"⚠️ {log_name}: Kayıt bulunamadı")
            
            return external_accounts
            
        except Error as e:
            self.log(f"❌ {domain_or_extension} sorgu hatası: {e}")
            return []
    
    def fetch_all_data(self):
        """Tüm kategoriler için veri çek ve FETCHED_ACCOUNTS tablosuna ekle"""
        self.log("🚀 Veri çekme ve FETCHED_ACCOUNTS tablosuna ekleme işlemi başlıyor...")
        
        total_items = len(ALL_DOMAINS) + len(DOMAIN_EXTENSIONS)
        self.log(f"🎯 Hedef: {len(ALL_DOMAINS)} domain + {len(DOMAIN_EXTENSIONS)} uzantı = {total_items} adet")
        
        current_item = 0
        
        for category, domains in TARGET_DOMAINS.items():
            if category == "turkish_extensions":
                continue
                
            self.log(f"\n📂 KATEGORİ: {category.upper()} ({len(domains)} domain)")
            self.log("-" * 50)
            
            category_accounts = []
            for domain in domains:
                current_item += 1
                self.log(f"📍 [{current_item}/{total_items}] {domain} işleniyor...")
                
                external_accounts = self.fetch_external_data(domain)
                category_accounts.extend(external_accounts)
                self.stats['total_found'] += len(external_accounts)
            
            if category_accounts:
                added_count = self.process_category_data(category_accounts, category)
                self.stats['by_category'][category] = added_count
                self.log(f"📊 {category} kategorisi: {added_count} kayıt eklendi")
            else:
                self.stats['by_category'][category] = 0
        
        self.log(f"\n📂 KATEGORİ: TÜRK UZANTILARI ({len(DOMAIN_EXTENSIONS)} uzantı)")
        self.log("-" * 50)
        
        extension_accounts = []
        for extension in DOMAIN_EXTENSIONS:
            current_item += 1
            self.log(f"📍 [{current_item}/{total_items}] {extension} uzantısı işleniyor...")
            
            ext_accounts = self.fetch_external_data(extension, is_extension=True)
            extension_accounts.extend(ext_accounts)
            self.stats['total_found'] += len(ext_accounts)
        
        if extension_accounts:
            added_count = self.process_category_data(extension_accounts, 'turkish_extensions')
            self.stats['by_category']['turkish_extensions'] = added_count
            self.log(f"📊 Türk uzantıları: {added_count} kayıt eklendi")
        else:
            self.stats['by_category']['turkish_extensions'] = 0
        
        self.stats['total_added'] = sum(self.stats['by_category'].values())
        self.stats['total_skipped'] = self.stats['total_found'] - self.stats['total_added']
        
        self.stats['end_time'] = datetime.now()
        self.log(f"\n🎉 Tüm veriler FETCHED_ACCOUNTS tablosuna eklendi!")
        self.log(f"📊 Toplam bulunan: {self.stats['total_found']} kayıt")
        self.log(f"✅ Toplam eklenen: {self.stats['total_added']} kayıt")
        self.log(f"⚠️ Zaten var olan: {self.stats['total_skipped']} kayıt")
    
    def process_category_data(self, accounts, category):
        """Kategori verilerini işle ve veritabanına ekle"""
        if not accounts:
            return 0
        
        self.log(f"💾 {category} kategorisinden {len(accounts)} kayıt ekleniyor...")
        
        batch_size = 1000
        total_added = 0
        
        for i in range(0, len(accounts), batch_size):
            batch = accounts[i:i + batch_size]
            
            self.log(f"📦 {category} Batch {i//batch_size + 1}: {len(batch)} kayıt işleniyor...")
            
            added_count = self.bulk_insert_accounts(batch, category)
            total_added += added_count
            
            self.log(f"✅ {category} Batch {i//batch_size + 1}: {added_count} yeni kayıt eklendi")
        
        return total_added
    
    def print_summary(self):
        """Özet bilgileri yazdır"""
        if not self.stats['end_time']:
            return
            
        duration = self.stats['end_time'] - self.stats['start_time']
        
        print("\n" + "="*80)
        print("📊 VERİ ÇEKME VE EKLEME ÖZETİ")
        print("="*80)
        print(f"🕒 Başlangıç: {self.stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🕒 Bitiş: {self.stats['end_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⏱️ Süre: {duration}")
        print(f"🎯 Taranan domain: {len(ALL_DOMAINS)}")
        print(f"🎯 Taranan uzantı: {len(DOMAIN_EXTENSIONS)}")
        print(f"📈 Bulunan toplam kayıt: {self.stats['total_found']}")
        print(f"✅ Veritabanına eklenen: {self.stats['total_added']}")
        print(f"⚠️ Zaten var olan (atlandı): {self.stats['total_skipped']}")
        print(f"📊 Başarı oranı: {(self.stats['total_added']/self.stats['total_found']*100 if self.stats['total_found'] > 0 else 0):.1f}%")
        print()
        
        print("📋 Kategori Bazında Sonuçlar:")
        print("-" * 50)
        for category, count in self.stats['by_category'].items():
            icon = "🏦" if category == "banks" else "🏛️" if category == "government" else "🎓" if category == "universities" else "🌐" if category == "turkish_extensions" else "🔝"
            print(f"{icon} {category.replace('_', ' ').title():<25} : {count:>8} kayıt")
        
        print(f"\n💾 Tüm veriler {datetime.now().strftime('%Y-%m-%d')} tarihiyle FETCHED_ACCOUNTS tablosuna kaydedildi!")
        print("="*80)
    
    def get_total_stats(self):
        """Genel istatistikler"""
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            cursor.execute("SELECT COUNT(*) as total FROM accs")
            total_accs = cursor.fetchone()['total']
            
            cursor.execute("SELECT COUNT(*) as total FROM fetched_accounts")
            total_fetched = cursor.fetchone()['total']
            
            self.log(f"📊 Ana veritabanı (accs): {total_accs} kayıt")
            self.log(f"📊 Fetched accounts: {total_fetched} kayıt")
                
        except Error as e:
            self.log(f"❌ İstatistik hatası: {e}")
    
    def run(self):
        """Ana çalıştırma fonksiyonu"""
        print("💾 VERİ TOPLAMA VE FETCHED_ACCOUNTS TABLOSUNA EKLEME")
        print("="*55)
        print("🎯 ACCS tablosundan veri çeker")
        print("📅 FETCHED_ACCOUNTS tablosuna ekler")
        print("🔄 Kategori ve tarih bilgisiyle saklar")
        print("="*55)
        
        if not self.connect_db():
            return False
        
        if not self.test_table():
            self.disconnect_db()
            return False
        
        self.get_total_stats()
        
        print(f"\n⚠️ Bu işlem toplam {len(ALL_DOMAINS) + len(DOMAIN_EXTENSIONS)} hedefi tarayacak")
        print("📊 Bulunan veriler FETCHED_ACCOUNTS tablosuna eklenecek")
        print("🗑️ Mevcut fetched_accounts verileri silinecek")
        
        confirm = input("\n🤔 Devam etmek istiyor musunuz? (y/N): ").lower().strip()
        
        if confirm not in ['y', 'yes', 'evet', 'e']:
            self.log("❌ İşlem kullanıcı tarafından iptal edildi")
            self.disconnect_db()
            return False
        
        print("\n" + "="*55)
        
        if not self.clear_fetched_accounts_table():
            self.log("❌ Tablo temizleme başarısız, işlem durduruldu")
            self.disconnect_db()
            return False
        
        self.fetch_all_data()
        
        self.print_summary()
        
        self.disconnect_db()
        return True

def main():
    """Ana fonksiyon"""
    try:
        fetcher = DataFetcher()
        fetcher.run()
        
    except KeyboardInterrupt:
        print("\n\n⚠️ İşlem kullanıcı tarafından durduruldu!")
        
    except Exception as e:
        print(f"\n❌ Beklenmeyen hata: {e}")

if __name__ == "__main__":
    main()