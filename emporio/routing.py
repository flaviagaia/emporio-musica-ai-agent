"""Small bilingual request parser shared by the offline demo and verification gate.

Unknown requests remain unknown; this is not a general language-understanding model.
"""
import re
from dataclasses import dataclass
from .store import normalize, search_tokens, Store

CATEGORY_TERMS = {
    'violoes': ('acoustic guitar', 'acoustic guitars', 'classical guitars', 'classical guitar', 'acoustic', 'violao', 'violoes'),
    'guitarras': ('electric guitar', 'electric guitars', 'guitar', 'guitars', 'guitarra', 'guitarras'),
    'baixos': ('bass guitar', 'bass guitars', 'bass', 'baixo', 'baixos'),
    'teclados': ('keyboard', 'keyboards', 'teclado', 'teclados', 'piano', 'pianos'),
    'baterias': ('drums', 'drum', 'bateria', 'baterias', 'percussao', 'percussion'),
    'ukuleles': ('ukulele', 'ukuleles'),
}


def has(text, terms):
    return any(re.search(r'\b' + re.escape(term) + r'\b', text) for term in terms)


def policy_topic(text):
    text = normalize(text)
    if has(text, ('defect', 'defective', 'defeito', 'warranty', 'garantia')):
        return 'defect'
    if has(text, ('exchange', 'troca', 'trocar')):
        return 'exchange'
    if has(text, ('return', 'returns', 'refund', 'regret', 'withdrawal', 'devolver', 'devolucao', 'arrependimento', 'arrependi')):
        return 'withdrawal'
    if has(text, ('address', 'endereco', 'hours', 'opening', 'open', 'horario', 'funcionamento')):
        return 'hours'
    if has(text, ('payment', 'payments', 'installment', 'installments', 'pagamento', 'pagamentos', 'parcelamento', 'parcelar')):
        return 'payment'
    if has(text, ('shipping', 'delivery', 'frete', 'entrega')):
        return 'shipping'
    if has(text, ('cable', 'cables', 'cabo', 'cabos', 'amplifier', 'amplifiers', 'amplificador', 'palheta')):
        return 'scope'
    return None


POLICY_QUERIES = {
    'defect': 'defeito garantia assistencia tecnica', 'exchange': 'troca exchange',
    'withdrawal': 'online withdrawal arrependimento', 'hours': 'endereco horario funcionamento',
    'payment': 'pagamento parcelamento pix', 'shipping': 'frete entrega', 'scope': 'acessorios cabos escopo',
}


def budget_value(text):
    match = re.search(r'(?:up to|under|ate|brl|r\$)\s*([\d.,]+)', normalize(text))
    if not match:
        return None
    value = match.group(1).rstrip('.,')
    if ',' in value and '.' in value:
        value = value.replace('.', '').replace(',', '.') if value.rfind(',') > value.rfind('.') else value.replace(',', '')
    elif re.fullmatch(r'\d{1,3}(?:[.,]\d{3})+', value):
        value = value.replace('.', '').replace(',', '')
    else:
        value = value.replace(',', '.')
    return float(value)


@dataclass(frozen=True)
class Request:
    kind: str = 'unknown'
    query: str = ''
    budget: float | None = None
    topic: str | None = None
    order_id: int | None = None
    promotion: bool = False
    specific: bool = False

    @property
    def tool(self):
        return {'catalog': 'search_products', 'policy': 'search_policies', 'order': 'get_order'}.get(self.kind)


def interpret(message, history=()):
    text = normalize(message)
    if has(text, ('all customers', 'all customer', 'customer emails', 'todos os clientes', 'emails dos clientes')):
        return Request('privacy')
    topic = policy_topic(text)
    if topic:
        return Request('policy', POLICY_QUERIES[topic], topic=topic)
    order = re.search(r'(?:order|pedido)\s*#?\s*(\d+)', text)
    if order:
        return Request('order', order_id=int(order.group(1)))
    promotion = has(text, ('promotion', 'promotions', 'promocao', 'promocoes', 'oferta', 'ofertas', 'desconto', 'discounted'))
    for product in Store().rows('products'):
        if normalize(product['name']) in text:
            return Request('catalog', product['name'], budget_value(text), promotion=promotion, specific=True)
    # Compact model references work even when a customer omits the brand.
    models = re.findall(r'\b[a-z]{1,5}-?\d+[a-z0-9-]*\b', text)
    if models:
        return Request('catalog', ' '.join(models), budget_value(text), promotion=promotion, specific=True)
    categories = sorted(((len(term), category, term) for category, terms in CATEGORY_TERMS.items() for term in terms), reverse=True)
    for _, category, term in categories:
        if has(text, (term,)):
            descriptors = [term for term in search_tokens(text) if term in ('nylon', 'steel', 'aco', 'iniciante')]
            return Request('catalog', ' '.join([category] + descriptors), budget_value(text), promotion=promotion)
    if promotion:
        return Request('catalog', '', budget_value(text), promotion=True)
    brands = ('yamaha', 'tagima', 'fender', 'gibson', 'takamine', 'cort', 'ibanez', 'roland', 'korg', 'nord', 'kala', 'kalani', 'ohana', 'shelby', 'rozini')
    brand = next((name for name in brands if has(text, (name,))), None)
    if brand:
        return Request('catalog', brand, budget_value(text))
    descriptors = [term for term in search_tokens(text) if term in ('nylon', 'aco', 'steel', 'iniciante')]
    if descriptors:
        return Request('catalog', ' '.join(descriptors), budget_value(text))
    if history:
        previous = next((m['content'] for m in reversed(history) if m['role'] == 'user'), '')
        prior = interpret(previous)
        if prior.kind == 'policy' and prior.topic in ('withdrawal', 'defect', 'exchange') and has(text, ('received', 'arrived', 'unused', 'recebi', 'chegou', 'sem uso', 'online', 'embalagem')):
            return prior
        if has(text, ('it', 'this', 'that', 'esse', 'este', 'desse', 'dele', 'anterior', 'pix', 'preco', 'price', 'stock', 'estoque')):
            # Use the last mentioned product, not an arbitrary first catalog match.
            answer = next((m['content'] for m in reversed(history) if m['role'] == 'assistant'), '')
            candidates = re.findall(r'\b[a-z]{1,5}-?\d+[a-z0-9-]*\b', normalize(answer))
            if len(set(candidates)) == 1:
                return Request('catalog', candidates[0], budget_value(text), specific=True)
            if prior.tool:
                return prior
    if has(text, ('price', 'prices', 'preco', 'precos', 'stock', 'estoque', 'availability', 'disponibilidade', 'pix', 'instrument', 'instrumentos', 'catalog', 'catalogo')):
        return Request('catalog', '', budget_value(text))
    return Request()
