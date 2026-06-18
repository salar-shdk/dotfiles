#!/usr/bin/env python3

import subprocess
import notify2
from deep_translator import GoogleTranslator

SOURCE_LANG = "auto"
TARGET_LANG = "fa"


def get_selected_text() -> str:
    """Get currently selected text using xclip."""
    try:
        return subprocess.check_output(
            ["xclip", "-out", "-selection", "primary"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
    except Exception:
        return ""


def translate_text(text: str) -> str:
    """Translate text to Persian."""
    translator = GoogleTranslator(source=SOURCE_LANG, target=TARGET_LANG)
    return translator.translate(text)


def send_notification(title: str, message: str):
    """Send desktop notification."""
    notify2.init("Translator")
    n = notify2.Notification(
        title,
        message,
        icon="accessories-dictionary"
    )
    n.set_timeout(5000)
    n.show()


def main():
    text = get_selected_text()

    if not text:
        send_notification("Translator", "No text selected")
        return

    translated = translate_text(text)
    send_notification(text, translated)


if __name__ == "__main__":
    main()
