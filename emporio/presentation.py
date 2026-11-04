"""Customer-facing text formatting without changing retrieved business facts."""
import re
from .i18n import format_money


def chat_prose(text):
    # Remove citation labels, not the surrounding policy or price qualifications.
    # Decimal section numbers such as 4.1 are part of the citation.
    text = re.sub(r'\s*(?:Source|Fonte):\s*(?:[^.;\n]|\.(?=\d))*[.;]', '', text)
    text = text.replace(' Offline mock template checked against the retrieved page.', '')
    text = text.replace('\r\n', '\n').replace('\u200b', '')
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def chat_markdown(text):
    # Escape exactly once: multiple R$ values must not become a math expression.
    text = re.sub(r'(?<!\\)\$', r'\\$', chat_prose(text))
    lines = text.split('\n')
    # Markdown otherwise merges the model's single line breaks into one sentence.
    return '\n'.join(line.rstrip() + '  ' if index + 1 < len(lines) and line.strip()
                     and lines[index + 1].strip() else line
                     for index, line in enumerate(lines))


def product_reply(products, language):
    portuguese = language == 'pt'
    currency = 'R$' if portuguese else 'BRL'
    blocks = []
    for product in products:
        price = f"{currency} {format_money(product['price_brl'], language)}"
        pix = f"{currency} {format_money(product['pix_price_brl'], language)}"
        lines = [f"**{product['name']}**", f"{'Preço' if portuguese else 'Price'}: **{price}**",
                 f"{'No PIX' if portuguese else 'With PIX'}: **{pix}**"]
        if float(product['discount_percent']):
            original = f"{currency} {format_money(product['list_price_brl'], language)}"
            discount = product['discount_percent']
            lines.append(f'Preço original: {original}. Desconto de {discount}%.' if portuguese else
                         f'Original price: {original}. {discount}% off.')
        if product['available']:
            units = product['stock_quantity']
            lines.append(f'Disponível: {units} unidades em estoque.' if portuguese else
                         f'Available: {units} units in stock.')
        else:
            lines.append('Indisponível no momento.' if portuguese else 'Currently unavailable.')
        blocks.append('\n\n'.join(lines))
    note = ('Confirme preços e disponibilidade com a loja. Descontos de PIX e promoções não se acumulam.'
            if portuguese else 'Confirm prices and availability with the store. PIX and promotional discounts cannot be combined.')
    return '\n\n'.join(blocks + [note])
