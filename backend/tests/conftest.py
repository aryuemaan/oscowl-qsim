import os

# Tests never call real AI services.
os.environ["QSIM_AI_MODE"] = "offline"
os.environ["GEMINI_API_KEY"] = ""
