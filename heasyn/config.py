# Embedding choices are independent of the LLM used for POP:
#   sentence-transformers/all-mpnet-base-v2 (default; lightweight)
#   BAAI/bge-large-en-v1.5
#   intfloat/e5-large
#   intfloat/multilingual-e5-large-instruct
#   nomic-ai/nomic-embed-text-v1.5
#   Qwen/Qwen3-Embedding-4B (requires more GPU/RAM)
#   nvidia/llama-embed-nemotron-8b (requires more GPU/RAM)
# Some models require --trust-remote-code. Inspect the model code first.
# Use --query-prefix/--document-prefix to override model-specific instructions.
DEFAULT_EMBEDDING = "sentence-transformers/all-mpnet-base-v2"

# POP model examples; availability depends on your account/local installation:
#   openai:    gpt-4o, gpt-4o-mini
#   anthropic: claude-sonnet-4-6, claude-opus-4-6
#   ollama:    qwen3-vl:8b, deepseek-r1:7b, llama3.2:3b, qwen2.5:7b
# The PDF parser supplies text, including when the chosen model supports vision.
DEFAULT_MODELS = {"openai": "gpt-4o", "anthropic": "claude-sonnet-4-6", "ollama": "qwen2.5:7b"}
