"""
Image resolution by folder convention.

Instead of pasting an image URL per player/team (which also silently fails
for Google Drive share links - those don't serve raw image bytes), we look
for a file on disk named after the player's phone number or the team's
slug, dropped into a fixed folder structure once.

    app/static/images/players/main/<phone>.png        -> player's default photo
    app/static/images/players/<team-slug>/<phone>.png -> photo in that team's kit (after sold)
    app/static/images/teams/<team-slug>.png            -> team logo

<team-slug> = team name, lowercased, spaces removed (e.g. "Spartans" -> "spartans").
.png is checked first, .jpg / .jpeg as a fallback, so either works.

If nothing is found on disk, we fall back to the DB url field (if one was
set another way) and finally to the built-in placeholder SVG - never a
broken image.
"""
import re
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / "static"
IMAGES_DIR = STATIC_DIR / "images"

PLACEHOLDER_PLAYER = "/static/img/placeholder_player_photo.svg"
PLACEHOLDER_TEAM = "/static/img/placeholder_team_logo.svg"

EXTS = (".png", ".jpg", ".jpeg")


def slugify(name: str) -> str:
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _find(folder: Path, stem: str):
    if not stem:
        return None
    for ext in EXTS:
        candidate = folder / f"{stem}{ext}"
        if candidate.is_file():
            rel = candidate.relative_to(STATIC_DIR)
            return f"/static/{rel.as_posix()}"
    return None


def resolve_player_photo(player, team=None) -> str:
    """Kit photo for `team` if present, else the player's main photo,
    else the DB url if one is set, else the placeholder."""
    if player is None:
        return PLACEHOLDER_PLAYER
    phone = getattr(getattr(player, "user", None), "phone", None)
    phone = re.sub(r"\D", "", phone or "")

    if team is not None:
        team_slug = slugify(getattr(team, "name", ""))
        found = _find(IMAGES_DIR / "players" / team_slug, phone)
        if found:
            return found

    found = _find(IMAGES_DIR / "players" / "main", phone)
    if found:
        return found

    if getattr(player, "profile_photo_url", None):
        return player.profile_photo_url

    return PLACEHOLDER_PLAYER


def resolve_team_logo(team) -> str:
    if team is None:
        return PLACEHOLDER_TEAM
    team_slug = slugify(getattr(team, "name", ""))
    found = _find(IMAGES_DIR / "teams", team_slug)
    if found:
        return found
    if getattr(team, "logo_url", None):
        return team.logo_url
    return PLACEHOLDER_TEAM


def player_image_folders():
    """Existing team-kit subfolders under images/players/, for admin UI hints."""
    base = IMAGES_DIR / "players"
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and p.name != "main")


ALLOWED_UPLOAD_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg"}


def save_uploaded_image(file, folder: Path, stem: str) -> str:
    """Save an uploaded image under `folder/stem.<ext>`, replacing any
    existing file for that stem (any extension) so there's never a stale
    duplicate. Returns the /static/... URL, or raises ValueError on a
    type we don't recognise."""
    ext = ALLOWED_UPLOAD_TYPES.get((file.content_type or "").lower())
    if not ext:
        # fall back to sniffing the filename if content-type header is missing/odd
        name = (file.filename or "").lower()
        for e in EXTS:
            if name.endswith(e):
                ext = ".jpg" if e in (".jpg", ".jpeg") else e
                break
    if not ext:
        raise ValueError("Only PNG or JPG images are supported.")

    folder.mkdir(parents=True, exist_ok=True)
    for old_ext in EXTS:
        stale = folder / f"{stem}{old_ext}"
        if stale.is_file():
            stale.unlink()

    dest = folder / f"{stem}{ext}"
    with open(dest, "wb") as out:
        out.write(file.file.read())

    rel = dest.relative_to(STATIC_DIR)
    return f"/static/{rel.as_posix()}"
