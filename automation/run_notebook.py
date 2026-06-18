from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def patched_source(source: str, repo_root: Path, notebook_path: Path) -> str:
    repo_root_text = str(repo_root).replace("\\", "/").rstrip("/") + "/"
    source = re.sub(
        r"try:\n\s+from google\.colab import drive\n\s+drive\.mount\(['\"]/content/drive['\"]\)\nexcept Exception:\n\s+print\([^\n]*\)\n",
        "print('[INFO] Google Colab 환경이 아니므로 drive.mount를 건너뜁니다.')\n",
        source,
    )
    source = source.replace("from google.colab import drive\n", "")
    source = source.replace("drive.mount('/content/drive')\n", "")
    source = source.replace('drive.mount("/content/drive")\n', "")
    source = re.sub(
        r'ROOT_PATH\s*=\s*["\']/content/drive/MyDrive/Data_analysis/The appropriateness of domestic oil prices compared to international oil prices/산업부/["\']',
        f'ROOT_PATH = "{repo_root_text}"',
        source,
    )
    if notebook_path.name == "01_data_preprocessing.ipynb":
        source = re.sub(
            r'PROCESSED_PATH\s*=\s*os\.path\.join\(ROOT_PATH,\s*["\']preprocessed_data["\']\)\s*\+\s*["\']/["\']',
            'PROCESSED_PATH = str(Path(ROOT_PATH) / "data-analysis" / "01_data_preprocessing" / "outputs") + "/"',
            source,
        )
    return source


def run_notebook(notebook_path: Path, repo_root: Path) -> None:
    nb = json.loads(notebook_path.read_text(encoding="utf-8"))

    def display(value: object = None, *args: object, **kwargs: object) -> None:
        if value is None:
            return
        to_string = getattr(value, "to_string", None)
        if callable(to_string):
            print(to_string())
        else:
            print(value)

    globals_dict: dict[str, object] = {
        "__name__": "__main__",
        "__file__": str(notebook_path),
        "display": display,
    }
    for idx, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        if not source.strip():
            continue
        source = patched_source(source, repo_root, notebook_path)
        print(f"[NOTEBOOK] running cell={idx}", flush=True)
        code = compile(source, f"{notebook_path}#cell-{idx}", "exec")
        exec(code, globals_dict, globals_dict)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("notebook")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    run_notebook(Path(args.notebook).resolve(), Path(args.repo_root).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
