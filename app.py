from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf

app = Flask(__name__)
CORS(app)

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)