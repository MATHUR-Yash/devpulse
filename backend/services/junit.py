"""Read one bounded JUnit report from a GitHub Actions attempt artifact."""

from io import BytesIO
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

import httpx2
from fastapi import HTTPException

from .github import github_get, github_headers

LIMIT = 2 * 1024 * 1024


def parse_report(archive: bytes) -> list[dict]:
    try:
        with ZipFile(BytesIO(archive)) as bundle:
            member = bundle.getinfo("junit.xml")
            if member.file_size > LIMIT:
                raise ValueError
            xml = bundle.read(member).decode("utf-8-sig")
        if "<!DOCTYPE" in xml.upper() or "\x00" in xml:
            raise ValueError
        root = ElementTree.fromstring(xml)
        if root.tag not in {"testsuites", "testsuite"}:
            raise ValueError
        cases = []
        for case in root.iter("testcase"):
            if len(cases) >= 5000:
                raise ValueError
            outcome = next((tag for tag in ("error", "failure", "skipped") if case.find(tag) is not None), "passed")
            cases.append({"name": case.get("name", "")[:300], "class": case.get("classname", "")[:300],
                          "status": outcome, "seconds": case.get("time", "")[:32]})
        return cases
    except (BadZipFile, KeyError, ValueError, ElementTree.ParseError, RuntimeError, OSError):
        raise HTTPException(422, "Expected a UTF-8 junit.xml under 2 MiB with up to 5000 test cases.") from None


def read_cases(base, run_id, attempt, token=None):
    name = f"devpulse-junit-{attempt}"
    artifacts = github_get(f"{base}/actions/runs/{run_id}/artifacts", token=token, name=name)
    artifact = next((a for a in artifacts["artifacts"] if a["name"] == name and not a["expired"]), None)
    if not artifact:
        return {"available": False, "cases": []}
    if artifact["size_in_bytes"] > LIMIT:
        raise HTTPException(422, "The report archive exceeds 2 MiB.")
    headers = github_headers(token)
    if "Authorization" not in headers:
        raise HTTPException(503, "Individual test results need a GitHub credential with Actions read access. "
                            "Ask the DevPulse administrator to configure it, or open the run on GitHub.")
    try:
        url = f"https://api.github.com{base}/actions/artifacts/{int(artifact['id'])}/zip"
        redirect = httpx2.get(url, headers=headers, timeout=10)
        location = redirect.headers.get("location", "")
        if redirect.status_code in {401, 403, 404} and redirect.headers.get("x-ratelimit-remaining") != "0":
            raise HTTPException(503, "DevPulse could not access this test report on GitHub. "
                                "Ask the DevPulse administrator to check the repository's Actions read access.")
        if redirect.status_code != 302 or not location.startswith("https://"):
            raise HTTPException(502, "GitHub could not provide the test report download. Try again in a moment.")
        archive = bytearray()
        with httpx2.stream("GET", location, timeout=10) as download:
            download.raise_for_status()
            for chunk in download.iter_bytes(chunk_size=65536):
                archive.extend(chunk)
                if len(archive) > LIMIT:
                    raise HTTPException(422, "The report archive exceeds 2 MiB.")
    except httpx2.HTTPError:
        raise HTTPException(502, "GitHub report download failed.") from None
    return {"available": True, "cases": parse_report(archive)}
