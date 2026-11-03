"""Small lexical retrieval over actual PDF pages, with page citations."""
import re
from collections import Counter
from .store import DATA, normalize

STOP = set('the a an is of to and do you i my can what how da de do e o a os as um uma qual que eu meu minha para com na no em'.split())
SYNONYMS = {
 'return': 'devolucao arrependimento troca', 'refund': 'reembolso devolucao',
 'exchange': 'troca', 'warranty': 'garantia defeito', 'defect': 'defeito garantia',
 'hours': 'horario funcionamento', 'open': 'horario funcionamento',
 'address': 'endereco', 'shipping': 'frete entrega', 'delivery': 'frete entrega',
 'payment': 'pagamento parcelamento pix', 'installments': 'parcelamento parcela',
 'promotion': 'promocao desconto', 'discount': 'desconto promocao',
 'privacy': 'privacidade dados', 'complaint': 'reclamacao',
 'devolver': 'devolucao arrependimento', 'trocar': 'troca defeito',
 'parcelar': 'parcelamento parcela', 'fecha': 'horario funcionamento',
}


def tokens(text):
    return [t for t in re.findall(r'[a-z0-9]+', normalize(text)) if t not in STOP]


class Policies:
    def __init__(self, path=DATA / 'store_policies.pdf'):
        import pymupdf
        with pymupdf.open(path) as pdf:
            self.pages = [(i + 1, page.get_text()) for i, page in enumerate(pdf)]

    def search(self, query):
        terms = tokens(query)
        expanded = set(terms)
        for term in terms:
            expanded.update(tokens(SYNONYMS.get(term, '')))
        ranked = []
        for page, text in self.pages:
            counts = Counter(tokens(text))
            score = sum(min(counts[t], 3) for t in expanded)
            if score:
                ranked.append((score, page, text))
        ranked.sort(key=lambda x: (-x[0], x[1]))
        return {'source': 'store_policies.pdf, version 2.1 (June 2025)',
                'matches': [{'page': page, 'text': text} for _, page, text in ranked[:3]],
                'note': 'Quoted store policy is not legal advice. Conflicts and missing boundary rules require staff confirmation.'}
