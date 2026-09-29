"""Projects and design version control (spec §21, §22): commit, branch, diff, merge, revert."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from autoeng import vcs
from autoeng.db.models import Branch, Project, User, Version, iso
from autoeng.domain.engine_design import EngineDesign
from autoeng.platform.vehicle import VehicleDesign


class Conflict(Exception):
    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message)
        self.detail = detail or {}


class NotFound(Exception):
    pass


PROJECT_KINDS = ("engine", "vehicle")


def normalise(design: dict, kind: str = "engine") -> dict:
    """Validate and return the canonical JSON form (so hashes and diffs are stable)."""
    if kind == "vehicle":
        return VehicleDesign.model_validate(design).model_dump(mode="json")
    return EngineDesign.model_validate(design).model_dump(mode="json")


def get_project(db: Session, user: User, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise NotFound("Project not found")
    return project


def get_branch(db: Session, project: Project, name: str) -> Branch:
    branch = db.scalar(select(Branch).where(Branch.project_id == project.id, Branch.name == name))
    if branch is None:
        raise NotFound(f"Branch '{name}' not found")
    return branch


def get_version(db: Session, project: Project, version_id: str) -> Version:
    v = db.get(Version, version_id)
    if v is None or v.project_id != project.id:
        raise NotFound("Version not found")
    return v


def _next_number(db: Session, project: Project) -> int:
    return (db.scalar(select(func.max(Version.number)).where(Version.project_id == project.id)) or 0) + 1


def _new_version(db, project, user, branch_name, message, design, parent_id=None, merge_parent_id=None) -> Version:
    v = Version(
        project_id=project.id, number=_next_number(db, project), parent_id=parent_id, merge_parent_id=merge_parent_id,
        branch=branch_name, message=message.strip() or "(no message)", design=design,
        design_hash=vcs.canonical_hash(design), author_id=user.id,
    )
    db.add(v)
    db.flush()
    return v


def create_project(db: Session, user: User, name: str, description: str, design: dict, kind: str = "engine") -> Project:
    if kind not in PROJECT_KINDS:
        raise ValueError(f"kind must be one of {PROJECT_KINDS}")
    design = normalise(design, kind)
    project = Project(owner_id=user.id, name=name, description=description, kind=kind)
    db.add(project)
    db.flush()
    v = _new_version(db, project, user, "main", "Initial design", design)
    db.add(Branch(project_id=project.id, name="main", head_version_id=v.id))
    db.commit()
    return project


def commit(db: Session, user: User, project: Project, branch_name: str, message: str, design: dict,
           expected_head: str | None = None) -> Version:
    """Append a version to a branch. `expected_head` guards against overwriting someone else's commit."""
    branch = get_branch(db, project, branch_name)
    if expected_head and branch.head_version_id != expected_head:
        raise Conflict("Branch moved since you loaded it; reload and re-apply your changes",
                       {"head_version_id": branch.head_version_id})
    design = normalise(design, project.kind)
    head = db.get(Version, branch.head_version_id)
    if head and head.design_hash == vcs.canonical_hash(design):
        raise Conflict("No changes to commit")
    v = _new_version(db, project, user, branch_name, message, design, parent_id=branch.head_version_id)
    branch.head_version_id = v.id
    project.updated_at = v.created_at
    db.commit()
    return v


def create_branch(db: Session, project: Project, name: str, from_version_id: str) -> Branch:
    name = name.strip()
    if not name or len(name) > 100 or any(c.isspace() for c in name):
        raise ValueError("Branch names must be 1-100 characters without spaces")
    if db.scalar(select(Branch).where(Branch.project_id == project.id, Branch.name == name)):
        raise Conflict(f"Branch '{name}' already exists")
    get_version(db, project, from_version_id)
    b = Branch(project_id=project.id, name=name, head_version_id=from_version_id)
    db.add(b)
    db.commit()
    return b


def delete_branch(db: Session, project: Project, name: str) -> None:
    if name == project.default_branch:
        raise Conflict("Cannot delete the default branch")
    db.delete(get_branch(db, project, name))
    db.commit()


def history(db: Session, project: Project) -> list[Version]:
    return list(db.scalars(select(Version).where(Version.project_id == project.id).order_by(Version.number.desc())))


def _ancestors(db: Session, version_id: str) -> list[str]:
    """All ancestors (breadth-first, nearest first), including the version itself."""
    order, seen, queue = [], set(), [version_id]
    while queue:
        vid = queue.pop(0)
        if vid in seen or vid is None:
            continue
        seen.add(vid)
        order.append(vid)
        v = db.get(Version, vid)
        if v:
            queue.extend([p for p in (v.parent_id, v.merge_parent_id) if p])
    return order


def merge_base(db: Session, a: str, b: str) -> str | None:
    ancestors_b = set(_ancestors(db, b))
    return next((vid for vid in _ancestors(db, a) if vid in ancestors_b), None)


def merge(db: Session, user: User, project: Project, source: str, target: str, message: str | None = None,
          resolutions: dict | None = None) -> Version:
    """Merge branch `source` into `target`. Conflicts raise unless resolved as {path: "ours"|"theirs"}."""
    src, dst = get_branch(db, project, source), get_branch(db, project, target)
    if src.head_version_id == dst.head_version_id:
        raise Conflict("Branches are already identical")
    base_id = merge_base(db, dst.head_version_id, src.head_version_id)
    if base_id == src.head_version_id:
        raise Conflict(f"'{target}' already contains every change on '{source}'")
    ours, theirs = db.get(Version, dst.head_version_id), db.get(Version, src.head_version_id)
    base = db.get(Version, base_id).design if base_id else ours.design
    merged, conflicts = vcs.merge3(base, ours.design, theirs.design)
    resolutions = resolutions or {}
    unresolved = [c for c in conflicts if c["path"] not in resolutions]
    if unresolved:
        raise Conflict("Merge has conflicts", {"conflicts": unresolved})
    if conflicts:
        flat = vcs.flatten(merged)
        for c in conflicts:
            choice = c["theirs"] if resolutions[c["path"]] == "theirs" else c["ours"]
            if choice is None:
                flat.pop(c["path"], None)
            else:
                flat[c["path"]] = choice
        merged = vcs.unflatten(flat)
    merged = normalise(merged, project.kind)
    v = _new_version(db, project, user, target, message or f"Merge '{source}' into '{target}'", merged,
                     parent_id=ours.id, merge_parent_id=theirs.id)
    dst.head_version_id = v.id
    db.commit()
    return v


def revert_to(db: Session, user: User, project: Project, branch_name: str, version_id: str) -> Version:
    """Create a new head whose design equals an earlier version (history is never rewritten)."""
    target = get_version(db, project, version_id)
    return commit(db, user, project, branch_name, f"Revert to v{target.number}", target.design)


def version_dict(v: Version, include_design: bool = False) -> dict:
    d = {
        "id": v.id, "number": v.number, "parent_id": v.parent_id, "merge_parent_id": v.merge_parent_id,
        "branch": v.branch, "message": v.message, "design_hash": v.design_hash, "author_id": v.author_id,
        "created_at": iso(v.created_at), "name": v.design.get("name"),
    }
    if include_design:
        d["design"] = v.design
    return d
