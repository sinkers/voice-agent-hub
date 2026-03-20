# Voice Agent Hub - Developer Guide

This guide is for developers working on the voice-agent-hub codebase.

## Workflow
1. An agent picks up a ticket or is assigned a ticket to work
2. Ticket is reviewed and if there are any questions the agent needs to ask those questions to the requestor or on the ticket, if no questions proceed
3. The agent should then map out how they are planning to address the change and communicate to the requestor or on the ticket, proceed this is not a blocking request for validation
4. Work should be done in small chunks and always on their own branch
5. A test is written to validate the planned change
6. The change is implemented
7. All tests are run locally to confirm the change doesn't break anything and that the target test passes
8. When the local work is completed, all tests are run and must pass before pushing to github
9. Make sure the README.md, AGENTS.md and any other relevant documentation is updated to cover any changes made
10. A PR is raised, all CD/CD must pass
11. Wait for a review from gemini which will automatically occur on the repository, once the comments appear address ALL of the comments on the PR
12. When all of the comments are addressed and CI is green it is OK to close the PR and merge the change
13. Move on to the next ticket if there is one available or wait for assignment


## Development Workflow

### Before Pushing to GitHub

**⚠️ IMPORTANT: All tests must pass before pushing to GitHub.**

Always run the following commands before committing and pushing:

```bash
# Run unit tests
make test

# Run linting
make lint

# Run all CI checks (recommended)
make ci
```

### Required Checks

1. **Unit Tests** - All tests in `tests/` must pass
   ```bash
   make test
   # Or directly:
   uv run pytest tests/ -v
   ```

2. **Linting** - Code must pass ruff checks
   ```bash
   make lint
   # Or directly:
   uv run ruff check backend/ tests/
   ```

3. **Frontend Build** - Frontend must build successfully
   ```bash
   cd frontend && npm run build
   ```

### Full CI Validation

To run all checks exactly as CI would (recommended before every push):

```bash
make ci
```

This runs:
- pytest (unit tests)
- ruff (linting)
- frontend build

### Integration Tests

For more comprehensive testing (requires LiveKit credentials):

```bash
# Set required environment variables first
export LIVEKIT_URL="wss://..."
export LIVEKIT_API_KEY="..."
export LIVEKIT_API_SECRET="..."
export DEEPGRAM_API_KEY="..."
export OPENAI_API_KEY="..."

# Run integration tests
make integration-test
```

## Git Workflow

1. Create a feature branch
   ```bash
   git checkout -b fix/your-feature-name
   ```

2. Make your changes

3. **Run tests and checks**
   ```bash
   make ci
   ```

4. Commit your changes
   ```bash
   git add .
   git commit -m "fix: your commit message"
   ```

5. Push to GitHub
   ```bash
   git push origin fix/your-feature-name
   ```

6. Create a pull request

## Testing Guidelines

### ⚠️ IMPORTANT: Test-First Development

**Before starting work on any new feature, write the tests first.**

This ensures:
- Clear requirements and acceptance criteria
- Better design (testable code is better code)
- No forgotten edge cases
- Faster development (no back-and-forth)
- Higher confidence in your implementation

**Process:**
1. **Write tests first** - Define what success looks like
2. **Run tests** - They should fail (feature doesn't exist yet)
3. **Implement feature** - Make the tests pass
4. **Refactor** - Clean up with test safety net

**Example:**
```bash
# 1. Write test for new feature
# tests/test_new_feature.py

# 2. Run test (should fail)
make test

# 3. Implement feature
# backend/main.py - add endpoint

# 4. Run test again (should pass)
make test

# 5. Commit both test and implementation
git add tests/test_new_feature.py backend/main.py
git commit -m "feat: add new feature with tests"
```

### Writing Tests

- Place backend unit tests in `tests/`
- Place backend integration tests in `tests/integration/`
- Place frontend E2E tests in `frontend/tests/e2e/`
- Use descriptive test names: `test_device_flow_complete`, `test_agent_register`
- Use pytest fixtures from `tests/conftest.py` for backend
- Use Playwright for frontend E2E tests

### Test Structure

```python
async def test_your_feature(app_client: AsyncClient):
    """Test description"""
    # Arrange
    data = {...}

    # Act
    response = await app_client.post("/endpoint", json=data)

    # Assert
    assert response.status_code == 200
    assert response.json()["field"] == expected_value
```

### Running Specific Tests

```bash
# Run a specific test file
uv run pytest tests/test_hub.py -v

# Run a specific test function
uv run pytest tests/test_hub.py::test_device_flow_complete -v

# Run with coverage
uv run pytest tests/ --cov=backend --cov-report=html
```

## Code Quality Standards

### Python Code

- Follow PEP 8 style guide
- Use type hints for function signatures
- Maximum line length: 100 characters
- Run `ruff` before committing:
  ```bash
  uv run ruff check backend/ tests/
  ```

### Auto-fix Linting Issues

```bash
make lint-fix
# Or directly:
uv run ruff check backend/ tests/ --fix
```

### TypeScript/React Code

- Use TypeScript strict mode
- Follow React best practices
- Use functional components with hooks

## Common Issues

### Tests Failing Locally

1. **Database locked errors**: Ensure no other process is using the test database
2. **Missing dependencies**: Run `uv sync --extra test`
3. **Import errors**: Ensure you're in the project root directory

### CI/CD Failures

If tests pass locally but fail in CI:
1. Check that all dependencies are in `pyproject.toml`
2. Verify environment variables are not hardcoded
3. Check for timezone-dependent tests
4. Ensure no local files are being used

## Pre-commit Checklist

Before every commit:

- [ ] All tests pass (`make test`)
- [ ] No linting errors (`make lint`)
- [ ] Frontend builds successfully (`cd frontend && npm run build`)
- [ ] No debug print statements or console.logs
- [ ] No commented-out code
- [ ] No hardcoded secrets or credentials
- [ ] Commit message follows convention (e.g., `fix:`, `feat:`, `chore:`)

## Quick Reference

| Command | Description |
|---------|-------------|
| `make test` | Run unit tests |
| `make lint` | Run linting checks |
| `make lint-fix` | Auto-fix linting issues |
| `make ci` | Run all CI checks (tests + lint + build) |
| `make integration-test` | Run integration tests (requires env vars) |
| `make smoke-test` | Run smoke tests against running instance |
| `make test-all` | Run all checks + integration tests |

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pytest Documentation](https://docs.pytest.org/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [LiveKit API Documentation](https://docs.livekit.io/)

## Getting Help

- Check `TODO.md` for known issues and planned improvements
- Review existing tests in `tests/` for examples
- See `README.md` for architecture and API reference
