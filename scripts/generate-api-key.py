#!/usr/bin/env python3
import secrets
import sys

project = sys.argv[1] if len(sys.argv) > 1 else "project"
slug = "".join(ch for ch in project.lower() if ch.isalnum() or ch == "-").strip("-") or "project"
print(f"scraper-{slug}-{secrets.token_urlsafe(24)}")
