"""Evidence-led university community research. Contains no messaging or joining code."""

import copy
import hashlib
import html
import ipaddress
import json
import math
import re
import sqlite3
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

DAY = 86400
TTLS = {
    "affiliation": 90 * DAY,
    "invite": 7 * DAY,
    "member": DAY,
    "posting": DAY,
    "charity": 30 * DAY,
    "activity": 7 * DAY,
}
VALUES = {
    "affiliation": {"verified", "unknown", "unverified"},
    "invite": {"valid", "expired", "unknown"},
    "member": {"yes", "no", "unknown"},
    "posting": {"all_members", "admins_only", "unknown"},
    "charity": {"allowed", "denied", "unknown"},
    "activity": {"active", "quiet", "unknown"},
}
KEY = "university_group_finder_v1"


class Conflict(ValueError):
    pass


def text(value, limit=500):
    if not isinstance(value, str):
        raise ValueError("Expected text.")
    return "".join(c for c in value if c >= " " or c in "\n\t").strip()[:limit]


def public_url(value):
    value = html.unescape(text(value, 3000))
    if any(c.isspace() for c in value) or "\\" in value:
        raise ValueError("Use a public HTTPS URL.")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Use a public HTTPS URL without credentials or custom ports.")
    host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    if "." not in host or host.endswith(
        (".localhost", ".local", ".internal", ".test", ".invalid", ".example")
    ):
        # Reserved example/test names are permitted as evidence fixtures, never fetched by the network layer.
        if not host.endswith((".test", ".example")):
            raise ValueError("Use a public host name.")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError("Private and reserved network addresses are not allowed.")
    except ValueError as exc:
        if "not allowed" in str(exc):
            raise
    return urlunsplit(("https", host, parsed.path or "/", parsed.query, ""))


def normalize_invite(value):
    parsed = urlsplit(public_url(value))
    token = parsed.path.strip("/")
    if parsed.hostname != "chat.whatsapp.com" or not re.fullmatch(r"[A-Za-z0-9]{22}", token):
        raise ValueError("Use a valid WhatsApp group invitation link.")
    return "https://chat.whatsapp.com/" + token


def official(url, university):
    host = urlsplit(url).hostname or ""
    return any(host == d or host.endswith("." + d) for d in university.get("domains", []))


def initial_state():
    return {
        "schema": 1,
        "universities": [],
        "groups": [],
        "jobs": [],
        "audit": [],
        "settings": {
            "enabled": False,
            "interval_hours": 24,
            "next_at": 0,
            "university_ids": [],
            "query_cursor": 0,
        },
        "requests": {},
    }


def valid_state(data):
    if (
        not isinstance(data, dict)
        or data.get("schema") != 1
        or any(
            not isinstance(data.get(k), list) for k in ("universities", "groups", "jobs", "audit")
        )
    ):
        raise RuntimeError("Group research records need repair. Existing data was preserved.")
    return data


class Repository:
    """One transaction per mutation; no lost updates across workers or instances."""

    def __init__(self, root, store=None):
        self.store = store
        self.path = Path(root) / "group-finder.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if store is None:
            db = self._local()
            try:
                with db:
                    db.execute(
                        "CREATE TABLE IF NOT EXISTS research (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)"
                    )
                    db.execute(
                        "INSERT OR IGNORE INTO research VALUES (1, ?)",
                        (json.dumps(initial_state()),),
                    )
            finally:
                db.close()

    def _local(self):
        return sqlite3.connect(self.path, timeout=15)

    def read(self):
        if self.store is not None:
            value = self.store.get(KEY)
            return copy.deepcopy(valid_state(value)) if value is not None else initial_state()
        db = self._local()
        try:
            return valid_state(
                json.loads(db.execute("SELECT payload FROM research WHERE id=1").fetchone()[0])
            )
        finally:
            db.close()

    def mutate(self, fn):
        if self.store is not None:
            if not hasattr(self.store, "connection"):
                raise RuntimeError(
                    "Transactional cloud persistence is required for research changes."
                )
            from persist import Jsonb

            with self.store.connection() as db, db.transaction():
                db.execute(
                    "INSERT INTO givelife_studio_state(key,value) VALUES(%s,%s) ON CONFLICT(key) DO NOTHING",
                    (KEY, Jsonb(initial_state())),
                )
                row = db.execute(
                    "SELECT value FROM givelife_studio_state WHERE key=%s FOR UPDATE", (KEY,)
                ).fetchone()
                data = valid_state(row[0])
                result = fn(data)
                db.execute(
                    "UPDATE givelife_studio_state SET value=%s,updated_at=NOW() WHERE key=%s",
                    (Jsonb(data), KEY),
                )
                return copy.deepcopy(result)
        db = self._local()
        try:
            db.execute("BEGIN IMMEDIATE")
            data = valid_state(
                json.loads(db.execute("SELECT payload FROM research WHERE id=1").fetchone()[0])
            )
            result = fn(data)
            db.execute(
                "UPDATE research SET payload=? WHERE id=1",
                (json.dumps(data, ensure_ascii=False, allow_nan=False),),
            )
            db.commit()
            return copy.deepcopy(result)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def fresh(check, kind, now):
    stamp = check.get("checked_at", 0)
    return (
        isinstance(stamp, (int, float))
        and not isinstance(stamp, bool)
        and math.isfinite(stamp)
        and 0 <= now - stamp <= TTLS[kind]
    )


def assess(row, university, now):
    row = copy.deepcopy(row)
    reasons, points = [], []
    checks = row["checks"]
    expected = {
        "affiliation": "verified",
        "invite": "valid",
        "member": "yes",
        "posting": "all_members",
        "charity": "allowed",
    }
    labels = {
        "affiliation": "University affiliation",
        "invite": "Invitation link",
        "member": "Your account membership",
        "posting": "All-member posting permission",
        "charity": "Charity posting permission",
    }
    for kind, wanted in expected.items():
        check = checks[kind]
        if check["value"] != wanted:
            suffix = (
                "admins only"
                if kind == "posting" and check["value"] == "admins_only"
                else check["value"]
            )
            reasons.append(labels[kind] + ": " + suffix)
        elif not fresh(check, kind, now):
            reasons.append(labels[kind] + ": check expired")
    if len(row["university_ids"]) != 1:
        reasons.append("Conflicting university attribution: review required")

    def add(label, value):
        points.append({"label": label, "points": value})

    if checks["affiliation"]["value"] == "verified" and fresh(
        checks["affiliation"], "affiliation", now
    ):
        add("Verified university affiliation", 30)
    if any(
        s.get("verified")
        and official(s["url"], university)
        and 0 <= now - s["checked_at"] <= TTLS["affiliation"]
        for s in row["sources"]
    ):
        add("Published by configured university domain", 15)
    title = (row["title"] + " " + " ".join(s.get("title", "") for s in row["sources"])).lower()
    if re.search(r"\b(welfare|charity|volunteer|alumni|society|societies)\b", title):
        add("Relevant society or alumni community", 15)
    for kind, value, label, weight in [
        ("posting", "all_members", "Members may post", 10),
        ("charity", "allowed", "Charity approved", 15),
        ("activity", "active", "Recently checked active community", 5),
    ]:
        if checks[kind]["value"] == value and fresh(checks[kind], kind, now):
            add(label, weight)
    fee = university.get("fee_evidence") or {}
    if university.get("annual_tuition_pkr") and 0 <= now - fee.get("checked_at", 0) <= 180 * DAY:
        amount = university["annual_tuition_pkr"]
        add(
            "Documented annual university fee context (not individual wealth)",
            10 if amount >= 1_000_000 else 6 if amount >= 500_000 else 3,
        )
    blocked = (
        bool(row.get("blocked"))
        or checks["charity"]["value"] == "denied"
        or checks["affiliation"]["value"] == "unverified"
    )
    if row.get("blocked"):
        reasons.insert(0, row.get("block_reason") or "Blocked by owner")
    status = (
        "blocked"
        if blocked
        else "expired"
        if checks["invite"]["value"] == "expired"
        else "needs_verification"
        if reasons
        else "ready"
    )
    row.update(
        status=status,
        reasons=reasons,
        score=sum(p["points"] for p in points),
        score_reasons=points,
        university_name=university["name"],
        city=university.get("city", ""),
        stale_checks=[
            kind
            for kind, check in checks.items()
            if check["value"] != "unknown" and not fresh(check, kind, now)
        ],
    )
    return row


class GroupBook:
    def __init__(self, root, store=None, clock=time.time):
        self.repo, self.clock = Repository(root, store), clock

    def _audit(self, data, action, ident, detail=""):
        data["audit"].append(
            {
                "id": uuid.uuid4().hex,
                "at": self.clock(),
                "action": action,
                "record": ident,
                "detail": detail,
            }
        )
        del data["audit"][:-1000]

    @staticmethod
    def _find(items, ident):
        row = next((x for x in items if x["id"] == ident), None)
        if row is None:
            raise ValueError("Research record not found.")
        return row

    def add_university(self, name, domains, aliases=None, city="", country="Pakistan"):
        name = text(name, 120)
        if not name:
            raise ValueError("Enter a university name.")
        if not isinstance(domains, list) or not 1 <= len(domains) <= 10:
            raise ValueError("Add at least one official university domain.")
        normalized = sorted(
            {urlsplit(public_url("https://" + text(d, 200).strip("/"))).hostname for d in domains}
        )
        if not isinstance(aliases or [], list) or len(aliases or []) > 12:
            raise ValueError("Use at most 12 aliases.")
        alias = [text(a, 120) for a in aliases or [] if text(a, 120)]
        city, country = text(city, 100), text(country, 100)

        def change(data):
            prior = next(
                (x for x in data["universities"] if x["name"].casefold() == name.casefold()), None
            )
            if prior:
                return prior
            if len(data["universities"]) >= 200:
                raise ValueError("Review existing universities before adding more.")
            row = {
                "id": uuid.uuid4().hex,
                "name": name,
                "domains": normalized,
                "aliases": alias,
                "city": city,
                "country": country,
                "created_at": self.clock(),
            }
            data["universities"].append(row)
            self._audit(data, "university_added", row["id"])
            return row

        return self.repo.mutate(change)

    def set_fee(self, ident, annual_tuition_pkr, source_url):
        if isinstance(annual_tuition_pkr, bool):
            raise ValueError("Use a valid annual amount in PKR.")
        try:
            amount = float(annual_tuition_pkr)
        except (TypeError, ValueError):
            raise ValueError("Use a valid annual amount in PKR.")
        if not math.isfinite(amount) or not 0 < amount <= 50_000_000:
            raise ValueError("Use a valid annual amount in PKR.")
        source_url = public_url(source_url)

        def change(data):
            uni = self._find(data["universities"], ident)
            if not official(source_url, uni):
                raise ValueError(
                    "Fee evidence must be on the configured official university domain."
                )
            uni.update(
                annual_tuition_pkr=round(amount, 2),
                fee_evidence={
                    "url": source_url,
                    "checked_at": self.clock(),
                    "origin": "owner_observation",
                },
            )
            self._audit(data, "fee_context_checked", ident)
            return uni

        return self.repo.mutate(change)

    def discover(
        self,
        invite,
        university_id,
        source_url,
        title="",
        excerpt="",
        source_verified=False,
        guard=None,
        on_discover=None,
    ):
        invite, source_url = normalize_invite(invite), public_url(source_url)
        title, excerpt = text(title, 180), text(excerpt, 1000)

        def change(data):
            if guard:
                guard(data)
            uni = self._find(data["universities"], university_id)
            row = next((x for x in data["groups"] if x["invite"] == invite), None)
            created = row is None
            if row is None:
                if len(data["groups"]) >= 5000:
                    raise ValueError("Research storage is full; review existing groups first.")
                row = {
                    "id": hashlib.sha256(invite.encode()).hexdigest()[:24],
                    "invite": invite,
                    "university_ids": [university_id],
                    "university_id": university_id,
                    "title": title or uni["name"] + " community",
                    "sources": [],
                    "checks": {
                        kind: {
                            "value": "unknown",
                            "checked_at": 0,
                            "origin": "none",
                            "reference": "",
                        }
                        for kind in VALUES
                    },
                    "created_at": self.clock(),
                    "updated_at": self.clock(),
                    "version": 0,
                    "blocked": False,
                    "jid": "",
                }
                data["groups"].append(row)
            if university_id not in row["university_ids"]:
                row["university_ids"].append(university_id)
            source = next((s for s in row["sources"] if s["url"] == source_url), None)
            verified = source_verified is True
            if source is None:
                source = {
                    "url": source_url,
                    "title": title,
                    "excerpt": excerpt,
                    "checked_at": self.clock(),
                    "verified": verified,
                }
                row["sources"].append(source)
                del row["sources"][:-30]
            elif verified:
                source.update(checked_at=self.clock(), verified=True, title=title, excerpt=excerpt)
            current = row["checks"]["affiliation"]
            if (
                verified
                and official(source_url, uni)
                and current["origin"] in ("none", "public_source")
                and len(row["university_ids"]) == 1
            ):
                row["checks"]["affiliation"] = {
                    "value": "verified",
                    "checked_at": self.clock(),
                    "origin": "public_source",
                    "reference": source_url,
                }
            row["version"] += 1
            row["updated_at"] = self.clock()
            self._audit(data, "source_discovered", row["id"], source_url)
            if on_discover:
                on_discover(data, created)
            return {
                **assess(row, self._find(data["universities"], row["university_id"]), self.clock()),
                "created": created,
            }

        return self.repo.mutate(change)

    def review(self, ident, changes, evidence, expected_version):
        if (
            not isinstance(changes, dict)
            or not changes
            or set(changes) - set(VALUES) - {"university_id", "blocked", "block_reason", "jid"}
        ):
            raise ValueError("Choose valid verification fields.")
        if not isinstance(evidence, dict) or evidence.get("kind") not in (
            "owner_observation",
            "admin_confirmation",
            "account_observation",
        ):
            raise ValueError(
                "Verification needs an owner check, administrator confirmation, or connected-account observation."
            )
        reference = text(evidence.get("reference", ""), 1000)
        if len(reference) < 8:
            raise ValueError("Describe the evidence you actually checked.")
        if isinstance(expected_version, bool) or not isinstance(expected_version, int):
            raise ValueError("A current record version is required.")
        for kind, value in changes.items():
            if kind in VALUES and value not in VALUES[kind]:
                raise ValueError("Invalid " + kind + " value.")
        if "blocked" in changes and not isinstance(changes["blocked"], bool):
            raise ValueError("Blocked must be true or false.")
        if (
            "jid" in changes
            and changes["jid"]
            and not re.fullmatch(r"[0-9-]{5,60}@g\.us", changes["jid"])
        ):
            raise ValueError("Choose a real joined group id.")
        if evidence["kind"] == "account_observation" and set(changes) - {"member", "posting"}:
            raise ValueError("An account check only verifies membership and posting permission.")

        def change(data):
            row = self._find(data["groups"], ident)
            if row["version"] != expected_version:
                raise Conflict("This group changed. Refresh it before saving your check.")
            for kind, value in changes.items():
                if kind in VALUES:
                    row["checks"][kind] = {
                        "value": value,
                        "checked_at": self.clock(),
                        "origin": evidence["kind"],
                        "reference": reference,
                    }
                elif kind == "university_id":
                    self._find(data["universities"], value)
                    row.update(university_id=value, university_ids=[value])
                elif kind == "block_reason":
                    row[kind] = text(value, 300)
                else:
                    row[kind] = value
            row["version"] += 1
            row["updated_at"] = self.clock()
            self._audit(data, "permissions_reviewed", ident, json.dumps(changes))
            return assess(row, self._find(data["universities"], row["university_id"]), self.clock())

        return self.repo.mutate(change)

    def get(self, ident):
        data = self.repo.read()
        row = self._find(data["groups"], ident)
        return assess(row, self._find(data["universities"], row["university_id"]), self.clock())

    def list(self, q="", tab="all", limit=50, offset=0):
        if tab not in ("all", "ready", "needs_verification", "blocked", "expired"):
            raise ValueError("Choose a research tab.")
        if isinstance(limit, bool) or isinstance(offset, bool):
            raise ValueError("Invalid page.")
        limit, offset = int(limit), int(offset)
        if not 1 <= limit <= 100 or not 0 <= offset <= 5000:
            raise ValueError("Invalid page.")
        q = text(q, 180).casefold()
        data = self.repo.read()
        unis = {u["id"]: u for u in data["universities"]}
        rows = [assess(row, unis[row["university_id"]], self.clock()) for row in data["groups"]]
        counts = {
            "all": len(rows),
            **{
                k: sum(r["status"] == k for r in rows)
                for k in ("ready", "needs_verification", "blocked", "expired")
            },
        }
        rows = [
            r
            for r in rows
            if (tab == "all" or r["status"] == tab)
            and (
                not q or q in (r["title"] + " " + r["university_name"] + " " + r["city"]).casefold()
            )
        ]
        rows.sort(key=lambda r: (-r["score"], -r["updated_at"], r["id"]))
        return {
            "items": rows[offset : offset + limit],
            "total": len(rows),
            "counts": counts,
            "universities": data["universities"],
            "settings": data["settings"],
            "jobs": data["jobs"][-15:],
            "audit": data["audit"][-30:],
        }
