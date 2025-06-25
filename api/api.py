from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
import hashlib
import secrets
import datetime
from datetime import datetime as dt
from functools import wraps
import os
import json
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)
CORS(app)

# Logging yapılandırması
if not os.path.exists('logs'):
    os.makedirs('logs')

# Ana log dosyası
file_handler = RotatingFileHandler('logs/api.log', maxBytes=10240000, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)

# İstek logları için ayrı dosya
request_handler = RotatingFileHandler('logs/requests.log', maxBytes=10240000, backupCount=10)
request_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(message)s'
))
request_handler.setLevel(logging.INFO)

request_logger = logging.getLogger('requests')
request_logger.addHandler(request_handler)
request_logger.setLevel(logging.INFO)

app.logger.setLevel(logging.INFO)
app.logger.info('LapsusAcc API başlatıldı')

# Database bağlantı bilgileri
DB_CONFIG = {
    'host': '127.0.0.1',
    'database': 'lapsusacc',
    'user': 'root',
    'password': 'daaqwWdas21as',
    'charset': 'utf8mb4'
}

# API Keys - Gerçek uygulamada veritabanında saklanmalı
API_KEYS = {
    'demo_key_123': {
        'name': 'Demo User',
        'permissions': ['read', 'write'],
        'rate_limit': 1000,  # günlük istek limiti
        'requests_today': 0,
        'last_reset': datetime.date.today()
    },
    'read_only_key_456': {
        'name': 'Read Only User',
        'permissions': ['read'],
        'rate_limit': 500,
        'requests_today': 0,
        'last_reset': datetime.date.today()
    }
}

# Database bağlantısı
def get_db_connection():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        app.logger.error(f"Database bağlantı hatası: {e}")
        return None

# İstek logları için database tablosu oluştur
def create_logs_table():
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            create_table_query = """
            CREATE TABLE IF NOT EXISTS `api_logs` (
                `id` int(11) NOT NULL AUTO_INCREMENT,
                `timestamp` datetime DEFAULT CURRENT_TIMESTAMP,
                `ip_address` varchar(45) NOT NULL,
                `api_key` varchar(255) DEFAULT NULL,
                `user_name` varchar(255) DEFAULT NULL,
                `method` varchar(10) NOT NULL,
                `endpoint` varchar(255) NOT NULL,
                `query_params` text DEFAULT NULL,
                `status_code` int(11) DEFAULT NULL,
                `response_time` float DEFAULT NULL,
                `user_agent` text DEFAULT NULL,
                `error_message` text DEFAULT NULL,
                PRIMARY KEY (`id`),
                INDEX `idx_timestamp` (`timestamp`),
                INDEX `idx_api_key` (`api_key`),
                INDEX `idx_endpoint` (`endpoint`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
            """
            cursor.execute(create_table_query)
            connection.commit()
            connection.close()
            app.logger.info("API logs tablosu kontrol edildi/oluşturuldu")
    except Error as e:
        app.logger.error(f"Logs tablosu oluşturma hatası: {e}")

# Başlangıçta logs tablosunu oluştur
create_logs_table()

# İstek loglama decorator'ı
def log_request(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        start_time = datetime.datetime.now()
        
        # İstek bilgilerini topla
        ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        user_name = None
        
        if api_key and api_key in API_KEYS:
            user_name = API_KEYS[api_key].get('name')
        
        method = request.method
        endpoint = request.endpoint or request.path
        query_params = dict(request.args) if request.args else None
        user_agent = request.headers.get('User-Agent', '')
        
        # Request body'yi log'a ekle (sadece POST/PUT için)
        request_data = None
        if method in ['POST', 'PUT'] and request.is_json:
            try:
                request_data = request.get_json()
                # Şifreleri gizle
                if isinstance(request_data, dict) and 'password' in request_data:
                    request_data['password'] = '***hidden***'
            except:
                pass
        
        # Function'ı çalıştır
        try:
            response = f(*args, **kwargs)
            
            # Response durumunu belirle
            if isinstance(response, tuple):
                status_code = response[1]
                response_data = response[0]
            else:
                status_code = 200
                response_data = response
                
            error_message = None
            
        except Exception as e:
            status_code = 500
            error_message = str(e)
            response = jsonify({'error': 'Sunucu hatası'}), 500
            response_data = response[0]
            app.logger.error(f"Endpoint hatası: {e}")
        
        # Süreyi hesapla
        end_time = datetime.datetime.now()
        response_time = (end_time - start_time).total_seconds()
        
        # Database'e log kaydet
        try:
            connection = get_db_connection()
            if connection:
                cursor = connection.cursor()
                
                log_query = """
                INSERT INTO api_logs 
                (timestamp, ip_address, api_key, user_name, method, endpoint, 
                 query_params, status_code, response_time, user_agent, error_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                values = (
                    start_time,
                    ip_address,
                    api_key[:50] if api_key else None,  # API key'i kısalt
                    user_name,
                    method,
                    endpoint,
                    json.dumps(query_params) if query_params else None,
                    status_code,
                    response_time,
                    user_agent[:500] if user_agent else None,  # User agent'ı kısalt
                    error_message[:1000] if error_message else None  # Error'ı kısalt
                )
                
                cursor.execute(log_query, values)
                connection.commit()
                connection.close()
                
        except Error as e:
            app.logger.error(f"Log kaydetme hatası: {e}")
        
        # Dosya log'u da ekle
        log_entry = {
            'timestamp': start_time.isoformat(),
            'ip': ip_address,
            'user': user_name or 'anonymous',
            'method': method,
            'endpoint': endpoint,
            'status': status_code,
            'response_time': f"{response_time:.3f}s",
            'query_params': query_params,
            'request_data': request_data
        }
        
        request_logger.info(json.dumps(log_entry, ensure_ascii=False))
        
        return response
    return decorated

# API Key doğrulama ve rate limiting
def api_key_required(permissions=None):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # Header'dan veya URL parameter'dan API key al
            api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
            
            if not api_key:
                return jsonify({
                    'error': 'API Key gerekli',
                    'message': 'X-API-Key header\'ında veya ?api_key= parameter\'ında API key\'inizi gönderin'
                }), 401
            
            if api_key not in API_KEYS:
                return jsonify({
                    'error': 'Geçersiz API Key',
                    'message': 'Lütfen geçerli bir API key kullanın'
                }), 403
            
            key_info = API_KEYS[api_key]
            
            # Rate limiting kontrolü
            today = datetime.date.today()
            if key_info['last_reset'] != today:
                key_info['requests_today'] = 0
                key_info['last_reset'] = today
            
            if key_info['requests_today'] >= key_info['rate_limit']:
                return jsonify({
                    'error': 'Rate limit aşıldı',
                    'message': f'Günlük {key_info["rate_limit"]} istek limitini aştınız'
                }), 429
            
            # İzin kontrolü
            if permissions:
                user_permissions = key_info.get('permissions', [])
                if not any(perm in user_permissions for perm in permissions):
                    return jsonify({
                        'error': 'Yetkisiz erişim',
                        'message': f'Bu işlem için {permissions} izinlerinden birine ihtiyacınız var'
                    }), 403
            
            # İstek sayısını artır
            key_info['requests_today'] += 1
            
            # Key bilgilerini request'e ekle
            request.api_key_info = key_info
            
            return f(*args, **kwargs)
        return decorated
    return decorator

# Ana sayfa - API dokümantasyonu
@app.route('/')
@log_request
def index():
    return jsonify({
        'message': 'LapsusAcc Public API',
        'version': '2.0.0',
        'documentation': {
            'authentication': 'X-API-Key header ile API key gönderin',
            'rate_limits': 'Günlük istek limitleri vardır',
            'endpoints': {
                'GET /api/accounts': 'Hesapları listele (sayfalama destekli)',
                'GET /api/accounts/{id}': 'Belirli hesabı getir',
                'POST /api/accounts': 'Yeni hesap ekle (write izni gerekli)',
                'PUT /api/accounts/{id}': 'Hesap güncelle (write izni gerekli)',
                'DELETE /api/accounts/{id}': 'Hesap sil (write izni gerekli)',
                'GET /api/search': 'Hesap ara',
                'GET /api/stats': 'İstatistikler',
                'POST /api/accounts/bulk': 'Toplu hesap ekleme (write izni gerekli)',
                'GET /api/key-info': 'API key bilgileri'
            }
        },
        'example_usage': {
            'headers': {
                'X-API-Key': 'your-api-key-here',
                'Content-Type': 'application/json'
            },
            'url_parameter': '?api_key=your-api-key-here'
        }
    })

# API Key bilgileri
@app.route('/api/key-info', methods=['GET'])
@log_request
@api_key_required()
def get_key_info():
    key_info = request.api_key_info
    return jsonify({
        'name': key_info['name'],
        'permissions': key_info['permissions'],
        'rate_limit': key_info['rate_limit'],
        'requests_today': key_info['requests_today'],
        'remaining_requests': key_info['rate_limit'] - key_info['requests_today']
    })

# Hesapları listele
@app.route('/api/accounts', methods=['GET'])
@log_request
@api_key_required(['read'])
def get_accounts():
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database bağlantı hatası'}), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # Pagination
        page = request.args.get('page', 1, type=int)
        limit = min(request.args.get('limit', 10, type=int), 100)  # Max 100 kayıt
        offset = (page - 1) * limit
        
        # Filtreleme
        filters = {}
        filter_fields = ['domain', 'region', 'source', 'spid']
        
        query = "SELECT * FROM accs WHERE 1=1"
        params = []
        
        for field in filter_fields:
            value = request.args.get(field)
            if value:
                if field in ['domain', 'source']:
                    query += f" AND {field} LIKE %s"
                    params.append(f"%{value}%")
                else:
                    query += f" AND {field} = %s"
                    params.append(value)
        
        # Tarih filtresi
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        if date_from:
            query += " AND date >= %s"
            params.append(date_from)
        
        if date_to:
            query += " AND date <= %s"
            params.append(date_to)
        
        # Sıralama
        sort_by = request.args.get('sort_by', 'id')
        sort_order = request.args.get('sort_order', 'desc')
        
        if sort_by in ['id', 'domain', 'date', 'region'] and sort_order.lower() in ['asc', 'desc']:
            query += f" ORDER BY {sort_by} {sort_order.upper()}"
        else:
            query += " ORDER BY id DESC"
        
        query += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        accounts = cursor.fetchall()
        
        # Toplam sayı
        count_query = "SELECT COUNT(*) as total FROM accs WHERE 1=1"
        count_params = []
        
        for field in filter_fields:
            value = request.args.get(field)
            if value:
                if field in ['domain', 'source']:
                    count_query += f" AND {field} LIKE %s"
                    count_params.append(f"%{value}%")
                else:
                    count_query += f" AND {field} = %s"
                    count_params.append(value)
        
        if date_from:
            count_query += " AND date >= %s"
            count_params.append(date_from)
        
        if date_to:
            count_query += " AND date <= %s"
            count_params.append(date_to)
        
        cursor.execute(count_query, count_params)
        total = cursor.fetchone()['total']
        
        connection.close()
        
        return jsonify({
            'success': True,
            'data': accounts,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit
            },
            'filters_applied': {k: v for k, v in request.args.items() if k not in ['page', 'limit']}
        })
        
    except Error as e:
        return jsonify({'error': f'Database hatası: {str(e)}'}), 500

# Tek hesap getir
@app.route('/api/accounts/<int:account_id>', methods=['GET'])
@api_key_required(['read'])
def get_account(account_id):
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database bağlantı hatası'}), 500
        
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM accs WHERE id = %s", (account_id,))
        account = cursor.fetchone()
        
        connection.close()
        
        if account:
            return jsonify({
                'success': True,
                'data': account
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Hesap bulunamadı'
            }), 404
            
    except Error as e:
        return jsonify({'error': f'Database hatası: {str(e)}'}), 500

# Yeni hesap ekle
@app.route('/api/accounts', methods=['POST'])
@api_key_required(['write'])
def create_account():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'JSON verisi gerekli'}), 400
        
        # Gerekli alanları kontrol et
        required_fields = ['domain', 'username', 'password']
        missing_fields = [field for field in required_fields if field not in data or not data[field]]
        
        if missing_fields:
            return jsonify({
                'error': 'Eksik alanlar',
                'missing_fields': missing_fields
            }), 400
        
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database bağlantı hatası'}), 500
        
        cursor = connection.cursor()
        
        insert_query = """
            INSERT INTO accs (spid, domain, username, password, region, source, date)
            VALUES (%s, %s, %s, %s, %s, %s, CURDATE())
        """
        
        values = (
            data.get('spid', 0),
            data['domain'],
            data['username'],
            data['password'],
            data.get('region', ''),
            data.get('source', f"API-{request.api_key_info['name']}")
        )
        
        cursor.execute(insert_query, values)
        connection.commit()
        
        new_id = cursor.lastrowid
        connection.close()
        
        return jsonify({
            'success': True,
            'message': 'Hesap başarıyla eklendi',
            'data': {
                'id': new_id,
                'domain': data['domain'],
                'username': data['username']
            }
        }), 201
        
    except Error as e:
        return jsonify({'error': f'Database hatası: {str(e)}'}), 500

# Hesap güncelle
@app.route('/api/accounts/<int:account_id>', methods=['PUT'])
@api_key_required(['write'])
def update_account(account_id):
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'JSON verisi gerekli'}), 400
        
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database bağlantı hatası'}), 500
        
        cursor = connection.cursor()
        
        # Hesabın var olup olmadığını kontrol et
        cursor.execute("SELECT id FROM accs WHERE id = %s", (account_id,))
        if not cursor.fetchone():
            return jsonify({
                'success': False,
                'error': 'Hesap bulunamadı'
            }), 404
        
        # Güncelleme sorgusu
        update_fields = []
        values = []
        
        updatable_fields = ['spid', 'domain', 'username', 'password', 'region', 'source']
        for field in updatable_fields:
            if field in data:
                update_fields.append(f"{field} = %s")
                values.append(data[field])
        
        if not update_fields:
            return jsonify({'error': 'Güncellenecek alan belirtilmedi'}), 400
        
        values.append(account_id)
        update_query = f"UPDATE accs SET {', '.join(update_fields)} WHERE id = %s"
        
        cursor.execute(update_query, values)
        connection.commit()
        connection.close()
        
        return jsonify({
            'success': True,
            'message': 'Hesap başarıyla güncellendi'
        })
        
    except Error as e:
        return jsonify({'error': f'Database hatası: {str(e)}'}), 500

# Hesap sil
@app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
@api_key_required(['write'])
def delete_account(account_id):
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database bağlantı hatası'}), 500
        
        cursor = connection.cursor()
        
        # Hesabın var olup olmadığını kontrol et
        cursor.execute("SELECT id FROM accs WHERE id = %s", (account_id,))
        if not cursor.fetchone():
            return jsonify({
                'success': False,
                'error': 'Hesap bulunamadı'
            }), 404
        
        cursor.execute("DELETE FROM accs WHERE id = %s", (account_id,))
        connection.commit()
        connection.close()
        
        return jsonify({
            'success': True,
            'message': 'Hesap başarıyla silindi'
        })
        
    except Error as e:
        return jsonify({'error': f'Database hatası: {str(e)}'}), 500

# Arama
@app.route('/api/search', methods=['GET'])
@api_key_required(['read'])
def search_accounts():
    try:
        query = request.args.get('q', '').strip()
        if not query:
            return jsonify({'error': 'Arama sorgusu (q parametresi) gerekli'}), 400
        
        if len(query) < 2:
            return jsonify({'error': 'Arama sorgusu en az 2 karakter olmalı'}), 400
        
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database bağlantı hatası'}), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # Limit
        limit = min(request.args.get('limit', 20, type=int), 100)
        
        search_query = """
            SELECT * FROM accs 
            WHERE domain LIKE %s OR username LIKE %s OR region LIKE %s OR source LIKE %s
            ORDER BY 
                CASE 
                    WHEN domain = %s THEN 1
                    WHEN username = %s THEN 2
                    ELSE 3
                END,
                id DESC
            LIMIT %s
        """
        
        search_term = f"%{query}%"
        cursor.execute(search_query, (search_term, search_term, search_term, search_term, query, query, limit))
        results = cursor.fetchall()
        
        connection.close()
        
        return jsonify({
            'success': True,
            'query': query,
            'results': results,
            'count': len(results)
        })
        
    except Error as e:
        return jsonify({'error': f'Database hatası: {str(e)}'}), 500

# İstatistikler
@app.route('/api/stats', methods=['GET'])
@api_key_required(['read'])
def get_stats():
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database bağlantı hatası'}), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # Toplam hesap sayısı
        cursor.execute("SELECT COUNT(*) as total FROM accs")
        total_accounts = cursor.fetchone()['total']
        
        # Bölgelere göre dağılım
        cursor.execute("SELECT region, COUNT(*) as count FROM accs WHERE region != '' GROUP BY region ORDER BY count DESC LIMIT 10")
        regions = cursor.fetchall()
        
        # Domain'lere göre dağılım
        cursor.execute("SELECT domain, COUNT(*) as count FROM accs GROUP BY domain ORDER BY count DESC LIMIT 10")
        domains = cursor.fetchall()
        
        # Son 30 gün içindeki hesaplar
        cursor.execute("SELECT COUNT(*) as count FROM accs WHERE date >= CURDATE() - INTERVAL 30 DAY")
        recent_accounts = cursor.fetchone()['count']
        
        # Günlük ekleme trendi (son 7 gün)
        cursor.execute("""
            SELECT DATE(date) as date, COUNT(*) as count 
            FROM accs 
            WHERE date >= CURDATE() - INTERVAL 7 DAY 
            GROUP BY DATE(date) 
            ORDER BY date DESC
        """)
        daily_trend = cursor.fetchall()
        
        connection.close()
        
        return jsonify({
            'success': True,
            'data': {
                'total_accounts': total_accounts,
                'recent_accounts_30d': recent_accounts,
                'top_regions': regions,
                'top_domains': domains,
                'daily_trend_7d': daily_trend
            }
        })
        
    except Error as e:
        return jsonify({'error': f'Database hatası: {str(e)}'}), 500

# Toplu hesap ekleme
@app.route('/api/accounts/bulk', methods=['POST'])
@api_key_required(['write'])
def bulk_create_accounts():
    try:
        data = request.get_json()
        
        if not data or 'accounts' not in data:
            return jsonify({'error': 'accounts dizisi gerekli'}), 400
        
        accounts = data['accounts']
        
        if not isinstance(accounts, list) or len(accounts) == 0:
            return jsonify({'error': 'En az 1 hesap gerekli'}), 400
        
        if len(accounts) > 100:
            return jsonify({'error': 'Maksimum 100 hesap bir seferde eklenebilir'}), 400
        
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database bağlantı hatası'}), 500
        
        cursor = connection.cursor()
        
        insert_query = """
            INSERT INTO accs (spid, domain, username, password, region, source, date)
            VALUES (%s, %s, %s, %s, %s, %s, CURDATE())
        """
        
        success_count = 0
        errors = []
        
        for i, account in enumerate(accounts):
            try:
                # Gerekli alanları kontrol et
                if not all(field in account for field in ['domain', 'username', 'password']):
                    errors.append(f"Satır {i+1}: domain, username, password alanları gerekli")
                    continue
                
                values = (
                    account.get('spid', 0),
                    account['domain'],
                    account['username'],
                    account['password'],
                    account.get('region', ''),
                    account.get('source', f"API-Bulk-{request.api_key_info['name']}")
                )
                
                cursor.execute(insert_query, values)
                success_count += 1
                
            except Exception as e:
                errors.append(f"Satır {i+1}: {str(e)}")
        
        connection.commit()
        connection.close()
        
        return jsonify({
            'success': True,
            'message': f'{success_count} hesap başarıyla eklendi',
            'summary': {
                'total_processed': len(accounts),
                'successful': success_count,
                'failed': len(errors)
            },
            'errors': errors
        })
        
    except Error as e:
        return jsonify({'error': f'Database hatası: {str(e)}'}), 500

# Log'ları görüntüle (admin endpoint)
@app.route('/api/logs', methods=['GET'])
@log_request
@api_key_required(['read'])
def get_logs():
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database bağlantı hatası'}), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # Pagination
        page = request.args.get('page', 1, type=int)
        limit = min(request.args.get('limit', 50, type=int), 200)
        offset = (page - 1) * limit
        
        # Filtreleme
        filters = {}
        where_conditions = []
        params = []
        
        # Tarih filtresi - format kontrolü ve mantık kontrolü
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        # Tarih formatını kontrol et ve geçersiz tarihleri filtrele
        if date_from:
            try:
                # Tarih formatını kontrol et
                parsed_date = dt.strptime(date_from, '%Y-%m-%d')
                
                # Çok eski tarihler (2015 öncesi) için uyarı
                if parsed_date.year < 2015:
                    return jsonify({
                        'error': 'Geçersiz tarih aralığı',
                        'message': 'date_from 2015 yılından sonra olmalıdır'
                    }), 400
                
                # Gelecek tarihler için uyarı
                if parsed_date > dt.now():
                    return jsonify({
                        'error': 'Geçersiz tarih aralığı', 
                        'message': 'date_from gelecek bir tarih olamaz'
                    }), 400
                
                where_conditions.append("timestamp >= %s")
                params.append(date_from)
                
            except ValueError:
                return jsonify({
                    'error': 'Geçersiz tarih formatı',
                    'message': 'date_from formatı YYYY-MM-DD olmalıdır (örnek: 2025-01-23)'
                }), 400
        
        if date_to:
            try:
                # Tarih formatını kontrol et
                parsed_date = dt.strptime(date_to, '%Y-%m-%d')
                
                # Gelecek tarihler için uyarı
                if parsed_date > dt.now():
                    return jsonify({
                        'error': 'Geçersiz tarih aralığı',
                        'message': 'date_to gelecek bir tarih olamaz'
                    }), 400
                
                where_conditions.append("timestamp <= %s")
                params.append(date_to + " 23:59:59")
                
            except ValueError:
                return jsonify({
                    'error': 'Geçersiz tarih formatı',
                    'message': 'date_to formatı YYYY-MM-DD olmalıdır (örnek: 2025-01-23)'
                }), 400
        
        # Tarih aralığı mantık kontrolü
        if date_from and date_to:
            try:
                start_date = dt.strptime(date_from, '%Y-%m-%d')
                end_date = dt.strptime(date_to, '%Y-%m-%d')
                
                if start_date > end_date:
                    return jsonify({
                        'error': 'Geçersiz tarih aralığı',
                        'message': 'date_from, date_to\'dan önce olmalıdır'
                    }), 400
                
                # Çok uzun aralık kontrolü (1 yıldan fazla)
                if (end_date - start_date).days > 365:
                    return jsonify({
                        'error': 'Tarih aralığı çok uzun',
                        'message': 'Maksimum 1 yıl aralığında sorgulama yapabilirsiniz'
                    }), 400
                    
            except ValueError:
                pass  # Format hatası zaten yukarıda yakalandı
        
        # API key filtresi
        api_key_filter = request.args.get('api_key')
        if api_key_filter:
            where_conditions.append("api_key LIKE %s")
            params.append(f"%{api_key_filter}%")
        
        # Endpoint filtresi
        endpoint_filter = request.args.get('endpoint')
        if endpoint_filter:
            where_conditions.append("endpoint LIKE %s")
            params.append(f"%{endpoint_filter}%")
        
        # Status code filtresi
        status_filter = request.args.get('status_code')
        if status_filter:
            where_conditions.append("status_code = %s")
            params.append(status_filter)
        
        # Method filtresi
        method_filter = request.args.get('method')
        if method_filter:
            where_conditions.append("method = %s")
            params.append(method_filter.upper())
        
        # User filtresi
        user_filter = request.args.get('user')
        if user_filter:
            where_conditions.append("user_name LIKE %s")
            params.append(f"%{user_filter}%")
        
        # Domain filtresi (query_params JSON'ında domain araması)
        domain_filter = request.args.get('domain')
        if domain_filter:
            where_conditions.append("(query_params LIKE %s OR endpoint LIKE %s)")
            params.extend([f'%"domain":"%{domain_filter}%"%', f'%{domain_filter}%'])
        
        # IP Address filtresi
        ip_filter = request.args.get('ip')
        if ip_filter:
            where_conditions.append("ip_address LIKE %s")
            params.append(f"%{ip_filter}%")
        
        # Where clause oluştur
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        # Ana sorgu
        query = f"""
            SELECT * FROM api_logs 
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
        """
        
        params.extend([limit, offset])
        cursor.execute(query, params)
        logs = cursor.fetchall()
        
        # Toplam sayı
        count_query = f"SELECT COUNT(*) as total FROM api_logs {where_clause}"
        cursor.execute(count_query, params[:-2])  # LIMIT ve OFFSET'i çıkar
        total = cursor.fetchone()['total']
        
        connection.close()
        
        # JSON parse et
        for log in logs:
            if log['query_params']:
                try:
                    log['query_params'] = json.loads(log['query_params'])
                except:
                    pass
        
        return jsonify({
            'success': True,
            'data': logs,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit
            },
            'filters_applied': {k: v for k, v in request.args.items() if k not in ['page', 'limit']}
        })
        
    except Error as e:
        app.logger.error(f"Log getirme hatası: {e}")
        return jsonify({'error': f'Database hatası: {str(e)}'}), 500

# Log istatistikleri
@app.route('/api/logs/stats', methods=['GET'])
@log_request
@api_key_required(['read'])
def get_log_stats():
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Database bağlantı hatası'}), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # Toplam istek sayısı
        cursor.execute("SELECT COUNT(*) as total FROM api_logs")
        total_requests = cursor.fetchone()['total']
        
        # Son 24 saat
        cursor.execute("""
            SELECT COUNT(*) as count FROM api_logs 
            WHERE timestamp >= NOW() - INTERVAL 24 HOUR
        """)
        last_24h = cursor.fetchone()['count']
        
        # Son 7 gün
        cursor.execute("""
            SELECT COUNT(*) as count FROM api_logs 
            WHERE timestamp >= NOW() - INTERVAL 7 DAY
        """)
        last_7d = cursor.fetchone()['count']
        
        # Status kodlarına göre dağılım
        cursor.execute("""
            SELECT status_code, COUNT(*) as count 
            FROM api_logs 
            GROUP BY status_code 
            ORDER BY count DESC
        """)
        status_distribution = cursor.fetchall()
        
        # En çok kullanılan endpoint'ler
        cursor.execute("""
            SELECT endpoint, COUNT(*) as count 
            FROM api_logs 
            GROUP BY endpoint 
            ORDER BY count DESC 
            LIMIT 10
        """)
        top_endpoints = cursor.fetchall()
        
        # Kullanıcılara göre dağılım
        cursor.execute("""
            SELECT user_name, COUNT(*) as count 
            FROM api_logs 
            WHERE user_name IS NOT NULL
            GROUP BY user_name 
            ORDER BY count DESC 
            LIMIT 10
        """)
        top_users = cursor.fetchall()
        
        # IP adreslerine göre dağılım
        cursor.execute("""
            SELECT ip_address, COUNT(*) as count 
            FROM api_logs 
            GROUP BY ip_address 
            ORDER BY count DESC 
            LIMIT 10
        """)
        top_ips = cursor.fetchall()
        
        # Günlük trend (son 7 gün)
        cursor.execute("""
            SELECT DATE(timestamp) as date, COUNT(*) as count 
            FROM api_logs 
            WHERE timestamp >= NOW() - INTERVAL 7 DAY
            GROUP BY DATE(timestamp) 
            ORDER BY date DESC
        """)
        daily_trend = cursor.fetchall()
        
        # Saatlik trend (son 24 saat)
        cursor.execute("""
            SELECT HOUR(timestamp) as hour, COUNT(*) as count 
            FROM api_logs 
            WHERE timestamp >= NOW() - INTERVAL 24 HOUR
            GROUP BY HOUR(timestamp) 
            ORDER BY hour
        """)
        hourly_trend = cursor.fetchall()
        
        # Ortalama response time
        cursor.execute("""
            SELECT AVG(response_time) as avg_response_time,
                   MIN(response_time) as min_response_time,
                   MAX(response_time) as max_response_time
            FROM api_logs 
            WHERE response_time IS NOT NULL
        """)
        response_times = cursor.fetchone()
        
        connection.close()
        
        return jsonify({
            'success': True,
            'data': {
                'summary': {
                    'total_requests': total_requests,
                    'last_24h': last_24h,
                    'last_7d': last_7d
                },
                'performance': {
                    'avg_response_time': round(response_times['avg_response_time'] or 0, 3),
                    'min_response_time': round(response_times['min_response_time'] or 0, 3),
                    'max_response_time': round(response_times['max_response_time'] or 0, 3)
                },
                'distributions': {
                    'status_codes': status_distribution,
                    'top_endpoints': top_endpoints,
                    'top_users': top_users,
                    'top_ips': top_ips
                },
                'trends': {
                    'daily_7d': daily_trend,
                    'hourly_24h': hourly_trend
                }
            }
        })
        
    except Error as e:
        app.logger.error(f"Log istatistik hatası: {e}")
        return jsonify({'error': f'Database hatası: {str(e)}'}), 500
    try:
        # Database bağlantısını test et
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            connection.close()
            db_status = "healthy"
        else:
            db_status = "unhealthy"
        
        return jsonify({
            'status': 'healthy' if db_status == 'healthy' else 'unhealthy',
            'timestamp': datetime.datetime.now().isoformat(),
            'version': '2.0.0',
            'database': db_status,
            'api_keys_loaded': len(API_KEYS)
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.datetime.now().isoformat()
        }), 500

# Hata yönetimi
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'error': 'Endpoint bulunamadı',
        'message': 'API dokümantasyonu için ana sayfayı ziyaret edin'
    }), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        'error': 'HTTP metodu desteklenmiyor',
        'message': 'Lütfen doğru HTTP metodunu kullanın'
    }), 405

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'error': 'Sunucu hatası',
        'message': 'Bir hata oluştu, lütfen daha sonra tekrar deneyin'
    }), 500

if __name__ == '__main__':
    print("🚀 LapsusAcc API başlatılıyor...")
    print("📚 Dokümantasyon: http://localhost:5000")
    print("🔑 Demo API Keys:")
    print("   - demo_key_123 (read/write, 1000 req/day)")
    print("   - read_only_key_456 (read only, 500 req/day)")
    print("📊 Log Endpoints:")
    print("   - GET /api/logs (istek logları)")
    print("   - GET /api/logs/stats (log istatistikleri)")
    print("📁 Log Dosyaları:")
    print("   - logs/api.log (genel loglar)")
    print("   - logs/requests.log (istek logları)")
    print("🗄️  Database: api_logs tablosu otomatik oluşturuldu")
    
    app.run(debug=True, host='0.0.0.0', port=5000)