import subprocess
import json
import shutil
from pathlib import Path
from typing import Union, Optional, Any

_PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
DEFAULT_RAKALY = _PROJECT_ROOT / "tools" / "rakaly.exe"

def v3_to_json(
    save_file: Union[str, Path],
    rakaly_path: Optional[Union[str, Path]] = None
) -> dict[str, Any]:
    """melts a v3 save file to json using rakaly

    Args:
        save_file (Union[str, Path]): The path to the v3 file to convert.
        rakaly_path (Optional[Union[str, Path]], optional): The path to the rakaly executable. Defaults to None.

    Returns:
        dict[str, Any]: The JSON representation of the v3 file.

    ## Throws:
        FileNotFoundError: If the specified v3 file or rakaly executable is not found
        RuntimeError: If the rakaly command fails or the output cannot be decoded as JSON.
    """
    save_path = Path(save_file)
    if not save_path.is_file():
        raise FileNotFoundError(f"File not found: {save_path}")
    
    if rakaly_path:
        rakaly_exe = Path(rakaly_path)
    else:
        found = shutil.which("rakaly")
        rakaly_exe = Path(found) if found else DEFAULT_RAKALY

    if not rakaly_exe.exists():
        raise FileNotFoundError(
            f"rakaly executable not found at {rakaly_exe!r}. "
            "Place it in tools/ or add it to your PATH."
        )
        
    cmd = [
        str(rakaly_exe),
        "json",
        "--duplicate-keys", "preserve",
        str(save_path)
    ]
    
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as exc:
        msg = exc.stderr or exc.stdout or str(exc)
        raise RuntimeError(f"rakaly failed (exit {exc.returncode}):\n{msg}")
    
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as je:
        raise RuntimeError(f"Failed to decode JSON from rakaly output:\n{je}")
    

# test usage
if __name__ == "__main__":
    out = v3_to_json("C:\\Users\\kaare\\OneDrive\\Dokumenter\\Paradox Interactive\\Victoria 3\\save games\\autosave.v3")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    