"""O Git lê a credencial pelo processo; ela não entra na URL nem nos argumentos."""

import os
import sys

if __name__ == "__main__":
    prompt = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    print("x-access-token" if "username" in prompt else os.environ.get("SEABIRDS_GITHUB_TOKEN", ""))
