"""Dev tool: drive the running UI with headless Chromium and save screenshots.

    tools/host.sh python tools/ui_check.py http://127.0.0.1:8099 out_dir step...
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

url, out = sys.argv[1], Path(sys.argv[2])
steps = sys.argv[3:]
out.mkdir(parents=True, exist_ok=True)


def wait_preview(page, timeout=30):
    t = time.time()
    while time.time() - t < timeout:
        if page.locator("img[src^='data:image/png']").count():
            time.sleep(0.6)
            return True
        time.sleep(0.3)
    return False


with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    for _ in range(40):                       # server may still be starting
        try:
            page.goto(url)
            break
        except Exception:
            time.sleep(0.5)
    for i, step in enumerate(steps):
        kind, _, arg = step.partition(":")
        if kind == "wait":
            wait_preview(page)
        elif kind == "click":
            page.get_by_text(arg, exact=True).first.click()
            time.sleep(0.8)
        elif kind == "shot":
            page.screenshot(path=str(out / f"{arg}.png"), full_page=False)
            print("shot", arg)
        elif kind == "sleep":
            time.sleep(float(arg))
        elif kind == "select":          # select:<field label>=<option text>
            label, _, opt = arg.partition("=")
            page.locator(".q-field", has_text=label).first.click()
            time.sleep(0.5)
            page.locator(".q-menu .q-item", has_text=opt).first.click()
            page.keyboard.press("Escape")
            time.sleep(0.8)
        elif kind == "text":            # text:<visible text> (click first match, substring)
            page.get_by_text(arg).first.click()
            time.sleep(0.8)
        elif kind == "dlg":             # dlg:<text> click inside the open dialog
            page.locator(".q-dialog").last.get_by_text(arg, exact=True).first.click()
            time.sleep(1.0)
        elif kind == "fill":            # fill:<field label>=<text> inside the open dialog
            label, _, text = arg.partition("=")
            fld = page.locator(".q-dialog").last.locator(".q-field", has_text=label).first
            fld.locator("input").fill(text)
            time.sleep(0.5)
        elif kind == "dlgbtn":          # dlgbtn:<button text substring> inside the dialog
            page.locator(".q-dialog").last.locator("button", has_text=arg).first.click()
            time.sleep(1.5)
        elif kind == "js":
            page.evaluate(arg)
    print("page errors:", errors or "none")
    b.close()
