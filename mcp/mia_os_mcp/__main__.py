"""Einstiegspunkt: startet den Server ueber stdio."""

from mia_os_mcp.server import mcp


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
