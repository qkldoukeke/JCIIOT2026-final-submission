from __future__ import annotations

from pathlib import Path
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = Path(r"D:\tool\anaconda3\envs\jci_clean\python.exe")
CONFIG_PATH = Path(
    "team_submission/training_configs/factory_sorting_l3_bc_resume_to_100.json"
)
OUTPUT_ROOT = PROJECT_ROOT / "team_submission" / ".local" / "training_logs"

def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    stdout_path = OUTPUT_ROOT / "resume_to_100_stdout.log"
    stderr_path = OUTPUT_ROOT / "resume_to_100_stderr.log"

    with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_file:
        process = subprocess.Popen(
            [
                str(PYTHON_EXE),
                "-m",
                "robomimic.scripts.train",
                "--config",
                str(CONFIG_PATH),
                "--resume",
            ],
            cwd=PROJECT_ROOT,
            stdout=stdout_file,
            stderr=stderr_file,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    print(process.pid)


if __name__ == "__main__":
    main()
