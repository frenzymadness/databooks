import logging
from pathlib import Path

from _pytest.logging import LogCaptureFixture
from py._path.local import LocalPath
from typer.testing import CliRunner

from databooks.cli import app
from databooks.common import write_notebook
from databooks.data_models.notebook import (
    Cell,
    CellMetadata,
    JupyterNotebook,
    NotebookMetadata,
)
from databooks.git_utils import get_conflict_blobs
from tests.test_data_models.test_notebook import TestJupyterNotebook  # type: ignore
from tests.test_git_utils import init_repo_conflicts

runner = CliRunner()


def test_version_callback() -> None:
    """Print version and help"""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "databooks version: " in result.stdout


def test_meta(tmpdir: LocalPath) -> None:
    """Fix notebook conflicts"""

    read_path = tmpdir.mkdir("notebooks") / "test_meta_nb.ipynb"  # type: ignore
    write_notebook(nb=TestJupyterNotebook().jupyter_notebook, path=read_path)

    nb_read = JupyterNotebook.parse_file(path=read_path, content_type="json")
    result = runner.invoke(app, ["meta", str(read_path)], input="y")
    nb_write = JupyterNotebook.parse_file(path=read_path, content_type="json")

    assert result.exit_code == 0
    assert len(nb_write.cells) == len(nb_read.cells)
    assert all(cell.metadata == CellMetadata() for cell in nb_write.cells)
    assert all(
        cell.execution_count is None
        for cell in nb_write.cells
        if cell.cell_type == "code"
    )
    assert all(
        not hasattr(cell, "outputs")
        for cell in nb_write.cells
        if cell.cell_type != "code"
    )
    assert all(
        not hasattr(cell, "execution_count")
        for cell in nb_write.cells
        if cell.cell_type != "code"
    )


def test_meta__check(tmpdir: LocalPath, caplog: LogCaptureFixture) -> None:
    """Fix notebook conflicts"""
    caplog.set_level(logging.INFO)

    read_path = tmpdir.mkdir("notebooks") / "test_meta_nb.ipynb"  # type: ignore
    write_notebook(nb=TestJupyterNotebook().jupyter_notebook, path=read_path)

    nb_read = JupyterNotebook.parse_file(path=read_path, content_type="json")
    result = runner.invoke(app, ["meta", str(read_path), "--check"])
    nb_write = JupyterNotebook.parse_file(path=read_path, content_type="json")

    logs = list(caplog.records)
    assert result.exit_code == 0
    assert len(logs) == 1
    assert nb_read == nb_write
    assert logs[0].message == "Found unwanted metadata in 1 out of 1 files"


def test_fix(tmpdir: LocalPath) -> None:
    """Fix notebook conflicts"""
    # Setup
    nb_path = Path("test_conflicts_nb.ipynb")
    notebook_1 = TestJupyterNotebook().jupyter_notebook
    notebook_2 = TestJupyterNotebook().jupyter_notebook

    notebook_1.metadata = NotebookMetadata(
        kernelspec=dict(
            display_name="different_kernel_display_name", name="kernel_name"
        ),
        field_to_remove=["Field to remove"],
        another_field_to_remove="another field",
    )

    extra_cell = Cell(
        cell_type="raw",
        metadata=CellMetadata(random_meta=["meta"]),
        source="extra",
    )
    notebook_2.cells = notebook_2.cells + [extra_cell]

    git_repo = init_repo_conflicts(
        tmpdir=tmpdir,
        filename=nb_path,
        contents_main=notebook_1.json(),
        contents_other=notebook_2.json(),
        commit_message_main="Notebook from main",
        commit_message_other="Notebook from other",
    )

    conflict_files = get_conflict_blobs(repo=git_repo)
    id_main = conflict_files[0].first_log
    id_other = conflict_files[0].last_log

    # Run CLI and check conflict resolution
    result = runner.invoke(app, ["fix", str(tmpdir)])
    fixed_notebook = JupyterNotebook.parse_file(
        path=(tmpdir / nb_path), content_type="json"
    )

    assert len(conflict_files) == 1
    assert result.exit_code == 0

    assert fixed_notebook.metadata == notebook_1.metadata
    assert fixed_notebook.nbformat == notebook_1.nbformat
    assert fixed_notebook.nbformat_minor == notebook_1.nbformat_minor
    assert fixed_notebook.cells == notebook_1.cells + [
        Cell(
            metadata=CellMetadata(git_hash=id_main),
            source=[f"`<<<<<<< {id_main}`"],
            cell_type="markdown",
        ),
        Cell(
            source=["`=======`"],
            cell_type="markdown",
            metadata=CellMetadata(),
        ),
        extra_cell,
        Cell(
            metadata=CellMetadata(git_hash=id_other),
            source=[f"`>>>>>>> {id_other}`"],
            cell_type="markdown",
        ),
    ]