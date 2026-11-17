import json

import token_logger


def test_usage_line_is_json_on_stdout_without_question_text(capsys):
    token_logger.log_usage(321, "hi")
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "token_usage"
    assert record["tokens_generated"] == 321
    assert record["lang"] == "hi"
    assert "question" not in record
    assert "timestamp" in record


def test_none_tokens_are_logged_as_zero(capsys):
    token_logger.log_usage(None, "en")
    record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert record["tokens_generated"] == 0


def test_answer_query_does_not_log_the_question(monkeypatch, capsys):
    import rag

    monkeypatch.setattr(rag, "_intent_answer", lambda question: None)
    monkeypatch.setattr(rag.groq_client, "generate_answer", lambda q, chunks, lang="en": ("answer", 42))
    secret_question = "how do I get a msme loan for my private business 9876543210"
    rag.answer_query(secret_question, "en")
    out = capsys.readouterr().out
    assert "9876543210" not in out
    assert '"tokens_generated":42' in out
