#import gettext

#_ = gettext.gettext 

#def setup_locale(locale='es', locales_dir = 'locales', domain= 'mensajes'):
#    global _

#    lang = gettext.translation(domain, localedir=locales_dir, languages=[locale], fallback=True)
#    lang.install()  # Esto hace que _ esté disponible globalmente
#    _ = lang.gettext

import gettext

_lang = gettext.NullTranslations()

def _(message):
    return _lang.gettext(message)

def setup_locale(locale="en_UK", locales_dir="locales", domain="messages"):
    global _lang
    _lang = gettext.translation(domain, localedir=locales_dir, languages=[locale], fallback=True)


