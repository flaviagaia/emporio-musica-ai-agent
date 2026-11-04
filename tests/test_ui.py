from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from emporio import ui
from emporio.backend import LiteLLMBackend
from emporio.ui_support import Settings, load_settings, transcript

APP = Path(__file__).resolve().parents[1] / 'streamlit_app.py'


@pytest.fixture(autouse=True)
def isolate_ui_configuration(monkeypatch):
    monkeypatch.setattr(ui, 'configured_settings', lambda: Settings())
    original = LiteLLMBackend.complete
    def no_live_calls(self, *args, **kwargs):
        if self.mode == 'groq':
            raise AssertionError('A UI test must not call the real API')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(LiteLLMBackend, 'complete', no_live_calls)


def app():
    result = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not result.exception
    return result


def test_home_defaults_to_mock_and_can_answer_without_key():
    at = app()
    assert at.radio(key='response_mode').value == 'Offline mock'
    assert not at.chat_input[0].disabled
    at.chat_input[0].set_value('What is the PIX price of Yamaha C40?').run()
    assert not at.exception
    assert '569.91' in at.session_state['records'][0]['answer']
    assert at.session_state['records'][0]['trace'][0]['tool'] == 'search_products'
    assert len(at.chat_message) == 2


def test_reruns_do_not_repeat_model_calls_or_messages():
    at = app()
    at.chat_input[0].set_value('What is the store address?').run()
    agent = at.session_state['agent']
    before = len(agent.history)
    at.checkbox(key='technical').check().run()
    assert not at.exception
    assert len(at.session_state['records']) == 1
    assert len(agent.history) == before


def test_mode_switch_clears_context_and_blocks_unconfigured_groq():
    at = app()
    at.chat_input[0].set_value('Yamaha C40 price?').run()
    at.radio(key='response_mode').set_value('Groq · real model').run()
    assert not at.exception
    assert at.session_state['records'] == []
    assert at.chat_input[0].disabled
    assert 'agent' not in at.session_state
    at.radio(key='response_mode').set_value('Offline mock').run()
    assert not at.chat_input[0].disabled


def test_catalog_search_pagination_and_filter_reset():
    at = app()
    at.radio(key='workspace').set_value('Catalog').run()
    assert not at.exception
    assert not at.button(key='catalog_next').disabled
    at.button(key='catalog_next').click().run()
    assert at.session_state['catalog_offset'] == 10
    at.text_input(key='catalog_query').set_value('Yamaha C40?').run()
    assert not at.exception
    assert at.session_state['catalog_offset'] == 0
    assert at.button(key='catalog_next').disabled
    assert any('599.90' in text.value for text in at.markdown)


def test_catalog_ask_button_opens_chat_and_looks_up_selected_model():
    at = app()
    at.radio(key='workspace').set_value('Catalog').run()
    at.text_input(key='catalog_query').set_value('Yamaha C70').run()
    at.button(key='ask_product_82').click().run()
    assert not at.exception
    assert at.radio(key='workspace').value == 'Chat'
    record = at.session_state['records'][0]
    assert 'Yamaha C70' in record['answer']
    assert record['trace'][0]['result']['products'][0]['product_id'] == 82


def test_store_guide_search_keeps_withdrawal_source_separate():
    at = app()
    at.radio(key='workspace').set_value('Store guide').run()
    at.text_input(key='guide_query').set_value('online withdrawal arrependimento').run()
    assert not at.exception
    assert any('section 4.1' in expander.label for expander in at.expander)
    next(button for button in at.button if button.label == 'Payments').click().run()
    assert not at.exception and not at.warning
    assert at.text_input(key='guide_query').value == 'payment installments'
    next(button for button in at.button if button.label == 'Ask Mel about this policy').click().run()
    assert not at.exception
    assert at.radio(key='workspace').value == 'Chat'
    assert 'PIX' in at.session_state['records'][0]['answer']


def test_sessions_have_independent_agent_instances_and_histories():
    one, two = app(), app()
    one.chat_input[0].set_value('Yamaha C40 price?').run()
    assert two.session_state['records'] == []
    two.chat_input[0].set_value('What is the store address?').run()
    assert one.session_state['agent'] is not two.session_state['agent']
    assert 'C40' not in two.session_state['records'][0]['answer']


def test_settings_precedence_and_exports_do_not_include_api_keys(tmp_path):
    local = tmp_path / '.env'
    local.write_text('GROQ_API_KEY=local-placeholder\nEMPORIO_DEMO_CUSTOMER_ID=3\n')
    settings = load_settings(secrets={'GROQ_API_KEY': 'secret-placeholder'},
                             env={'GROQ_API_KEY': 'environment-placeholder'}, path=local)
    assert settings.api_key == 'environment-placeholder'
    assert settings.demo_customer_id == 3
    assert settings.api_key not in repr(settings)
    exported = transcript([{'question': 'price?', 'answer': 'fixture', 'trace': [], 'error': None}], 'mock', settings.model)
    assert settings.api_key not in exported and 'scripted simulator' in exported


def test_provider_failure_is_displayed_once_and_does_not_leak_error(monkeypatch):
    monkeypatch.setattr(ui, 'configured_settings', lambda: Settings(api_key='fixture-key'))
    class FailedAgent:
        last_trace = []
        last_error = 'provider_failure'
        def reply(self, message):
            return 'The assistant service is unavailable. Please try again or contact the store team.'
    monkeypatch.setattr(ui, 'create_agent', lambda mode, settings: FailedAgent())
    at = app()
    at.radio(key='response_mode').set_value('Groq · real model').run()
    at.chat_input[0].set_value('price?').run()
    assert not at.exception
    assert len(at.session_state['records']) == 1
    assert len(at.warning) == 1
    assert 'fixture-key' not in '\n'.join(x.value for x in at.markdown)


def test_language_switch_keeps_history_and_changes_new_replies_and_export():
    at = app()
    assert at.selectbox(key='language').value == 'en'
    at.chat_input[0].set_value('Yamaha C40 price?').run()
    original = at.session_state['records'][0].copy()
    agent = at.session_state['agent']
    at.selectbox(key='language').set_value('pt').run()
    assert not at.exception
    assert at.session_state['records'][0] == original
    assert at.chat_input[0].placeholder.startswith('Pergunte')
    at.chat_input[0].set_value('Qual o preço do Yamaha C40 no PIX?').run()
    assert not at.exception
    assert at.session_state['agent'] is agent
    assert len(agent.history) == 4
    record = at.session_state['records'][-1]
    assert '569,91' in record['answer'] and 'Fonte:' in record['answer']
    assert record['language'] == 'pt'
    exported = transcript(at.session_state['records'], 'mock', 'fixture', 'pt')
    assert 'Idioma: Português' in exported and original['answer'] in exported
    at.selectbox(key='language').set_value('en').run()
    assert len(at.session_state['records']) == 2


def test_portuguese_catalog_and_guide_actions_keep_stable_navigation():
    at = app()
    at.selectbox(key='language').set_value('pt').run()
    at.radio(key='workspace').set_value('Catalog').run()
    at.text_input(key='catalog_query').set_value('Yamaha C40').run()
    assert not at.exception
    assert any('599,90' in text.value for text in at.markdown)
    assert any(button.label == 'Perguntar à Mel sobre este instrumento' for button in at.button)
    at.radio(key='workspace').set_value('Store guide').run()
    next(button for button in at.button if button.label == 'Pagamentos').click().run()
    next(button for button in at.button if button.label == 'Perguntar à Mel sobre esta política').click().run()
    assert not at.exception
    assert at.radio(key='workspace').value == 'Chat'
    assert 'O manual lista PIX' in at.session_state['records'][-1]['answer']
