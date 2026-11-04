"""Typed read-only access to the supplied operational snapshot."""
import csv
import json
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from difflib import get_close_matches
from .paths import DATA

CATEGORY_ALIASES = {
    'electric guitars': 'guitarras', 'electric guitar': 'guitarras',
    'bass guitars': 'baixos', 'bass guitar': 'baixos',
    'acoustic guitars': 'violoes', 'acoustic guitar': 'violoes',
    'classical guitars': 'violoes', 'classical guitar': 'violoes',
    'drums and percussion': 'baterias', 'drums': 'baterias', 'drum': 'baterias',
    'keyboards': 'teclados', 'keyboard': 'teclados', 'pianos': 'teclados', 'piano': 'teclados',
    'guitars': 'guitarras', 'guitar': 'guitarras', 'bass': 'baixos',
    'acoustic': 'violoes', 'violao': 'violoes', 'ukulele': 'ukuleles',
    'beginner': 'iniciante', 'beginners': 'iniciante',
}


def search_tokens(query):
    query = normalize(query)
    for phrase, replacement in CATEGORY_ALIASES.items():
        query = re.sub(r'\b' + re.escape(phrase) + r'\b', replacement, query)
    stop = set('instrument instruments instrumento instrumentos product products available options for to a an the de do da para com um uma e'.split())
    return [t for t in re.findall(r'[a-z0-9]+', query) if t not in stop]


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

    def products(self, query='', max_price=None, available_only=True, promotion_only=False, offset=0):
        if type(offset) is not int or offset < 0:
            raise ValueError('offset must be a nonnegative integer')
        if type(promotion_only) is not bool or type(available_only) is not bool:
            raise ValueError('catalog flags must be boolean')
        categories = {r['category_id']: r['name'] for r in self.rows('categories')}
        promotions = self.rows('promotions')
        tokens = search_tokens(query)
        model_comparison = len(tokens) > 1 and all(re.fullmatch(r'[a-z]+\d+[a-z0-9-]*', t) for t in tokens)
        results = []
        if max_price is not None and (not Decimal(str(max_price)).is_finite() or Decimal(str(max_price)) < 0):
            raise ValueError('max_price must be a finite nonnegative number')
        for row in self.rows('products'):
            searchable = normalize(' '.join([row['name'], categories.get(row['category_id'], ''), row['description'], row['specs']]))
            words = re.findall(r'[a-z0-9]+', searchable)
            if model_comparison:
                if not any(re.search(r'\b' + re.escape(t) + r'\b', normalize(row['name'])) for t in tokens):
                    continue
            elif not all(t in searchable or (t == 'violoes' and 'violao' in searchable)
                       or (len(t) >= 5 and not any(c.isdigit() for c in t)
                           and get_close_matches(t, words, n=1, cutoff=.88)) for t in tokens):
                continue
            stock = int(row['stock_quantity'])
            available = row['status'] == 'active' and stock > 0
            if available_only and not available:
                continue
            discounts = [Decimal(p['discount_percent']) for p in promotions
                         if p['product_id'] == row['product_id'] and p['is_active'] == '1']
            discount = max(discounts, default=Decimal(0)) if available else Decimal(0)
            if promotion_only and not discount:
                continue
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
                'total_matches': len(results), 'offset': offset,
                'next_offset': offset + 10 if offset + 10 < len(results) else None,
                'products': results[offset:offset + 10],
                'note': 'At most 10 matches per page, sorted by current price. Use next_offset for more results; promotion_only filters before paging. Not a live inventory integration. Active flag is authoritative; no promotion dates were supplied.'}

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
