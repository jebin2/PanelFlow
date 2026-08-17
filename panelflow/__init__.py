"""
panelflow - AI-powered comic panel video content creator
"""
# Service keys (TTT_API_KEY, GEMINI_API_KEY) live in ~/.envs/.env, and nothing
# else here reads them in, so a run started outside an exporting shell had none.
# Same loader the TTT repo uses.
try:
    from jebin_lib import load_env
except ImportError:  # tests run against a bare interpreter without the runtime deps
    pass
else:
    load_env()
