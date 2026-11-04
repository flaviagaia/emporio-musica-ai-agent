"""Scripted offline simulator; real CSV/PDF tools are dispatched by Agent."""
import json
import re
from .store import normalize, Store

def tool_call(name, args):
    return {'role': 'assistant', 'content': None, 'tool_calls': [{
        'id': 'mock_call_1', 'type': 'function',
        'function': {'name': name, 'arguments': json.dumps(args)}}]}


def answer(text):
    return {'role': 'assistant', 'content': text}


def mock_message(messages):
    """Limited scripted simulator, NOT a language model or a fallback for API errors.

    Routing and wording are hand-authored for the documented demo scenarios.
    Tools still run in Agent; prices, stock and order status come from their results.
    """
    user = next(m['content'] for m in reversed(messages) if m['role'] == 'user')
    query = normalize(user)
    if messages[-1]['role'] == 'tool':
        return answer(mock_summary(query, json.loads(messages[-1]['content'])))
    if any(x in query for x in ('ignore your', 'all customers', 'customer emails', 'all customer')):
        return answer('I cannot share customer records. I can help with instruments and store policies.')
    if any(x in query for x in ('cable', 'palheta', 'amplifier', 'cordas avulsas')):
        return tool_call('search_policies', {'query': 'acessorios cabos escopo'})
    order = re.search(r'(?:order|pedido)\s*#?\s*(\d+)', query)
    if order and not any(x in query for x in ('return', 'refund', 'regret')):
        return tool_call('get_order', {'order_id': int(order.group(1))})
    for product in Store().rows('products'):
        if normalize(product['name']) in query:
            return tool_call('search_products', {'query': product['name'], 'max_price': None, 'available_only': False})
    if 'c40' in query:
        return tool_call('search_products', {'query': 'Yamaha C40', 'max_price': None, 'available_only': False})
    if 'gd20' in query:
        return tool_call('search_products', {'query': 'Takamine GD20', 'max_price': None, 'available_only': False})
    if any(x in query for x in ('promotion', 'promocao', 'discounted')):
        # Retrieve all available instruments. Simulator filters active promotions in summary.
        return tool_call('search_products', {'query': '', 'max_price': None, 'available_only': True, 'promotion_only': True})
    if any(x in query for x in ('acoustic', 'violao', 'violoes', 'under', 'up to')):
        budget = re.search(r'(?:up to|under|ate|brl|r\$)\s*(\d+(?:\.\d{1,2})?)', query)
        return tool_call('search_products', {'query': 'violão', 'max_price': float(budget.group(1)) if budget else None,
                                            'available_only': True})
    if any(x in query for x in ('address', 'endereco', 'hours', 'opening')):
        return tool_call('search_policies', {'query': 'endereco horario funcionamento'})
    if any(x in query for x in ('payment', 'installment', 'pagamento', 'parcelamento')):
        return tool_call('search_policies', {'query': 'pagamento parcelamento pix'})
    if any(x in query for x in ('shipping', 'delivery', 'frete', 'entrega')):
        return tool_call('search_policies', {'query': 'frete entrega'})
    if any(x in query for x in ('return', 'regret', 'received', 'refund', 'devolver')):
        return tool_call('search_policies', {'query': 'online return refund devolucao arrependimento'})
    return answer('Offline mock demo: try acoustic instruments up to BRL 1000, Yamaha C40 PIX price, store address, returns, or order 1. Use --mode groq for open-ended conversation.')


def mock_summary(query, result):
    if result.get('error'):
        return result.get('message', 'I could not retrieve reliable information. Please contact the store team.')
    if 'products' in result:
        products = result['products']
        if any(x in query for x in ('promotion', 'promocao', 'discounted')):
            products = [p for p in products if float(p['discount_percent']) > 0]
            if not products:
                return 'No active promotion appears in these returned matches. The mock has limited search coverage; use Groq or narrow the product query.'
        if not products:
            return 'No matching product is available in the supplied snapshot. Please ask the team about alternatives.'
        lines = []
        for p in products:
            availability = f"{p['stock_quantity']} units" if p['available'] else p['status'] + ', unavailable'
            lines.append(f"{p['name']}: BRL {p['price_brl']} (list BRL {p['list_price_brl']}; discount {p['discount_percent']}%; PIX BRL {p['pix_price_brl']}; {availability}).")
        return '\n'.join(lines) + '\nSource: supplied CSV snapshot, not live inventory. Promotional and PIX discounts do not stack.'
    if 'order_id' in result:
        return (f"Order {result['order_id']} status: {result['status']}. "
                f"Tracking: {result['tracking_code'] or 'not available'}. "
                'Source: historical order snapshot; estimated dates are not current delivery promises.')
    pages = {m['page'] for m in result.get('matches', [])}
    if any(x in query for x in ('address', 'endereco', 'hours', 'opening')) and 2 in pages:
        return ('The store is at Rua 14 de Maio, 3200, Centro, Campo Grande - MS, CEP 79202-333. '
                'Weekdays: 09:00-18:00; Saturday: 09:00-13:00; Sundays and holidays: closed. '
                'Source: store policy, PDF page 2. Offline mock template checked against the retrieved page.')
    if any(x in query for x in ('cable', 'palheta', 'amplifier', 'cordas avulsas')) and 6 in pages:
        return 'We focus on musical instruments and do not sell cables or amplifiers. I can help you find an instrument. Source: store policy, PDF page 6.'
    if any(x in query for x in ('payment', 'installment', 'pagamento', 'parcelamento')) and 3 in pages:
        return ('The manual lists PIX, debit cards, credit cards and bank slips. PIX gives 5% off the list price; credit cards allow up to 12 interest-free installments. '
                'The general table and detailed installment tiers have conflicting minimum amounts, so please confirm the installment conditions with staff. Source: PDF page 3.')
    if any(x in query for x in ('shipping', 'delivery', 'frete', 'entrega')) and 4 in pages:
        return ('For metropolitan Campo Grande, the manual states free shipping above BRL 500 and a BRL 35 fee below BRL 500, with an estimated 1–3 business days. '
                'Exactly BRL 500 is not specified; please ask the team to confirm. Other destinations require a quote based on destination and parcel details. Source: PDF pages 4–5. These are policy estimates, not a live delivery promise.')
    if any(x in query for x in ('return', 'regret', 'received', 'refund', 'devolver')) and 4 in pages:
        if all(x in query for x in ('online', 'three days', 'unused', 'not customized')):
            return ('You are within the stated online return window. Please confirm the original packaging, accessories and manuals; unused does not establish those facts. '
                    'It states store-paid return shipping and refund through the original payment method within ten business days. '
                    'Please contact the team to confirm and arrange the return; I cannot approve or process it. Source: PDF page 4.')
        return ('Was the purchase online, when did you actually receive it, and is it unused with original packaging and no customization? '
                'The supplied manual describes a seven-calendar-day online withdrawal period. I need those facts before applying it. Source: PDF page 4.')
    return 'The offline mock cannot summarize this evidence. Please use Groq or contact the store team.'
