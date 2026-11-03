from decimal import Decimal
from emporio.store import Store
from emporio.policies import Policies


def test_catalog_filters_stock_and_budget():
    result = Store().products('violão', 1000)
    assert result['total_matches'] > 0
    assert all(p['available'] and Decimal(p['price_brl']) <= 1000 for p in result['products'])


def test_inactive_promotions_do_not_change_price():
    store = Store()
    for product in store.products('Takamine GD20', available_only=False)['products']:
        assert product['discount_percent'] == '0'
        assert product['list_price_brl'] == product['price_brl']


def test_active_promotion_does_not_stack_pix():
    store = Store()
    active = next(p for p in store.rows('promotions') if p['is_active'] == '1'
                  and any(r['product_id'] == p['product_id'] and r['status'] == 'active'
                          and int(r['stock_quantity']) > 0 for r in store.rows('products')))
    row = next(r for r in store.rows('products') if r['product_id'] == active['product_id'])
    product = store.products(row['name'])['products'][0]
    assert Decimal(product['price_brl']) < Decimal(product['list_price_brl'])
    assert product['pix_price_brl'] == product['price_brl']


def test_orders_require_identity_and_enforce_ownership():
    store = Store()
    assert store.order(1)['error'] == 'authentication_required'
    assert store.order(1, 7)['error'] == 'not_found'
    assert store.order(1, 3)['order_id'] == 1
    assert 'email' not in store.order(1, 3)


def test_live_snapshot_reads_not_cached(tmp_path):
    import shutil
    from emporio.store import DATA
    for path in DATA.glob('*.csv'):
        shutil.copy(path, tmp_path / path.name)
    store = Store(tmp_path)
    assert store.products('Yamaha C40')['products'][0]['stock_quantity'] == 12
    path = tmp_path / 'products.csv'
    path.write_text(path.read_text().replace(',12,active,', ',0,active,'))
    assert store.products('Yamaha C40')['products'] == []


def test_policy_retrieval_english_and_portuguese():
    policies = Policies()
    for query in ['Can I return my order?', 'Posso devolver meu pedido?']:
        assert 4 in [m['page'] for m in policies.search(query)['matches']]


def test_compound_english_category_matches_portuguese_catalog():
    store = Store()
    expected = store.products('violão', 1000)['total_matches']
    for query in ['acoustic guitar', 'acoustic guitars', 'classical guitar', 'acoustic instruments']:
        assert store.products(query, 1000)['total_matches'] == expected > 0


def test_online_withdrawal_retrieval_separates_exchange_exceptions():
    result = Policies().search('online withdrawal arrependimento')
    assert len(result['matches']) == 1
    match = result['matches'][0]
    assert match['page'] == 4 and match['section'] == '4.1'
    assert '7 (sete) dias' in match['text']
    assert '4.4' not in match['text'] and 'venda final' not in match['text']


def test_catalog_pagination_can_reach_every_match_without_duplicates():
    store = Store()
    first = store.products('violão', 1000)
    second = store.products('violão', 1000, offset=first['next_offset'])
    ids = [p['product_id'] for p in first['products'] + second['products']]
    assert len(ids) == first['total_matches'] == len(set(ids))
    assert second['next_offset'] is None


def test_promotions_are_filtered_before_the_ten_product_limit(tmp_path):
    import csv
    import shutil
    from emporio.store import DATA
    for path in DATA.glob('*.csv'):
        shutil.copy(path, tmp_path / path.name)
    store = Store(tmp_path)
    expensive = next(row for row in store.rows('products')
                     if row['status'] == 'active' and int(row['stock_quantity']) > 0
                     and Decimal(row['price_brl']) > 2000)
    with (tmp_path / 'promotions.csv').open('a', newline='') as stream:
        csv.writer(stream).writerow([999, expensive['product_id'], 10, 'Test offer', 1])
    result = store.products(promotion_only=True)
    assert int(expensive['product_id']) in [p['product_id'] for p in result['products']]
    assert all(Decimal(p['discount_percent']) > 0 for p in result['products'])


def test_defect_return_queries_do_not_retrieve_only_withdrawal_policy():
    policies = Policies()
    for query in ['posso devolver um produto com defeito?', 'return and warranty for defective item']:
        result = policies.search(query)
        assert any('4.2' in match['text'] for match in result['matches'])


def test_exact_model_search_tolerates_question_punctuation():
    assert Store().products('Yamaha C40?')['products'][0]['product_id'] == 81
