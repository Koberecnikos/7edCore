"""Mods per server: install (upload / URL / GitHub), find a release compatible with the
server's game version, update in place while keeping files the user edited."""
import asyncio
import hashlib
import os
import re
import shutil
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import aiohttp
from aiohttp import web

from . import versions
from .util import dir_size, load_json, safe_extract, save_json, stamp

GITHUB_API = "https://api.github.com"
NEXUS_API = "https://api.nexusmods.com/v1/games/7daystodie"
MAX_DOWNLOAD = 2 * 1024 ** 3
UA = {"User-Agent": "7edCore-panel"}


# ------------------------------------------------------------------ sources
def parse_source(text):
    """'owner/repo', GitHub URL, Nexus URL or direct .zip URL -> source dict."""
    s = (text or "").strip()
    m = re.match(r"^(?:https?://github\.com/)?([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/.*)?$", s)
    if m and ("github.com" in s or re.fullmatch(r"[\w.-]+/[\w.-]+", s)):
        if s.lower().endswith(".zip") and "github.com" in s and "/releases/download/" in s:
            return {"type": "url", "url": s, "repo": f"{m.group(1)}/{m.group(2)}"}
        return {"type": "github", "repo": f"{m.group(1)}/{m.group(2)}"}
    m = re.match(r"^https?://(?:www\.)?nexusmods\.com/7daystodie/mods/(\d+)", s)
    if m:
        return {"type": "nexus", "id": int(m.group(1)), "url": f"https://www.nexusmods.com/7daystodie/mods/{m.group(1)}"}
    if re.match(r"^https?://", s):
        return {"type": "url", "url": s}
    raise web.HTTPBadRequest(text="Unknown mod source - use owner/repo, a GitHub/Nexus link or a direct .zip URL")


async def _get_json(url, headers=None):
    async with aiohttp.ClientSession(headers={**UA, **(headers or {})}, timeout=aiohttp.ClientTimeout(total=30)) as s:
        async with s.get(url) as r:
            if r.status == 403 and "rate limit" in (await r.text()).lower():
                raise web.HTTPServiceUnavailable(text="GitHub API rate limit reached - add a GitHub token in Settings or try later")
            if r.status >= 400:
                raise web.HTTPBadGateway(text=f"{url}: HTTP {r.status}")
            return await r.json()


async def download(url, dest: Path, headers=None):
    async with aiohttp.ClientSession(headers={**UA, **(headers or {})}, timeout=aiohttp.ClientTimeout(total=1800)) as s:
        async with s.get(url) as r:
            if r.status >= 400:
                raise web.HTTPBadGateway(text=f"Download failed: HTTP {r.status}")
            size = 0
            with open(dest, "wb") as f:
                async for chunk in r.content.iter_chunked(1 << 20):
                    size += len(chunk)
                    if size > MAX_DOWNLOAD:
                        raise web.HTTPRequestEntityTooLarge(max_size=MAX_DOWNLOAD, actual_size=size)
                    f.write(chunk)


async def github_releases(repo, token=None):
    h = {"Accept": "application/vnd.github+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = await _get_json(f"{GITHUB_API}/repos/{repo}/releases?per_page=30", h)
    out = []
    for r in data:
        if r.get("draft"):
            continue
        assets = [{"name": a["name"], "url": a["browser_download_url"], "size": a["size"]}
                  for a in r.get("assets", []) if a["name"].lower().endswith(".zip")]
        text = " ".join([r.get("tag_name") or "", r.get("name") or "", (r.get("body") or "")[:4000],
                         " ".join(a["name"] for a in assets)])
        out.append({"tag": r.get("tag_name"), "name": r.get("name") or r.get("tag_name"), "prerelease": r.get("prerelease"),
                    "published": r.get("published_at"), "assets": assets, "zipball": r.get("zipball_url"),
                    "mentions": versions.find_all(text), "url": r.get("html_url")})
    return out


def pick_release(releases, game_v, allow_unknown=True, allow_pre=False):
    """Newest release made for the game version; fallback: newest without any version info."""
    unknown = None
    for r in releases:
        if r["prerelease"] and not allow_pre:
            continue
        c = versions.mod_compat(r["mentions"], game_v)
        if c == "yes":
            return r, "yes"
        if c == "unknown" and unknown is None:
            unknown = r
    if allow_unknown and unknown:
        return unknown, "unknown"
    return None, "no"


def pick_asset(rel, game_v):
    zips = rel["assets"]
    if game_v and len(zips) > 1:
        for a in zips:
            if versions.mod_compat(versions.find_all(a["name"]), game_v) == "yes":
                return a["url"]
    if zips:
        return zips[0]["url"]
    return rel["zipball"]


# ------------------------------------------------------------------ files
def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest(d: Path):
    return {str(p.relative_to(d)): sha(p) for p in d.rglob("*") if p.is_file()}


def carry_over(old: Path, new: Path, baseline: dict):
    """Copy files the user changed/added in the old mod folder into the new one.
    If the mod author also changed that file, the author's version is kept next to it as *.new."""
    kept, conflicts, base = [], [], {}
    if not baseline:
        return kept, conflicts, base
    for p in old.rglob("*"):
        if not p.is_file():
            continue
        rp = str(p.relative_to(old))
        if baseline.get(rp) == sha(p):
            continue                          # untouched by the user
        target = new / rp
        author = sha(target) if target.exists() else None
        if author and author != baseline.get(rp, ""):
            shutil.copy2(target, target.with_name(target.name + ".new"))
            conflicts.append(rp)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        kept.append(rp)
        base[rp] = author                     # baseline = author's file, so the user edit stays detectable
    return kept, conflicts, base


def mod_info(d: Path, enabled: bool):
    info = {"folder": d.name, "enabled": enabled, "name": d.name, "version": "", "author": "", "description": "",
            "website": ""}
    mi = d / "ModInfo.xml"
    if mi.exists():
        try:
            root = ET.parse(mi).getroot()
            dn, nm = root.find(".//DisplayName"), root.find(".//Name")
            info["name"] = (dn.get("value") if dn is not None and dn.get("value") else
                            nm.get("value") if nm is not None and nm.get("value") else d.name)
            for k in ("Version", "Author", "Description", "Website"):
                el = root.find(f".//{k}")
                if el is not None and el.get("value"):
                    info[k.lower()] = el.get("value")
        except ET.ParseError:
            info["description"] = "(ModInfo.xml is not valid XML)"
    else:
        info["description"] = "(ModInfo.xml missing)"
    return info


# ------------------------------------------------------------------ per-server manager
class Mods:
    def __init__(self, inst):
        self.inst = inst
        self.on = inst.userdata / "Mods"
        self.off = inst.userdata / "Mods_disabled"
        self.meta_file = inst.dir / "mods.json"
        self.meta = load_json(self.meta_file, {})
        self.lock = asyncio.Lock()

    def save(self):
        save_json(self.meta_file, self.meta)

    def path(self, folder):
        folder = Path(str(folder)).name
        for base in (self.on, self.off):
            if (base / folder).is_dir():
                return base / folder
        return None

    def list(self):
        out = []
        for base, en in ((self.on, True), (self.off, False)):
            if base.exists():
                for d in sorted(base.iterdir()):
                    if d.is_dir():
                        i = mod_info(d, en)
                        i["size"] = dir_size(d)
                        m = self.meta.get(d.name, {})
                        i.update(source=m.get("source"), release=m.get("release"), compat=m.get("compat"),
                                 check=m.get("check"), installed_at=m.get("installed_at"))
                        out.append(i)
        return out

    # ---------------------------------------------------------- install
    async def install_zip(self, zpath: Path, source=None, release=None, compat=None, only=None):
        """Install every mod (folder with ModInfo.xml) found in a ZIP. Existing ones are replaced
        and files the user edited are carried over."""
        async with self.lock:
            self.on.mkdir(parents=True, exist_ok=True)
            tmp = Path(tempfile.mkdtemp(dir=self.inst.dir, prefix=".mod_"))
            report = []
            try:
                ex = tmp / "x"
                await asyncio.to_thread(safe_extract, zpath, ex)
                infos = sorted(ex.rglob("ModInfo.xml"), key=lambda p: len(p.parts))
                roots = []
                for mi in infos:                      # skip ModInfo.xml nested inside another mod
                    if not any(r in mi.parents for r in roots):
                        roots.append(mi.parent)
                if not roots:
                    raise web.HTTPBadRequest(text="No ModInfo.xml in the archive - is this a 7 Days to Die mod?")
                for src in roots:
                    name = src.name if src != ex else Path(zpath).stem
                    if only and name != only and len(roots) > 1:
                        continue
                    old = self.path(name)
                    enabled = old is None or old.parent == self.on
                    dst = (self.on if enabled else self.off) / name
                    kept, conflicts, base = [], [], {}
                    if old:
                        kept, conflicts, base = await asyncio.to_thread(carry_over, old, src,
                                                                        self.meta.get(name, {}).get("manifest") or {})
                        bdir = self.inst.dir / "mod_backups"
                        bdir.mkdir(exist_ok=True)
                        shutil.move(str(old), str(bdir / f"{name}_{stamp()}"))
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
                    man = await asyncio.to_thread(manifest, dst)
                    for rp, h in base.items():
                        if h:
                            man[rp] = h
                        else:
                            man.pop(rp, None)         # user-added file, not part of the mod
                    for k in [k for k in man if k.endswith(".new")]:
                        man.pop(k)
                    self.meta[name] = {**self.meta.get(name, {}), "manifest": man, "installed_at": time.time(),
                                       **({"source": source} if source else {}),
                                       **({"release": release} if release else {}),
                                       **({"compat": compat} if compat else {})}
                    report.append({"folder": name, "kept": kept, "conflicts": conflicts, "updated": old is not None})
                self.save()
                return report
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

    async def install_from(self, source_text, token=None):
        src = parse_source(source_text)
        game_v = versions.parse(self.inst.game_version_label() or "")
        tmp = Path(tempfile.mkdtemp(dir=self.inst.dir, prefix=".dl_"))
        try:
            zp = tmp / "mod.zip"
            release, compat = None, None
            if src["type"] == "github":
                rels = await github_releases(src["repo"], token)
                if not rels:
                    raise web.HTTPNotFound(text=f"{src['repo']} has no releases - use a direct .zip link")
                rel, compat = pick_release(rels, game_v)
                if not rel:
                    raise web.HTTPConflict(text=f"No release of {src['repo']} is made for {game_v['label'] if game_v else 'this game version'}")
                await download(pick_asset(rel, game_v), zp, {"Authorization": f"Bearer {token}"} if token else None)
                release = rel["tag"]
            elif src["type"] == "url":
                await download(src["url"], zp)
            else:
                raise web.HTTPBadRequest(text="Nexus Mods does not allow direct downloads without Premium - download the ZIP and upload it, then link the Nexus page for update checks")
            return await self.install_zip(zp, source=src, release=release, compat=compat)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ---------------------------------------------------------- updates
    async def check(self, folder, token=None, nexus_key=None):
        """Look for the newest release compatible with the server's game version."""
        m = self.meta.get(folder) or {}
        src = m.get("source")
        game_v = versions.parse(self.inst.game_version_label() or "")
        res = {"checked": time.time(), "update": False}
        try:
            if not src:
                res["status"] = "no_source"
            elif src["type"] == "github":
                rels = await github_releases(src["repo"], token)
                rel, compat = pick_release(rels, game_v)
                if not rel:
                    res.update(status="none_compatible")
                else:
                    res.update(status="ok", latest=rel["tag"], compat=compat, url=rel["url"],
                               update=rel["tag"] != m.get("release"))
                    cur = next((r for r in rels if r["tag"] == m.get("release")), None)
                    if cur is not None:
                        res["current_compat"] = versions.mod_compat(cur["mentions"], game_v)
            elif src["type"] == "nexus":
                if not nexus_key:
                    res["status"] = "nexus_key_needed"
                else:
                    data = await _get_json(f"{NEXUS_API}/mods/{src['id']}/files.json", {"apikey": nexus_key})
                    files = [f for f in data.get("files", []) if f.get("category_name") in ("MAIN", "UPDATE", "OPTIONAL")]
                    files.sort(key=lambda f: f.get("uploaded_timestamp", 0), reverse=True)
                    best = None
                    for f in files:
                        c = versions.mod_compat(versions.find_all(f"{f.get('name')} {f.get('version')} {f.get('description', '')}"), game_v)
                        if c in ("yes", "unknown"):
                            best = (f, c)
                            break
                    if best:
                        res.update(status="ok", latest=best[0].get("version"), compat=best[1], url=src["url"],
                                   update=best[0].get("version") != m.get("release"), manual=True)
                    else:
                        res["status"] = "none_compatible"
            else:
                res["status"] = "no_check"
        except web.HTTPException as e:
            res.update(status="error", error=e.text)
        if folder in self.meta:
            self.meta[folder]["check"] = res
            self.save()
        return res

    async def update(self, folder, token=None):
        m = self.meta.get(folder) or {}
        src = m.get("source")
        if not src or src["type"] not in ("github", "url"):
            raise web.HTTPBadRequest(text="This mod has no downloadable source - upload the new ZIP manually")
        game_v = versions.parse(self.inst.game_version_label() or "")
        tmp = Path(tempfile.mkdtemp(dir=self.inst.dir, prefix=".dl_"))
        try:
            zp = tmp / "mod.zip"
            release, compat = m.get("release"), m.get("compat")
            if src["type"] == "github":
                rel, compat = pick_release(await github_releases(src["repo"], token), game_v)
                if not rel:
                    raise web.HTTPConflict(text="No compatible release found")
                await download(pick_asset(rel, game_v), zp, {"Authorization": f"Bearer {token}"} if token else None)
                release = rel["tag"]
            else:
                await download(src["url"], zp)
            rep = await self.install_zip(zp, source=src, release=release, compat=compat, only=folder)
            if folder in self.meta:
                self.meta[folder].pop("check", None)
                self.save()
            return rep
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def set_source(self, folder, source_text):
        if not self.path(folder):
            raise web.HTTPNotFound(text="Mod not found")
        m = self.meta.setdefault(folder, {})
        if source_text:
            m["source"] = parse_source(source_text)
        else:
            m.pop("source", None)
        if not m.get("manifest"):          # baseline from now on (edits made later will be carried over)
            m["manifest"] = manifest(self.path(folder))
        self.save()

    def toggle(self, folder):
        p = self.path(folder)
        if not p:
            raise web.HTTPNotFound(text="Mod not found")
        target = (self.off if p.parent == self.on else self.on) / p.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(target))
        return target.parent == self.on

    def delete(self, folder):
        p = self.path(folder)
        if not p:
            raise web.HTTPNotFound(text="Mod not found")
        shutil.rmtree(p)
        self.meta.pop(p.name, None)
        self.save()
