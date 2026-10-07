# AI SOC Lab

A Python/Streamlit learning app for synthetic security investigations with local Ollama.

For a guided code walkthrough and exercises, see [MCP learning guide](MCP_LEARNING_GUIDE.md).

## Run

Run from the project folder. The existing environment is already set up:

```sh
source .venv/bin/activate
python -m streamlit run app.py
```

Open http://localhost:8501. Keep this terminal running. **Ctrl+C** stops the app; **Ctrl+Z** suspends it and can leave an unresponsive process holding the port. If you accidentally suspend it, use `jobs` and `fg` in the same terminal, then continue or stop it with Ctrl+C.

If Ollama is not already running, start `ollama serve` in a **separate terminal**, or open the Ollama desktop app. `ollama serve` stays in the foreground, so placing it before Streamlit in the same terminal prevents the next command from running.

For a fresh checkout only:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
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


### Visible evidence gathering

**Scenario reference evidence** is the fixture visible to you, not the full initial model input in MCP mode. Each MCP answer now has an evidence summary beneath it; historical runs show the same summary. It separates successful model-requested retrievals, failed/rejected calls, and app-only process inspection.

`get_device_history` provides additional synthetic records stored separately in `soc/device_data.py`. Direct mode does not receive them. Try asking the MCP analyst to check device familiarity and confirm the tool actually succeeded before attributing new evidence to it. Device retrieval is optional; no results are silently injected. Restart Streamlit after updating these Python modules.

### Graphical execution view

Each MCP answer now has an **Investigation execution** graph above its evidence summary. The graph follows actual recorded model turns and tool outcomes, including repeated calls, rejections, limits, and final validation. **Expand execution view and inspect steps** shows the full vertical sequence and lets you select a step to read its recorded payload. The same view is available for historical runs.

This is a completed-run snapshot, not live animation. `soc/execution.py` converts trace entries into stable execution events independently of Streamlit. Future live updates can reuse this representation while the workflow publishes progress. Older runs infer a normal stop only when a recorded model response contains no tool calls; missing outcomes remain unknown. Server process inspection stays separate from investigation tools.

The execution view also covers **direct mode**. New runs record submission, prompt/evidence preparation, the final Ollama request, response, schema/citation checks, and saving metrics. MCP runs add their actual gathering sequence between preparation and final generation. Older runs show only stages supported by their saved data; submission and persistence details are not invented. A gathering failure does not display a final model request that never happened.

In MCP mode the investigation sidebar starts with **Incoming alert** metadata. **Retrieved investigation evidence** fills with successfully fetched profiles, timelines, and optional device history after the latest run. The full original fixture is collapsed under **Scenario reference evidence** for verification. Clearing conversation or changing scenario/model/mode resets the retrieved view. Direct mode continues to show the evidence supplied upfront.
