"""Validate the entire reference dataset and report its reproducible version."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from .store import Store, DATA


class DataValidationError(ValueError):
    pass


def validate_data(data_dir=DATA):
    store = Store(data_dir)
    errors = []
    tables = {}
    primary = {'categories': 'category_id', 'products': 'product_id', 'customers': 'customer_id',
               'orders': 'order_id', 'promotions': 'promotion_id'}
    required = {
        'categories': {'category_id', 'name'},
        'products': {'product_id', 'category_id', 'name', 'price_brl', 'stock_quantity', 'status', 'specs'},
        'customers': {'customer_id'}, 'orders': {'order_id', 'customer_id', 'total_brl', 'status'},
        'promotions': {'promotion_id', 'product_id', 'discount_percent', 'is_active'},
        'order_items': {'order_id', 'product_id', 'quantity'},
    }
    for name, columns in required.items():
        try:
            rows = store.rows(name)
            if not rows or not columns <= set(rows[0]):
                errors.append(f'{name}: missing rows or required columns')
                continue
            tables[name] = rows
        except (OSError, ValueError):
            errors.append(f'{name}: unreadable table')
    if errors:
        raise DataValidationError('; '.join(errors))
    ids = {}
    for name, key in primary.items():
        values = [row[key] for row in tables[name]]
        ids[name] = set(values)
        if len(ids[name]) != len(values) or any(not v.isdigit() or int(v) < 1 for v in values):
            errors.append(f'{name}: duplicate or invalid IDs')
    links = [('products', 'category_id', 'categories'), ('orders', 'customer_id', 'customers'),
             ('promotions', 'product_id', 'products'), ('order_items', 'product_id', 'products'),
             ('order_items', 'order_id', 'orders')]
    for table, key, parent in links:
        if any(row[key] not in ids[parent] for row in tables[table]):
            errors.append(f'{table}: invalid {key} relationship')
    numeric = [('products', 'price_brl', 0, None, False), ('products', 'stock_quantity', 0, None, True),
               ('orders', 'total_brl', 0, None, False), ('order_items', 'quantity', 1, None, True),
               ('promotions', 'discount_percent', 0, 100, False)]
    for table, key, minimum, maximum, integral in numeric:
        for row in tables[table]:
            try:
                value = Decimal(row[key])
                if not value.is_finite() or value < minimum or (maximum is not None and value > maximum) or (integral and value != value.to_integral_value()):
                    raise ValueError()
            except (InvalidOperation, ValueError, TypeError):
                errors.append(f'{table}: invalid {key}')
                break
    for row in tables['products']:
        try:
            if not isinstance(json.loads(row['specs']), dict):
                raise ValueError()
        except (ValueError, TypeError):
            errors.append('products: invalid specifications')
            break
    if any(row['is_active'] not in ('0', '1') for row in tables['promotions']):
        errors.append('promotions: invalid active flag')
    if any(row['status'] not in ('active', 'discontinued', 'coming_soon') for row in tables['products']):
        errors.append('products: invalid status')
    pairs = [(row['order_id'], row['product_id']) for row in tables['order_items']]
    if len(set(pairs)) != len(pairs):
        errors.append('order_items: duplicate order/product relationship')
    try:
        import pymupdf
        with pymupdf.open(store.data_dir / 'store_policies.pdf') as pdf:
            if not len(pdf) or not any(page.get_text().strip() for page in pdf):
                raise ValueError()
    except Exception:
        errors.append('store_policies: unreadable or empty PDF')
    if errors:
        raise DataValidationError('; '.join(errors))
    digest = hashlib.sha256()
    for path in sorted(store.data_dir.glob('*')):
        if path.suffix in ('.csv', '.pdf'):
            digest.update(path.name.encode()); digest.update(path.read_bytes())
    return {'valid': True, 'version_sha256': digest.hexdigest(),
            'checked_at_utc': datetime.now(timezone.utc).isoformat(),
            'rows': {name: len(rows) for name, rows in tables.items()}}


def main():
    parser = argparse.ArgumentParser(description='Validate Mel reference data')
    parser.add_argument('--data-dir', default=str(DATA))
    args = parser.parse_args()
    try:
        print(json.dumps(validate_data(args.data_dir), indent=2))
    except DataValidationError as error:
        parser.exit(1, f'Data validation failed: {error}\n')


if __name__ == '__main__':
    main()
