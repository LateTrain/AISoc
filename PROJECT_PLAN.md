# AI SOC Learning Project

## Goal

Build a small AI security analyst using synthetic data to learn AI engineering and AWS deployment. Assume strong Python, data science, and cybersecurity experience, plus familiarity with Ollama. Focus on the new engineering concepts rather than introductory programming or security material.

## What we will build

Given a suspicious login alert, the analyst queries related events, retrieves a relevant playbook, and produces a cited investigation summary with uncertainty and recommended next steps.

Start with four scenarios: likely compromise, benign unusual login, failed attack, and insufficient evidence. Use read-only tools and human review of recommendations.

## Learning goals

- **LLMs:** Prompts, structured outputs, context management, and tool calling.
- **Vector search and RAG:** Embeddings, chunking, retrieval quality, and grounded citations.
- **MCP:** Exposing investigation tools through a standard client/server interface.
- **Evaluation and monitoring:** Evidence accuracy, failure cases, saved traces, latency, token usage, and comparisons across models.
- **AWS and Terraform:** Deploying Python services, managing infrastructure, and understanding serverless tradeoffs.

## Workplace technologies to explore

- **LightLLM**
- **Penellope**
- **Terraform**
- **AWS Lambda**
- **Python async / asyncio:** Async wrappers, coroutines, `await`, context managers, timeouts, and their role in MCP and model API calls. Confirm the specific wrapper used at work.

These are technologies we use at work that would be useful to learn. Confirm the specific projects and how they are used internally, then add a focused experiment for each where it fits the build plan.

## Build plan

| Step | Build | Done when |
|---|---|---|
| 1. Local baseline | Python project, synthetic alerts and logs, and a simple Streamlit investigation UI | We can inspect each scenario and its expected findings |
| 2. LLM analyst | Use Ollama to turn supplied evidence into a validated structured summary | Findings cite evidence and acknowledge missing information |
| 3. RAG | Embed playbooks in a local vector database and retrieve relevant passages | We can inspect retrieval results and compare summaries with and without RAG |
| 4. Tools and MCP | Add bounded log/user queries through direct tool calling, then expose them through MCP | The analyst gathers evidence through both paths and handles tool failures |
| 5. Evaluation | Run known scenarios and cases with misleading context or missing evidence | We can measure quality, inspect failures, and compare changes |
| 6. AWS deployment | Deploy a small investigation API using Terraform and Lambda where appropriate | We can run a cloud investigation, inspect logs and cost, and tear down the infrastructure |

## Deployment direction

Build locally first with Python and Ollama. Keep model access, storage, and investigation logic separate so deployment does not require rewriting the core application.

For the AWS milestone, start with API Gateway → Python Lambda → model endpoint, with persistent data outside Lambda and CloudWatch logs. Use Terraform to manage infrastructure, IAM permissions, configuration, and teardown. Choose the cloud model endpoint and storage after the local version works.

Our starting design uses Lambda for short investigation requests and tool execution, with inference hosted separately. We will assess whether a persistent vector service or MCP server needs a different hosting option rather than forcing every component into Lambda. Review cold starts, timeouts, retries, and state management as part of the exercise. See [AWS Lambda best practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html).

## How we will learn

For each step: explain the concept, implement a small piece, inspect its behavior, and run one experiment that exposes a tradeoff. Keep brief learning notes and add evaluation checks as capabilities appear. Add a UI only if it helps inspect evidence, retrieval, and tool calls.

Success is being able to explain the full investigation path, diagnose its failures, and deploy and remove a small AWS version with Terraform.

## Next step

The starter includes a Streamlit chat UI, synthetic scenarios, configurable Ollama access, and saved run monitoring. The MCP lab now demonstrates a separate stdio server, tool discovery, and model-selected evidence gathering. Next, inspect a no-model MCP demo, then compare tool selection and evidence accuracy across models. Start with `llama3.2:latest` and compare other non-abliterated models over time. Select the vector database when we reach retrieval; set an AWS spending limit before cloud deployment.
