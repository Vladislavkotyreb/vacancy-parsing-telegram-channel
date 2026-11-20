"""Читает текст резюме из stdin в отдельном процессе с лимитом времени у вызывающего."""
import sys
from contextlib import closing


def main() -> None:
    try:
        import pypdfium2 as pdfium
    except (ImportError, OSError):
        sys.exit(3)
    with pdfium.PdfDocument(sys.stdin.buffer.read()) as document:
        for i in range(min(20, len(document))):
            with closing(document[i]) as page, closing(page.get_textpage()) as text:
                sys.stdout.buffer.write(text.get_text_bounded().encode("utf-8") + b"\n")


if __name__ == "__main__":
    main()
