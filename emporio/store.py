"""Typed read-only access to the supplied operational snapshot."""
import csv
import json
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value)).lower()
                   if not unicodedata.combining(c))


def money(value):
    return str(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


class Store:
    def __init__(self, data_dir=DATA):
        self.data_dir = Path(data_dir)

    def rows(self, table):
        # Table names are internal constants, never SQL or user-supplied paths.
        with (self.data_dir / f'{table}.csv').open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))

    def products(self, query='', max_price=None, available_only=True):
        categories = {r['category_id']: r['name'] for r in self.rows('categories')}
        promotions = self.rows('promotions')
        aliases = {'violao': 'violoes', 'guitar': 'guitarras', 'acoustic': 'violoes', 'bass': 'baixos', 'keyboard': 'teclados', 'ukulele': 'ukuleles'}
        normalized_query = normalize(query)
        for phrase in ('acoustic guitars', 'acoustic guitar', 'classical guitars', 'classical guitar'):
            normalized_query = normalized_query.replace(phrase, 'violoes')
        generic_terms = {'instrument', 'instruments', 'instrumento', 'instrumentos', 'product', 'products', 'available', 'options'}
        tokens = [aliases.get(t, t) for t in normalized_query.split() if t not in generic_terms]
        results = []
        if max_price is not None and (not Decimal(str(max_price)).is_finite() or Decimal(str(max_price)) < 0):
            raise ValueError('max_price must be a finite nonnegative number')
        for row in self.rows('products'):
            searchable = normalize(row['name'] + ' ' + categories.get(row['category_id'], ''))
            if not all(t in searchable or (t == 'violoes' and 'violao' in searchable) for t in tokens):
                continue
            stock = int(row['stock_quantity'])
            available = row['status'] == 'active' and stock > 0
            if available_only and not available:
                continue
            discounts = [Decimal(p['discount_percent']) for p in promotions
                         if p['product_id'] == row['product_id'] and p['is_active'] == '1']
            discount = max(discounts, default=Decimal(0)) if available else Decimal(0)
            price = Decimal(row['price_brl'])
            current = Decimal(money(price * (1 - discount / 100)))
            if max_price is not None and current > Decimal(str(max_price)):
                continue
            results.append(dict(product_id=int(row['product_id']), name=row['name'],
                                category=categories.get(row['category_id']), description=row['description'],
                                status=row['status'], stock_quantity=stock, available=available,
                                list_price_brl=money(price), price_brl=money(current),
                                discount_percent=str(discount),
                                pix_price_brl=money(current if discount else price * Decimal('.95')),
                                specs=json.loads(row['specs'])))
        results.sort(key=lambda x: (Decimal(x['price_brl']), x['product_id']))
        return {'source': 'products.csv + categories.csv + promotions.csv (supplied snapshot)',
                'total_matches': len(results), 'products': results[:10],
                'note': 'At most 10 cheapest matches. Not a live inventory integration. Active flag is authoritative; no promotion dates were supplied.'}

    def order(self, order_id, trusted_customer_id=None):
        # Identity comes from the application, not the LLM, a name or a phone in chat.
        if trusted_customer_id is None:
            return {'error': 'authentication_required', 'message': 'Please use an authenticated channel or contact the store team.'}
        matches = [r for r in self.rows('orders')
                   if r['order_id'] == str(order_id) and r['customer_id'] == str(trusted_customer_id)]
        if not matches:
            return {'error': 'not_found', 'message': 'No order available for this authenticated customer.'}
        row = matches[0]
        items = [{'product_id': int(r['product_id']), 'quantity': int(r['quantity'])}
                 for r in self.rows('order_items') if r['order_id'] == row['order_id']]
        return {'source': 'orders.csv + order_items.csv (supplied snapshot)',
                'order_id': int(row['order_id']), 'status': row['status'],
                'order_date': row['order_date'], 'estimated_delivery': row['estimated_delivery'],
                'tracking_code': row['tracking_code'] if row['status'] in ('shipped', 'delivered') else None,
                'total_brl': money(row['total_brl']), 'items': items,
                'note': 'Estimated delivery is historical snapshot data, not a current delivery promise. No actual received_at or sales channel is supplied.'}
