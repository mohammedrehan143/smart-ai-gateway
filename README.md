# Smart AI Gateway

**A unified AI infrastructure platform for intelligent model routing, multi-provider orchestration, cost visibility, and agentic developer workflows.**

Smart AI Gateway gives developers one consistent interface for working with multiple hosted AI providers. It routes requests between configured model tiers, normalizes provider responses, records request traces and usage, and supports retry and fallback policies. Its Python CLI also provides an agentic workflow for working with files and running development tasks from the terminal.

## Key capabilities

- **Multi-provider integration:** Work with supported AI providers through a common adapter interface and configurable credentials.
- **Intelligent model routing:** Route requests using configurable policies such as `adaptive`, `always_cheap`, and `always_strong`.
- **Model tiers and aliases:** Configure lower-cost, stronger, and fallback model aliases.
- **Usage and cost visibility:** Record request usage, latency, routing decisions, and cost estimates when rate data is available.
- **Reliability controls:** Apply bounded retries and configured fallback behavior for eligible provider failures.
- **Agentic CLI:** Interact with the gateway and run development tasks from a terminal, including supported file creation and editing workflows.
- **Traceability:** Keep request and routing records to help inspect how a request was handled.

> Actual provider and model availability depends on your configuration, API credentials, provider limits, and the current implementation. Cost figures are estimates where provider usage or rate-card data requires estimation.

## Architecture at a glance

A typical request follows this flow:

1. A client or CLI sends a request to the gateway.
2. The gateway validates the request and evaluates the configured routing policy.
3. The router selects a configured model tier and records the decision.
4. A provider adapter sends the request to the selected hosted model.
5. Retry or fallback behavior is applied when configured and appropriate.
6. The gateway returns a normalized response and records trace and usage information.

The routing policy is deterministic and explainable; provider-specific request and response handling stays inside provider adapters.

## Repository structure

The repository is organized around the gateway service, provider integrations, routing and orchestration logic, the CLI, documentation, and tests. Some useful areas include:

- `app/` — gateway API, domain logic, routing, provider adapters, and services.
- `smart_ai_cli/` — command-line interface and developer-agent workflows.
- `agents/` — agent roles and supporting credential/agent components.
- `tests/` — unit, integration, CLI, security, and functional tests.
- `.env.example` — example configuration variables.
- `PROJECT_CHARTER.md`, `SCOPE_AND_NON_GOALS.md`, and `IMPLEMENTATION_GUIDE.md` — project scope and engineering guidance.

## Windows CLI setup guide

The following instructions install the CLI directly from this GitHub repository and launch it through Python's module launcher.

### 1. Prerequisites

Install:

- Python 3.10 or newer (the original setup was tested with Python 3.14).
- Git for Windows.
- Windows PowerShell.

Verify the installations:

```powershell
python --version
git --version
```

### 2. Install Smart AI Gateway

Open PowerShell and run:

```powershell
python -m pip install "git+https://github.com/mohammedrehan143/smart-ai-gateway.git"
```

Verify the package installation:

```powershell
python -m pip show smart-ai-gateway
```

### 3. Verify the CLI files

Run:

```powershell
python -m pip show -f smart-ai-gateway
```

The installed package should include the `smart_ai_cli` module and its module launcher files. Depending on the package installation and platform, a `smartai.exe` command entry point may also be installed.

**Windows note:** On the original setup device, Windows Application Control blocked `pip.exe` and `smartai.exe`. The Python module launcher worked instead. If this happens on your device, use `python -m pip` and `python -m smart_ai_cli` as shown below. Do not disable Windows security policies.

### 4. Launch Smart AI CLI

Display available commands:

```powershell
python -m smart_ai_cli --help
```

Start interactive chat:

```powershell
python -m smart_ai_cli chat
```

### 5. Login

When gateway authentication is required, run:

```powershell
python -m smart_ai_cli login
```

Follow the authentication instructions displayed in the terminal.

### 6. Check gateway status

```powershell
python -m smart_ai_cli status
```

### 7. Create files using AI

First, navigate to the folder where you want the CLI to create files. For example:

```powershell
cd "$env:USERPROFILE\Desktop\TestFolder"
```

Check your current directory:

```powershell
Get-Location
```

Run an autonomous task:

```powershell
python -m smart_ai_cli do "Create a hello.md file in the current directory with a Hello World heading and a short welcome message. Actually create the file, do not just provide its contents."
```

Verify that the file was created:

```powershell
Test-Path .\hello.md
```

The `do` command is intended for task execution. Review the proposed or performed changes and terminal commands before relying on them in an important project.

### 8. Other CLI commands

The CLI also exposes commands for inspecting models, usage, cost, routing, benchmarks, and configuration:

```powershell
python -m smart_ai_cli models
python -m smart_ai_cli usage
python -m smart_ai_cli cost
python -m smart_ai_cli route
python -m smart_ai_cli benchmark
python -m smart_ai_cli config
```

Use `python -m smart_ai_cli --help` to see the commands and options available in your installed version.

### 9. Important notes

1. Use `python -m smart_ai_cli` instead of `smartai` if Windows blocks the generated executable.
2. Use `do` for autonomous file creation and editing tasks.
3. Use `chat` for interactive conversations.
4. Run the CLI from the directory where you want relative file operations to take place.
5. If Windows Application Control blocks execution, use an administrator-approved installation and execution method. Do not disable security policies.
6. If the gateway is configured with a mock provider, configure a supported real provider and valid API credentials before expecting real LLM responses or real provider-backed agent execution.
7. Never commit API keys or other secrets to the repository. Keep credentials in environment variables or an approved secret store.

### 10. Final verification

Run:

```powershell
python -m smart_ai_cli --version
python -m smart_ai_cli --help
python -m smart_ai_cli status
```

The CLI installation is ready for further testing when it launches successfully and the gateway status command reports the expected connection state.

## Configuration

Start by reviewing `.env.example` for the available settings. Configuration commonly includes:

- Gateway environment and API authentication.
- Provider API keys and base URLs.
- Cheap, strong, and fallback model aliases.
- Request timeouts, retry limits, and token limits.
- Database and cache configuration.
- Routing-policy and rate-card versions.

For local development, create your own environment configuration from the example and fill in the credentials for the provider(s) you intend to use. Do not share or commit your populated environment file.

## Development and tests

Create and activate a virtual environment, install the project's development dependencies as specified by its dependency files, and run the test suite using the project's configured test tooling.

A typical test command is:

```powershell
python -m pytest
```

The repository includes unit and integration coverage for areas such as routing decisions, cost calculation, provider behavior, retry/fallback, CLI workflows, and security. Tests that require live provider credentials or external services may need additional configuration.

## Scope and limitations

Smart AI Gateway is focused on gateway infrastructure, model routing, operational visibility, and developer-oriented agent workflows. It is not a model-training or foundation-model-hosting platform. Provider capabilities, model names, rate limits, and pricing can change; use the provider's current documentation when configuring a live integration.

See the project documentation for the detailed product boundaries and engineering decisions:

- [Project Charter](PROJECT_CHARTER.md)
- [Scope and Non-Goals](SCOPE_AND_NON_GOALS.md)
- [Implementation Guide](IMPLEMENTATION_GUIDE.md)

## Contributing

Contributions are welcome. Please review the project scope and implementation guidance before making changes, add or update tests alongside code changes, and document any changes to API or configuration contracts.

## License

This project is licensed under the [MIT License](LICENSE).
