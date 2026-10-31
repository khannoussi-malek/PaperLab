import pytest

from app.core import diagram as dg
from app.core import diagram_tikz as dt
from app.providers.llm import FakeLLM

pytestmark = pytest.mark.anyio
PIC = "\\begin{tikzpicture}\n\\node (a) {Encoder};\n\\node[right=of a] {Decoder};\n\\end{tikzpicture}"
GOOD = f"Here you go:\n<tikz>\n\\usetikzlibrary{{positioning}}\n{PIC}\n</tikz>\nHope it helps."


class Scripted:
    model = "fake:scripted"

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    async def stream(self, system, prompt):
        self.prompts.append(prompt)
        yield self.replies.pop(0)


def test_prompt_loads_with_split_and_draws_only_what_is_named():
    assert "only what the description names" in dg.SYSTEM_PROMPT
    assert "{description}" in dg.PROMPT_TEMPLATE and "<!-- prompt -->" not in dg.SYSTEM_PROMPT
    prompt = dg.build_prompt("An {encoder} feeds a decoder.")
    assert "An {encoder} feeds a decoder." in prompt and "arrows.meta" in prompt


def test_parse_reply_takes_the_first_block_inside_chatter():
    assert dg.parse_reply(GOOD) == f"\\usetikzlibrary{{positioning}}\n{PIC}"
    assert dg.parse_reply(f"<TIKZ>\n```latex\n{PIC}\n```\n</TIKZ> <tikz>x</tikz>") == PIC
    assert dg.parse_reply("no block here") is None and dg.parse_reply("<tikz> </tikz>") is None


async def test_generate_splits_libraries_and_flags_invented_labels():
    llm = Scripted(GOOD)
    got = await dg.generate("An encoder and a decoder.", llm=llm)
    assert (got.libraries, got.picture, got.errors, got.model) == (["positioning"], PIC, [], "fake:scripted")
    assert got.labels_not_in_description == []
    got = await dg.generate("An encoder only.", llm=Scripted(GOOD))
    assert got.labels_not_in_description == ["Decoder"]


async def test_a_reply_without_the_block_is_retried_once_with_the_reason():
    llm = Scripted("Sure! \\begin{tikzpicture}\\end{tikzpicture}", GOOD)
    got = await dg.generate("An encoder and a decoder.", llm=llm)
    assert got.picture == PIC and len(llm.prompts) == 2
    assert llm.prompts[1].startswith(llm.prompts[0]) and "<tikz>" in llm.prompts[1][len(llm.prompts[0]) :]


async def test_two_replies_without_the_block_are_a_model_error():
    with pytest.raises(dg.DiagramFailed, match="model_error"):
        await dg.generate("An encoder.", llm=Scripted("nope", "still nope"))


async def test_guard_problems_come_back_with_the_code_kept():
    bad = "<tikz>\n\\usetikzlibrary{external}\n" + PIC.replace("{Decoder}", "{\\input{x}}") + "\n</tikz>"
    got = await dg.generate("An encoder and a decoder.", llm=Scripted(bad))
    assert "\\input{x}" in got.picture and got.libraries == ["external"]
    assert any("external" in e for e in got.errors) and any("\\input" in e for e in got.errors)


@pytest.mark.parametrize(
    "description",
    ['A "raw text" goes to a "tokenizer" then to "embeddings 50%".', "Sensors feed a model", "x"],
)
async def test_the_fake_model_draws_named_phrases_and_passes_the_guard(description):
    got = await dg.generate(description, llm=FakeLLM())
    assert got.errors == [] and got.labels_not_in_description == []
    assert set(got.libraries) <= set(dt.ALLOWED_LIBRARIES) and dt.node_labels(got.picture)


async def test_model_comments_never_reach_the_picture():  # final review I1
    reply = (
        "<tikz>\n% Here is my explanation of the figure.\n"
        + PIC.replace("{Encoder};", "{Encoder}; % reads text")
        + "\n</tikz>"
    )
    got = await dg.generate("An encoder and a decoder.", llm=Scripted(reply))
    assert "%" not in got.picture and "explanation" not in got.picture and "Encoder" in got.picture
