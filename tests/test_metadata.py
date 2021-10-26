"""Test data models and methods"""
from pathlib import Path

from databooks.data_models import CellMetadata, JupyterNotebook
from databooks.metadata import clear


def test_metadata_clear():
    read_path = Path("notebooks/small.ipynb")
    write_path = Path("notebooks/clean_small.ipynb")

    clear(read_path=read_path, write_path=write_path, outputs=True)

    nb = JupyterNotebook.parse_file(write_path, content_type="json")

    assert write_path.exists()
    assert nb.metadata.kernelspec is None
    assert all(cell.metadata == CellMetadata() for cell in nb.cells)
    assert all(cell.outputs == [] for cell in nb.cells if cell.cell_type == "code")
    assert all(
        cell.execution_count is None for cell in nb.cells if cell.cell_type == "code"
    )