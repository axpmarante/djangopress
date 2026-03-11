"""
sync_skills management command — sync Claude Code skills from djangopress package to child site.

Creates symlinks in the child project's .claude/skills/ directory pointing to the
skills in the installed djangopress package. Also generates a CLAUDE.md with
project-specific instructions.

Usage:
    python manage.py sync_skills          # sync all skills + CLAUDE.md
    python manage.py sync_skills --list   # list available skills
    python manage.py sync_skills --clean  # remove stale skills not in package
"""

import os
import shutil
from pathlib import Path

from django.core.management.base import BaseCommand

import djangopress


CLAUDE_MD_TEMPLATE = """\
# {project_name} — DjangoPress Child Project

This is a DjangoPress child site. The CMS engine is the `djangopress` pip package.

## Architecture

See the [DjangoPress Architecture](/djangopress-architecture) skill for full reference.

## Project Structure

- `config/` — thin settings, urls, wsgi (imports from djangopress)
- `.env` — secrets and API keys (never committed)
- `requirements.txt` — points to djangopress package
- `manage.py` — Django entry point
- `briefings/` — site briefing markdown files

## Key Commands

```bash
python manage.py runserver 8000                        # Dev server
python manage.py migrate                               # Run migrations
python manage.py sync_skills                           # Re-sync skills from djangopress
python manage.py generate_site briefings/<briefing>.md # Generate site from briefing
python manage.py push_data https://<domain>            # Push local DB to production
python manage.py pull_data https://<domain>            # Pull remote DB to local
```

## Skills

Use `/generate-site`, `/update-site`, `/add-app`, `/deploy-site-railway`, `/sync-data`, etc.

## Git Conventions

- **Do not include `Co-Authored-By` lines in commit messages.**

## Key Reminders

- **Home page slug must be `home` in ALL languages**
- **Set domain BEFORE uploading media** (GCS uses domain as folder name)
- **Decoupled app URLs** must register BEFORE `core.urls` (catch-all)
"""


class Command(BaseCommand):
    help = 'Sync Claude Code skills and CLAUDE.md from the djangopress package to this project'

    def add_arguments(self, parser):
        parser.add_argument(
            '--list', action='store_true',
            help='List available skills without syncing',
        )
        parser.add_argument(
            '--clean', action='store_true',
            help='Remove skills in child site that no longer exist in the package',
        )
        parser.add_argument(
            '--skip-claude-md', action='store_true',
            help='Skip generating CLAUDE.md',
        )

    def handle(self, *args, **options):
        # Locate the djangopress package skills directory
        # Skills are bundled inside the djangopress package at djangopress/skills/
        package_skills_dir = Path(djangopress.__file__).resolve().parent / 'skills'

        if not package_skills_dir.is_dir():
            self.stderr.write(self.style.ERROR(
                f'Package skills directory not found: {package_skills_dir}'
            ))
            return

        # Locate the child project root (where manage.py lives)
        project_dir = Path(os.getcwd())
        project_skills_dir = project_dir / '.claude' / 'skills'

        # Discover available skills in package
        available_skills = sorted([
            d.name for d in package_skills_dir.iterdir()
            if d.is_dir() and (d / 'SKILL.md').exists()
        ])

        if options['list']:
            self.stdout.write(self.style.SUCCESS(f'Available skills ({len(available_skills)}):'))
            for skill in available_skills:
                source = package_skills_dir / skill
                local = project_skills_dir / skill
                status = ''
                if local.is_symlink():
                    if local.resolve() == source.resolve():
                        status = self.style.SUCCESS(' [linked]')
                    else:
                        status = self.style.WARNING(' [stale link]')
                elif local.is_dir():
                    status = self.style.WARNING(' [copy, not linked]')
                else:
                    status = self.style.NOTICE(' [not installed]')
                self.stdout.write(f'  {skill}{status}')
            return

        # Create .claude/skills/ directory if needed
        # Remove existing symlink (from old broken setup) if present
        if project_skills_dir.is_symlink():
            project_skills_dir.unlink()
        project_skills_dir.mkdir(parents=True, exist_ok=True)

        # Sync each skill
        created = 0
        updated = 0
        skipped = 0

        for skill_name in available_skills:
            source = package_skills_dir / skill_name
            target = project_skills_dir / skill_name

            if target.is_symlink():
                if target.resolve() == source.resolve():
                    skipped += 1
                    continue
                # Stale symlink — remove and recreate
                target.unlink()
                os.symlink(source, target)
                updated += 1
                self.stdout.write(f'  Updated: {skill_name}')
            elif target.is_dir():
                # It's a copy — replace with symlink
                shutil.rmtree(target)
                os.symlink(source, target)
                updated += 1
                self.stdout.write(f'  Replaced copy with symlink: {skill_name}')
            else:
                # New skill
                os.symlink(source, target)
                created += 1
                self.stdout.write(f'  Created: {skill_name}')

        # Clean stale skills
        removed = 0
        if options['clean']:
            for item in project_skills_dir.iterdir():
                if item.is_dir() or item.is_symlink():
                    if item.name not in available_skills:
                        if item.is_symlink():
                            item.unlink()
                        else:
                            shutil.rmtree(item)
                        removed += 1
                        self.stdout.write(f'  Removed stale: {item.name}')

        # Generate CLAUDE.md if it doesn't exist
        if not options['skip_claude_md']:
            claude_md_path = project_dir / 'CLAUDE.md'
            project_name = project_dir.name.replace('-', ' ').title()
            if not claude_md_path.exists():
                claude_md_path.write_text(
                    CLAUDE_MD_TEMPLATE.format(project_name=project_name)
                )
                self.stdout.write(f'  Created: CLAUDE.md')
            else:
                self.stdout.write(f'  CLAUDE.md already exists, skipping')

        # Summary
        parts = []
        if created:
            parts.append(f'{created} created')
        if updated:
            parts.append(f'{updated} updated')
        if skipped:
            parts.append(f'{skipped} up-to-date')
        if removed:
            parts.append(f'{removed} removed')

        summary = ', '.join(parts) if parts else 'nothing to do'
        self.stdout.write(self.style.SUCCESS(f'Skills synced: {summary}'))
