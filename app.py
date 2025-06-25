from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
import mysql.connector
from mysql.connector import Error
import logging
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
import requests
import os


app = Flask(__name__)

# Session için secret key - PRODUCTION'da değiştirin!
app.secret_key = secrets.token_hex(32)
app.permanent_session_lifetime = timedelta(hours=24)  # 24 saat session

# Loglama ayarları
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Veritabanı bağlantı bilgileri
DB_CONFIG = {
    'host': '192.168.70.70',
    'database': 'lapsusacc',
    'user': 'root',
    'password': 'daaqwWdas21as',
    'charset': 'utf8mb4',
    'port': 3306
}

# API Configuration - GÜVENLİ BACKEND'TE SAKLANIR
API_CONFIG = {
    'base_url': os.getenv('API_BASE_URL', 'http://192.168.70.71:5000'),
    'api_key': os.getenv('API_KEY', 'demo_key_123'),
    'timeout': 30,
    'max_retries': 3
}
# Admin kullanıcı bilgileri - PRODUCTION'da veritabanından alın!
ADMIN_USERS = {
    'admin': {
        'password_hash': hashlib.sha256('admin123'.encode()).hexdigest(),
        'role': 'admin',
        'name': 'Admin User'
    },
    'lapsus': {
        'password_hash': hashlib.sha256('lapsus2025'.encode()).hexdigest(),
        'role': 'admin', 
        'name': 'Lapsus Admin'
    }
}

# Kategori isimlerini Türkçeye çevirme - GERÇEK KATEGORİLER
CATEGORY_TRANSLATIONS = {
    'government': 'Kamu Kurumları',
    'banks': 'Finansal Kuruluşlar', 
    'popular_turkish': 'Öne Çıkan Türk Siteler',
    'turkish_extensions': 'Türkiye Uzantılı Platformlar',
    'universities': 'Yükseköğretim Kurumları'
}

# Kategori renkleri
CATEGORY_COLORS = {
    'government': '#1e90ff',
    'banks': '#87ceeb',
    'popular_turkish': '#00bfff',
    'turkish_extensions': '#4682b4',
    'universities': '#5f9ea0'
}

# Kategori ikonları
CATEGORY_ICONS = {
    'government': 'building',
    'banks': 'landmark',
    'popular_turkish': 'star',
    'turkish_extensions': 'globe',
    'universities': 'graduation-cap'
}

# Kategori sıralama öncelikleri
CATEGORY_ORDER = ['government', 'banks', 'popular_turkish', 'turkish_extensions', 'universities']

# Login gerekli decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Bu sayfaya erişmek için giriş yapmalısınız.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Admin gerekli decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Bu sayfaya erişmek için giriş yapmalısınız.', 'error')
            return redirect(url_for('login'))
        
        user = ADMIN_USERS.get(session['user_id'])
        if not user or user['role'] != 'admin':
            flash('Bu sayfaya erişim yetkiniz yok.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# API Request Helper - GÜVENLİ API ÇAĞRISI
def make_api_request(endpoint, method='GET', params=None, data=None, retries=0):
    """Güvenli API request helper"""
    try:
        url = f"{API_CONFIG['base_url']}{endpoint}"
        headers = {
            'X-API-Key': API_CONFIG['api_key'],  # Doğru anahtar: api_key
            'Content-Type': 'application/json',
            'User-Agent': 'Lapsus-Dashboard/1.0'
        }
        
        if method == 'GET':
            response = requests.get(url, headers=headers, params=params, timeout=API_CONFIG['timeout'])
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=API_CONFIG['timeout'])
        else:
            raise ValueError(f"Desteklenmeyen HTTP metodu: {method}")
        
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.Timeout:
        logging.error(f"API timeout: {endpoint}")
        if retries < API_CONFIG['max_retries']:
            return make_api_request(endpoint, method, params, data, retries + 1)
        raise Exception("API zaman aşımı - sunucu yanıt vermiyor")
        
    except requests.exceptions.ConnectionError:
        logging.error(f"API bağlantı hatası: {endpoint}")
        raise Exception("API sunucusuna bağlanılamıyor")
        
    except requests.exceptions.HTTPError as e:
        logging.error(f"API HTTP hatası: {e.response.status_code} - {endpoint}")
        if e.response.status_code == 401:
            raise Exception("API yetkilendirme hatası")
        elif e.response.status_code == 429:
            raise Exception("API rate limit aşıldı")
        else:
            raise Exception(f"API sunucu hatası: {e.response.status_code}")
            
    except Exception as e:
        logging.error(f"API genel hatası: {str(e)}")
        if retries < API_CONFIG['max_retries']:
            return make_api_request(endpoint, method, params, data, retries + 1)
        raise
# Kullanıcı doğrulama
def verify_user(username, password):
    user = ADMIN_USERS.get(username)
    if user:
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if password_hash == user['password_hash']:
            return user
    return None

# Veritabanı bağlantısı
def get_db_connection():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            logging.info("Veritabanına başarıyla bağlanıldı.")
            return connection
    except Error as e:
        logging.error(f"Veritabanı bağlantı hatası: {e}")
        return None

# LOGIN ROUTES
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)
        
        if not username or not password:
            flash('Kullanıcı adı ve şifre gereklidir.', 'error')
            return render_template('login.html')
        
        user = verify_user(username, password)
        if user:
            session.permanent = bool(remember)
            session['user_id'] = username
            session['user_name'] = user['name']
            session['user_role'] = user['role']
            session['login_time'] = datetime.now().isoformat()
            
            flash(f'Hoş geldiniz, {user["name"]}!', 'success')
            logging.info(f"Başarılı giriş: {username} - {request.remote_addr}")
            
            # Redirect to next page or dashboard
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Geçersiz kullanıcı adı veya şifre.', 'error')
            logging.warning(f"Başarısız giriş denemesi: {username} - {request.remote_addr}")
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    username = session.get('user_id', 'Bilinmeyen')
    session.clear()
    flash('Başarıyla çıkış yaptınız.', 'info')
    logging.info(f"Çıkış yapıldı: {username}")
    return redirect(url_for('login'))

# SEARCH PAGE ROUTE
@app.route('/search')
@login_required
def search_page():
    """Arama sayfası - güvenli API key olmadan"""
    return render_template('search.html', 
                         user_name=session.get('user_name'),
                         user_role=session.get('user_role'))

# SECURE API PROXY ENDPOINTS - API KEY'İ FRONTEND'E MARUZ BIRAKMAZ

@app.route('/api/proxy/search')
@login_required
def proxy_search():
    """Güvenli arama proxy - API key frontend'de görünmez"""
    try:
        # Frontend'den gelen parametreleri al
        query = request.args.get('q', '').strip()
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 20, type=int)
        domain = request.args.get('domain', '')
        region = request.args.get('region', '')
        source = request.args.get('source', '')
        
        # Doğrulama
        if not query or len(query) < 2:
            return jsonify({
                'success': False,
                'error': 'Arama sorgusu en az 2 karakter olmalıdır'
            }), 400
        
        if limit > 100:
            limit = 100
            
        # API parametrelerini hazırla
        api_params = {
            'q': query,
            'page': page,
            'limit': limit
        }
        
        # Filtreleri ekle
        if domain:
            api_params['domain'] = domain
        if region:
            api_params['region'] = region
        if source:
            api_params['source'] = source
        
        # Güvenli API çağrısı yap
        api_response = make_api_request('/api/search', params=api_params)
        
        # Response'u frontend'e gönder
        return jsonify(api_response)
        
    except Exception as e:
        logging.error(f"Search proxy error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/proxy/accounts')
@login_required
def proxy_accounts():
    """Güvenli hesap listesi proxy"""
    try:
        # Parametreleri al
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 10, type=int)
        domain = request.args.get('domain', '')
        region = request.args.get('region', '')
        source = request.args.get('source', '')
        
        api_params = {
            'page': page,
            'limit': min(limit, 100)  # Maksimum 100
        }
        
        if domain:
            api_params['domain'] = domain
        if region:
            api_params['region'] = region
        if source:
            api_params['source'] = source
        
        api_response = make_api_request('/api/accounts', params=api_params)
        return jsonify(api_response)
        
    except Exception as e:
        logging.error(f"Accounts proxy error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/proxy/account/<int:account_id>')
@login_required
def proxy_single_account(account_id):
    """Tekil hesap bilgisi proxy"""
    try:
        api_response = make_api_request(f'/api/accounts/{account_id}')
        return jsonify(api_response)
        
    except Exception as e:
        logging.error(f"Single account proxy error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/proxy/statistics')
@login_required
def proxy_statistics():
    """İstatistik proxy"""
    try:
        api_response = make_api_request('/api/stats')
        return jsonify(api_response)
        
    except Exception as e:
        logging.error(f"Statistics proxy error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/proxy/health')
@login_required
def proxy_health():
    """Sistem sağlık kontrolü proxy"""
    try:
        api_response = make_api_request('/api/health')
        return jsonify(api_response)
        
    except Exception as e:
        logging.error(f"Health proxy error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# DASHBOARD ROUTES (Login Gerekli)
@app.route('/')
@login_required
def dashboard():
    """Ana dashboard sayfası - sadece gerçek veriyle"""
    connection = None
    chart_data = []
    summary_data = {'labels': [], 'counts': [], 'percentages': [], 'colors': []}
    error = ""
    stats = {
        'total_accounts': 0,
        'unique_domains': 0,
        'categories': [],
        'last_updated': 'Bilinmiyor'
    }

    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            
            # Kategori bazında veri çek
            cursor.execute("SELECT category, COUNT(*) as count FROM fetched_accounts GROUP BY category ORDER BY count DESC")
            categories = cursor.fetchall()
            
            if categories:
                total_count = sum(category['count'] for category in categories)
                
                # Kategori sıralaması ile veri hazırla
                chart_data = []
                category_dict = {cat['category']: cat['count'] for cat in categories}
                
                # Önce tanımlı sıralamadaki kategorileri ekle
                for cat_key in CATEGORY_ORDER:
                    if cat_key in category_dict:
                        count = category_dict[cat_key]
                        percentage = round((count / total_count) * 100, 1)
                        
                        chart_data.append({
                            'category': cat_key,
                            'label': CATEGORY_TRANSLATIONS.get(cat_key, cat_key.title()),
                            'count': count,
                            'percentage': percentage,
                            'color': CATEGORY_COLORS.get(cat_key, '#6B7280'),
                            'icon': CATEGORY_ICONS.get(cat_key, 'folder')
                        })
                
                # Sonra tanımlanmamış kategorileri ekle (varsa)
                for category in categories:
                    cat_key = category['category']
                    if cat_key not in CATEGORY_ORDER:
                        percentage = round((category['count'] / total_count) * 100, 1)
                        chart_data.append({
                            'category': cat_key,
                            'label': CATEGORY_TRANSLATIONS.get(cat_key, cat_key.title()),
                            'count': category['count'],
                            'percentage': percentage,
                            'color': CATEGORY_COLORS.get(cat_key, '#6B7280'),
                            'icon': CATEGORY_ICONS.get(cat_key, 'folder')
                        })
                
                summary_data = {
                    'labels': [item['label'] for item in chart_data],
                    'counts': [item['count'] for item in chart_data],
                    'percentages': [item['percentage'] for item in chart_data],
                    'colors': [item['color'] for item in chart_data]
                }
                
                # Ek istatistikler
                cursor.execute("SELECT COUNT(*) as total FROM fetched_accounts")
                stats['total_accounts'] = cursor.fetchone()['total']
                
                cursor.execute("SELECT COUNT(DISTINCT domain) as unique_domains FROM fetched_accounts")
                stats['unique_domains'] = cursor.fetchone()['unique_domains']
                
                # En son güncelleme tarihi
                cursor.execute("SELECT MAX(fetch_date) as last_update FROM fetched_accounts")
                last_update_result = cursor.fetchone()
                stats['last_updated'] = str(last_update_result['last_update']) if last_update_result['last_update'] else 'Bilinmiyor'
                
                stats['categories'] = chart_data
                
                logging.info(f"Gerçek veritabanından {len(categories)} kategori alındı. Toplam: {total_count}")
                
            else:
                error = "fetched_accounts tablosunda veri bulunamadı! Veri ekleme scriptini çalıştırın."
                logging.warning("fetched_accounts tablosunda veri bulunamadı")
                
            cursor.close()
            connection.close()
            
        else:
            error = "Veritabanına bağlanılamadı! Bağlantı ayarlarını kontrol edin."
            logging.error("Veritabanına bağlanılamadı")
            
    except Error as e:
        error = f"Veri çekme hatası: {str(e)}"
        logging.error(f"Veri çekme hatası: {e}")
        if connection:
            connection.close()

    # Template'e gönderilen tüm değişkenler - INDEX.HTML kullanıyoruz
    return render_template('index.html', 
                         chart_data=chart_data, 
                         summary_data=summary_data, 
                         stats=stats,
                         error=error,
                         user_name=session.get('user_name'),
                         user_role=session.get('user_role'))

@app.route('/index')
@login_required  
def index():
    return redirect(url_for('dashboard'))


# Veritabanı bağlantı test endpoint'i
@app.route('/test-db')
@login_required
def test_db():
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            # fetched_accounts tablosu kontrolü
            cursor.execute("SHOW TABLES LIKE 'fetched_accounts'")
            result = cursor.fetchone()
            if result:
                cursor.execute("SELECT COUNT(*) FROM fetched_accounts")
                count = cursor.fetchone()[0]
                connection.close()
                return f"✅ Veritabanı bağlantısı başarılı! fetched_accounts tablosunda {count} kayıt bulundu."
            else:
                connection.close()
                return "⚠️ Veritabanı bağlantısı başarılı ancak fetched_accounts tablosu bulunamadı!"
        except Error as e:
            connection.close()
            return f"❌ Tablo kontrolü hatası: {e}"
    return "❌ Veritabanı bağlantısı başarısız! Logları kontrol edin."

# API endpoint - gerçek zamanlı veri
@app.route('/api/stats')
@login_required
def api_stats():
    """API endpoint - gerçek zamanlı istatistikler"""
    connection = None
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            
            # Kategori bazında sayım
            cursor.execute("SELECT category, COUNT(*) as count FROM fetched_accounts GROUP BY category ORDER BY count DESC")
            categories = cursor.fetchall()
            
            if categories:
                total_count = sum(category['count'] for category in categories)
                
                # API formatında veri hazırla - kategori sıralaması ile
                stats_data = []
                category_dict = {cat['category']: cat['count'] for cat in categories}
                
                # Önce tanımlı sıralamadaki kategorileri ekle
                for cat_key in CATEGORY_ORDER:
                    if cat_key in category_dict:
                        count = category_dict[cat_key]
                        stats_data.append({
                            'category': cat_key,
                            'label': CATEGORY_TRANSLATIONS.get(cat_key, cat_key.title()),
                            'count': count,
                            'percentage': round((count / total_count) * 100, 1),
                            'color': CATEGORY_COLORS.get(cat_key, '#6B7280'),
                            'icon': CATEGORY_ICONS.get(cat_key, 'folder')
                        })
                
                # Sonra tanımlanmamış kategorileri ekle (varsa)
                for category in categories:
                    cat_key = category['category']
                    if cat_key not in CATEGORY_ORDER:
                        stats_data.append({
                            'category': cat_key,
                            'label': CATEGORY_TRANSLATIONS.get(cat_key, cat_key.title()),
                            'count': category['count'],
                            'percentage': round((category['count'] / total_count) * 100, 1),
                            'color': CATEGORY_COLORS.get(cat_key, '#6B7280'),
                            'icon': CATEGORY_ICONS.get(cat_key, 'folder')
                        })
                
                # Toplam istatistikler
                cursor.execute("SELECT COUNT(*) as total FROM fetched_accounts")
                total_fetched = cursor.fetchone()['total']
                
                cursor.execute("SELECT COUNT(DISTINCT domain) as unique_domains FROM fetched_accounts")
                unique_domains = cursor.fetchone()['unique_domains']
                
                # En son ekleme tarihi
                cursor.execute("SELECT MAX(fetch_date) as last_update FROM fetched_accounts")
                last_update_result = cursor.fetchone()
                last_update = last_update_result['last_update'] if last_update_result['last_update'] else 'Bilinmiyor'
                
                response_data = {
                    'success': True,
                    'total_accounts': total_fetched,
                    'unique_domains': unique_domains,
                    'categories': stats_data,
                    'last_updated': str(last_update),
                    'user': session.get('user_name', 'Kullanıcı')
                }
                
                cursor.close()
                connection.close()
                return jsonify(response_data)
            else:
                # Veritabanında veri yok
                cursor.close()
                connection.close()
                return jsonify({
                    'success': False,
                    'error': 'fetched_accounts tablosunda veri bulunamadı',
                    'total_accounts': 0,
                    'unique_domains': 0,
                    'categories': []
                })
                
        else:
            # Bağlantı başarısız
            return jsonify({
                'success': False,
                'error': 'Veritabanına bağlanılamadı',
                'total_accounts': 0,
                'unique_domains': 0,
                'categories': []
            })
        
    except Error as e:
        logging.error(f"API veri çekme hatası: {e}")
        if connection:
            connection.close()
        return jsonify({
            'success': False,
            'error': str(e),
            'total_accounts': 0,
            'unique_domains': 0,
            'categories': []
        })

# Kategori detay endpoint'i
@app.route('/api/category/<category_name>')
@login_required
def category_detail(category_name):
    """Belirli bir kategorinin detaylarını getir"""
    connection = None
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            
            # Kategori detayları
            cursor.execute("""
                SELECT domain, region, fetch_date 
                FROM fetched_accounts 
                WHERE category = %s 
                ORDER BY fetch_date DESC 
                LIMIT 100
            """, (category_name,))
            
            accounts = cursor.fetchall()
            
            cursor.execute("SELECT COUNT(*) as total FROM fetched_accounts WHERE category = %s", (category_name,))
            total = cursor.fetchone()['total']
            
            cursor.close()
            connection.close()
            
            return jsonify({
                'success': True,
                'category': category_name,
                'label': CATEGORY_TRANSLATIONS.get(category_name, category_name.title()),
                'total_count': total,
                'accounts': accounts[:50],  # İlk 50 tanesini göster
                'showing': min(50, len(accounts)),
                'user': session.get('user_name', 'Kullanıcı')
            })
            
    except Error as e:
        logging.error(f"Kategori detay hatası: {e}")
        if connection:
            connection.close()
            
    return jsonify({
        'success': False,
        'error': 'Kategori detayları alınamadı'
    })

# User info endpoint
@app.route('/api/user')
@login_required
def user_info():
    return jsonify({
        'success': True,
        'user_id': session.get('user_id'),
        'user_name': session.get('user_name'),
        'user_role': session.get('user_role'),
        'login_time': session.get('login_time')
    })

# API Configuration endpoint - Frontend için
@app.route('/api/config')
@login_required
def api_config():
    """Frontend için güvenli API konfigürasyonu"""
    return jsonify({
        'success': True,
        'endpoints': {
            'search': '/api/proxy/search',
            'accounts': '/api/proxy/accounts',
            'statistics': '/api/proxy/statistics',
            'health': '/api/proxy/health'
        },
        'user': session.get('user_name', 'Kullanıcı')
    })

# Admin panel (opsiyonel)
@app.route('/admin')
@admin_required
def admin_panel():
    return render_template('admin.html', 
                         user_name=session.get('user_name'),
                         user_role=session.get('user_role'))

# Error handlers
@app.errorhandler(404)
def not_found(error):
    if 'user_id' in session:
        return render_template('404.html'), 404
    return redirect(url_for('login'))

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)