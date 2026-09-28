# Starts a separate, local-only Ollama server on 127.0.0.1:11435 that uses an integrated GPU through Ollama's
# Vulkan backend. It does not change your normal Ollama installation or its settings; stop it with Ctrl+C.
# Then, in the shell that runs the app or the evaluation:   $env:VDI_OLLAMA_URL = "http://127.0.0.1:11435"
# Measured on an Intel Arc 140V iGPU: ~19 s per receipt image instead of ~100 s on the CPU (see docs/metrics-and-results.md).
$env:OLLAMA_HOST = "127.0.0.1:11435"
$env:OLLAMA_VULKAN = "1"
$env:OLLAMA_IGPU_ENABLE = "1"
ollama serve
