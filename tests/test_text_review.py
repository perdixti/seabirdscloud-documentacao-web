import json
from urllib.error import HTTPError

import pytest

from seabirds import text_review
from seabirds.text_review import TextReview


def apply(text, suggestions, automatic=False):
    # A API usa offsets UTF-16, como os campos de texto do navegador.
    raw = text.encode("utf-16-le")
    for item in sorted(suggestions, key=lambda value: value["start"], reverse=True):
        if automatic and not item["automatic"]:
            continue
        left, right = item["start"] * 2, item["end"] * 2
        assert raw[left:right].decode("utf-16-le") == item["before"]
        raw = raw[:left] + item["after"].encode("utf-16-le") + raw[right:]
    return raw.decode("utf-16-le")


def test_local_review_corrects_portuguese_with_emoji_and_preserves_commands(tmp_path):
    reviewer = TextReview(tmp_path)
    original = (
        "🐧 Voce nao configurou a aplicacao,confira a conexao\n\nOs servidores está ativos.\n\n"
        + "\x60\x60\x60bash\nsudo executar configuracao --usuario voce\n\x60\x60\x60\nUse \x60codigo_nao\x60 e https://exemplo.invalid/configuracao/voce.\n![imagem](imagens/configuracao.png)\n"
    )
    result = reviewer.review(original)
    changed = apply(original, result["suggestions"], automatic=True)
    assert "🐧 Você não configurou a aplicação, confira a conexão" in changed
    assert "Os servidores estão ativos." in changed
    assert "sudo executar configuracao --usuario voce" in changed
    assert (
        "\x60codigo_nao\x60" in changed and "https://exemplo.invalid/configuracao/voce." in changed
    )
    assert "![imagem](imagens/configuracao.png)" in changed
    assert result["provider"] == "local" and not reviewer.status()["key_configured"]


def test_ambiguous_punctuation_is_a_suggestion_and_does_not_add_period_before_code(tmp_path):
    reviewer = TextReview(tmp_path)
    text = "Este parágrafo precisa ser conferido antes de publicar"
    result = reviewer.review(text)
    assert any(item["after"] == "." and not item["automatic"] for item in result["suggestions"])
    assert apply(text, result["suggestions"], automatic=True) == text
    command = "Para executar a aplicação utilize o comando \x60git status\x60"
    assert not any(item["after"] == "." for item in reviewer.review(command)["suggestions"])
    assert not any(
        item["after"] == "."
        for item in reviewer.review("# Este é um título da documentação")["suggestions"]
    )


def test_unclosed_fence_html_paths_and_ignored_words_are_protected(tmp_path):
    reviewer = TextReview(tmp_path)
    reviewer.configure(
        {
            "provider": "local",
            "model": "gpt-4o-mini",
            "allow_cloud": False,
            "ignored_words": ["voce"],
            "key_action": "keep",
            "api_key": "",
        }
    )
    text = "voce nao <code>configuracao voce</code> /etc/configuracao.conf\n\x60\x60\x60\nvoce nao configuracao"
    changed = apply(text, reviewer.review(text)["suggestions"], automatic=True)
    assert changed.startswith("voce não <code>configuracao voce</code> /etc/configuracao.conf")
    assert changed.endswith("\x60\x60\x60\nvoce nao configuracao")


def test_cloud_settings_encrypt_key_and_require_explicit_consent(tmp_path):
    reviewer = TextReview(tmp_path)
    secret = "sk-chave-sintetica-nao-usar"
    configured = reviewer.configure(
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "allow_cloud": False,
            "ignored_words": [],
            "key_action": "replace",
            "api_key": secret,
        }
    )
    assert configured["key_configured"] and secret not in json.dumps(configured)
    assert secret.encode() not in reviewer.path.read_bytes()
    with pytest.raises(ValueError, match="autorize"):
        reviewer.review("Voce nao configurou a aplicacao.")
    restarted = TextReview(tmp_path)
    assert restarted.secret() == secret
    restarted.configure(
        {
            "provider": "local",
            "model": "gpt-4o-mini",
            "allow_cloud": False,
            "ignored_words": [],
            "key_action": "remove",
            "api_key": "",
        }
    )
    assert not restarted.status()["key_configured"]


def test_cloud_request_omits_code_and_uses_schema_and_no_storage(tmp_path, monkeypatch):
    reviewer = TextReview(tmp_path)
    reviewer.configure(
        {
            "provider": "openai",
            "model": "modelo-configuravel",
            "allow_cloud": True,
            "ignored_words": ["NGINX"],
            "key_action": "replace",
            "api_key": "sk-sintetica-para-teste",
        }
    )
    captured = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size):
            return json.dumps(
                {
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        {
                                            "segments": [
                                                {
                                                    "id": 0,
                                                    "text": "Você não configurou a aplicação.",
                                                }
                                            ]
                                        }
                                    ),
                                }
                            ],
                        }
                    ],
                }
            ).encode()

    def fake(request, timeout):
        captured.append(json.loads(request.data))
        assert request.full_url == "https://api.openai.com/v1/responses"
        return Response()

    monkeypatch.setattr(text_review, "urlopen", fake)
    original = "Voce nao configurou a aplicacao.\n\n\x60\x60\x60bash\nsegredo_sintetico=nao_enviar\n\x60\x60\x60\n"
    result = reviewer.review(original)
    changed = apply(original, result["suggestions"])
    assert changed.startswith("Você não configurou a aplicação.")
    assert "segredo_sintetico=nao_enviar" in changed
    assert "segredo_sintetico" not in captured[0]["input"]
    assert captured[0]["store"] is False
    assert captured[0]["text"]["format"]["strict"] is True


def test_cloud_error_and_invalid_structure_do_not_leak_key_or_change_document(
    tmp_path, monkeypatch
):
    reviewer = TextReview(tmp_path)
    secret = "sk-sintetica-confidencial"
    reviewer.configure(
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "allow_cloud": True,
            "ignored_words": [],
            "key_action": "replace",
            "api_key": secret,
        }
    )

    def fail(*args, **kwargs):
        raise HTTPError("https://api.openai.com", 401, secret, {}, None)

    monkeypatch.setattr(text_review, "urlopen", fail)
    with pytest.raises(ValueError) as error:
        reviewer.review("Voce nao configurou a aplicacao.")
    assert secret not in str(error.value) and "401" in str(error.value)


def test_review_limit_is_bounded_for_small_server(tmp_path):
    with pytest.raises(ValueError, match="50 mil"):
        TextReview(tmp_path).review("a" * 50001)


def test_dictionary_suggests_typos_and_preserves_technical_terms(tmp_path):
    reviewer = TextReview(tmp_path)
    text = "O documetno descreve o nginx e o terraform."
    result = reviewer.review(text)
    assert any(
        item["before"] == "documetno" and item["after"] == "documento" and not item["automatic"]
        for item in result["suggestions"]
    )
    assert not any(item["before"] in {"nginx", "terraform"} for item in result["suggestions"])
    assert apply(text, result["suggestions"], automatic=True) == text


def test_object_pronouns_are_not_mistaken_for_verb_subjects(tmp_path):
    reviewer = TextReview(tmp_path)
    text = "Para nós foi tranquilo. O formato para as imagens está correto."
    result = reviewer.review(text)
    assert apply(text, result["suggestions"], automatic=True) == text


def test_screenshot_text_is_corrected_in_safe_mode_and_names_are_preserved(tmp_path):
    reviewer = TextReview(tmp_path)
    text = (
        "# Teste de documentação\n\nMeu nome é Lucas Perdigão de Oliveira.\n\n"
        "lápis.\n\nMeu testo fala sobre cachorro\n\n"
        "![imagem](../../imagens/projetos/outros/teste/img-0.png)\n"
    )
    changed = apply(text, reviewer.review(text)["suggestions"], automatic=True)
    assert "Meu texto fala sobre cachorro." in changed
    assert "\nLápis.\n" in changed
    assert "Meu nome é Lucas Perdigão de Oliveira." in changed
    assert "![imagem](../../imagens/projetos/outros/teste/img-0.png)" in changed
    assert not reviewer.review(changed)["suggestions"]


def test_context_rules_do_not_change_the_valid_verb_or_protected_markdown(tmp_path):
    reviewer = TextReview(tmp_path)
    text = "Eu testo o servidor.\n\nQuando testo o servidor, verifico o log.\n\n`Meu testo fala sobre cachorro`\n\n```\nmeu testo fala sobre cachorro\n```"
    assert apply(text, reviewer.review(text)["suggestions"], automatic=True) == text


def test_capitalization_spelling_and_dictionary_can_be_applied_without_overlap(tmp_path):
    reviewer = TextReview(tmp_path)
    text = "voce pode mecher no documetno.\n\nmeu testo explica o serviço"
    changed = apply(text, reviewer.review(text)["suggestions"])
    assert changed == "Você pode mexer no documento.\n\nMeu texto explica o serviço."


def test_common_overlapping_agreement_is_corrected_in_one_pass(tmp_path):
    reviewer = TextReview(tmp_path)
    text = "Os servidor está ativos. As pagina está prontas."
    assert (
        apply(text, reviewer.review(text)["suggestions"], automatic=True)
        == "Os servidores estão ativos. As páginas estão prontas."
    )
