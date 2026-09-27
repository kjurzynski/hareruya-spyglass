#!/usr/bin/env python3
from __future__ import annotations

from app.cardmarket_data import download_and_merge


def main() -> int:
    def progress(percent: float, message: str) -> None:
        print(f"[{percent:6.1f}%] {message}")

    try:
        download_and_merge(progress)
    except Exception as exc:
        print(f"Cardmarket update failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
