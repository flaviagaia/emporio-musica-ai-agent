"""Scripted offline simulator; real CSV/PDF tools are dispatched by Agent."""
import json
import re
from .store import normalize, Store
from .i18n import translate, format_money
from .presentation import chat_prose, product_reply

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
    language = 'pt' if any(m['role'] == 'system' and '[OUTPUT_LANGUAGE:pt]' in m['content'] for m in messages) else 'en'
    chat = any(m['role'] == 'system' and '[CHAT_PRESENTATION]' in m['content'] for m in messages)
    def reply(text):
        text = translate(text, language)
        return answer(chat_prose(text) if chat else text)
    user = next(m['content'] for m in reversed(messages) if m['role'] == 'user')
    query = normalize(user)
    if messages[-1]['role'] == 'tool':
        result = json.loads(messages[-1]['content'])
        if chat and result.get('products'):
            return reply(product_reply(result['products'], language))
        return reply(mock_summary(query, result, language))
    if any(x in query for x in ('ignore your', 'all customers', 'customer emails', 'all customer', 'ignore as instrucoes', 'todos os clientes', 'emails dos clientes')):
        return reply('I cannot share customer records. I can help with instruments and store policies.')
    if any(x in query for x in ('cable', 'cabos', 'palheta', 'amplifier', 'amplificador', 'cordas avulsas')):
        return tool_call('search_policies', {'query': 'acessorios cabos escopo'})
    order = re.search(r'(?:order|pedido)\s*#?\s*(\d+)', query)
    if order and not any(x in query for x in ('return', 'refund', 'regret', 'devolver', 'devolucao', 'arrepend')):
        return tool_call('get_order', {'order_id': int(order.group(1))})
    for product in Store().rows('products'):
        if normalize(product['name']) in query:
            return tool_call('search_products', {'query': product['name'], 'max_price': None, 'available_only': False})
    if 'c40' in query:
        return tool_call('search_products', {'query': 'Yamaha C40', 'max_price': None, 'available_only': False})
    if 'gd20' in query:
        return tool_call('search_products', {'query': 'Takamine GD20', 'max_price': None, 'available_only': False})
    if any(x in query for x in ('promotion', 'promocao', 'promocoes', 'ofertas', 'desconto', 'discounted')):
        # Retrieve all available instruments. Simulator filters active promotions in summary.
        return tool_call('search_products', {'query': '', 'max_price': None, 'available_only': True, 'promotion_only': True})
    if any(x in query for x in ('acoustic', 'violao', 'violoes', 'under', 'up to')):
        budget = re.search(r'(?:up to|under|ate|brl|r\$)\s*([\d.,]+)', query)
        return tool_call('search_products', {'query': 'violão', 'max_price': parse_budget(budget.group(1)) if budget else None,
                                            'available_only': True})
    if any(x in query for x in ('address', 'endereco', 'hours', 'opening', 'horario', 'funcionamento')):
        return tool_call('search_policies', {'query': 'endereco horario funcionamento'})
    if any(x in query for x in ('payment', 'installment', 'pagamento', 'parcelamento')):
        return tool_call('search_policies', {'query': 'pagamento parcelamento pix'})
    if any(x in query for x in ('shipping', 'delivery', 'frete', 'entrega')):
        return tool_call('search_policies', {'query': 'frete entrega'})
    if any(x in query for x in ('return', 'regret', 'received', 'refund', 'devolver', 'devolucao', 'arrepend', 'recebi')):
        return tool_call('search_policies', {'query': 'online return refund devolucao arrependimento'})
    return reply('Offline mock demo: try acoustic instruments up to BRL 1000, Yamaha C40 PIX price, store address, returns, or order 1. Use --mode groq for open-ended conversation.')


def mock_summary(query, result, language='en'):
    if language == 'pt':
        return mock_summary_pt(query, result)
    if result.get('error'):
        return result.get('message', 'I could not retrieve reliable information. Please contact the store team.')
    if 'products' in result:
        products = result['products']
        if any(x in query for x in ('promotion', 'promocao', 'promocoes', 'ofertas', 'desconto', 'discounted')):
            products = [p for p in products if float(p['discount_percent']) > 0]
            if not products:
                return 'No active promotion appears in these returned matches. The mock has limited search coverage; use Groq or narrow the product query.'
        if not products:
            return 'No matching product is available in the supplied snapshot. Please ask the team about alternatives.'
        lines = []
        for p in products:
            availability = f"{p['stock_quantity']} units" if p['available'] else p['status'] + ', unavailable'
            lines.append(f"{p['name']}: BRL {p['price_brl']} (list BRL {p['list_price_brl']}; discount {p['discount_percent']}%; PIX BRL {p['pix_price_brl']}; {availability}).")
        return '\n'.join(lines) + '\nSource: store catalog. Confirm prices and availability with the store. Promotional and PIX discounts do not stack.'
    if 'order_id' in result:
        return (f"Order {result['order_id']} status: {result['status']}. "
                f"Tracking: {result['tracking_code'] or 'not available'}. "
                'Source: historical order snapshot; estimated dates are not current delivery promises.')
    pages = {m['page'] for m in result.get('matches', [])}
    if any(x in query for x in ('address', 'endereco', 'hours', 'opening', 'horario', 'funcionamento')) and 2 in pages:
        return ('The store is at Rua 14 de Maio, 3200, Centro, Campo Grande - MS, CEP 79202-333. '
                'Weekdays: 09:00-18:00; Saturday: 09:00-13:00; Sundays and holidays: closed. '
                'Source: store policy, PDF page 2. Offline mock template checked against the retrieved page.')
    if any(x in query for x in ('cable', 'cabos', 'palheta', 'amplifier', 'amplificador', 'cordas avulsas')) and 6 in pages:
        return 'We focus on musical instruments and do not sell cables or amplifiers. I can help you find an instrument. Source: store policy, PDF page 6.'
    if any(x in query for x in ('payment', 'installment', 'pagamento', 'parcelamento')) and 3 in pages:
        return ('The manual lists PIX, debit cards, credit cards and bank slips. PIX gives 5% off the list price; credit cards allow up to 12 interest-free installments. '
                'The general table and detailed installment tiers have conflicting minimum amounts, so please confirm the installment conditions with staff. Source: PDF page 3.')
    if any(x in query for x in ('shipping', 'delivery', 'frete', 'entrega')) and 4 in pages:
        return ('For metropolitan Campo Grande, the manual states free shipping above BRL 500 and a BRL 35 fee below BRL 500, with an estimated 1–3 business days. '
                'Exactly BRL 500 is not specified; please ask the team to confirm. Other destinations require a quote based on destination and parcel details. Source: PDF pages 4–5. These are policy estimates, not a live delivery promise.')
    if any(x in query for x in ('return', 'regret', 'received', 'refund', 'devolver', 'devolucao', 'arrepend', 'recebi')) and 4 in pages:
        if all(x in query for x in ('online', 'three days', 'unused', 'not customized')):
            return ('You are within the stated online return window. Please confirm the original packaging, accessories and manuals; unused does not establish those facts. '
                    'It states store-paid return shipping and refund through the original payment method within ten business days. '
                    'Please contact the team to confirm and arrange the return; I cannot approve or process it. Source: PDF page 4.')
        return ('Was the purchase online, when did you actually receive it, and is it unused with original packaging and no customization? '
                'The supplied manual describes a seven-calendar-day online withdrawal period. I need those facts before applying it. Source: PDF page 4.')
    return 'The offline mock cannot summarize this evidence. Please use Groq or contact the store team.'


def parse_budget(value):
    value = value.rstrip('.,')
    if ',' in value and '.' in value:
        value = value.replace('.', '').replace(',', '.') if value.rfind(',') > value.rfind('.') else value.replace(',', '')
    elif re.fullmatch(r'\d{1,3}(?:[.,]\d{3})+', value):
        value = value.replace('.', '').replace(',', '')
    else:
        value = value.replace(',', '.')
    return float(value)


def mock_summary_pt(query, result):
    if result.get('error'):
        return translate(result.get('message', 'Unable to retrieve reliable data. Refer to the team.'), 'pt')
    if 'products' in result:
        products = result['products']
        if any(x in query for x in ('promotion', 'promocao', 'promocoes', 'ofertas', 'desconto', 'discounted')):
            products = [p for p in products if float(p['discount_percent']) > 0]
        if not products:
            return 'Nenhum instrumento corresponde à consulta na base fornecida. Consulte a equipe sobre alternativas.'
        lines = []
        for p in products:
            stock = f"{p['stock_quantity']} unidades em estoque" if p['available'] else 'indisponível: ' + translate(p['status'], 'pt')
            lines.append(f"{p['name']}: R$ {format_money(p['price_brl'], 'pt')} (tabela: R$ {format_money(p['list_price_brl'], 'pt')}; desconto: {p['discount_percent']}%; PIX: R$ {format_money(p['pix_price_brl'], 'pt')}; {stock}).")
        return '\n'.join(lines) + '\nFonte: catálogo da loja. Confirme preços e disponibilidade com a equipe. PIX e descontos promocionais não se acumulam.'
    if 'order_id' in result:
        return (f"Pedido {result['order_id']}: {translate(result['status'], 'pt')}. "
                f"Rastreamento: {result.get('tracking_code') or 'não disponível'}. "
                'Fonte: base histórica de pedidos; datas estimadas não representam uma nova promessa de entrega.')
    pages = {m['page'] for m in result.get('matches', [])}
    if any(x in query for x in ('address', 'endereco', 'hours', 'opening', 'horario', 'funcionamento')) and 2 in pages:
        return ('A loja fica na Rua 14 de Maio, 3200, Centro, Campo Grande - MS, CEP 79202-333. '
                'Atendimento de segunda a sexta, das 09h às 18h; sábado, das 09h às 13h. Domingos e feriados: fechado. Fonte: manual, página 2.')
    if any(x in query for x in ('cable', 'cabos', 'palheta', 'amplifier', 'amplificador', 'cordas avulsas')) and 6 in pages:
        return 'Trabalhamos com instrumentos musicais e não vendemos cabos ou amplificadores. Posso ajudar você a encontrar um instrumento. Fonte: manual, página 6.'
    if any(x in query for x in ('payment', 'installment', 'pagamento', 'parcelamento')) and 3 in pages:
        return ('O manual lista PIX, cartão de débito, cartão de crédito e boleto. O PIX oferece 5% sobre o preço de tabela, e o cartão permite até 12 parcelas sem juros. '
                'A tabela geral e as faixas de parcelamento apresentam valores mínimos conflitantes; confirme as condições com a equipe. Fonte: manual, página 3.')
    if any(x in query for x in ('shipping', 'delivery', 'frete', 'entrega')) and 4 in pages:
        return ('Na região metropolitana de Campo Grande, o manual informa frete grátis acima de R$ 500,00 e taxa de R$ 35,00 abaixo desse valor, com estimativa de 1 a 3 dias úteis. '
                'O valor exato de R$ 500,00 não tem regra definida; confirme com a equipe. Outras cidades exigem cotação. Fonte: manual, páginas 4 e 5; estas são estimativas da política, não uma promessa de entrega ao vivo.')
    if any(x in query for x in ('return', 'regret', 'received', 'refund', 'devolver', 'devolucao', 'arrepend', 'recebi')) and 4 in pages:
        if ('online' in query and ('three days' in query or 'tres dias' in query or '3 dias' in query)
                and ('unused' in query or 'sem uso' in query)):
            return ('O recebimento informado está dentro da janela de sete dias corridos descrita no manual. Confirme também a embalagem original, os acessórios e os manuais; estar sem uso não confirma esses detalhes. '
                    'O manual prevê frete de devolução pago pela loja e reembolso na forma original em até dez dias úteis, mas não define o início desse prazo. '
                    'A equipe precisa confirmar e organizar a devolução; não posso aprovar ou processar o reembolso. Fonte: seção 4.1, página 4.')
        return ('A compra foi online? Quando você recebeu o produto? Ele está sem uso, na embalagem original e com os acessórios e manuais? '
                'O manual descreve sete dias corridos após o recebimento para arrependimento em compras online. Preciso desses dados antes de aplicar a regra. Fonte: seção 4.1, página 4.')
    return translate('The offline mock cannot summarize this evidence. Please use Groq or contact the store team.', 'pt')
