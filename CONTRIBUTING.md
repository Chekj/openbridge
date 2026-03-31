# Contributing to OpenBridge

First off, thank you for considering contributing to OpenBridge! It's people like you that make OpenBridge such a great tool.

## Code of Conduct

This project and everyone participating in it is governed by our Code of Conduct. By participating, you are expected to uphold this code.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the existing issues to see if the problem has already been reported. When you are creating a bug report, please include as many details as possible:

- **Use a clear and descriptive title**
- **Describe the exact steps to reproduce the problem**
- **Provide specific examples to demonstrate the steps**
- **Describe the behavior you observed and what behavior you expected**
- **Include code samples and screenshots if applicable**

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion, please include:

- **Use a clear and descriptive title**
- **Provide a step-by-step description of the suggested enhancement**
- **Provide specific examples to demonstrate the enhancement**
- **Explain why this enhancement would be useful**

### Pull Requests

1. Fork the repository
2. Create a new branch from `main` (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run the tests (`pytest`)
5. Run linting (`ruff check src/` and `black src/`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Development Setup

```bash
# Clone your fork
git clone https://github.com/yourusername/openbridge.git
cd openbridge

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check src/
black src/

# Type checking
mypy src/openbridge
```

## Style Guidelines

### Python Code Style

- Follow PEP 8
- Use type hints
- Maximum line length: 100 characters
- Use `black` for formatting
- Use `ruff` for linting

### Git Commit Messages

- Use the present tense ("Add feature" not "Added feature")
- Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit the first line to 72 characters or less
- Reference issues and pull requests liberally after the first line

### Documentation

- Update the README.md if you change functionality
- Add docstrings to all public functions and classes
- Keep the Architecture section updated

## Testing

- Write tests for new functionality
- Ensure all tests pass before submitting PR
- Aim for high test coverage

## Adding New Platform Adapters

If you want to add support for a new messaging platform:

1. Create a new file in `src/openbridge/adapters/`
2. Implement the `BaseAdapter` interface
3. Register it with the `@register_adapter` decorator
4. Add tests
5. Update documentation

Example:

```python
from openbridge.adapters import BaseAdapter, UserMessage, BotResponse, register_adapter

@register_adapter("myplatform")
class MyPlatformAdapter(BaseAdapter):
    async def connect(self) -> bool:
        # Implementation
        pass
    
    async def send_message(self, user_id: str, response: BotResponse) -> bool:
        # Implementation
        pass
```

## Questions?

Feel free to open an issue with your question or join our discussions.

Thank you for contributing!
