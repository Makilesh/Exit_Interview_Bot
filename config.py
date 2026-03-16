"""
Top-level configuration file.
All tunable parameters live here and are imported by other modules.
"""

MAX_TURNS = 15
MAX_FOLLOWUPS_PER_QUESTION = 2
TEMPERATURE = 0.3
MODEL_NAME = "gpt-4.1"
SUMMARY_MODEL = "gpt-4.1"
FALLBACK_MODEL_NAME = "gpt-oss:20b"
# FALLBACK_MODEL_NAME = "qwen2.5:14b"
OUTPUT_DIR = "outputs"
