"""Compatibility entry point; implementation lives in the heasyn package."""
import logging
from heasyn.cli import main

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
