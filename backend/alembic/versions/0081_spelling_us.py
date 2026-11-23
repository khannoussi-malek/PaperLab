"""chunks.tsv indexes UK spellings as US ones (haemodialysis as hemodialysis), and questions go through the same
spelling_us(), so either spelling finds both (RAG report 2026-11-22: the english stemmer keeps them apart)

Revision ID: 0081
Revises: 0080
Create Date: 2026-11-23
"""

from alembic import op

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None

# Each rule is (pattern, replacement), applied in order to the lowercased text; \m and \M are word edges. Words that
# need 2-3 letters before the ending leave short lookalikes alone (four, your, rise, vogue): tests/test_spelling.py.
# ponytail: a fixed list of patterns for the families medical and SE papers use; add a family when a miss shows one.
RULES = [
    ("ae([dm])", r"e\1"),  # haem-, anaem-, -glycaem-; paed-, orthopaed-
    (r"\moe(dem|soph|str)", r"e\1"),  # oedema, oesophageal, oestrogen
    (r"\mfoet", "fet"),
    ("rrhoea", "rrhea"),
    ("coeliac", "celiac"),
    (r"([a-z]{2,})is(e|ed|es|ing|ation|ations)\M", r"\1iz\2"),  # randomised, organisation, optimising
    (r"([a-z]{2,})ys(e|ed|es|ing)\M", r"\1yz\2"),  # analysed, dialyse
    (r"([a-z]{3,})our(s|ed|ing|al|ite|ites|able)?\M", r"\1or\2"),  # behaviour, tumours, favourite
    (r"(cent|fib|lit|met|theat|lust|calib)re(s)?\M", r"\1er\2"),  # centre, fibres, millilitre
    (r"([a-z]{3,})ogue(s)?\M", r"\1og\2"),  # catalogue, dialogues
    (r"\m(def|off|lic|pret)ence", r"\1ense"),  # defence, licence
    (r"gramme(s)?\M", r"gram\1"),  # programme
]


def _function() -> str:
    steps = "\n".join(f"  t := regexp_replace(t, '{pattern}', '{replacement}', 'g');" for pattern, replacement in RULES)
    return f"""
CREATE FUNCTION spelling_us(t text) RETURNS text
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
BEGIN
  t := lower(t);
{steps}
  RETURN t;
END
$$
"""


def _tsv(expression: str) -> None:
    # Dropping the column drops its GIN index; adding it back rewrites the table (seconds for ~50k chunks).
    op.execute("ALTER TABLE chunks DROP COLUMN tsv")
    op.execute(f"ALTER TABLE chunks ADD COLUMN tsv tsvector GENERATED ALWAYS AS ({expression}) STORED")
    op.execute("CREATE INDEX chunks_tsv_idx ON chunks USING gin (tsv)")


def upgrade() -> None:
    op.execute(_function())
    _tsv("to_tsvector('english', spelling_us(text))")


def downgrade() -> None:
    _tsv("to_tsvector('english', text)")
    op.execute("DROP FUNCTION spelling_us(text)")
