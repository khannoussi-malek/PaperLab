import pytest

from evals import answer_check


def test_answer_check_needs_a_paper_and_a_workspace(capsys):
    args = answer_check.parse_args(["--paper", "Attention Is", "--workspace", "Thesis"])

    assert (args.paper, args.workspace, args.question) == ("Attention Is", "Thesis", answer_check.DEFAULT_QUESTION)
    with pytest.raises(SystemExit) as exit_info:
        answer_check.parse_args(["--paper", "Attention Is"])
    assert exit_info.value.code == 2
    assert "--workspace" in capsys.readouterr().err
