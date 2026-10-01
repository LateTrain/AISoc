# AI SOC Lab

A Python/Streamlit learning app for synthetic security investigations with local Ollama.

For a guided code walkthrough and exercises, see [MCP learning guide](MCP_LEARNING_GUIDE.md).

## Run

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ollama serve  # only if Ollama is not already running
streamlit run app.py
```

Select a scenario, keep `llama3.2:latest` or enter another installed model, and click **Investigate this alert**. Ask follow-up questions in chat. Changing the model or scenario resets conversation context.

The **Model monitoring** tab records requests, responses, latency, input/output token counts, generation throughput, API/schema failures, and unknown evidence citations. Ollama reports durations in nanoseconds: [usage metrics](https://github.com/ollama/ollama/blob/main/docs/api/usage.mdx). Chat uses [Streamlit chat elements](https://docs.streamlit.io/develop/api-reference/chat).

Runs persist in `runs.sqlite3` and can be exported as JSON. This includes full prompts and evidence; keep experiments synthetic. Delete the database to reset monitoring.

## First experiment

Run the same initial question on the same scenario with two non-abliterated models. Compare latency and conclusions, then try the insufficient-evidence scenario. A valid schema or citation ID does **not** prove factual accuracy. Review whether each claim is supported and whether uncertainty is appropriate. Model comparisons should use matching scenarios/questions; these are exploratory measurements, not benchmarks.

## Boundaries

This starter supplies evidence directly. It has no vector database, RAG, or cloud deployment yet. Optional MCP mode adds model-selected read-only evidence tools. Model access and monitoring live in `soc/core.py`, separate from the UI, so those capabilities can be added incrementally. Token counts may be unavailable on failed calls; missing values are not zero usage. Local inference cost is not estimated.

## Verify

```sh
python -m unittest discover -s tests -v
```

## Learning inspector

The **Learning inspector** tab previews a question without calling the model and shows the actual last request after a chat submission. Inspect every message, the output schema, and the complete API payload. Historical runs have the same inspector under **Model monitoring**.

Set **Requested context tokens** (`num_ctx`) and **Maximum output tokens** (`num_predict`) in the sidebar. The budget shows a rough character-based input estimate plus the maximum output allowance. After a request, it also shows Ollama's reported input and generated token counts. The estimate is not a tokenizer; requested context is not a verified server limit, and reported counts cannot prove that no truncation occurred. See [Ollama context configuration](https://github.com/ollama/ollama/blob/main/docs/context-length.mdx).

The app retains the last eight conversation messages, always resupplying evidence; the inspector shows how many earlier messages were omitted. The exact API payload is distinct from the final prompt rendered by Ollama's model template. Raw model content and validated output appear side by side, including failed validation and citation warnings.

## Inference experiments

The sidebar exposes temperature, top-p, top-k, repeat penalty, and an optional fixed seed. These are per-request API options, separate from the system prompt; changing them requires no new model or Modelfile. They appear in the request inspector and monitoring table. See [Ollama parameter reference](https://github.com/ollama/ollama/blob/main/docs/modelfile.mdx).

For a controlled experiment, keep the model, scenario, question, and history constant: clear the conversation before each initial investigation and change one setting at a time. Start by comparing temperature 0 with 0.7. Sampling filters and seed may have little visible effect at temperature 0. A fixed seed helps control randomness but does not guarantee reproducibility across environments. Existing conversation messages remain when inference settings change, so clear chat when comparing independent runs.


## MCP lab

Restart Streamlit after installing the new dependency (the environment already has it):

```sh
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open **MCP lab** and click **Discover tools and fetch sample evidence (no model)**. Inspect initialization, discovered tool schemas, arguments, results, and the client/server PIDs. The app launches `python -m soc.mcp_server` using the same virtual environment. A real MCP client exchanges protocol messages over stdin/stdout pipes; diagnostic server logs use stderr. The child process stops when the session closes.

Then enable **Gather evidence through MCP** and investigate an alert. The model sees only alert metadata, chooses tools, and the app executes requests through MCP. Tools expose alerts, user profiles, and synthetic investigation timelines; `server_info` is an app-only inspection tool. Each run allows up to four model-selection turns and six model-requested tool calls. MCP connections and the overall gathering stage have timeouts. There is no hidden fallback supplying the original events when a model fails to fetch them.

The final structured response is generated separately using only the evidence successfully fetched. **Learning inspector** and historical monitoring show each intermediate model request/response and each MCP call. End-to-end latency includes all stages; the main token columns describe the final generation only. Intermediate usage is available in the trace. MCP mode investigates each question afresh without prior conversation context; it does not yet support conversational tool history. Fixture evidence remains visible to you for comparison but is not automatically supplied to the model.

Try the no-model demo first, then compare model behavior: discovering and invoking tools is separate from whether a model selects useful tools. This implementation pins the SDK's v1 API for a small explicit stdio example: [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/v1/). Model selection uses [Ollama tool calling](https://github.com/ollama/ollama/blob/main/docs/capabilities/tool-calling.mdx).
