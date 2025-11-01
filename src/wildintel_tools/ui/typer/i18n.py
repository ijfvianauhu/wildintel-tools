"""
Lightweight internationalization (i18n) utility module using Python's :mod:`gettext`.

This module provides a simplified interface for message translation within the
application. It defines a global translation object and two helper functions:

    - ``_()``: A shorthand for translating strings.
    - ``setup_locale()``: Initializes the translation system with a given locale.

By default, if no valid translation file is found, messages will be returned as-is.

Example:
    .. code-block:: python

        from wildintel_tools.ui.typer.i18n import setup_locale, _

        setup_locale(locale="es_ES", locales_dir="locales", domain="messages")
        print(_("Hello world"))  # -> "Hola mundo" (if translation exists)
"""

import gettext

_lang = gettext.NullTranslations()

def _(message):
    """
    Translates a message string using the currently active locale.

    :param message: The message string to translate.
    :type message: str
    :return: The translated string if available, otherwise the original message.
    :rtype: str

    Example:
        .. code-block:: python

            print(_("Upload successful"))
    """
    return _lang.gettext(message)

def setup_locale(locale: str = "en_UK", locales_dir: str ="locales", domain:str ="messages"):
    """
    Initializes the translation system with a given locale.
    :param locale: The locale to use.
    :type message: str
    :param locales_dir: Directory containing compiled translation files (.mo) organized.
    :type message: str
    :param domain: Translation domain (the base name of the .mo file, typically ``"messages"``).
    :type message: str
    :return:
    """
    global _lang
    _lang = gettext.translation(domain, localedir=locales_dir, languages=[locale], fallback=True)