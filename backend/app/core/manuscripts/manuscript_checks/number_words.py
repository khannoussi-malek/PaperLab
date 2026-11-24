"""The words and patterns the number-provenance check reads prose with: numbers, units, and the cues that excuse
a number."""

import re

NUMBER = re.compile(
    r"(?<![\w.,\-/:=\[\\])"  # not glued to a word, a version, a range, a path, a key= or an [option]
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?!\w|[.,]\d)"  # not 3.5mm, 1.2.3, 2e-4
    r"(?P<pct>\s*(?:\\,\s*)?(?:\\%|percent\b)|\}\s*\{\\percent\})?"  # 91.3\%, 91.3\,\%, \SI{91.3}{\percent}
)
BRACED = re.compile(r"\\(?:num|SI|qty|textbf|textit|emph|underline)\{$")  # the only commands whose {arg} is prose
UNITS = (
    "ms ns us µs μs s sec secs seconds second min mins minutes minute h hrs hours hour days day Hz kHz MHz GHz "
    "dB dBm dBi nm µm μm mm cm m km mg g kg KB kB MB GB TB Kbps Mbps Gbps W mW kW V mV A mA mAh J kJ K "
    "°C °F ° px pixels fps FLOPs GFLOPs TFLOPs ppm rpm bits bytes Pa kPa MPa"
).split()  # calibration knob
UNIT = re.compile(
    r"(?:\s|\\[,; ]|\\thinspace\b)*(?:\\(?:text|textrm|mathrm|si|unit)\{\s*)?"  # 3.5\,\text{ms}, 3.5\thinspace s
    r"(?:" + "|".join(sorted(map(re.escape, UNITS), key=len, reverse=True)) + r")(?![A-Za-z])|\}\s*\{\\"
)  # 3.5 ms, 3.5\,ms, 3.5~ms (prose() turns ~ into a space), \SI{3.5}{\milli\second}
LIST_TO_UNIT = re.compile(r"(?:\s*,\s*(?:and\s+|or\s+)?|\s+(?:and|or|to)\s+)\d+(?:\.\d+)?")  # 0.96, 1.19 and 1.97\,s
CUE_WORDS = {  # a decimal right after one of these is a reference or a version, not a result
    "section",
    "sections",
    "sec",
    "secs",
    "chapter",
    "chapters",
    "chap",
    "figure",
    "figures",
    "fig",
    "figs",
    "table",
    "tables",
    "tab",
    "appendix",
    "eq",
    "eqs",
    "equation",
    "equations",
    "algorithm",
    "alg",
    "line",
    "lines",
    "step",
    "steps",
    "page",
    "pages",
    "p",
    "pp",
    "theorem",
    "thm",
    "lemma",
    "definition",
    "corollary",
    "proposition",
    "remark",
    "example",
    "part",
    "item",
    "version",
    "ver",
    "v",
    "release",
    "rev",
    "python",
    "pytorch",
    "torch",
    "tensorflow",
    "cuda",
    "cudnn",
    "ubuntu",
    "java",
    "node",
    "gcc",
    "numpy",
    "scipy",
    "sklearn",
    "jax",
    "macos",
    "ios",
    "android",
    "windows",
    "xgboost",
    "lightgbm",
    "catboost",
    "sqlite",
    "ros",
    "tensorrt",
    "onnx",
    "opencv",
    "keras",
    "matlab",
    "llama",
    "qwen",
    "mistral",
    "mixtral",
    "gemma",
    "phi",
    "gpt",
    "claude",
    "gemini",
    "falcon",
    "deepseek",
    "vicuna",
    "sonnet",
    "opus",
    "haiku",
    "postgres",
    "postgresql",
    "docker",
    "pgvector",
    "ollama",  # calibration knob: products with versions
}
SECTION_SIGN = re.compile(r"(?:§|\\S)[\s~]*$")  # §4.2, § 4.2, \S~4.2
STAT_BEFORE = re.compile(
    # alpha and significance level: the operator is optional, "alpha level 0.05", "significance level of 0.01"
    r"(?:(?i:\balpha)(?:\s+level)?|α|\\alpha|(?i:\bsignificance\s+level))\$?\s*"
    r"(?:of\s+|(?:[=<>≤≥]|\\[lg]eq?\b)\s*)?\$?\s*$"
    # p = 0.03, p < 0.001: p needs its operator
    r"|\bp(?:-values?)?\$?\s*(?:[=<>≤≥]|\\[lg]eq?\b|\\text(?:less|greater)|of\b)\s*\$?\s*$"
)
CONFIDENCE_AFTER = re.compile(r"(?:\s|\\,)*(?:confidence|CI)\b")  # 95% confidence, 95% CI
CURRENCY = re.compile(r"[$€£]\s*$")  # $12.50, \$12.50 (the backslash is not adjacent to the digits)
RATIO_BEFORE = re.compile(r"/\s*$")  # the 0.1 in 0.8/0.1/0.1
RATIO_AFTER = re.compile(r"\s*/\s*\d")  # the 0.8 in 0.8/0.1/0.1
LAST_WORD = re.compile(r"([A-Za-z]+)\.?\s*\(?$")
HYPER = re.compile(
    r"learning[ -]rates?|\blr\b|dropout|batch[ -]sizes?|weight[ -]decay|\bdecay|\\?(?:var)?epsilon|ε"
    r"|momentum|\\beta|β|\\lambda|λ|temperature|label[ -]smoothing|warm[ -]?up|step[ -]sizes?"
    r"|\\?gamma|γ|discount[ -]factor|\bthreshold|top[ -]?p\b",
    re.I,
)
HYPER_AFTER = re.compile(r"\s+(?:sampling|learning|dropout)[ -]rates?\b", re.I)  # a 0.75 sampling rate
# The one list of difference cues: before the number, after any number, and after a percent only.
DIFF_BEFORE = re.compile(
    r"improve[sd]? by|improvements? (?:of|by)|gains? of|increase[sd]? (?:of|by)"
    r"|decrease[sd]? (?:of|by)|drop(?:s|ped)? (?:of|by)|reduce[sd]? by|higher than|lower than",
    re.I,
)
DIFF_AFTER = re.compile(r"(?:\s|\\,)*(?:percentage\s+points?|points?|pp)\b", re.I)  # 4.2 points, 1.5 pp
DIFF_AFTER_PERCENT = re.compile(r"(?:\s|\\,)*(?:increase|improvement|gain|drop)s?\b", re.I)  # a 12% gain
CONNECTORS = {
    "of",
    "to",
    "at",
    "is",
    "was",
    "were",
    "be",
    "set",
    "fixed",
    "equal",
    "equals",
    "and",
    "or",
    "a",
    "an",
    "the",
    "in",
    "from",
    "between",
    "initial",
    "initially",
    "rate",
    "with",
    "probability",
    "coefficient",
    "factor",
    "ratio",
    "schedule",
    "value",
    "parameter",
}
DIFF_CONNECTORS = CONNECTORS | {"about", "around", "roughly", "nearly", "almost", "up"}
CUE_WINDOW = 40  # characters before the number for hyperparameter and difference cues; calibration knob
SENTENCE_END = re.compile(
    r"(?<!\bal)(?<!\be\.g)(?<!\bi\.e)(?<!\bcf)(?<!\bvs)(?<!\bFig)(?<!\bEq)(?<!\bSec)[.!?]\s"
    r"|\n[ \t]*\n"
)  # "et al. " and "e.g. " do not end a sentence
SENTENCE_REACH = 600  # ponytail: a sentence is the text between ". " marks within this reach, not a real split
