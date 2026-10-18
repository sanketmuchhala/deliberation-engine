import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.engine import run


def main() -> None:
    load_dotenv()
    if len(sys.argv) < 2:
        sys.exit('usage: python -m src.main "<question>"')
    config = json.loads(Path("config.json").read_text())
    result = run(sys.argv[1], config)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
