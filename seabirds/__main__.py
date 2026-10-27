import argparse
import os

import uvicorn


def main():
    cli = argparse.ArgumentParser(description="SeaBirdsCloud — editor de documentação")
    cli.add_argument("--host", default=os.environ.get("SEABIRDS_HOST", "127.0.0.1"))
    cli.add_argument("--port", type=int, default=int(os.environ.get("SEABIRDS_PORT", "8000")))
    args = cli.parse_args()
    uvicorn.run("seabirds.app:create_app", factory=True, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
