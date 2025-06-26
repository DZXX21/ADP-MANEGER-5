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
import json

app = Flask(__name__)

# Session için secret key - PRODUCTION'da çevre değişkeninden alın!
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.permanent_session_lifetime = timedelta(hours=24)

# Loglama ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('lapsus.log'),
        logging.StreamHandler()
    ]
)

# Veritabanı bağlantı bilgileri - PRODUCTION'da çevre değişkenlerinden alın!
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '192.168.70.70'),
    'database': os.getenv('DB_NAME', 'lapsusacc'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'daaqwWdas21as'),
    'charset': 'utf8mb4',
    'port': int(os.getenv('DB_PORT', 3306)),
    'autocommit': True,
    'raise_on_warnings': True
}

# API Configuration - GÜVENLİ BACKEND'TE SAKLANIR
API_CONFIG = {
    'base_url': os.getenv('API_BASE_URL', 'http://192.168.70.71:5000'),
    'api_key': os.getenv('API_KEY', 'demo_key_123'),
    'timeout': int(os.getenv('API_TIMEOUT', 30)),
    'max_retries': int(os.getenv('API_MAX_RETRIES', 3))
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

# Kategori isimlerini Türkçeye çevirme
CATEGORY_TRANSLATIONS = {
    'government': 'Kamu Kurumları',
    'banks': 'Finansal Kuruluşlar', 
    'popular_turkish': 'Öne Çıkan Türk Siteler',
    'turkish_extensions': 'Türkiye Uzantılı Platformlar',
    'universities': 'Yükseköğretim Kurumları',
    'social_media': 'Sosyal Medya',
    'email_providers': 'E-posta Sağlayıcıları',
    'tech_companies': 'Teknoloji Şirketleri'
}

# Kategori renkleri
CATEGORY_COLORS = {
    'government': '#1e90ff',
    'banks': '#87ceeb',
    'popular_turkish': '#00bfff',
    'turkish_extensions': '#4682b4',
    'universities': '#5f9ea0',
    'social_media': '#ff6b6b',
    'email_providers': '#4ecdc4',
    'tech_companies': '#45b7d1'
}

# Kategori ikonları
CATEGORY_ICONS = {
    'government': 'building',
    'banks': 'landmark',
    'popular_turkish': 'star',
    'turkish_extensions': 'globe',
    'universities': 'graduation-cap',
    'social_media': 'users',
    'email_providers': 'mail',
    'tech_companies': 'cpu'
}

# Kategori sıralama öncelikleri
CATEGORY_ORDER = ['government', 'banks', 'popular_turkish', 'turkish_extensions', 'universities', 'social_media', 'email_providers', 'tech_companies']


# Decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Bu sayfaya erişmek için giriş yapmalısınız.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

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


# Database Functions
def get_db_connection():
    """Güvenli veritabanı bağlantısı"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            logging.info("Veritabanına başarıyla bağlanıldı.")
            return connection
    except Error as e:
        logging.error(f"Veritabanı bağlantı hatası: {e}")
        return None

def test_db_connection():
    """Veritabanı bağlantısını test et"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            connection.close()
            return True
        except Error as e:
            logging.error(f"Veritabanı test hatası: {e}")
            if connection:
                connection.close()
    return False


# API Request Helper
def make_api_request(endpoint, method='GET', params=None, data=None, retries=0):
    """Güvenli API request helper"""
    try:
        url = f"{API_CONFIG['base_url']}{endpoint}"
        headers = {
            'X-API-Key': API_CONFIG['api_key'],
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


# Authentication Functions
def verify_user(username, password):
    """Kullanıcı doğrulama"""
    user = ADMIN_USERS.get(username)
    if user:
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if password_hash == user['password_hash']:
            return user
    return None


# Routes

# Login/Logout Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Giriş sayfası"""
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
            
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Geçersiz kullanıcı adı veya şifre.', 'error')
            logging.warning(f"Başarısız giriş denemesi: {username} - {request.remote_addr}")
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Çıkış"""
    username = session.get('user_id', 'Bilinmeyen')
    session.clear()
    flash('Başarıyla çıkış yaptınız.', 'info')
    logging.info(f"Çıkış yapıldı: {username}")
    return redirect(url_for('login'))


# Main Routes
@app.route('/')
@login_required
def dashboard():
    """Ana dashboard sayfası"""
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
            cursor.execute("""
                SELECT category, COUNT(*) as count 
                FROM fetched_accounts 
                GROUP BY category 
                ORDER BY count DESC
            """)
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
                
                # Sonra tanımlanmamış kategorileri ekle
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
                
                logging.info(f"Dashboard verileri yüklendi: {len(categories)} kategori, toplam {total_count} kayıt")
                
            else:
                error = "fetched_accounts tablosunda veri bulunamadı!"
                logging.warning("fetched_accounts tablosunda veri bulunamadı")
                
            cursor.close()
            connection.close()
            
        else:
            error = "Veritabanına bağlanılamadı!"
            logging.error("Veritabanına bağlanılamadı")
            
    except Error as e:
        error = f"Veri çekme hatası: {str(e)}"
        logging.error(f"Dashboard veri çekme hatası: {e}")
        if connection:
            connection.close()

    return render_template('index.html', 
                         chart_data=chart_data, 
                         summary_data=summary_data, 
                         stats=stats,
                         error=error,
                         user_name=session.get('user_name'),
                         user_role=session.get('user_role'))

@app.route('/search')
@login_required
def search_page():
    """Arama sayfası"""
    return render_template('search.html', 
                         user_name=session.get('user_name'),
                         user_role=session.get('user_role'))


# API Proxy Endpoints - Frontend API key'lerini gizler
@app.route('/api/proxy/search')
@login_required
def proxy_search():
    """Güvenli arama proxy"""
    try:
        # Frontend'den gelen parametreleri al ve doğrula
        query = request.args.get('q', '').strip()
        page = request.args.get('page', 1, type=int)
        limit = min(request.args.get('limit', 20, type=int), 100)  # Max 100
        domain = request.args.get('domain', '')
        region = request.args.get('region', '')
        source = request.args.get('source', '')
        
        if not query or len(query) < 2:
            return jsonify({
                'success': False,
                'error': 'Arama sorgusu en az 2 karakter olmalıdır'
            }), 400
        
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
        
        # Log the search
        logging.info(f"Arama yapıldı: '{query}' - Kullanıcı: {session.get('user_name')}")
        
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
        page = request.args.get('page', 1, type=int)
        limit = min(request.args.get('limit', 10, type=int), 100)
        domain = request.args.get('domain', '')
        region = request.args.get('region', '')
        source = request.args.get('source', '')
        
        api_params = {
            'page': page,
            'limit': limit
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


# Local API Endpoints - Veritabanından direkt veri
@app.route('/api/stats')
@login_required
def api_stats():
    """Gerçek zamanlı istatistikler"""
    connection = None
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            
            # Kategori bazında sayım
            cursor.execute("""
                SELECT category, COUNT(*) as count 
                FROM fetched_accounts 
                GROUP BY category 
                ORDER BY count DESC
            """)
            categories = cursor.fetchall()
            
            if categories:
                total_count = sum(category['count'] for category in categories)
                
                # API formatında veri hazırla
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
                
                # Sonra tanımlanmamış kategorileri ekle
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

# ✅ ARAMA FONKSİYONU - API'DEN VERİ ÇEK
@app.route('/api/search')
@login_required
def api_search():
    """API'den arama - Veritabanı yerine API kullan"""
    try:
        # Parametreleri al
        query = request.args.get('q', '').strip()
        page = request.args.get('page', 1, type=int)
        limit = min(request.args.get('limit', 20, type=int), 100)
        domain_filter = request.args.get('domain', '')
        region_filter = request.args.get('region', '')
        source_filter = request.args.get('source', '')
        
        if not query or len(query) < 2:
            return jsonify({
                'success': False,
                'error': 'Arama sorgusu en az 2 karakter olmalıdır'
            }), 400
        
        # API parametrelerini hazırla
        api_params = {
            'q': query,
            'page': page,
            'limit': limit
        }
        
        # Filtreleri ekle
        if domain_filter:
            api_params['domain'] = domain_filter
        if region_filter:
            api_params['region'] = region_filter
        if source_filter:
            api_params['source'] = source_filter
        
        logging.info(f"API'den arama başlatılıyor: '{query}' - Parametreler: {api_params}")
        
        # API'den veri çek
        try:
            api_response = make_api_request('/api/search', params=api_params)
            
            # API yanıtını logla
            logging.info(f"API arama başarılı: '{query}' - {len(api_response.get('results', []))} sonuç")
            
            # Eğer API yanıtında debug bilgisi yoksa ekle
            if 'debug' not in api_response:
                api_response['debug'] = {
                    'data_source': 'external_api',
                    'api_endpoint': f"{API_CONFIG['base_url']}/api/search",
                    'query': query,
                    'params': api_params
                }
            
            return jsonify(api_response)
            
        except Exception as api_error:
            logging.warning(f"API arama başarısız, fallback'e geçiliyor: {str(api_error)}")
            
            # API başarısız olursa fallback olarak veritabanından ara
            return fallback_database_search(query, page, limit, domain_filter, region_filter, source_filter)
        
    except Exception as e:
        logging.error(f"Arama hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'data_source': 'error'
        }), 500

# ✅ FALLBACK VERİTABANI ARAMA FONKSİYONU
def fallback_database_search(query, page=1, limit=20, domain_filter='', region_filter='', source_filter=''):
    """API başarısız olduğunda veritabanından arama yap"""
    connection = None
    try:
        logging.info(f"Fallback veritabanı araması başlatılıyor: '{query}'")
        
        connection = get_db_connection()
        if not connection:
            return jsonify({
                'success': False,
                'error': 'API ve veritabanı bağlantısı başarısız',
                'data_source': 'fallback_failed'
            }), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # Tablo yapısını öğren
        cursor.execute("DESCRIBE fetched_accounts")
        table_columns = cursor.fetchall()
        available_columns = [col['Field'] for col in table_columns]
        
        # Arama kolonlarını belirle
        search_columns = []
        if 'domain' in available_columns:
            search_columns.append('domain')
        
        username_columns = ['username', 'user', 'email', 'login', 'user_name', 'account']
        for col in username_columns:
            if col in available_columns and col not in search_columns:
                search_columns.append(col)
                break
        
        password_columns = ['password', 'pass', 'pwd', 'passwd', 'secret']
        for col in password_columns:
            if col in available_columns and col not in search_columns:
                search_columns.append(col)
                break
        
        # WHERE koşulları
        where_conditions = []
        params = []
        
        # Arama koşulu
        if search_columns:
            search_parts = []
            search_pattern = f"%{query}%"
            for col in search_columns:
                search_parts.append(f"{col} LIKE %s")
                params.append(search_pattern)
            where_conditions.append(f"({' OR '.join(search_parts)})")
        else:
            where_conditions.append("domain LIKE %s")
            params.append(f"%{query}%")
        
        # Filtreler
        if domain_filter:
            where_conditions.append("domain LIKE %s")
            params.append(f"%{domain_filter}%")
        if region_filter and 'region' in available_columns:
            where_conditions.append("region = %s")
            params.append(region_filter)
        if source_filter and 'source' in available_columns:
            where_conditions.append("source = %s")
            params.append(source_filter)
        
        where_clause = "WHERE " + " AND ".join(where_conditions)
        
        # Toplam sayı
        count_query = f"SELECT COUNT(*) as total FROM fetched_accounts {where_clause}"
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()['total']
        
        # Sayfalama
        total_pages = (total_count + limit - 1) // limit
        offset = (page - 1) * limit
        
        # Tarih kolonu
        date_column = 'fetch_date'
        if 'fetch_date' not in available_columns:
            for alt_date in ['created_at', 'date_added', 'timestamp', 'date', 'created']:
                if alt_date in available_columns:
                    date_column = alt_date
                    break
            else:
                date_column = available_columns[0]
        
        # Ana sorgu
        search_query = f"""
            SELECT * FROM fetched_accounts 
            {where_clause}
            ORDER BY {date_column} DESC
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])
        
        cursor.execute(search_query, params)
        results = cursor.fetchall()
        
        # Sonuçları formatla
        formatted_results = []
        for result in results:
            username_value = None
            password_value = None
            
            for col in username_columns:
                if col in result and result[col]:
                    username_value = result[col]
                    break
            
            for col in password_columns:
                if col in result and result[col]:
                    password_value = result[col]
                    break
            
            formatted_result = {
                'id': result.get('id', 0),
                'domain': result.get('domain', ''),
                'username': username_value or 'N/A',
                'password': password_value or 'N/A',
                'region': result.get('region', 'Unknown'),
                'source': result.get('source', 'TXT'),
                'category': result.get('category', 'uncategorized'),
                'spid': f"SP{1000 + result.get('id', 0)}" if result.get('id', 0) % 3 == 0 else None
            }
            
            date_value = result.get('fetch_date') or result.get('created_at') or result.get('date_added')
            if date_value:
                formatted_result['date'] = date_value.isoformat() if hasattr(date_value, 'isoformat') else str(date_value)
            else:
                formatted_result['date'] = None
            
            formatted_results.append(formatted_result)
        
        cursor.close()
        connection.close()
        
        response_data = {
            'success': True,
            'results': formatted_results,
            'pagination': {
                'page': page,
                'pages': total_pages,
                'total': total_count,
                'has_next': page < total_pages,
                'has_prev': page > 1
            },
            'summary': {
                'exact_matches': len([r for r in formatted_results if query.lower() in r['domain'].lower()]),
                'partial_matches': len(formatted_results)
            },
            'debug': {
                'data_source': 'fallback_database',
                'search_columns': search_columns,
                'available_columns': available_columns,
                'query': query,
                'warning': 'API başarısız oldu, veritabanından arama yapıldı'
            }
        }
        
        logging.info(f"Fallback arama tamamlandı: '{query}' - {len(formatted_results)} sonuç")
        return jsonify(response_data)
        
    except Exception as e:
        logging.error(f"Fallback arama hatası: {str(e)}")
        if connection:
            connection.close()
        return jsonify({
            'success': False,
            'error': str(e),
            'data_source': 'fallback_error'
        }), 500

# ✅ VERİTABANI ARAMA ENDPOINT'İ - SADECE DEBUG İÇİN
@app.route('/api/search-db')
@login_required
def api_search_database():
    """Doğrudan veritabanından arama - Sadece debug/test için"""
    return fallback_database_search(
        query=request.args.get('q', '').strip(),
        page=request.args.get('page', 1, type=int),
        limit=min(request.args.get('limit', 20, type=int), 100),
        domain_filter=request.args.get('domain', ''),
        region_filter=request.args.get('region', ''),
        source_filter=request.args.get('source', '')
    )
@login_required
def category_detail(category_name):
    """Kategori detayları"""
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
                'accounts': accounts[:50],
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

@app.route('/api/user')
@login_required
def user_info():
    """Kullanıcı bilgileri"""
    return jsonify({
        'success': True,
        'user_id': session.get('user_id'),
        'user_name': session.get('user_name'),
        'user_role': session.get('user_role'),
        'login_time': session.get('login_time')
    })

@app.route('/api/config')
@login_required
def api_config():
    """Frontend için güvenli API konfigürasyonu"""
    return jsonify({
        'success': True,
        'endpoints': {
            'search': '/api/search',  # Local search kullan
            'accounts': '/api/proxy/accounts',
            'statistics': '/api/stats',  # Local stats kullan
            'health': '/api/proxy/health'
        },
        'user': session.get('user_name', 'Kullanıcı')
    })


# ✅ GÜNCELLENMIŞ DEBUG ENDPOINT'LERİ
@app.route('/debug/table-structure')
@login_required
def debug_table_structure():
    """Tablo yapısını kontrol et"""
    connection = None
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            
            # Tablo yapısını al
            cursor.execute("DESCRIBE fetched_accounts")
            columns = cursor.fetchall()
            
            # Örnek veri al
            cursor.execute("SELECT * FROM fetched_accounts LIMIT 1")
            sample_data = cursor.fetchone()
            
            # Tablo sayısı
            cursor.execute("SELECT COUNT(*) as total FROM fetched_accounts")
            total_count = cursor.fetchone()['total']
            
            # Domain örnekleri
            cursor.execute("SELECT DISTINCT domain FROM fetched_accounts LIMIT 10")
            sample_domains = [row['domain'] for row in cursor.fetchall()]
            
            cursor.close()
            connection.close()
            
            return jsonify({
                'success': True,
                'table_structure': columns,
                'sample_data': sample_data,
                'columns_list': [col['Field'] for col in columns],
                'total_records': total_count,
                'sample_domains': sample_domains,
                'recommendations': {
                    'username_columns': [col['Field'] for col in columns if any(keyword in col['Field'].lower() for keyword in ['user', 'email', 'login', 'account'])],
                    'password_columns': [col['Field'] for col in columns if any(keyword in col['Field'].lower() for keyword in ['pass', 'pwd', 'secret'])],
                    'date_columns': [col['Field'] for col in columns if any(keyword in col['Field'].lower() for keyword in ['date', 'time', 'created', 'added'])]
                }
            })
    except Exception as e:
        if connection:
            connection.close()
        return jsonify({
            'success': False,
            'error': str(e)
        })

    return jsonify({'success': False, 'error': 'Veritabanı bağlantısı başarısız'})

# Utility Routes
@app.route('/test-db')
@login_required
def test_db():
    """Veritabanı bağlantı testi - Gelişmiş versiyon"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            
            # Tablo kontrolü
            cursor.execute("SHOW TABLES LIKE 'fetched_accounts'")
            result = cursor.fetchone()
            
            if result:
                # Tablo yapısı
                cursor.execute("DESCRIBE fetched_accounts")
                table_structure = cursor.fetchall()
                
                # Kayıt sayısı
                cursor.execute("SELECT COUNT(*) as count FROM fetched_accounts")
                count = cursor.fetchone()['count']
                
                # Örnek veri
                cursor.execute("SELECT * FROM fetched_accounts LIMIT 1")
                sample = cursor.fetchone()
                
                # Domain örnekleri
                cursor.execute("SELECT DISTINCT domain FROM fetched_accounts LIMIT 10")
                sample_domains = [row['domain'] for row in cursor.fetchall()]
                
                connection.close()
                
                return jsonify({
                    'success': True,
                    'message': f'Veritabanı bağlantısı başarılı! {count:,} kayıt bulundu.',
                    'table_exists': True,
                    'record_count': count,
                    'has_sample_data': sample is not None,
                    'table_structure': table_structure,
                    'sample_data': sample,
                    'sample_domains': sample_domains,
                    'available_columns': [col['Field'] for col in table_structure]
                })
            else:
                connection.close()
                return jsonify({
                    'success': False,
                    'message': 'fetched_accounts tablosu bulunamadı!',
                    'table_exists': False
                })
                
        except Exception as e:
            connection.close()
            return jsonify({
                'success': False,
                'message': f'Tablo kontrolü hatası: {e}'
            })
    
    return jsonify({
        'success': False,
        'message': 'Veritabanı bağlantısı başarısız!'
    })

@app.route('/health')
def health_check():
    """Sistem sağlık kontrolü"""
    try:
        db_status = test_db_connection()
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'database': 'connected' if db_status else 'disconnected',
            'session_active': 'user_id' in session,
            'version': '1.0.0'
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


# Admin Routes
@app.route('/admin')
@admin_required
def admin_panel():
    """Admin panel"""
    return render_template('admin.html', 
                         user_name=session.get('user_name'),
                         user_role=session.get('user_role'))


# Error Handlers
@app.errorhandler(404)
def not_found(error):
    if 'user_id' in session:
        return render_template('404.html'), 404
    return redirect(url_for('login'))

@app.errorhandler(500)
def internal_error(error):
    logging.error(f"Internal server error: {error}")
    return render_template('500.html'), 500

@app.errorhandler(403)
def forbidden(error):
    flash('Bu işlem için yetkiniz yok.', 'error')
    return redirect(url_for('dashboard'))


# Context Processors
@app.context_processor
def inject_user():
    """Template'lere kullanıcı bilgilerini enjekte et"""
    return dict(
        current_user=session.get('user_name', 'Misafir'),
        user_role=session.get('user_role', 'guest'),
        is_logged_in='user_id' in session
    )


# Development/Debug Routes
@app.route('/debug/session')
@login_required
def debug_session():
    """Session debug bilgileri"""
    if not app.debug:
        return jsonify({'error': 'Debug mode disabled'}), 403
    
    return jsonify({
        'session_data': dict(session),
        'session_permanent': session.permanent,
        'session_new': session.new
    })


if __name__ == '__main__':
    # Başlangıç kontrolü
    logging.info("Lapsus uygulaması başlatılıyor...")
    
    # Veritabanı bağlantı testi
    if test_db_connection():
        logging.info("✅ Veritabanı bağlantısı başarılı")
    else:
        logging.warning("⚠️ Veritabanı bağlantısı başarısız - bazı özellikler çalışmayabilir")
    
    # Uygulamayı başlat
    app.run(
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true',
        host=os.getenv('FLASK_HOST', '0.0.0.0'),
        port=int(os.getenv('FLASK_PORT', 7071))
    )