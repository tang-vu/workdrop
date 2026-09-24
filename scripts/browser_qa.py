"""Browser walkthrough against a fresh running local API and Vite dev server.

Use WORKDROP_DATA_DIR=data/browserqa on the API. This changes that local database.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

source=str(Path("assets/sample/aura-product-screenshot.png").resolve())
errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={"width":1440,"height":900})
    page.on("pageerror",lambda e:errors.append(str(e)))
    page.goto("http://127.0.0.1:5173/")
    first=page.request.get("http://127.0.0.1:8000/api/state",headers={"X-Demo-Wallet":"A"}).json()
    assert first["balances"]["A"]["units"]==0 and not first["jobs"],"Use a fresh WORKDROP_DATA_DIR"
    def set_quantity(target):
        current=int(page.locator(".trade-quantity strong").inner_text())
        button=page.locator(".trade-quantity button").last if target>current else page.locator(".trade-quantity button").first
        for _ in range(abs(target-current)):button.click()
    page.get_by_role("button",name="Get a credit",exact=True).click()
    set_quantity(10)
    page.get_by_role("button",name="Buy in local demo").click()
    page.locator(".balance-card.acid strong").get_by_text("10").wait_for(timeout=45000)

    def submit(n):
        page.get_by_role("button",name="Create",exact=True).click()
        page.locator('input[type="file"]').set_input_files(source)
        page.get_by_placeholder("e.g. Aura").fill(f"Aura browser {n}")
        page.get_by_placeholder("What is the most compelling thing your product does?").fill("A calmer daily ritual for focused work.")
        page.get_by_placeholder("e.g. Explore Aura").fill("Explore Aura")
        page.get_by_role("button",name="Start production").click()
        page.get_by_text("It’s ready to move.").wait_for(timeout=120000)
        page.locator(".private-video video").wait_for(timeout=30000)
        assert page.locator(".private-video video").evaluate("v=>v.readyState")>=2
        page.get_by_role("button",name="View public receipt").click()
        assert "Local simulation only" in page.locator(".receipt-card").inner_text()
        page.get_by_role("button",name="My slots",exact=True).click()

    for n in (1,2,3):submit(n)
    page.get_by_role("button",name="Trade",exact=True).click()
    page.get_by_role("button",name="Sell credits").click()
    set_quantity(7)
    page.get_by_role("button",name="Sell in local demo").click()
    page.locator(".balance-card.acid strong").get_by_text("00").wait_for(timeout=45000)
    page.get_by_role("button",name="DEMO WALLET A").click()
    page.get_by_role("button",name="Trade",exact=True).click()
    page.get_by_role("button",name="Buy credits").click()
    set_quantity(7)
    page.get_by_role("button",name="Buy in local demo").click()
    page.locator(".balance-card.acid strong").get_by_text("07").wait_for(timeout=45000)
    submit(4)
    page.locator(".balance-card.acid strong").get_by_text("06").wait_for(timeout=45000)
    page.screenshot(path="docs/screenshots/browser-loop-final.png",full_page=True)
    response=page.request.get("http://127.0.0.1:8000/api/state",headers={"X-Demo-Wallet":"B"})
    state=response.json()
    summary={"A":state["balances"]["A"]["units"]//state["unit"],"B":state["balances"]["B"]["units"]//state["unit"],"pool":state["batch"]["pool_units"]//state["unit"],"completed":state["batch"]["consumed_units"]//state["unit"],"errors":errors}
    assert summary=={"A":0,"B":6,"pool":2,"completed":4,"errors":[]},summary
    print(json.dumps(summary,indent=2))
    browser.close()
