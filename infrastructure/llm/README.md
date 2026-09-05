# LLM adapters

One contract (`domain.llm.protocols.LLM`), one implemented adapter, and stubs
for the rest.

The remaining stubs are deliberate. Writing four adapters before any has carried
real traffic is guessing at four wire formats at once; what needed pinning down
early is the *contract*, and that is in `domain/`. Each stub states what its
provider differs on, so filling it in later is a known job rather than a
discovery.

| File | Status |
|---|---|
| `chat_completions.py` | the shared wire format - `POST /chat/completions` |
| `openrouter.py` | implemented - the hosted provider |
| `local.py` | implemented - a model served on this machine (Ollama and alike) |
| `openai.py` | stub |
| `anthropic.py` | stub |
| `gemini.py` | stub |

Two providers ship, not one. The second cost almost nothing - it speaks the same
wire format - and it earns its place twice over: the phase can be validated
without a key or a bill, and having two implementations behind one contract is
the only real evidence that the contract is a contract.

Adding a provider means: write the adapter here, add its models to
`models.toml`, and register the provider name in `factory.py`. Nothing in
`domain/`, `application/` or any employee declaration changes.
