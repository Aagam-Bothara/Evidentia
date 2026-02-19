# Contributing to Evidentia

Thank you for your interest in contributing to Evidentia.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/evidentia.git
cd evidentia

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install with dev dependencies
pip install -e ".[dev,retrieval,pdf]"

# Run tests
pytest

# Run linter
ruff check .

# Run type checker
mypy evidentia/
```

## Project Structure

| Directory | Purpose |
|-----------|---------|
| `evidentia/core/` | Config, models, exceptions, logging |
| `evidentia/orchestrator/` | Planner, tool router, decision engine |
| `evidentia/tools/` | Tool implementations |
| `evidentia/retrieval/` | Hybrid search, vector store, reranker |
| `evidentia/validator/` | Schema, citation, evidence validation |
| `evidentia/connectors/` | BYO-API runtime and vault |
| `evidentia/schemas/` | Pydantic I/O schemas |
| `evidentia/cli/` | CLI entry point |
| `evidentia/api/` | FastAPI server and routes |
| `tests/` | Test suite |

## Adding a New Tool

1. Create a new file in `evidentia/tools/`
2. Define input/output schemas in `evidentia/schemas/tool_io.py`
3. Implement the `BaseTool` interface
4. Register the tool in the tool registry
5. Add tests in `tests/`

Example:

```python
from evidentia.tools.base import BaseTool, ToolMetadata

class MyTool(BaseTool):
    metadata = ToolMetadata(
        name="my_tool",
        description="What my tool does.",
        category="public_api",
        input_schema=MyInput.model_json_schema(),
        output_schema=MyOutput.model_json_schema(),
    )

    async def execute(self, input_data: dict) -> dict:
        params = MyInput.model_validate(input_data)
        # ... implementation ...
        return MyOutput(...).model_dump()
```

## Commit Messages

Use conventional commits:

- `feat: add new tool for X`
- `fix: handle timeout in arxiv tool`
- `docs: update contributing guide`
- `test: add tests for validator`
- `refactor: simplify router logic`

## Pull Requests

1. Create a feature branch from `main`
2. Make your changes
3. Ensure all tests pass
4. Submit a PR with a clear description
