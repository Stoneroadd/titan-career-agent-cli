"""Configured RSS/Atom discovery, CSV import, and deterministic matching."""
from __future__ import annotations

import csv
import hashlib
import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from .storage import feeds_path, jobs_path, load, save


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def plain_text(value: str) -> str:
    parser = TextExtractor()
    try:
        parser.feed(value or "")
        return " ".join(parser.parts)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html.unescape(value or "")).strip()


def tag_text(element: ET.Element, names: tuple[str, ...]) -> str:
    for child in element.iter():
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local in names and child.text:
            return child.text.strip()
    return ""


def feed_items(payload: bytes) -> list[dict]:
    root = ET.fromstring(payload)
    items = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}]
    results = []
    for item in items:
        title = tag_text(item, ("title",))
        description = tag_text(item, ("description", "summary", "content"))
        link = ""
        for node in item.iter():
            if node.tag.rsplit("}", 1)[-1].lower() != "link":
                continue
            link = (node.attrib.get("href") or (node.text or "")).strip()
            if link and (node.attrib.get("rel", "alternate") == "alternate"):
                break
        published = tag_text(item, ("published", "updated", "pubdate", "date"))
        if title:
            results.append({"title": title, "url": link, "description": plain_text(description)[:6000],
                            "published": published})
    return results


def add_feed(home: Path, name: str, url: str) -> None:
    if not url.startswith("https://"):
        raise ValueError("Por seguridad, las fuentes RSS deben usar HTTPS.")
    feeds = load(feeds_path(home), [])
    if any(feed["url"].rstrip("/").lower() == url.rstrip("/").lower() for feed in feeds):
        raise ValueError("Esta fuente ya está configurada.")
    feeds.append({"name": name.strip(), "url": url.strip()})
    save(feeds_path(home), feeds)


def sync_feeds(home: Path) -> tuple[int, list[str]]:
    feeds = load(feeds_path(home), [])
    jobs = load(jobs_path(home), [])
    known = {job.get("url", "").strip().lower() for job in jobs if job.get("url")}
    known_ids = {job.get("id") for job in jobs}
    added = 0
    errors = []
    for feed in feeds:
        try:
            req = urllib.request.Request(feed["url"], headers={"User-Agent": "TITAN-Career-Agent/0.1 (+RSS reader)"})
            with urllib.request.urlopen(req, timeout=20) as response:
                payload = response.read(5_000_001)
            if len(payload) > 5_000_000:
                raise ValueError("fuente excede 5 MB")
            for item in feed_items(payload):
                key = item["url"].strip().lower()
                fallback = hashlib.sha256(f"{item['title']}|{feed['name']}".encode()).hexdigest()
                if key and key in known:
                    continue
                job_id = hashlib.sha256((key or fallback).encode()).hexdigest()[:12]
                if job_id in known_ids:
                    continue
                jobs.append({"id": job_id, "title": item["title"], "company": "", "url": item["url"],
                             "description": item["description"], "skills": [], "location": "",
                             "published": item["published"], "source": feed["name"],
                             "discovered_at": datetime.now(timezone.utc).isoformat()})
                known_ids.add(job_id)
                if key:
                    known.add(key)
                added += 1
        except Exception as error:
            errors.append(f"{feed['name']}: {error}")
    save(jobs_path(home), jobs)
    return added, errors


def import_csv(home: Path, path: Path) -> int:
    rows_added = 0
    jobs = load(jobs_path(home), [])
    known = {job.get("url", "").strip().lower() for job in jobs if job.get("url")}
    known_ids = {job.get("id") for job in jobs}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"title"}.issubset({name.strip().lower() for name in reader.fieldnames}):
            raise ValueError("El CSV debe tener al menos la columna title.")
        for raw in reader:
            row = {str(k).strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            title, url = row.get("title", ""), row.get("url", "") or row.get("application_url", "")
            if not title or (url and not url.startswith(("http://", "https://"))):
                continue
            if url and url.lower() in known:
                continue
            identity = url or f"{title}|{row.get('company', '')}|{row.get('source', '')}"
            job_id = hashlib.sha256(identity.casefold().encode()).hexdigest()[:12]
            if job_id in known_ids:
                continue
            jobs.append({"id": job_id, "title": title, "company": row.get("company", ""),
                         "url": url, "description": row.get("description", "")[:10000],
                         "skills": [item.strip() for item in re.split(r"[,;]", row.get("skills", "")) if item.strip()],
                         "location": row.get("location", ""), "published": row.get("published", ""),
                         "source": row.get("source", "CSV import"),
                         "discovered_at": datetime.now(timezone.utc).isoformat()})
            if url:
                known.add(url.lower())
            known_ids.add(job_id)
            rows_added += 1
    save(jobs_path(home), jobs)
    return rows_added


def candidate_skills(candidate: dict) -> set[str]:
    skills = candidate.get("skills", [])
    return {str(item).strip().casefold() for item in skills if str(item).strip()}


def score_job(job: dict, candidate: dict) -> dict:
    required = {str(item).strip().casefold() for item in job.get("skills", []) if str(item).strip()}
    resume_text = candidate.get("cv_text", "").casefold()
    profile_skills = candidate_skills(candidate)
    if not required:
        vocabulary = {"python", "sql", "excel", "power bi", "tableau", "pandas", "numpy", "pytorch",
                      "tensorflow", "machine learning", "deep learning", "llm", "aws", "azure", "gcp",
                      "docker", "kubernetes", "linux", "git", "java", "javascript", "typescript", "react",
                      "node.js", "fastapi", "flask", "django", "postgresql", "mysql", "mongodb", "airflow",
                      "spark", "databricks", "dbt", "scikit-learn", "nlp", "computer vision", "rag",
                      "salesforce", "sap", "project management", "agile", "scrum", "communication", "leadership"}
        description = (str(job.get("title", "")) + " " + str(job.get("description", ""))).casefold()
        required = {skill for skill in vocabulary if re.search(r"(?<!\w)" + re.escape(skill) + r"(?!\w)", description)}
    matched = sorted(skill for skill in required if skill in profile_skills or skill in resume_text)
    return {"score": round(100 * len(matched) / len(required)) if required else 0,
            "matched": matched, "missing": sorted(required - set(matched)),
            "basis": "literal skill overlap; not a hiring probability"}


def infer_language(text: str) -> str:
    words = re.findall(r"[a-záéíóúñ]+", text.lower())
    es = sum(word in {"de", "para", "con", "experiencia", "requisitos", "trabajo", "empresa", "datos"} for word in words)
    en = sum(word in {"the", "and", "with", "experience", "requirements", "role", "company", "data"} for word in words)
    return "es" if es >= en else "en"
