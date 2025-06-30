import subprocess
import datetime
import sys
import os
import re
import smtplib
from email.message import EmailMessage
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

class WPScanTurkishPDFReporter:
    def __init__(self):
        # SMTP Ayarları - Yandex
        self.SMTP_SERVER = "smtp.yandex.com"
        self.SMTP_PORT = 465
        
        # E-posta bilgileri
        self.EMAIL_ADRESI = "taha@szutestteknoloji.com.tr"
        self.EMAIL_SIFRE = "HgkXr7+fwA"
        self.ALICI = "taha@szutestteknoloji.com.tr"
        
        # Tarih ve dosya bilgileri
        self.TARIH = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        self.PDF_DOSYASI = f"WPScan_Rapor_{self.TARIH}.pdf"
        
        # Tarama sonuçları
        self.tarama_sonucu = ""
        self.tarama_durumu = "basarisiz"
        self.tarama_istatistikleri = {}
        
        # Türkçe font yükle
        self.setup_turkish_fonts()
    
    def setup_turkish_fonts(self):
        """Türkçe karakter desteği için fontları ayarla"""
        try:
            # Sistem fontlarını dene
            font_paths = [
                # Linux
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
                '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
                # macOS
                '/System/Library/Fonts/Arial.ttf',
                '/System/Library/Fonts/Arial Bold.ttf',
                # Windows
                'C:\\Windows\\Fonts\\arial.ttf',
                'C:\\Windows\\Fonts\\arialbd.ttf',
            ]
            
            normal_font_loaded = False
            bold_font_loaded = False
            
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        if 'Bold' in font_path or 'bold' in font_path.lower() or 'bd' in font_path:
                            pdfmetrics.registerFont(TTFont('TurkishFont-Bold', font_path))
                            bold_font_loaded = True
                            print(f"✅ Kalın font yüklendi: {font_path}")
                        else:
                            pdfmetrics.registerFont(TTFont('TurkishFont', font_path))
                            normal_font_loaded = True
                            print(f"✅ Normal font yüklendi: {font_path}")
                    except Exception as e:
                        print(f"⚠️ Font yükleme hatası ({font_path}): {e}")
                        continue
                
                if normal_font_loaded and bold_font_loaded:
                    break
            
            if not normal_font_loaded or not bold_font_loaded:
                print("⚠️ Bazı fontlar yüklenemedi, varsayılan fontlar kullanılacak")
                
        except Exception as e:
            print(f"⚠️ Font sistemi hatası: {e}")
    
    def wpscan_calistir(self, hedef_url, ek_parametreler=""):
        """WPScan taramasını çalıştır"""
        print(f"🔍 WPScan taraması başlatılıyor...")
        print(f"🎯 Hedef: {hedef_url}")
        print(f"📅 Tarih: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}")
        print("-" * 50)
        
        try:
            # WPScan komutunu hazırla
            komut = f"wpscan --url {hedef_url} {ek_parametreler}"
            print(f"💻 Komut: {komut}")
            
            # Taramayı çalıştır
            sonuc = subprocess.run(
                komut.split(),
                capture_output=True,
                text=True,
                timeout=600  # 10 dakika timeout
            )
            
            # Sonuçları kaydet
            self.tarama_sonucu = sonuc.stdout
            if sonuc.stderr:
                self.tarama_sonucu += "\n\n--- HATALAR ---\n" + sonuc.stderr
            
            # İstatistikleri çıkar
            self.istatistikleri_cikart()
            
            if sonuc.returncode == 0:
                self.tarama_durumu = "basarili"
                print("✅ Tarama başarıyla tamamlandı!")
            else:
                self.tarama_durumu = "hatali"
                print(f"⚠️ Tarama tamamlandı ama hatalar var (kod: {sonuc.returncode})")
            
            return True
            
        except subprocess.TimeoutExpired:
            self.tarama_sonucu = "❌ Tarama zaman aşımına uğradı (10 dakika)"
            self.tarama_durumu = "zaman_asimi"
            print("⏰ Tarama zaman aşımına uğradı!")
            return False
            
        except FileNotFoundError:
            self.tarama_sonucu = "❌ WPScan bulunamadı! Lütfen WPScan'i kurun."
            self.tarama_durumu = "wpscan_yok"
            print("❌ WPScan bulunamadı!")
            print("💡 Kurulum: gem install wpscan")
            return False
            
        except Exception as e:
            self.tarama_sonucu = f"❌ Beklenmeyen hata: {str(e)}"
            self.tarama_durumu = "hata"
            print(f"❌ Hata: {e}")
            return False
    
    def istatistikleri_cikart(self):
        """Tarama sonuçlarından istatistikleri çıkar"""
        if not self.tarama_sonucu:
            return
        
        # WordPress versiyonu
        wp_version = re.search(r'WordPress version ([\d.]+)', self.tarama_sonucu)
        self.tarama_istatistikleri['wp_version'] = wp_version.group(1) if wp_version else 'Tespit edilemedi'
        
        # Tema bilgisi
        theme_match = re.search(r'WordPress theme in use: (\w+)', self.tarama_sonucu)
        self.tarama_istatistikleri['theme'] = theme_match.group(1) if theme_match else 'Tespit edilemedi'
        
        # Plugin sayısı
        plugin_sayisi = len(re.findall(r'\[32m\[\+\]\[0m [a-z0-9-]+\n \| Location:', self.tarama_sonucu))
        self.tarama_istatistikleri['plugin_count'] = plugin_sayisi
        
        # Güvenlik uyarıları
        warning_sayisi = self.tarama_sonucu.count('[33m[!][0m')
        self.tarama_istatistikleri['warnings'] = warning_sayisi
        
        # Kullanıcı sayısı
        user_sayisi = len(re.findall(r'\[32m\[\+\]\[0m [A-Za-z ]+\n \| Found By: Rss Generator', self.tarama_sonucu))
        self.tarama_istatistikleri['users'] = user_sayisi
        
        # Tarama istatistikleri
        requests_match = re.search(r'Requests Done: (\d+)', self.tarama_sonucu)
        self.tarama_istatistikleri['requests'] = requests_match.group(1) if requests_match else '0'
        
        elapsed_match = re.search(r'Elapsed time: ([\d:]+)', self.tarama_sonucu)
        self.tarama_istatistikleri['elapsed_time'] = elapsed_match.group(1) if elapsed_match else '00:00:00'
    
    def get_safe_font(self, bold=False):
        """Güvenli font döndür"""
        try:
            if bold:
                # Önce özel fontları dene
                if 'TurkishFont-Bold' in pdfmetrics.getRegisteredFontNames():
                    return 'TurkishFont-Bold'
                return 'Helvetica-Bold'
            else:
                if 'TurkishFont' in pdfmetrics.getRegisteredFontNames():
                    return 'TurkishFont'
                return 'Helvetica'
        except:
            return 'Helvetica-Bold' if bold else 'Helvetica'
    
    def pdf_rapor_olustur(self, hedef_url):
        """Profesyonel PDF raporu oluştur"""
        try:
            print(f"📄 PDF raporu oluşturuluyor...")
            
            # PDF dokümanını oluştur
            doc = SimpleDocTemplate(
                self.PDF_DOSYASI,
                pagesize=A4,
                rightMargin=40,
                leftMargin=40,
                topMargin=40,
                bottomMargin=40
            )
            
            # Stil tanımlamaları
            styles = getSampleStyleSheet()
            
            # Özel stiller (Türkçe karakter desteği)
            title_style = ParagraphStyle(
                'TurkishTitle',
                parent=styles['Heading1'],
                fontSize=28,
                spaceAfter=30,
                textColor=colors.darkblue,
                alignment=TA_CENTER,
                fontName=self.get_safe_font(bold=True),
                leading=35
            )
            
            header_style = ParagraphStyle(
                'TurkishHeader',
                parent=styles['Heading2'],
                fontSize=18,
                spaceAfter=15,
                spaceBefore=20,
                textColor=colors.darkred,
                fontName=self.get_safe_font(bold=True),
                leading=22
            )
            
            subheader_style = ParagraphStyle(
                'TurkishSubHeader',
                parent=styles['Heading3'],
                fontSize=14,
                spaceAfter=10,
                spaceBefore=15,
                textColor=colors.darkgreen,
                fontName=self.get_safe_font(bold=True),
                leading=18
            )
            
            normal_style = ParagraphStyle(
                'TurkishNormal',
                parent=styles['Normal'],
                fontSize=11,
                spaceAfter=8,
                alignment=TA_JUSTIFY,
                fontName=self.get_safe_font(),
                leading=14
            )
            
            bullet_style = ParagraphStyle(
                'TurkishBullet',
                parent=styles['Normal'],
                fontSize=11,
                spaceAfter=6,
                leftIndent=20,
                fontName=self.get_safe_font(),
                leading=14
            )
            
            # Rapor içeriğini hazırla
            story = []
            
            # Başlık sayfası
            story.append(Spacer(1, 30))
            
            # Ana başlık
            story.append(Paragraph("WordPress Guvenlik Tarama Raporu", title_style))
            story.append(Spacer(1, 20))
            
            # Şirket bilgisi - Basit format
            company_info = f"""SZU Test Teknoloji
WordPress Guvenlik Analiz Sistemi

Rapor Tarihi: {datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")}
Hedef Website: {hedef_url}
Rapor ID: WPS-{self.TARIH}"""
            
            company_style = ParagraphStyle(
                'Company',
                parent=normal_style,
                fontSize=14,
                alignment=TA_CENTER,
                textColor=colors.darkblue,
                fontName=self.get_safe_font(bold=True)
            )
            
            story.append(Paragraph(company_info, company_style))
            story.append(Spacer(1, 40))
            
            # Özet kutu
            ozet_data = [
                ['TARAMA OZETI', ''],
                ['Tarama Durumu', self.tarama_durumu.upper()],
                ['WordPress Surumu', self.tarama_istatistikleri.get('wp_version', 'Bilinmiyor')],
                ['Guvenlik Uyarisi', f"{self.tarama_istatistikleri.get('warnings', 0)} adet"],
                ['Tespit Edilen Plugin', f"{self.tarama_istatistikleri.get('plugin_count', 0)} adet"],
                ['Tespit Edilen Kullanici', f"{self.tarama_istatistikleri.get('users', 0)} adet"],
                ['Tarama Suresi', self.tarama_istatistikleri.get('elapsed_time', 'Bilinmiyor')]
            ]
            
            ozet_table = Table(ozet_data, colWidths=[3*inch, 3*inch])
            ozet_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), self.get_safe_font(bold=True)),
                ('FONTSIZE', (0, 0), (-1, 0), 14),
                ('FONTNAME', (0, 1), (-1, -1), self.get_safe_font()),
                ('FONTSIZE', (0, 1), (-1, -1), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.lightgrey, colors.white]),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('SPAN', (0, 0), (1, 0)),
            ]))
            
            story.append(ozet_table)
            story.append(PageBreak())
            
            # Güvenlik Durumu Analizi
            story.append(Paragraph("Guvenlik Durumu Analizi", header_style))
            
            warning_count = self.tarama_istatistikleri.get('warnings', 0)
            
            # Güvenlik durumu stilini tanımla
            if warning_count > 0:
                guvenlik_style = ParagraphStyle(
                    'GuvenlikUyari',
                    parent=normal_style,
                    fontSize=12,
                    textColor=colors.red,
                    fontName=self.get_safe_font(bold=True)
                )
                guvenlik_text = f"DIKKAT: {warning_count} guvenlik uyarisi tespit edilmistir!"
                story.append(Paragraph(guvenlik_text, guvenlik_style))
                
                aciklama_text = "Sitenizde potansiyel guvenlik riskleri bulunmaktadir. Bu riskler kotu niyetli kisiler tarafindan istismar edilebilir ve sitenizin guvenligini tehlikeye atabilir. Acil mudahale gerekebilir."
                story.append(Paragraph(aciklama_text, normal_style))
            else:
                guvenlik_style = ParagraphStyle(
                    'GuvenlikIyi',
                    parent=normal_style,
                    fontSize=12,
                    textColor=colors.green,
                    fontName=self.get_safe_font(bold=True)
                )
                guvenlik_text = "Guvenlik Durumu Iyi Gorunuyor"
                story.append(Paragraph(guvenlik_text, guvenlik_style))
                
                aciklama_text = "Kritik guvenlik aciklari tespit edilmemistir. Ancak guvenlik surekli bir surec oldugu icin duzenli kontroller ve guncellemeler yapilmasi onerilir."
                story.append(Paragraph(aciklama_text, normal_style))
            story.append(Spacer(1, 20))
            
            # Tespit Edilen Sorunlar
            story.append(Paragraph("Tespit Edilen Güvenlik Sorunları", subheader_style))
            
            sorunlar = self.sorunlari_analiz_et()
            for i, sorun in enumerate(sorunlar, 1):
                story.append(Paragraph(f"{i}. {sorun}", bullet_style))
            
            story.append(Spacer(1, 20))
            
            # Detaylı Güvenlik Önerileri
            story.append(Paragraph("Detaylı Güvenlik Önerileri", header_style))
            
            # Acil Öncelikli Öneriler
            story.append(Paragraph("Acil Öncelikli İşlemler:", subheader_style))
            
            acil_oneriler = [
                "WordPress çekirdeği ve tüm eklentileri en son sürümlerine güncelleyin",
                "Tüm kullanıcı hesapları için güçlü ve benzersiz şifreler belirleyin",
                "Yönetici hesabı kullanıcı adını 'admin' dışında bir isim yapın",
                "İki faktörlü kimlik doğrulama (2FA) sistemini aktif hale getirin",
                "Güvenlik eklentisi kurun (Wordfence, Sucuri Security vb.)",
                "SSL sertifikası aktif ise HTTPS yönlendirmesi yapın"
            ]
            
            for i, oneri in enumerate(acil_oneriler, 1):
                story.append(Paragraph(f"{i}. {oneri}", bullet_style))
            
            story.append(Spacer(1, 15))
            
            # Orta Öncelikli Öneriler
            story.append(Paragraph("Orta Öncelikli İyileştirmeler:", subheader_style))
            
            orta_oneriler = [
                "XML-RPC protokolünü kullanmıyorsanız devre dışı bırakın",
                "Giriş denemelerini sınırlandıran bir sistem kurun",
                "wp-config.php dosyasına ek güvenlik anahtarları ekleyin",
                "Veritabanı tablo önekini 'wp_' dışında bir değer yapın",
                "Dosya izinlerini doğru şekilde ayarlayın (755/644)",
                "Kullanılmayan temalar ve eklentileri tamamen silin"
            ]
            
            for i, oneri in enumerate(orta_oneriler, 1):
                story.append(Paragraph(f"{i}. {oneri}", bullet_style))
            
            story.append(Spacer(1, 15))
            
            # Uzun Vadeli Öneriler
            story.append(Paragraph("Uzun Vadeli Güvenlik Stratejileri:", subheader_style))
            
            uzun_vadeli = [
                "Düzenli otomatik yedekleme sistemi kurun ve yedekleri test edin",
                "Web sitesi dosyalarının bütünlüğünü kontrol eden sistemler kurun",
                "Güvenlik günlüklerini düzenli olarak inceleyin",
                "wp-admin dizinine IP tabanlı erişim kısıtlaması uygulayın",
                "Content Security Policy (CSP) başlıklarını yapılandırın",
                "Düzenli güvenlik taramaları ve penetrasyon testleri yaptırın"
            ]
            
            for i, oneri in enumerate(uzun_vadeli, 1):
                story.append(Paragraph(f"{i}. {oneri}", bullet_style))
            
            story.append(PageBreak())
            
            # Teknik Detaylar
            story.append(Paragraph("Teknik Tarama Detaylari", header_style))
            
            teknik_bilgi = f"""Tarama Parametreleri:
• Hedef URL: {hedef_url}
• Tarama Turu: Kapsamli Guvenlik Analizi
• Kullanilan Arac: WPScan v3.x
• Toplam Istek Sayisi: {self.tarama_istatistikleri.get('requests', 'Bilinmiyor')}
• Tarama Suresi: {self.tarama_istatistikleri.get('elapsed_time', 'Bilinmiyor')}

Kontrol Edilen Alanlar:
• WordPress cekirdek dosyalari ve surum bilgisi
• Yuklu eklentiler ve guvenlik durumlari
• Aktif tema ve yapilandirma bilgileri
• Kullanici hesaplari ve yetki seviyeleri
• Dosya izinleri ve yapilandirma hatalari
• Bilinen guvenlik aciklarinin varligi"""
            
            story.append(Paragraph(teknik_bilgi, normal_style))
            story.append(Spacer(1, 20))
            
            # Acil Durum Eylem Planı
            story.append(Paragraph("Acil Durum Eylem Plani", subheader_style))
            
            acil_durum = """Eger siteniz saldiriya ugradığini dusunuyorsaniz:

1. Hemen tum sifreleri degistirin: WordPress admin, FTP, hosting panel
2. Guvenlik eklentisi kurun ve tam sistem taramasi yapin
3. Son temiz yedegionizi belirleyin ve gerekirse geri yukleyin
4. Hosting saglayicinizla iletisime gecin ve durumu bildirin
5. Kotu amacli dosyalari temizleyin ve sistem butunlugunu kontrol edin
6. Google Search Console'da guvenlik sorunlarini kontrol edin"""
            
            story.append(Paragraph(acil_durum, normal_style))
            story.append(Spacer(1, 30))
            
            # Footer bilgileri - Basit format
            footer_style = ParagraphStyle(
                'Footer',
                parent=normal_style,
                fontSize=10,
                textColor=colors.grey,
                alignment=TA_CENTER
            )
            
            footer_bilgi = f"""
SZU Test Teknoloji - WordPress Guvenlik Uzmanlari
Web: https://szutestteknoloji.com.tr | E-posta: info@szutestteknoloji.com.tr
Bu rapor {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')} tarihinde otomatik olarak olusturulmustur.
Rapor ID: WPS-{self.TARIH} | WordPress Guvenlik Tarama Sistemi v2.0"""
            
            story.append(Paragraph(footer_bilgi, footer_style))
            
            # PDF'i oluştur
            doc.build(story)
            print(f"✅ PDF raporu başarıyla oluşturuldu: {self.PDF_DOSYASI}")
            return True
            
        except Exception as e:
            print(f"❌ PDF oluşturulurken hata: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def sorunlari_analiz_et(self):
        """Tarama sonuçlarından sorunları analiz et ve Türkçe raporla"""
        sorunlar = []
        
        if not self.tarama_sonucu:
            return ["Tarama sonucu analiz edilemedi"]
        
        # XML-RPC kontrolü
        if "XML-RPC seems to be enabled" in self.tarama_sonucu:
            sorunlar.append("XML-RPC protokolü etkin durumda - DDoS ve brute force saldırı riski yüksek")
        
        # WP-Cron kontrolü
        if "WP-Cron seems to be enabled" in self.tarama_sonucu:
            sorunlar.append("External WP-Cron etkin - Site performansını olumsuz etkileyebilir")
        
        # Güncel olmayan eklentiler
        if "The version is out of date" in self.tarama_sonucu:
            eski_eklentiler = re.findall(r'(\w+(?:-\w+)*)\n.*out of date', self.tarama_sonucu)
            for eklenti in eski_eklentiler[:5]:  # İlk 5 tanesini göster
                sorunlar.append(f"'{eklenti}' eklentisi güncel değil - Güvenlik açığı riski")
        
        # Kullanıcı bilgileri açığa çıkmış
        if self.tarama_istatistikleri.get('users', 0) > 0:
            sorunlar.append("Kullanıcı adları herkese açık - Brute force saldırı riski yüksek")
        
        # robots.txt bulundu
        if "robots.txt found" in self.tarama_sonucu:
            sorunlar.append("robots.txt dosyası mevcut - Hassas dizin bilgileri açığa çıkmış olabilir")
        
        # wp-config.php backup dosyası
        if "wp-config.php backup" in self.tarama_sonucu.lower():
            sorunlar.append("wp-config.php yedek dosyası tespit edildi - Kritik bilgi sızıntısı riski")
        
        # Directory listing
        if "directory listing" in self.tarama_sonucu.lower():
            sorunlar.append("Dizin listeleme etkin - Dosya yapısı herkese açık")
        
        # Debug log dosyası
        if "debug.log" in self.tarama_sonucu:
            sorunlar.append("Debug log dosyası herkese açık - Sistem bilgileri sızıntısı")
        
        if not sorunlar:
            sorunlar.append("Önemli güvenlik sorunu tespit edilmedi - Düzenli kontroller önerilir")
        
        return sorunlar
    
    def email_mesaji_olustur(self, hedef_url):
        """E-posta mesajını oluştur"""
        # Durum emojisi
        durum_emoji = {
            "basarili": "✅",
            "hatali": "⚠️", 
            "zaman_asimi": "⏰",
            "wpscan_yok": "❌",
            "hata": "❌",
            "basarisiz": "❌"
        }
        
        emoji = durum_emoji.get(self.tarama_durumu, "❓")
        warning_count = self.tarama_istatistikleri.get('warnings', 0)
        
        mesaj = EmailMessage()
        mesaj["From"] = self.EMAIL_ADRESI
        mesaj["To"] = self.ALICI
        mesaj["Subject"] = f"{emoji} WordPress Guvenlik Raporu - {hedef_url} - {self.TARIH}"
        
        # E-posta içeriği
        icerik = f"""
🛡️ WordPress Guvenlik Tarama Raporu
{'='*60}

📊 Tarama Bilgileri:
• Tarih: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
• Hedef Site: {hedef_url}
• Tarama Durumu: {self.tarama_durumu.upper()} {emoji}

📈 Sonuc Ozeti:
• WordPress Surumu: {self.tarama_istatistikleri.get('wp_version', 'Tespit edilemedi')}
• Guvenlik Uyarisi: {warning_count} adet
• Plugin Sayisi: {self.tarama_istatistikleri.get('plugin_count', 0)}
• Kullanici Sayisi: {self.tarama_istatistikleri.get('users', 0)}
• Tarama Suresi: {self.tarama_istatistikleri.get('elapsed_time', 'N/A')}

🎯 Guvenlik Durumu:
{'🚨 DIKKAT! Guvenlik uyarilari var!' if warning_count > 0 else '✅ Kritik sorun yok'}

📎 EKLER:
✅ Detayli PDF Raporu (Turkce Karakter Destekli)
✅ Profesyonel Format

⚠️ ONEMLI NOTLAR:
• PDF raporu tam analiz ve oneriler icerir
• Turkce karakterler duzgun goruntulenir
• Renkli ve grafik tabanli sunum
• Yazdirılabilir format

🔧 HIZLI COZUMLER:
1. WordPress'i guncelleyin
2. Eklentileri guncelleyin
3. Guvenlik eklentisi kurun
4. Guclu sifreler kullanin
5. XML-RPC'yi devre disi birakin

🤖 Bu rapor otomatik olarak WPScan sistemi tarafindan olusturulmustur.

---
SZU Test Teknoloji
📞 Destek: support@szutestteknoloji.com.tr
🌐 Web: https://szutestteknoloji.com.tr
"""
        
        mesaj.set_content(icerik)
        return mesaj
    
    def email_gonder(self, hedef_url):
        """E-postayı gönder"""
        try:
            print(f"📤 E-posta raporu hazirlanıyor...")
            
            # E-posta mesajını oluştur
            mesaj = self.email_mesaji_olustur(hedef_url)
            
            # PDF dosyasını e-postaya ekle
            if os.path.exists(self.PDF_DOSYASI):
                print(f"📎 PDF raporu ekleniyor: {self.PDF_DOSYASI}")
                try:
                    with open(self.PDF_DOSYASI, "rb") as file:
                        pdf_icerik = file.read()
                        mesaj.add_attachment(
                            pdf_icerik,
                            maintype="application",
                            subtype="pdf",
                            filename=f"WPScan_Guvenlik_Raporu_{hedef_url.replace('https://','').replace('http://','').replace('/','_')}_{self.TARIH}.pdf"
                        )
                    print("✅ PDF raporu basariyla eklendi!")
                except Exception as e:
                    print(f"⚠️ PDF eklenirken hata: {e}")
            
            print(f"📧 E-posta gonderiliyor...")
            print(f"   Kimden: {self.EMAIL_ADRESI}")
            print(f"   Kime: {self.ALICI}")
            
            with smtplib.SMTP_SSL(self.SMTP_SERVER, self.SMTP_PORT) as smtp:
                smtp.login(self.EMAIL_ADRESI, self.EMAIL_SIFRE)
                smtp.send_message(mesaj)
            
            print("✅ E-posta basariyla gonderildi!")
            print(f"📄 PDF Raporu: {self.PDF_DOSYASI}")
            return True
            
        except Exception as e:
            print(f"❌ E-posta gonderiminde hata: {e}")
            return False
    
    def temizlik_yap(self, dosya_sil=True):
        """Geçici dosyaları temizle"""
        try:
            if dosya_sil:
                if os.path.exists(self.PDF_DOSYASI):
                    os.remove(self.PDF_DOSYASI)
                    print(f"🗑️ PDF dosyasi temizlendi")
            else:
                print(f"💾 PDF dosyasi saklandi: {self.PDF_DOSYASI}")
        except:
            pass

def main():
    """Ana fonksiyon"""
    print("🚀 WordPress Güvenlik Tarayıcısı - PDF Rapor Sistemi")
    print("=" * 60)
    
    # ReportLab kontrolü
    try:
        from reportlab.lib.pagesizes import A4
        print("✅ ReportLab kütüphanesi yüklü ve hazır")
    except ImportError:
        print("❌ ReportLab kütüphanesi bulunamadı!")
        print("💡 Kurulum komutu: pip install reportlab")
        print("💡 Ubuntu/Debian: sudo apt install python3-reportlab")
        sys.exit(1)
    
    # Hedef URL'i al
    if len(sys.argv) > 1:
        hedef_url = sys.argv[1]
    else:
        hedef_url = input("🎯 Taranacak WordPress sitesinin URL'ini girin: ").strip()
    
    if not hedef_url:
        print("❌ URL girilmedi! Program sonlandırılıyor.")
        sys.exit(1)
    
    # URL formatını kontrol et ve düzelt
    if not hedef_url.startswith(('http://', 'https://')):
        hedef_url = 'https://' + hedef_url
        print(f"🔧 URL düzeltildi: {hedef_url}")
    
    print(f"🎯 Hedef: {hedef_url}")
    print(f"📅 Tarih: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("-" * 60)
    
    # Tarayıcıyı başlat
    tarayici = WPScanTurkishPDFReporter()
    
    try:
        # 1. WPScan taramasını çalıştır
        print("🔍 1. Adım: WordPress güvenlik taraması başlatılıyor...")
        tarama_basarili = tarayici.wpscan_calistir(hedef_url, "--enumerate p,t,u")
        
        # 2. PDF raporu oluştur
        print("📄 2. Adım: PDF raporu oluşturuluyor...")
        pdf_basarili = tarayici.pdf_rapor_olustur(hedef_url)
        
        # 3. E-posta gönder
        print("📧 3. Adım: E-posta gonderiliyor...")
        email_basarili = tarayici.email_gonder(hedef_url)
        
        # 4. Temizlik yap
        tarayici.temizlik_yap(dosya_sil=True)
        
        # Sonuç bildirimi
        if pdf_basarili and email_basarili:
            print("\n" + "="*60)
            print("🎉 Islem basariyla tamamlandi!")
            print("📄 PDF Raporu olusturuldu ve e-posta ile gonderildi")
            print("✅ Turkce karakter destegi aktif")
            print("✅ Profesyonel format uygulandi")
            print("="*60)
        elif pdf_basarili:
            print("\n" + "="*60)
            print("⚠️ PDF raporu olusturuldu ama e-posta gonderilemedi")
            print(f"📄 PDF Raporu: {tarayici.PDF_DOSYASI}")
            print("="*60)
        else:
            print("\n⚠️ PDF raporu olusturulamadi!")
            
    except KeyboardInterrupt:
        print("\n⏹️ İşlem kullanıcı tarafından durduruldu.")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Beklenmeyen hata oluştu: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()