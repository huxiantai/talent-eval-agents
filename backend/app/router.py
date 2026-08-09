from enum import StrEnum
from pathlib import Path


class ParserKind(StrEnum):
    LANGCHAIN = "langchain"
    NATIVE = "native"
    MINERU = "mineru"
    AUDIO = "audio"


PARSER_BY_SUFFIX = {
    ".csv": ParserKind.LANGCHAIN,
    ".json": ParserKind.LANGCHAIN,
    ".html": ParserKind.LANGCHAIN,
    ".htm": ParserKind.LANGCHAIN,
    ".docx": ParserKind.LANGCHAIN,
    ".md": ParserKind.NATIVE,
    ".markdown": ParserKind.NATIVE,
    ".xlsx": ParserKind.NATIVE,
    ".pptx": ParserKind.NATIVE,
    ".pdf": ParserKind.MINERU,
    ".png": ParserKind.MINERU,
    ".jpg": ParserKind.MINERU,
    ".jpeg": ParserKind.MINERU,
    ".wav": ParserKind.AUDIO,
    ".mp3": ParserKind.AUDIO,
    ".m4a": ParserKind.AUDIO,
}


def choose_parser(filename: str) -> ParserKind:
    suffix = Path(filename).suffix.lower()
    try:
        return PARSER_BY_SUFFIX[suffix]
    except KeyError as exc:
        raise ValueError(f"不支持的文件格式: {suffix or '无扩展名'}") from exc
