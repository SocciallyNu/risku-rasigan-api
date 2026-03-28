from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import firebase_admin
from firebase_admin import credentials, firestore, messaging
import math
import os
import json

app = Flask(__name__)
CORS(app)

# Initialize Firebase Admin
if not firebase_admin._apps:
    firebase_creds = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT', '{}'))
    cred = credentials.Certificate(firebase_creds)
    firebase_admin.initialize_app(cred)

db = firestore.client()

@app.route('/stock', methods=['GET'])
def get_stock():
    symbol = request.args.get('symbol', '')
    if not symbol:
        return jsonify({'error': 'No symbol provided'}), 400
    if not symbol.endswith('.NS') and not symbol.endswith('.BO'):
        symbol = f'{symbol}.NS'
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return jsonify({
            'status': 'success',
            'symbol': symbol,
            'data': {
                'last_price': info.get('currentPrice') or info.get('regularMarketPrice') or 0,
                'pe_ratio': info.get('trailingPE') or 0,
                'earnings_per_share': info.get('trailingEps') or 0,
                'book_value': info.get('bookValue') or 0,
                'dividend_yield': info.get('dividendYield') or 0,
                'sector': info.get('sector') or '',
                'company_name': info.get('longName') or symbol,
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

@app.route('/check_signals', methods=['POST'])
def check_signals():
    try:
        users_ref = db.collection('users').stream()
        for user_doc in users_ref:
            uid = user_doc.id
            user_data = user_doc.to_dict()
            fcm_token = user_data.get('fcmToken')
            if not fcm_token:
                continue

            # Load thresholds
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

            # Load stocks
            stocks = db.collection('users').document(uid)\
                .collection('stocks').stream()

            triggered = []

            for stock_doc in stocks:
                s = stock_doc.to_dict()
                ticker_sym = s.get('ticker', '')
                if not ticker_sym:
                    continue

                try:
                    t = yf.Ticker(f'{ticker_sym}.NS')
                    info = t.info
                    price = info.get('currentPrice') or info.get('regularMarketPrice') or 0
                    pe = info.get('trailingPE') or 0
                    eps = s.get('manualEps') or info.get('trailingEps') or 0
                    bv = s.get('manualBookValue') or info.get('bookValue') or 0
                    div = (info.get('dividendYield') or 0) * 100

                    graham = math.sqrt(22.5 * eps * bv) if eps > 0 and bv > 0 else 0
                    pbv = price / bv if bv > 0 else 0
                    pex_pbv = pe * pbv

                    graham_ok = graham > 0 and price < graham
                    pe_ok = pex_pbv > 0 and pex_pbv < pe_threshold
                    div_ok = div >= div_threshold

                    if graham_ok and pe_ok and div_ok:
                        triggered.append(s.get('name', ticker_sym))
                        db.collection('users').document(uid)\
                            .collection('alerts').add({
                                'stockName': s.get('name', ticker_sym),
                                'ticker': ticker_sym,
                                'livePrice': price,
                                'grahamValue': graham,
                                'pexPbv': pex_pbv,
                                'dividendYield': div / 100,
                                'triggeredAt': firestore.SERVER_TIMESTAMP,
                            })
                except:
                    continue

            if triggered:
                count = len(triggered)
                message = messaging.Message(
                    notification=messaging.Notification(
                        title='Risku Rasigan 📈',
                        body=f'Kanna {count} laddu thinna aasaya aasaya aasaya 🍬',
                    ),
                    token=fcm_token,
                )
                messaging.send(message)

        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)