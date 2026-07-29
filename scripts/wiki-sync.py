#!/usr/bin/env python3
"""Wiki sync script — generates all wiki pages from docs/ source files."""

import sys
from pathlib import Path


def main():
    repo_root = Path(__file__).parent.parent
    wiki_dir = repo_root / "docs" / "wiki"
    
    # Ensure wiki directory exists
    wiki_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Wiki output directory: {wiki_dir}")
    
    # List of files that should be in wiki (source → wiki page name)
    mappings = [
        ("README.md", "Home.md", "home"),
        ("docs/ARCHITECTURE.md", "Architecture.md", "architecture"),
    ]
    
    for source, target, _ in mappings:
        src = repo_root / source
        dst = wiki_dir / target
        
        if src.exists():
            content = src.read_text(encoding="utf-8")
            dst.write_text(content, encoding="utf-8")
            print(f"  Synced: {source} → docs/wiki/{target}")
        else:
            print(f"  SKIP: {source} not found (pre-existing wiki page)")
    
    # CHANGELOG.md is handled by changelog-to-wiki.py separately
    print("\nWiki sync complete.")


if __name__ == "__main__":
    main()
