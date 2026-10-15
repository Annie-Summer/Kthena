#!/usr/bin/env python3
"""Capture PPT screenshots from Yunqi agendaId=123 PAI forum."""
from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

URL = "https://yunqi.aliyun.com/2026/session?agendaId=123"
ROOT = Path(__file__).resolve().parent
SHOTS = ROOT / "screenshots"

TALKS = {
    "01-zhou-agentic-infra": {
        "times": [90, 180, 300, 420, 540, 660, 780, 900, 1020, 1140, 1260, 1380],
    },
    "02-huang-platform": {
        "times": [1500, 1620, 1740, 1860, 1980, 2100, 2220, 2340, 2460, 2580, 2700],
    },
    "03-zhai-posttrain": {
        "times": [2760, 2880, 3000, 3120, 3240, 3360, 3480, 3600, 3720, 3840, 3960, 4080, 4200, 4320, 4440],
    },
    "04-zhang-autoforch": {
        "times": [4560, 4680, 4800, 4920, 5040, 5160, 5280],
    },
    "05-li-inference": {
        "times": [5400, 5520, 5640, 5760, 5880, 6000, 6120, 6240, 6360],
    },
    "06-jiang-cariad": {
        "times": [6480, 6600, 6720, 6840, 6960, 7080, 7200, 7320, 7440],
    },
    "07-wu-xiaomi": {
        "times": [7560, 7680, 7800, 7920, 8040, 8160, 8280, 8400],
    },
    "08-huang-physical": {
        "times": [8520, 8700, 8880, 9060, 9240, 9420, 9600, 9780, 9960],
    },
    "09-shi-turbox": {
        "times": [10080, 10140, 10200, 10260, 10320, 10440, 10800, 11100, 11220, 11280, 11340, 11460],
    },
    "10-roundtable": {
        "times": [11600, 11800, 12000, 12200, 12400, 12600, 12800, 13000, 13200, 13400, 13600],
    },
}


def fmt(t: int) -> str:
    h = t // 3600
    m = (t % 3600) // 60
    s = t % 60
    return f"t{h:02d}-{m:02d}-{s:02d}.png"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(
            viewport={"width": 1600, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_selector("video", timeout=60000)
        await page.evaluate(
            """() => {
            const v=document.querySelector('video');
            if(!v) return;
            v.muted=true;
            try { const p=v.play(); if(p&&p.then) p.then(()=>{}).catch(()=>{}); } catch(e) {}
            }"""
        )
        for _ in range(60):
            dur = await page.evaluate(
                """() => { const v=document.querySelector('video'); return v&&isFinite(v.duration)?v.duration:0; }"""
            )
            if dur and dur > 100:
                break
            await page.wait_for_timeout(1000)
        print("duration", dur)

        for folder, meta in TALKS.items():
            out = SHOTS / folder
            out.mkdir(parents=True, exist_ok=True)
            for t in meta["times"]:
                if t >= dur - 2:
                    continue
                path = out / fmt(t)
                if path.exists() and path.stat().st_size > 10000:
                    print("skip", path)
                    continue
                await page.evaluate(
                    """(t)=>{const v=document.querySelector('video'); v.pause(); v.currentTime=t;}""",
                    float(t),
                )
                await page.wait_for_timeout(1600)
                video = page.locator("video").first
                box = await video.bounding_box()
                if box and box["width"] > 10:
                    await page.screenshot(path=str(path), clip=box)
                else:
                    await page.screenshot(path=str(path))
                print("wrote", path)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
