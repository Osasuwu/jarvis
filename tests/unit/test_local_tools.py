"""Tests for local built-in tools."""

import shutil
from pathlib import Path

import pytest
from jarvis.tools.builtin import (
    FileReadTool,
    FileWriteTool,
    ListDirectoryTool,
    ShellExecuteTool,
    WebFetchTool,
    WebSearchTool,
)


@pytest.mark.asyncio
async def test_file_write_and_read() -> None:
    base = Path.cwd() / "tmp_local_tools"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)

    writer = FileWriteTool()
    reader = FileReadTool()

    target = base / "sample.txt"

    result_write = await writer.execute(path=str(target.relative_to(Path.cwd())), content="hello")
    assert result_write.success

    result_read = await reader.execute(path=str(target.relative_to(Path.cwd())))
    assert result_read.success
    assert result_read.output == "hello"


@pytest.mark.asyncio
async def test_file_read_missing() -> None:
    reader = FileReadTool()
    result = await reader.execute(path="nonexistent.txt")
    assert result.success is False


@pytest.mark.asyncio
async def test_list_directory() -> None:
    base = Path.cwd() / "tmp_local_tools"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)
    (base / "a.txt").write_text("a")
    (base / "b.txt").write_text("b")

    lister = ListDirectoryTool()
    result = await lister.execute(path=str(base.relative_to(Path.cwd())), max_items=10)
    assert result.success
    names = [entry["name"] for entry in result.output]
    assert "a.txt" in names and "b.txt" in names


@pytest.mark.asyncio
async def test_shell_execute_success() -> None:
    shell = ShellExecuteTool()
    cmd = "echo hello"
    result = await shell.execute(command=cmd)
    assert result.success
    assert "hello" in (result.output or "")


@pytest.mark.asyncio
async def test_shell_execute_no_command() -> None:
    shell = ShellExecuteTool()
    result = await shell.execute(command="")
    assert result.success is False


@pytest.mark.asyncio
async def test_web_fetch_invalid_url() -> None:
    fetch = WebFetchTool()
    result = await fetch.execute(url="http://example.invalid")
    assert result.success is False


@pytest.mark.asyncio
async def test_web_search_no_query() -> None:
    search = WebSearchTool()
    result = await search.execute(query="")
    assert result.success is False
