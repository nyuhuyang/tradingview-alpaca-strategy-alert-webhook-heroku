from flask import Flask, render_template, request,logging
import alpaca_trade_api as tradeapi
import config, json, requests
# in two terminal windows with ml4t, run:
# ngrok http --domain=safe-ray-blessed.ngrok-free.app 80
# python app.py

app = Flask(__name__)

#api = tradeapi.REST(config.API_KEY, config.API_SECRET, base_url='https://paper-api.alpaca.markets')
api = tradeapi.REST(config.API_KEY, config.API_SECRET, base_url='https://api.alpaca.markets')

@app.route('/')
def dashboard():
    orders = api.list_orders(status='all')
    
    return render_template('dashboard.html', alpaca_orders=orders)

@app.route('/webhook', methods=['POST'])
def webhook():
    webhook_message = json.loads(request.data)
    print('#############################################')
    print('#===========================================#')

    print(webhook_message)
    if webhook_message['passphrase'] != config.WEBHOOK_PASSPHRASE:
        return {
           'code': 'error',
            'message': 'nice try buddy'
       }
    price = float(webhook_message['strategy']['order_price'])
    quantity = webhook_message['strategy']['order_contracts']
    symbol = webhook_message['ticker']
    order_action = webhook_message['strategy']['order_action']
    position_number = webhook_message['strategy']['position_number']
    prev_market_position = webhook_message['strategy']['prev_market_position']
    
    account = api.get_account()
    
    max_quantity = float(quantity)*float(account.daytrading_buying_power)/30000/4/int(position_number) #daytrading_buying_power = 4 * (last_equity - last_maintenance_margin)
    try:
        quote = api.get_latest_quote(symbol)
        bid_price = quote.bp
        if price > bid_price:
            price = bid_price
    except Exception as e:
        if 'no quote found for' in str(e):
            logging.warning(f"{symbol}: get_alpaca_bid_ask: Error for symbol: {e}")
        else:
            logging.warning(f"{symbol}: get_alpaca_bid_ask: Error retrieving bid/ask prices: {e}")

    # close all orders
    #orders = api.list_orders()
    #for order in orders:
    #    api.cancel_order(order.id)
    # Get a list of all open positions
    positions = []
    portfolio = api.list_positions()
    # Print the quantity of shares for each position.
    # get all symbols of all open positions and store in a list

    # Iterate through the list of positions and close each one
    for position in portfolio:
        positions.append(position.symbol)
        print("{} shares of {}".format(position.qty, position.symbol))
        if position.symbol == symbol and int(position.qty) > 0 and order_action == "sell":
            print("Closing position for ", position.symbol, " X ", position.qty)
            order = api.submit_order(
                    symbol=position.symbol,
                    qty=position.qty,
                    side='sell',
                    type='market',
                    time_in_force='gtc'
                    )
            print(order)
        if position.symbol == symbol and int(position.qty) > 0 and order_action == "buy":
            possible_quantity = min(int(max_quantity),int(float(account.cash)/price))
            print("Position open for ",symbol, " X ", possible_quantity)
            order = api.submit_order(
                    symbol=symbol,
                    qty=str(possible_quantity),
                    side='buy',
                    type='limit',
                    time_in_force='day',
                    limit_price = price
                    )
            print(order)
    
    if  (portfolio == [] or (symbol not in positions)) and order_action == "buy":
        possible_quantity = min(int(max_quantity),int(float(account.cash)/price))
        print("Position new open for ",symbol, " X ", possible_quantity)
        order = api.submit_order(
                symbol=symbol,
                qty=str(possible_quantity),
                side='buy',
                type='limit',
                time_in_force='day',
                limit_price = price
                )
        print(order)
    
    return {    'code': 'success',
                'message': 'order executed successfully'}
    

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=80, debug=False)