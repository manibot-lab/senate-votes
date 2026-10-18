#!/usr/bin/env python3
"""Pull Senate roll-call votes on nominations from senate.gov (no API key needed)
and write site/data/votes.json. Incremental: only fetches votes it hasn't stored."""
import json, os, re, sys, time, datetime as dt
import urllib.request, urllib.error
import xml.etree.ElementTree as ET

CONGRESS = 119
SESSIONS = [1, 2]
BASE = "https://www.senate.gov/legislative/LIS"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "data", "votes.json")
UA = {"User-Agent": "senate-nominee-tracker (GitHub Pages project)"}
CAST = {"yea": "Y", "nay": "N", "not voting": "NV", "present": "P"}


def get(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return ET.fromstring(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    return None


def txt(el, tag):
    n = el.find(tag)
    return (n.text or "").strip() if n is not None and n.text else ""


def iso_date(raw):
    m = re.search(r"([A-Za-z]+ \d{1,2}, \d{4})", raw)
    try:
        return dt.datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()
    except Exception:
        return raw


def parse_vote(root, session):
    """Return (vote_dict, senators_dict) for nomination votes, else None."""
    question = txt(root, "vote_question_text") or txt(root, "question")
    if "nomination" not in question.lower():
        return None
    votes, senators = {}, {}
    for m in root.iter("member"):
        lid = txt(m, "lis_member_id")
        if not lid:
            continue
        senators[lid] = {
            "n": f'{txt(m, "first_name")} {txt(m, "last_name")}'.strip(),
            "p": txt(m, "party"),
            "s": txt(m, "state"),
        }
        votes[lid] = CAST.get(txt(m, "vote_cast").lower(), "NV")
    vote = {
        "session": session,
        "number": int(txt(root, "vote_number") or 0),
        "date": iso_date(txt(root, "vote_date")),
        "title": txt(root, "vote_document_text") or txt(root, "vote_title") or question,
        "nomination": txt(root, "document/document_name"),
        "result": txt(root, "vote_result_text") or txt(root, "vote_result"),
        "yeas": txt(root, "count/yeas"),
        "nays": txt(root, "count/nays"),
        "votes": votes,
    }
    return vote, senators


def candidates(session):
    menu = get(f"{BASE}/roll_call_lists/vote_menu_{CONGRESS}_{session}.xml")
    if menu is None:
        return None
    out = []
    for v in menu.iter("vote"):
        q, issue = txt(v, "question").lower(), txt(v, "issue").upper()
        if "nomination" in q or issue.startswith("PN"):
            out.append(int(txt(v, "vote_number")))
    return out


def main():
    data = {"updated": None, "senators": {}, "votes": []}
    if os.path.exists(OUT):
        with open(OUT) as f:
            data = json.load(f)
    seen = {(v["session"], v["number"]) for v in data["votes"]}
    added, reached = 0, False
    for session in SESSIONS:
        nums = candidates(session)
        if nums is None:
            print(f"session {session}: menu not available, skipping")
            continue
        reached = True
        todo = [n for n in nums if (session, n) not in seen]
        print(f"session {session}: {len(nums)} candidate votes, {len(todo)} new")
        for n in todo:
            root = get(f"{BASE}/roll_call_votes/vote{CONGRESS}{session}/vote_{CONGRESS}_{session}_{n:05d}.xml")
            parsed = parse_vote(root, session) if root is not None else None
            if parsed:
                data["votes"].append(parsed[0])
                data["senators"].update(parsed[1])
                added += 1
            time.sleep(0.3)
    if not reached:
        sys.exit("Could not reach senate.gov vote menus")
    if added:
        data["votes"].sort(key=lambda v: (v["date"], v["session"], v["number"]), reverse=True)
        data["updated"] = dt.datetime.now(dt.timezone.utc).date().isoformat()
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w") as f:
            json.dump(data, f, separators=(",", ":"))
    print(f"added {added} votes, {len(data['votes'])} total")


if __name__ == "__main__":
    main()
