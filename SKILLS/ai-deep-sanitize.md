---
name: ai-deep-sanitize
description: Auto-configures Git credentials, deeply analyzes codebase using AI semantics to redact ALL sensitive data (IPs, Keys, Internal Paths, Webhooks, Emails), and safely mirrors clean code to GitHub's main branch without exposing history or tokens.
---

# AI Deep Sanitization & Mirror Skill

When the user requests to sync, mirror, or push code to GitHub, execute the following workflow:

### Pre-flight Check: Git Credential Security
Before running any git push commands, ensure the Git credential helper is active to prevent tokens from leaking into `.git/config`:
1. Run `git config --global credential.helper`.
2. If EMPTY, inform the user and run the appropriate configuration:
   - If `gh` CLI exists: `gh auth setup-git`
   - Otherwise on Linux: `git config --global credential.helper 'cache --timeout=3600'`
   - On macOS: `git config --global credential.helper osxkeychain`

### Step 1: Pre-Commit File System Cleanup (Hard Exclusions)
Ensure the following patterns are force-removed from Git tracking before mirror:
- All database files (`*.sqlite`, `*.db`, `*.sql`)
- All log files (`*.log`, `npm-debug.log*`)
- Key files (`*.pem`, `*.crt`, `*.key`, `id_rsa*`)
- Environment files (`.env*` except `.env.example`)

### Step 2: Semantic AI Redaction Pass (Smart Scanning)
Review all staged/modified code files. Automatically replace/mask the following categories using contextual analysis (or rely on the auto-sanitize script to do so):
1. **IP Addresses & Domains:** Replace public/private IPs with `process.env.SERVER_IP || "localhost"`.
2. **Absolute File Paths:** Replace Linux/Mac paths (`/home/...`, `/root/...`) with relative paths (`./`) or `process.env.BASE_DIR`.
3. **API Keys & Webhooks:** Replace JWT/Encryption Keys with `"REDACTED_SECRET"`. Replace Webhook URLs with `"https://hooks.redacted.com/services/REDACTED"`.
4. **Personal Information (PII):** Replace real developer emails or admin usernames with `admin@example.com`.
5. **Internal Comments & Prompts:** Remove internal architectural secrets or MBM agent private notes from code comments.

### Step 3: Execution via Auto-Mirror Script
Run the automated git mirror process on an isolated branch. The script handles masking, amending commits (to hide redaction history), and pushing cleanly to GitHub's main branch:
```bash
chmod +x ./scripts/auto-sanitize-push.sh
./scripts/auto-sanitize-push.sh github
