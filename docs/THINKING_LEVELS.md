# Thinking Levels

`POST /api/chat` accepts `thinking_level`: `off`, `low`, `medium`, or `high`; the default is `medium`.

Llama 3.1 through Ollama has no model-independent native reasoning-token API. AtlasIQ maps levels to prompt instructions and bounded `num_predict` values: off=512, low=768, medium=1536, high=3072. RAG retrieval remains fixed and unchanged.

Enabled levels request private scratch work inside `<thought>...</thought>`. AtlasIQ removes those blocks before returning the answer. Set `THINKING_DEBUG=true` only for local debugging to route filtered thoughts to server debug logs. Thought text is never sent to the browser or chat history.

Higher levels increase latency and resource use and do not guarantee better answers. `off` requests a direct response.
