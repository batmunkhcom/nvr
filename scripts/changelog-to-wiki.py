#!/usr/bin/env python3
"""Generate Latest-Releases.md from CHANGELOG.md (auto-synced to wiki)."""

import re
import sys
from pathlib import Path


def parse_changelog(changelog_path: str) -> list[dict]:
    """Parse CHANGELOG.md and extract version entries."""
    content = Path(changelog_path).read_text(encoding="utf-8")
    
    # Match version headers: ## v0.01.21 (2026-07-25) — Title
    pattern = r'^## (v[\d.]+) \((\d{4}-\d{2}-\d{2})\) — (.+)$'
    
    versions = []
    current = None
    
    for line in content.splitlines():
        m = re.match(pattern, line.strip())
        if m:
            if current:
                versions.append(current)
            current = {
                "version": m.group(1),
                "date": m.group(2),
                "title": m.group(3),
                "items": [],
                "categories": {"features": [], "fixes": [], "other": []}
            }
        elif current and line.strip().startswith("- **"):
            # Parse bullet point with bold title
            item_m = re.match(r'^- \*\*(.+?)\*\* — (.+)$', line.strip()[2:])
            if item_m:
                title, desc = item_m.groups()
                entry = {"title": title, "desc": desc}
                
                # Categorize based on keywords
                lower = title.lower()
                if any(k in lower for k in ["new", "added", "enabled", "support", "introduced"]):
                    current["categories"]["features"].append(entry)
                elif any(k in lower for k in ["fix", "fixed", "revert", "removed unused", "cleanup"]):
                    current["categories"]["fixes"].append(entry)
                else:
                    current["categories"]["other"].append(entry)
            else:
                # Simple bullet without bold title
                current["items"].append(line.strip()[2:].strip())
    
    if current:
        versions.append(current)
    
    return versions


def generate_wiki_page(versions: list[dict]) -> str:
    """Generate Latest-Releases.md markdown content."""
    lines = ["# Latest Releases", ""]
    lines.append("> Auto-generated from CHANGELOG.md — updated on every docs/ push.")
    lines.append("")
    
    for v in versions[:10]:  # Show latest 10 versions
        lines.append(f"## {v['version']} ({v['date']})")
        lines.append("")
        
        # Features
        if v["categories"]["features"]:
            lines.append("### New Features")
            for item in v["categories"]["features"]:
                lines.append(f"- **{item['title']}** — {item['desc']}")
            lines.append("")
        
        # Fixes
        if v["categories"]["fixes"]:
            lines.append("### Bug Fixes")
            for item in v["categories"]["fixes"]:
                lines.append(f"- **{item['title']}** — {item['desc']}")
            lines.append("")
        
        # Other improvements
        if v["categories"]["other"]:
            lines.append("### Improvements")
            for item in v["categories"]["other"]:
                lines.append(f"- **{item['title']}** — {item['desc']}")
            lines.append("")
        
        # Simple bullets (no categorization matched)
        if v["items"] and not v["categories"]["features"] and not v["categories"]["fixes"] and not v["categories"]["other"]:
            for item in v["items"]:
                lines.append(f"- {item}")
            lines.append("")
    
    return "\n".join(lines)


def main():
    repo_root = Path(__file__).parent.parent
    changelog_path = repo_root / "CHANGELOG.md"
    output_path = repo_root / "docs" / "wiki" / "Latest-Releases.md"
    
    if not changelog_path.exists():
        print(f"ERROR: {changelog_path} not found", file=sys.stderr)
        sys.exit(1)
    
    versions = parse_changelog(str(changelog_path))
    content = generate_wiki_page(versions)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    
    print(f"Generated {output_path} ({len(versions)} versions)")


if __name__ == "__main__":
    main()
