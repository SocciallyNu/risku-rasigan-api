from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import math
import os
import json
import time

app = Flask(__name__)
CORS(app)

_cache = {}
CACHE_TTL = 900

def get_firebase():
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore, messaging
        if not firebase_admin._apps:
            firebase_creds_str = os.environ.get('FIREBASE_SERVICE_ACCOUNT', '{}')
            if firebase_creds_str and firebase_creds_str != '{}':
                firebase_creds = json.loads(firebase_creds_str)
                cred = credentials.Certificate(firebase_creds)
                firebase_admin.initialize_app(cred)
        return firestore.client(), messaging
    except Exception as e:
        print(f'Firebase error: {e}')
        return None, None

def fetch_stock_data(symbol):
    now = time.time()
    if symbol in _cache:
        cached = _cache[symbol]
        if now - cached['timestamp'] < CACHE_TTL:
            return cached['data'], True
    ticker = yf.Ticker(symbol)
    info = ticker.info
    data = {
        'last_price': info.get('currentPrice') or info.get('regularMarketPrice') or 0,
        'pe_ratio': info.get('trailingPE') or 0,
        'earnings_per_share': info.get('trailingEps') or 0,
        'book_value': info.get('bookValue') or 0,
        'dividend_yield': info.get('dividendYield') or 0,
        'sector': info.get('sector') or '',
        'company_name': info.get('longName') or symbol,
    }
    _cache[symbol] = {'data': data, 'timestamp': now}
    return data, False

@app.route('/stock', methods=['GET'])
def get_stock():
    symbol = request.args.get('symbol', '')
    if not symbol:
        return jsonify({'error': 'No symbol provided'}), 400
    if not symbol.endswith('.NS') and not symbol.endswith('.BO'):
        symbol = f'{symbol}.NS'
    try:
        data, from_cache = fetch_stock_data(symbol)
        return jsonify({
            'status': 'success',
            'symbol': symbol,
            'from_cache': from_cache,
            'data': data
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

@app.route('/check_signals', methods=['POST'])
def check_signals():
    db, messaging = get_firebase()
    if not db:
        return jsonify({'status': 'error', 'message': 'Firebase not initialized'}), 500
    try:
        from firebase_admin import firestore as fs
        users_ref = db.collection('users').stream()
        for user_doc in users_ref:
            uid = user_doc.id
            user_data = user_doc.to_dict()
            fcm_token = user_data.get('fcmToken')
            if not fcm_token:
                continue

            pe_threshold = 22.5
            div_threshold = 1.0
            try:
                thresh_doc = db.collection('users').document(uid)\
                    .collection('settings').document('thresholds').get()
                if thresh_doc.exists:
                    thresh_data = thresh_doc.to_dict()
                    pe_threshold = thresh_data.get('peXpbv', 22.5)
                    div_threshold = thresh_data.get('dividendYield', 1.0)
            except:
                pass

            stocks = db.collection('users').document(uid)\
                .collection('stocks').stream()
            triggered = []

            for stock_doc in stocks:
                s = stock_doc.to_dict()
                ticker_sym = s.get('ticker', '')
                if not ticker_sym:
                    continue
                try:
                    data, _ = fetch_stock_data(f'{ticker_sym}.NS')
                    price = data['last_price']
                    pe = data['pe_ratio']
                    eps = s.get('manualEps') or data['earnings_per_share']
                    bv = s.get('manualBookValue') or data['book_value']
                    div = data['dividend_yield'] * 100

                    graham = math.sqrt(22.5 * eps * bv) if eps > 0 and bv > 0 else 0
                    pbv = price / bv if bv > 0 else 0
                    pex_pbv = pe * pbv

                    if graham > 0 and price < graham and pex_pbv > 0 and pex_pbv < pe_threshold and div >= div_threshold:
                        triggered.append(s.get('name', ticker_sym))
                        db.collection('users').document(uid)\
                            .collection('alerts').add({
                                'stockName': s.get('name', ticker_sym),
                                'ticker': ticker_sym,
                                'livePrice': price,
                                'grahamValue': graham,
                                'pexPbv': pex_pbv,
                                'dividendYield': div / 100,
                                'triggeredAt': fs.SERVER_TIMESTAMP,
                            })
                except Exception as e:
                    print(f'Error {ticker_sym}: {e}')
                    continue

            if triggered:
                from firebase_admin import messaging as msg
                message = msg.Message(
                    notification=msg.Notification(
                        title='Risku Rasigan 📈',
                        body=f'Kanna {len(triggered)} laddu thinna aasaya aasaya aasaya 🍬',
                    ),
                    token=fcm_token,
                )
                msg.send(message)

        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)