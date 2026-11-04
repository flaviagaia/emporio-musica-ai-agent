"""Streamlit interface over the same Agent used by the CLI."""
import hashlib
from functools import partial
import html
import math
from pathlib import Path
import time
import streamlit as st
from .agent import Agent
from .backend import LiteLLMBackend, ConfigurationError
from .policies import Policies
from .store import Store, DATA
from .ui_support import CATEGORY_LABELS, load_settings, transcript
from .i18n import translate, format_money, LANGUAGES

MAX_VISIBLE_TURNS = 40
SUGGESTIONS = [
    ('Find an acoustic guitar', 'Which acoustic instruments are available for up to BRL 1000?'),
    ('Check a price', 'What is the PIX price of the Yamaha C40?'),
    ('See active offers', 'Show one instrument with an active promotion and explain whether PIX adds a discount.'),
    ('Ask about returns', 'I regret my purchase. Can I return my order?'),
]
TOOL_NAMES = {'search_products': 'Product catalog', 'search_policies': 'Store policy', 'get_order': 'Order lookup'}


def t(text):
    return translate(text, st.session_state.get('language', 'en'))


def mode_name(value, language):
    return translate({'Offline mock': 'Guided demo', 'Groq · real model': 'Chat with Mel'}[value], language)


def money(value):
    return format_money(value, st.session_state.get('language', 'en'))


def clear_conversation():
    for key in ('agent', 'agent_signature', 'pending_question'):
        st.session_state.pop(key, None)
    st.session_state.records = []


def queue_question(question):
    st.session_state.pending_question = question
    st.session_state.workspace = 'Chat'


def reset_catalog_page():
    st.session_state.catalog_offset = 0


def move_catalog_page(offset):
    st.session_state.catalog_offset = offset


def select_guide(query):
    st.session_state.guide_query = query


def configured_settings():
    try:
        secrets = dict(st.secrets)
    except FileNotFoundError:
        secrets = {}
    return load_settings(secrets=secrets)


def create_agent(mode, settings):
    return Agent(LiteLLMBackend(mode=mode, model=settings.model, api_key=settings.api_key),
                 trusted_customer_id=settings.demo_customer_id)


def sources(trace, technical=False):
    if not trace:
        return
    labels = list(dict.fromkeys(t(TOOL_NAMES.get(step['tool'], step['tool'])) for step in trace))
    with st.expander(t('Sources consulted · ') + ' / '.join(labels)):
        for index, step in enumerate(trace, 1):
            result = step['result']
            st.markdown(f"**{index}. {t(TOOL_NAMES.get(step['tool'], 'Source lookup'))}**")
            if result.get('error'):
                st.caption(t(result.get('message', 'This lookup could not retrieve reliable information.')))
            elif step['tool'] == 'search_policies':
                for match in result.get('matches', []):
                    st.caption(t('Store manual · page {page}').format(page=match['page']) + (t(' · section {section}').format(section=match['section']) if match.get('section') else ''))
                    st.text(match['text'])
            elif step['tool'] == 'search_products':
                products = result.get('products', [])
                if products:
                    st.dataframe([{t('Instrument'): p['name'], t('Price (BRL)'): money(p['price_brl']),
                                   t('PIX (BRL)'): money(p['pix_price_brl']), t('Units'): p['stock_quantity'],
                                   t('Available'): p['available']} for p in products], hide_index=True, width='stretch')
                else:
                    st.caption(t('No matching instruments in this lookup.'))
                st.caption(t('Confirm prices and availability with the store.'))
            elif step['tool'] == 'get_order':
                st.write({t('Order'): result['order_id'], t('Status'): t(result['status']), t('Tracking'): result.get('tracking_code')})
                st.caption(t('Contact the store for the latest order information.'))
            if technical:
                st.json({'tool': step['tool'], 'arguments': step['arguments']})


def render_chat(mode, settings, show_sources, technical):
    records = st.session_state.records
    if not records:
        st.markdown(f'<div class="hero-panel"><div class="eyebrow">{t("YOUR NEXT CHAPTER STARTS WITH A NOTE")}</div><h1 class="hero-title">{t("Find your next sound.")}</h1>'
                    f'<div class="hero-copy">{t("Hi, I’m Mel. Let’s find the right instrument, check a price, or work through a store question together.")}</div>'
                    f'<div class="mode-pill"><span class="mode-dot"></span>{t("Guided demo") if mode == "mock" else t("Chat with Mel")}</div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="section-label">{t("Start with a question")}</div>', unsafe_allow_html=True)
        with st.container(key='starter_actions'):
            icons = ['search', 'payments', 'local_offer', 'assignment_return']
            for row in range(2):
                columns = st.columns(2)
                for index, (column, (label, question)) in enumerate(zip(columns, SUGGESTIONS[row * 2:row * 2 + 2])):
                    column.button(t(label), key='suggest_' + str(row) + label, on_click=queue_question,
                                  args=(t(question),), icon=f':material/{icons[row * 2 + index]}:', width='stretch')
        st.caption(t('Explore instruments, prices and store information with Mel.'))
    else:
        st.subheader(t('Your conversation with Mel'))
    for record in records:
        render_turn(record, show_sources, technical)
    ready = mode == 'mock' or bool(settings.api_key)
    question = st.chat_input(t('Ask about an instrument, an order, or the store…'), key='chat_prompt',
                             max_chars=4000, disabled=not ready)
    question = question or st.session_state.pop('pending_question', None)
    if not question:
        return
    if not ready:
        st.info(t('Chat is temporarily unavailable. You can use the guided demo.'))
        return
    signature = (mode, settings.model, settings.demo_customer_id,
                 hashlib.sha256(settings.api_key.encode()).hexdigest())
    if st.session_state.get('agent_signature') != signature or not hasattr(st.session_state.get('agent'), 'language'):
        previous_agent = st.session_state.get('agent')
        previous_history = getattr(previous_agent, 'history', []).copy() if st.session_state.get('agent_signature') == signature else []
        try:
            st.session_state.agent = create_agent(mode, settings)
            st.session_state.agent.history = previous_history
        except ConfigurationError:
            st.error(t('Chat is temporarily unavailable. You can use the guided demo.'))
            return
        st.session_state.agent_signature = signature
    with st.chat_message('user'):
        st.markdown(question)
    agent = st.session_state.agent
    agent.language = st.session_state.get('language', 'en')
    started = time.monotonic()
    with st.spinner(t('Mel is checking the store information…')):
        answer = agent.reply(question)
    record = {'question': question, 'answer': answer, 'trace': agent.last_trace.copy(),
              'error': agent.last_error, 'language': agent.language, 'elapsed': time.monotonic() - started}
    st.session_state.records = (st.session_state.records + [record])[-MAX_VISIBLE_TURNS:]
    render_answer(record, show_sources, technical)
    # A rerun displays the updated download and transcript controls without resending the request.
    st.rerun()


def render_turn(record, show_sources, technical):
    with st.chat_message('user'):
        st.markdown(record['question'])
    render_answer(record, show_sources, technical)


def render_answer(record, show_sources, technical):
    with st.chat_message('assistant', avatar=':material/music_note:'):
        # Currency symbols must remain literal instead of opening Markdown math.
        if record['error']:
            st.warning(t('Mel could not complete your request. Please try again in a moment.'))
        else:
            st.markdown(record['answer'].replace('$', r'\$'))
        if show_sources and not record['error']:
            sources(record['trace'], technical)


def render_catalog():
    st.markdown(f'<div class="eyebrow">{t("THE INSTRUMENT COLLECTION")}</div><h1 class="hero-title">{t("Make room for music.")}</h1>'
                f'<div class="hero-copy">{t("Find your instrument and compare prices and availability.")}</div>', unsafe_allow_html=True)
    store = Store()
    categories = store.rows('categories')
    category_options = {'All instruments': ''} | {CATEGORY_LABELS[r['category_id']]: r['name'] for r in categories}
    filters = st.columns([2, 1.4, 1.4])
    query = filters[0].text_input(t('Search instruments'), placeholder='Yamaha, Takamine, ukulele…', key='catalog_query', on_change=reset_catalog_page)
    category = filters[1].selectbox(t('Category'), list(category_options), format_func=partial(translate, language=st.session_state.language), key='catalog_category', on_change=reset_catalog_page)
    highest_price = math.ceil(max(float(p['price_brl']) for p in store.rows('products')) / 100) * 100
    budget = filters[2].number_input(t('Maximum price (BRL)'), min_value=0, max_value=highest_price,
                                    value=highest_price, step=100, key='catalog_budget', on_change=reset_catalog_page)
    options = st.columns(2)
    available = options[0].checkbox(t('Available instruments only'), value=True, key='catalog_available', on_change=reset_catalog_page)
    promotion = options[1].checkbox(t('Active promotions only'), key='catalog_promotion', on_change=reset_catalog_page)
    result = store.products(' '.join([category_options[category], query]).strip(), budget,
                            available_only=available, promotion_only=promotion,
                            offset=st.session_state.get('catalog_offset', 0))
    count = result['total_matches']
    st.caption(t("{count} matching instrument(s) · sorted by current price").format(count=count) if st.session_state.get("language") == "pt" else f"{count} matching instrument{'s' if count != 1 else ''} · sorted by current price")
    if not result['products']:
        st.info(t('No instruments match these filters. Try another name, raise your budget, or include unavailable items.'))
        return
    for start in range(0, len(result['products']), 2):
        columns = st.columns(2)
        for column, product in zip(columns, result['products'][start:start + 2]):
            with column.container(border=True):
                category_label = next((CATEGORY_LABELS[r['category_id']] for r in categories if r['name'] == product['category']), product['category'])
                st.markdown(f'<div class="product-category">{html.escape(t(category_label))}</div>'
                            f'<div class="product-name">{html.escape(product["name"])}</div>'
                            f'<div class="product-price">R$ {html.escape(money(product["price_brl"]))}</div>', unsafe_allow_html=True)
                if float(product['discount_percent']):
                    st.markdown(f'<span class="product-original">R$ {html.escape(money(product["list_price_brl"]))}</span>'
                                f'<span class="product-promo">{t("{discount}% off").format(discount=html.escape(product["discount_percent"]))}</span>', unsafe_allow_html=True)
                st.caption(t("PIX R$ {price} · {stock} in stock").format(price=money(product["pix_price_brl"]), stock=product["stock_quantity"]) if product["available"] else t("Unavailable · {status}").format(status=t(product["status"])))
                with st.expander(t('Instrument details')):
                    st.write(product['description'])
                    st.json(product['specs'])
                st.button(t('Ask Mel about this instrument'), key=f'ask_product_{product["product_id"]}',
                          on_click=queue_question, args=(t('What is the price and availability of {name}?').format(name=product['name']),), width='stretch')
    controls = st.columns([1, 2, 1])
    offset = result['offset']
    controls[0].button(t('Previous'), key='catalog_previous', disabled=offset == 0,
                       on_click=move_catalog_page, args=(max(0, offset - 10),), width='stretch')
    controls[1].caption(t("Showing {start}–{end} of {count}").format(start=offset + 1, end=min(offset + 10, count), count=count))
    controls[2].button(t('Next'), key='catalog_next', disabled=result['next_offset'] is None,
                       on_click=move_catalog_page, args=(result['next_offset'],), width='stretch')
    st.caption(t('Confirm prices and availability with the store. PIX and promotional discounts cannot be combined.'))


def render_guide():
    st.markdown(f'<div class="eyebrow">{t("A LITTLE CLARITY GOES A LONG WAY")}</div><h1 class="hero-title">{t("The store guide.")}</h1>'
                f'<div class="hero-copy">{t("Read the original policy evidence for opening hours, payments, shipping and returns. Ask Mel to explain it in your selected language.")}</div>', unsafe_allow_html=True)
    columns = st.columns(4)
    for column, (label, query) in zip(columns, [('Opening hours', 'hours address'), ('Payments', 'payment installments'),
                                               ('Returns', 'online withdrawal arrependimento'), ('Shipping', 'shipping delivery')]):
        column.button(t(label), on_click=select_guide, args=(t(query),), width='stretch')
    query = st.text_input(t('Search the store manual'), value=t('hours address'), key='guide_query')
    if query.strip():
        result = Policies().search(query)
        matches = result['matches']
        if not matches:
            st.info(t('No policy pages matched. Try a different term or ask Mel for help.'))
        for index, match in enumerate(matches):
            label = t('Store manual · page {page}').format(page=match['page']) + (t(' · section {section}').format(section=match['section']) if match.get('section') else '')
            with st.expander(label, expanded=index == 0):
                st.text(match['text'])
        st.caption(t('Original source: Portuguese policy manual, version 2.1, June 2025. Conflicting or unspecified rules require staff confirmation.'))
        st.button(t('Ask Mel about this policy'), on_click=queue_question,
                  args=(t('Please explain the store policy for: {query}').format(query=query),))
    st.download_button(t('Download the original store manual'), data=(DATA / 'store_policies.pdf').read_bytes(),
                       file_name='Emporio da Musica - Store policies.pdf', mime='application/pdf')


def run_app():
    st.set_page_config(page_title='Mel | Empório da Música', page_icon=':material/music_note:', layout='wide')
    st.markdown(Path(__file__).with_name('ui.css').read_text(), unsafe_allow_html=True)
    settings = configured_settings()
    if 'records' not in st.session_state:
        st.session_state.records = []
    with st.sidebar:
        st.markdown('<div class="brand"><div class="brand-mark">m</div><div><div class="brand-name">Mel</div>'
                    '<div class="brand-caption">EMPÓRIO DA MÚSICA</div></div></div>', unsafe_allow_html=True)
        st.selectbox('Language / Idioma', list(LANGUAGES), format_func=LANGUAGES.get, key='language', on_change=reset_catalog_page)
        st.caption(t('Language changes apply to new replies. Existing messages are kept.'))
        view = st.radio(t('Workspace'), ['Chat', 'Catalog', 'Store guide'], format_func=partial(translate, language=st.session_state.language), key='workspace', label_visibility='collapsed', on_change=reset_catalog_page)
        st.divider()
        mode_label = st.radio(t('Response mode'), ['Offline mock', 'Groq · real model'], format_func=partial(mode_name, language=st.session_state.language), key='response_mode',
                              captions=[t('Try example questions.'), t('Ask your own questions.')], on_change=clear_conversation)
        mode = 'mock' if mode_label == 'Offline mock' else 'groq'
        if mode == 'groq' and not settings.api_key:
            st.warning(t('Chat is temporarily unavailable. You can use the guided demo.'))
        st.button(t('New conversation'), on_click=clear_conversation, width='stretch')
        st.download_button(t('Download conversation'), data=transcript(st.session_state.records, mode, settings.model, st.session_state.language),
                           file_name='Mel - Conversation.md', mime='text/markdown', disabled=not st.session_state.records,
                           on_click='ignore', width='stretch')
        with st.expander(t('View options')):
            show_sources = st.checkbox(t('Show sources with replies'), value=True, key='show_sources')
            technical = False
        with st.expander(t('About this demo')):
            st.caption(t('This is a demonstration with fictional store data. Confirm prices, availability and order details with the store.'))
            st.caption(t('Your conversation is kept only while this page stays open.'))
            st.link_button(t('View project on GitHub'), 'https://github.com/flaviagaia/emporio-musica-ai-agent')
    st.markdown(f'<div class="case-header"><div class="case-wordmark">MEL<span> /</span></div>'
                f'<div class="case-label">{t("Your music assistant")}<br>EMPÓRIO DA MÚSICA</div></div>', unsafe_allow_html=True)
    if view == 'Chat':
        render_chat(mode, settings, show_sources, technical)
    elif view == 'Catalog':
        render_catalog()
    else:
        render_guide()
    st.markdown(f'<div class="app-footer">Empório da Música · {t("Your music starts here.")} &nbsp; | &nbsp; {t("Created by Flávia Gaia")}</div>', unsafe_allow_html=True)
