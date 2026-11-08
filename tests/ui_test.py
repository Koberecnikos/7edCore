"""UI smoke test with playwright: python3 ui_test.py http://127.0.0.1:18200 pass outdir"""
import sys, asyncio
from playwright.async_api import async_playwright
URL, PW, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 1400, "height": 900})
        errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(URL)
        await pg.wait_for_selector("#gatePw")
        await pg.screenshot(path=f"{OUT}/0_login.png")
        await pg.fill("#gatePw", PW); await pg.click("#gateBtn")
        await pg.wait_for_selector("#app:not([hidden])")
        await pg.wait_for_timeout(1500)
        await pg.screenshot(path=f"{OUT}/1_overview.png", full_page=True)
        for tab in ["world", "settings", "mods", "backups", "files", "automation", "console"]:
            await pg.click(f"#tabs button[data-tab={tab}]"); await pg.wait_for_timeout(700)
            await pg.screenshot(path=f"{OUT}/2_{tab}.png", full_page=True)
        await pg.click("#tabs button[data-tab=settings]"); await pg.wait_for_timeout(500)
        await pg.click("[data-lv=detailed]"); await pg.wait_for_timeout(400)
        await pg.screenshot(path=f"{OUT}/3_detailed.png")
        await pg.click("[data-lv=advanced]"); await pg.wait_for_timeout(400)
        await pg.screenshot(path=f"{OUT}/3_advanced.png")
        await pg.click("#btnVersions"); await pg.wait_for_timeout(1200)
        await pg.screenshot(path=f"{OUT}/4_versions.png", full_page=True)
        await pg.click("#btnPanel"); await pg.wait_for_timeout(800)
        await pg.select_option("#pageView .lang-pick", "cs"); await pg.wait_for_timeout(500)
        await pg.screenshot(path=f"{OUT}/5_panel_cs.png", full_page=True)
        await pg.click(".brand"); await pg.wait_for_timeout(500)
        await pg.click("#tabs button[data-tab=overview]"); await pg.wait_for_timeout(800)
        await pg.screenshot(path=f"{OUT}/6_overview_cs.png", full_page=True)
        await pg.click("#btnNew"); await pg.wait_for_timeout(600)
        await pg.screenshot(path=f"{OUT}/7_new.png")
        await pg.keyboard.press("Escape")
        print("console errors:", errs)
        await b.close()
asyncio.run(main())
