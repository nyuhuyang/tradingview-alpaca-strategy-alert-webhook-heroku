import datetime
import pytz
from flask import Flask, render_template, request,logging
import alpaca_trade_api as tradeapi
import config, json, requests
# in two terminal windows with ml4t, run:
# ngrok http --domain=safe-ray-blessed.ngrok-free.app 80
# python app.py

app = Flask(__name__)

#api = tradeapi.REST(config.API_KEY, config.API_SECRET, base_url='https://paper-api.alpaca.markets')
api = tradeapi.REST(config.API_KEY, config.API_SECRET, base_url='https://api.alpaca.markets')
# Function to check if a given time is during extended hours


# Utility function to check extended hours
def is_extended_hours(timestamp, exchange):
    if exchange == "NYSE":
        eastern = pytz.timezone('America/New_York')
        time = timestamp.astimezone(eastern)
        market_open = datetime.time(9, 30)  # 9:30 AM ET
        market_close = datetime.time(16, 0)  # 4:00 PM ET
        pre_market_start = datetime.time(4, 0)  # 4:00 AM ET
        after_market_end = datetime.time(20, 0)  # 8:00 PM ET
        return time.time() < market_open and time.time() >= pre_market_start or time.time() > market_close and time.time() <= after_market_end
    return False
    
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
    comment = webhook_message['strategy']['comment']
    
    # Get current time in UTC
    current_time = datetime.datetime.now(pytz.timezone('America/New_York'))
    is_extended = is_extended_hours(current_time, "NYSE")
    print("Is it extended hours?", is_extended)
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
    possible_quantity = min(int(max_quantity),int(float(account.cash)/price))

    # close all orders
    orders = api.list_orders()
    for order in orders:
        api.cancel_order(order.id)
    # Get a list of all open positions
    positions = []
    portfolio = api.list_positions()
    # Print the quantity of shares for each position.
    # get all symbols of all open positions and store in a list

    for position in portfolio:
        positions.append(position.symbol)
        print("{} shares of {}".format(position.qty, position.symbol))
        
        if position.symbol == symbol and int(position.qty) > 0:
            if order_action == "sell":
                print("Closing position for ", position.symbol, " X ", position.qty)
                # Always use limit order for sells during extended hours
                if is_extended:
                    order = api.submit_order(
                        symbol=position.symbol,
                        qty=position.qty,
                        side='sell',
                        type='limit',
                        time_in_force='day',
                        limit_price=price,  # Ensure you have a realistic limit price
                        extended_hours=True
                    )
                else:
                    # Normal market order during regular hours
                    order = api.submit_order(
                        symbol=position.symbol,
                        qty=position.qty,
                        side='sell',
                        type='market',
                        time_in_force='gtc',
                        extended_hours=False
                    )
                print(order)
                
            elif order_action == "buy":
                if comment == "LONG TvIS entry":
                    if not is_extended:
                        # Use market order only during regular hours for "LONG TvIS entry"
                        print("Open market position for ", position.symbol, " X ", possible_quantity)
                        order = api.submit_order(
                            symbol=symbol,
                            qty=str(possible_quantity),
                            side='buy',
                            type='market',
                            time_in_force='gtc',
                            extended_hours=False
                        )
                    else:
                        # Use limit order during extended hours even for "LONG TvIS entry"
                        print("Open limit position for ", position.symbol, " X ", possible_quantity)
                        order = api.submit_order(
                            symbol=symbol,
                            qty=str(possible_quantity),
                            side='buy',
                            type='limit',
                            time_in_force='day',
                            limit_price=price,
                            extended_hours=True
                        )
                else:
                    # Use limit order in all other conditions
                    print("Open limit position for ", position.symbol, " X ", possible_quantity)
                    order = api.submit_order(
                        symbol=symbol,
                        qty=str(possible_quantity),
                        side='buy',
                        type='limit',
                        time_in_force='day',
                        limit_price=price,
                        extended_hours=is_extended
                    )
                print(order)
    
    if (portfolio == [] or (symbol not in positions)) and order_action == "buy":
        print("Open position for ", symbol, " X ", possible_quantity)
        if comment == "LONG TvIS entry" and not extended_hours:
            # Market order only during regular hours for "LONG TvIS entry"
            order = api.submit_order(
                symbol=symbol,
                qty=str(possible_quantity),
                side='buy',
                type='market',
                time_in_force='gtc',
                extended_hours=False
            )
        else:
            # Always use limit day order during extended hours or for other comments
            print("Open limit position for ", symbol, " X ", possible_quantity)
            order = api.submit_order(
                symbol=symbol,
                qty=str(possible_quantity),
                side='buy',
                type='limit',
                time_in_force='day',
                limit_price=price,
                extended_hours=is_extended
            )
        print(order)
    
    return {    'code': 'success',
                'message': 'order executed successfully'}
    

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=80, debug=False)