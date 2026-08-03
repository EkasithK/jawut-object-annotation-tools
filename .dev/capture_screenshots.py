"""Drive the running app in a real browser and capture the guide screenshots."""

import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import Page, Route, sync_playwright

SCRATCH = Path(sys.argv[1])
SHOTS = Path(sys.argv[2])
PORT = int(sys.argv[3])
BASE = f"http://127.0.0.1:{PORT}"

# A deliberate, predictable location: it appears in the screenshots, so it has to
# be short and free of anything personal.
DEMO_HOME = Path("/tmp/jawut-demo")  # noqa: S108
(DEMO_HOME / "Documents" / "Jawut Projects").mkdir(parents=True, exist_ok=True)
SHOTS.mkdir(parents=True, exist_ok=True)
VIEWPORT = {"width": 1440, "height": 900}


def shot(page: Page, name: str, pause: float = 0.6) -> None:
    time.sleep(pause)
    page.screenshot(path=str(SHOTS / f"{name}.png"))
    print(f"  captured {name}.png")


def api(method: str, path: str, **kwargs: Any) -> Any:
    response = requests.request(method, f"{BASE}{path}", timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()["data"]


def envelope(data: Any) -> str:
    return json.dumps(
        {
            "data": data,
            "error": None,
            "meta": {"request_id": "screenshot", "timestamp": "2026-01-01T00:00:00Z"},
        }
    )


#: What the folder chooser "returns" for each field it is opened from, so the
#: captured flow matches what someone using the packaged app actually does.
BROWSE_ANSWERS: dict[str, str] = {}


def fake_capabilities(route: Route) -> None:
    """Report native dialogs as present.

    The Browse buttons only exist in the desktop window, and these screenshots
    are taken in a browser. Without this the guide would show a UI that nobody
    running the released exe ever sees.
    """
    route.fulfill(
        status=200,
        content_type="application/json",
        body=envelope({"native_dialogs": True}),
    )


def fake_browse(route: Route) -> None:
    kind = (route.request.post_data_json or {}).get("kind", "folder")
    route.fulfill(
        status=200,
        content_type="application/json",
        body=envelope({"path": BROWSE_ANSWERS.get(kind)}),
    )


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
    page.route("**/api/v1/system/capabilities", fake_capabilities)
    page.route("**/api/v1/system/browse", fake_browse)

    # ── 1. Welcome screen, first run ─────────────────────────────────────────
    page.goto(BASE, wait_until="networkidle")
    shot(page, "01-welcome")

    # ── 1b. Opening a dataset that already exists ────────────────────────────
    # Built here rather than reusing the demo images: the point of the shot is a
    # folder that arrived from somewhere else, already labeled.
    existing = DEMO_HOME / "helmet_wit"
    shutil.rmtree(existing, ignore_errors=True)
    (existing / "images").mkdir(parents=True)
    (existing / "labels").mkdir(parents=True)
    for index in range(1, 25):
        shutil.copy(
            DEMO_HOME / "images" / f"site_{(index % 6) + 1:03d}.jpg",
            existing / "images" / f"frame_{index:04d}.jpg",
        )
        if index <= 14:
            (existing / "labels" / f"frame_{index:04d}.txt").write_text(
                "0 0.5 0.42 0.09 0.11\n", encoding="utf-8"
            )
    (existing / "data.yaml").write_text(
        "nc: 4\nnames: ['Helmet', 'Helmet_Ngob', 'Ngob', 'No_Helmet']\n",
        encoding="utf-8",
    )
    BROWSE_ANSWERS["folder"] = str(existing)

    page.click("text=Open existing dataset…")
    page.wait_for_selector("#dataset-source")
    page.click("dialog[open] >> text=Browse…")
    page.wait_for_timeout(500)
    shot(page, "01a-open-dataset")

    page.click("dialog[open] >> text=Read folder")
    page.wait_for_selector("text=Create project from this", timeout=20000)
    shot(page, "01b-dataset-found")

    page.click("dialog[open] >> [aria-label=Close]")
    page.wait_for_timeout(500)
    BROWSE_ANSWERS.clear()

    # ── 2. New project form filled in ────────────────────────────────────────
    page.fill("#project-name", "Helmet Relabel")
    page.fill("#project-location", str(DEMO_HOME / "Documents" / "Jawut Projects"))
    shot(page, "02-new-project")

    page.click("button[type=submit]")
    page.wait_for_selector("text=Add images", timeout=15000)
    shot(page, "03-empty-workspace")

    # ── 3. Add images dialog ─────────────────────────────────────────────────
    page.click("header >> text=Add images")
    page.wait_for_selector("#import-source")
    page.fill("#import-source", str(DEMO_HOME / "images"))
    shot(page, "04-add-images")

    page.click("dialog[open] >> button[type=submit]")
    page.wait_for_selector("text=Imported", timeout=30000)
    shot(page, "05-import-report")

    page.click("dialog[open] >> [aria-label=Close]")
    page.wait_for_timeout(800)

    # ── 4. Classes ───────────────────────────────────────────────────────────
    for name in ("Helmet", "Helmet_Ngob", "Ngob", "No_Helmet"):
        page.fill("input[placeholder='Add a class…']", name)
        page.press("input[placeholder='Add a class…']", "Enter")
        page.wait_for_timeout(400)
    palette = {
        "Helmet": "#4c8dff",
        "Helmet_Ngob": "#c77dff",
        "Ngob": "#4fd1c5",
        "No_Helmet": "#f2789f",
    }
    for cls in api("GET", "/api/v1/classes")["classes"]:
        api(
            "PATCH",
            f"/api/v1/classes/{cls['id']}",
            json={"color": palette[cls["name"]]},
        )
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(900)
    shot(page, "06-classes")

    # ── 5. Draw a box on the canvas ──────────────────────────────────────────
    # Seed boxes through the API so the canvas shows a realistic labeled frame:
    # simulating a precise drag reliably is far more fragile than this.
    classes = {c["name"]: c["id"] for c in api("GET", "/api/v1/classes")["classes"]}
    images = api("GET", "/api/v1/images")["images"]

    # Coordinates taken from the ground-truth rectangles already burned into these
    # figures, so every box lands exactly on a head.
    layouts = {
        "site_001.jpg": [
            ("Helmet", 0.1977, 0.3457, 0.075, 0.0667),
            ("Helmet", 0.2958, 0.3019, 0.075, 0.0679),
            ("Helmet", 0.3648, 0.3537, 0.0481, 0.0556),
            ("Helmet", 0.5005, 0.3321, 0.1102, 0.0716),
            ("Helmet", 0.6986, 0.3759, 0.0787, 0.0753),
            ("Helmet", 0.8148, 0.3216, 0.0796, 0.0679),
        ],
        "site_002.jpg": [
            ("No_Helmet", 0.4652, 0.5172, 0.0492, 0.0594),
            ("No_Helmet", 0.6934, 0.3484, 0.0367, 0.051),
            ("No_Helmet", 0.8598, 0.3609, 0.0477, 0.0594),
        ],
        "site_003.jpg": [("Ngob", 0.4337, 0.3647, 0.1778, 0.1164)],
        "site_004.jpg": [
            ("Helmet_Ngob", 0.4567, 0.5938, 0.1318, 0.1289),
            ("Helmet_Ngob", 0.6048, 0.5857, 0.1034, 0.1181),
        ],
    }

    for image in images:
        layout = layouts.get(image["filename"])
        if not layout:
            continue
        api(
            "PUT",
            f"/api/v1/annotations/{image['id']}",
            json={
                "boxes": [
                    {"class_id": classes[name], "cx": cx, "cy": cy, "w": w, "h": h}
                    for name, cx, cy, w, h in layout
                ]
            },
        )

    page.reload(wait_until="networkidle")
    page.wait_for_timeout(1500)
    shot(page, "07-labeled-canvas")

    # The Helmet_Ngob frame is the case this taxonomy exists for.
    page.click("text=site_004.jpg")
    page.wait_for_timeout(1800)
    shot(page, "08-helmet-ngob")

    # ── 6. Status filters ────────────────────────────────────────────────────
    api("PATCH", f"/api/v1/images/{images[0]['id']}/status", json={"status": "done"})
    api("PATCH", f"/api/v1/images/{images[1]['id']}/status", json={"status": "done"})
    api(
        "PATCH",
        f"/api/v1/images/{images[3]['id']}/status",
        json={"status": "needs_review"},
    )
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(1200)
    shot(page, "09-filters")

    # ── 7. Import labels wizard ──────────────────────────────────────────────
    labels_dir = DEMO_HOME / "old-labels"
    labels_dir.mkdir(exist_ok=True)
    (labels_dir / "data.yaml").write_text(
        "nc: 2\nnames: ['No_Helmet', 'Safety-Helmet']\n", encoding="utf-8"
    )
    for image in images[4:]:
        stem = Path(image["filename"]).stem
        (labels_dir / f"{stem}.txt").write_text(
            "1 0.45 0.55 0.09 0.11\n0 0.62 0.58 0.08 0.10\n", encoding="utf-8"
        )
    # One pose-format line, to show the repair reported in the wizard.
    stem = Path(images[5]["filename"]).stem  # pose-format sample
    (labels_dir / f"{stem}.txt").write_text(
        "1 0.5 0.5 0.1 0.12 " + " ".join(["0.5 0.5 2"] * 5) + "\n", encoding="utf-8"
    )

    page.click("header >> text=Import labels")
    page.wait_for_selector("#labels-dir")
    page.fill("#labels-dir", str(labels_dir))
    shot(page, "10-import-labels")

    page.click("dialog[open] >> text=Read folder")
    page.wait_for_selector("text=Map classes", timeout=20000)
    page.select_option("select[aria-label='Map class Safety-Helmet']", label="Helmet")
    page.wait_for_timeout(400)
    shot(page, "11-class-mapping")

    page.click("dialog[open] >> text=/Import \\d+ images/")
    page.wait_for_selector("text=Images labeled", timeout=20000)
    shot(page, "12-import-labels-result")

    page.click("dialog[open] >> text=Done")
    page.wait_for_timeout(800)

    # ── 8. Delete a class ────────────────────────────────────────────────────
    page.hover("text=No_Helmet")
    page.click("[aria-label='Delete class No_Helmet']")
    page.wait_for_selector("text=/use this class/", timeout=15000)
    shot(page, "13-delete-class")

    page.click("dialog[open] >> [aria-label=Close]")
    page.wait_for_timeout(600)

    # ── 9. Export ────────────────────────────────────────────────────────────
    export_dir = DEMO_HOME / "helmet-v2"
    shutil.rmtree(export_dir, ignore_errors=True)

    page.click("header >> text=Export")
    page.wait_for_selector("#export-destination")
    page.fill("#export-destination", str(export_dir))
    shot(page, "14-export")

    page.click("dialog[open] >> button[type=submit]")
    page.wait_for_selector("text=/Wrote/", timeout=30000)
    shot(page, "15-export-result")

    browser.close()

print("done")
