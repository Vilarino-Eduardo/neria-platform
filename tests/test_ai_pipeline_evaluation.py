import json
from unittest.mock import patch

from scripts.evaluate_ai_pipeline import main


def test_pipeline_evaluation_blocks_paid_call_without_confirmation(capsys) -> None:
    with patch("sys.argv", ["evaluate_ai_pipeline.py"]):
        exit_code = main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["maximum_paid_calls"] == 1
    assert "bloqueada" in payload["error"]
