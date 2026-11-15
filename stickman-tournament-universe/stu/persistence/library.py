"""Persistent, versioned JSON libraries (the long-term memory of the universe).

Each library file looks like::

    {"schema": "stu.techniques", "version": 1, "updated": "...", "items": {id: {...}}}

* Stable ids are derived from a canonical *signature* (content hash), so the same
  technique/combination generated twice is stored once (duplicate detection).
* Writes are atomic (temp file + rename).
* Loading validates schema name + version and migrates older versions.
* Libraries only ever grow/merge; nothing is overwritten wholesale.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import zipfile

from .. import PROJECT_ROOT

SCHEMA_VERSION = 1

LIBRARIES = {
    "abilities": "library/abilities.json",
    "techniques": "library/techniques.json",
    "combinations": "library/combinations.json",
    "animations": "library/animations.json",
    "fighters": "library/fighters.json",
    "effects": "library/effects.json",
    "statistics": "library/statistics.json",
    "tournaments": "library/tournaments.json",
    "render_configs": "library/render_configs.json",
    "arenas": "library/arenas.json",
}

REQUIRED_FIELDS = {
    "abilities": ["name", "theme", "tags"],
    "techniques": ["name", "signature", "delivery"],
    "combinations": ["abilities", "reaction"],
    "fighters": ["name", "abilities", "color"],
    "animations": ["keys"],
    "effects": ["style"],
}


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def stable_id(prefix: str, signature) -> str:
    sig = signature if isinstance(signature, str) else canonical(signature)
    return f"{prefix}_{hashlib.sha1(sig.encode()).hexdigest()[:10]}"


def atomic_write_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


class LibraryError(Exception):
    pass


class Library:
    def __init__(self, name: str, path: str):
        self.name = name
        self.path = path
        self.items: dict = {}
        self.dirty = False
        self.load()

    # -- io -----------------------------------------------------------------
    def load(self):
        if not os.path.exists(self.path):
            self.items = {}
            return
        with open(self.path) as f:
            data = json.load(f)
        schema = data.get("schema")
        if schema != f"stu.{self.name}":
            raise LibraryError(f"{self.path}: unexpected schema {schema!r}")
        version = data.get("version", 0)
        if version > SCHEMA_VERSION:
            raise LibraryError(f"{self.path}: version {version} is newer than engine ({SCHEMA_VERSION})")
        items = data.get("items", {})
        if version < SCHEMA_VERSION:
            items = migrate(self.name, version, items)
            self.dirty = True
        for k, v in items.items():
            self._validate(k, v)
        self.items = items

    def _validate(self, key, item):
        for field in REQUIRED_FIELDS.get(self.name, []):
            if field not in item:
                raise LibraryError(f"{self.path}: item {key} missing field {field!r}")

    def save(self, force=False):
        if not (self.dirty or force):
            return
        atomic_write_json(self.path, {
            "schema": f"stu.{self.name}",
            "version": SCHEMA_VERSION,
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "count": len(self.items),
            "items": self.items,
        })
        self.dirty = False

    # -- content --------------------------------------------------------------
    def get(self, key, default=None):
        return self.items.get(key, default)

    def __contains__(self, key):
        return key in self.items

    def __len__(self):
        return len(self.items)

    def values(self):
        return self.items.values()

    def put(self, key, item, merge=True):
        """Insert or merge. Returns True if the item is new."""
        self._validate(key, item)
        existing = self.items.get(key)
        if existing is None:
            self.items[key] = item
            self.dirty = True
            return True
        if merge:
            changed = False
            for k, v in item.items():
                if k not in existing:
                    existing[k] = v
                    changed = True
            self.dirty |= changed
        return False

    def bump(self, key, field, amount=1):
        it = self.items.setdefault(key, {})
        it[field] = it.get(field, 0) + amount
        self.dirty = True


def migrate(name, version, items):
    # Version 0 (pre-release) stored lists; convert to id-keyed dicts.
    if isinstance(items, list):
        items = {it.get("id") or stable_id(name[:3], it): it for it in items}
    return items


class Universe:
    """Access to every persistent library of the project."""

    def __init__(self, root=PROJECT_ROOT):
        self.root = root
        self.libs = {n: Library(n, os.path.join(root, p)) for n, p in LIBRARIES.items()}

    def __getitem__(self, name) -> Library:
        return self.libs[name]

    def theme_path(self, theme_key):
        return os.path.join(self.root, "themes", f"{theme_key}.json")

    def load_theme(self, theme_key):
        p = self.theme_path(theme_key)
        if not os.path.exists(p):
            return None
        with open(p) as f:
            data = json.load(f)
        if data.get("schema") != "stu.theme":
            raise LibraryError(f"{p}: not a theme package")
        return data

    def save_theme(self, theme):
        theme["schema"] = "stu.theme"
        theme["version"] = SCHEMA_VERSION
        theme["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        atomic_write_json(self.theme_path(theme["key"]), theme)

    def list_themes(self):
        d = os.path.join(self.root, "themes")
        return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json")) if os.path.isdir(d) else []

    def save_all(self):
        for lib in self.libs.values():
            lib.save()

    # -- backup / import / export ---------------------------------------------
    def backup(self):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = os.path.join(self.root, "library", "backups", f"backup-{stamp}.zip")
        return self.export(dest)

    def export(self, dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            for rel in list(LIBRARIES.values()):
                p = os.path.join(self.root, rel)
                if os.path.exists(p):
                    z.write(p, rel)
            for t in self.list_themes():
                z.write(self.theme_path(t), f"themes/{t}.json")
        return dest

    def import_bundle(self, src):
        """Merge a bundle into the current libraries (never deletes)."""
        added = 0
        with zipfile.ZipFile(src) as z, tempfile.TemporaryDirectory() as tmp:
            z.extractall(tmp)
            for name, rel in LIBRARIES.items():
                p = os.path.join(tmp, rel)
                if os.path.exists(p):
                    other = Library(name, p)
                    for k, v in other.items.items():
                        added += self.libs[name].put(k, v)
            tdir = os.path.join(tmp, "themes")
            if os.path.isdir(tdir):
                for f in os.listdir(tdir):
                    dest = os.path.join(self.root, "themes", f)
                    if not os.path.exists(dest):
                        shutil.copy(os.path.join(tdir, f), dest)
                        added += 1
        self.save_all()
        return added
