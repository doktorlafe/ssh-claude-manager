from __future__ import annotations

import argparse

from . import config


def main() -> None:
    parser = argparse.ArgumentParser(prog="ccm", description="tmux/SSH manager for Claude Code agents")
    parser.add_argument("hosts", nargs="*",
                        help=f"SSH hosts to manage, or 'local' (default: from {config.CONFIG_PATH})")
    args = parser.parse_args()
    cfg = config.load()
    if args.hosts:
        if any(h.startswith("-") for h in args.hosts):
            parser.error("host names cannot start with '-'")
        cfg.hosts = args.hosts

    from .app import CcmApp

    CcmApp(cfg).run()


if __name__ == "__main__":
    main()
