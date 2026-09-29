#!/usr/bin/env python3
"""Capture PPT screenshots from Yunqi session video via Playwright."""
import asyncio
import json
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

URL = "https://yunqi.aliyun.com/2026/session?agendaId=164"
OUT = Path("/workspace/yunqi-2026-cipu-forum")
SHOTS = OUT / "screenshots"

# Known / candidate seek times (seconds)
CANDIDATES = {
    "map": [
        60, 127, 300, 600, 900, 1200, 1800, 2060, 2400, 3000, 3760, 4200,
        4800, 5440, 5800, 6200, 6600, 7000, 7400, 7800, 8200, 8600, 9000,
        9400, 9800, 10200, 10600, 11000, 11400, 11800, 12200, 12600, 13000,
        13400, 13800, 14200, 14600, 14900,
    ],
}


async def wait_video(page, timeout=120000):
    await page.wait_for_selector("video", timeout=timeout)
    # wait until video has duration
    for _ in range(60):
        dur = await page.evaluate(
            """() => {
            const v = document.querySelector('video');
            return v && v.duration && isFinite(v.duration) ? v.duration : 0;
            }"""
        )
        if dur and dur > 100:
            return dur
        await page.wait_for_timeout(1000)
    raise RuntimeError("Video duration not ready")


async def get_src(page):
    return await page.evaluate(
        """() => {
        const v = document.querySelector('video');
        if (!v) return null;
        return {currentSrc: v.currentSrc, src: v.src, duration: v.duration};
        }"""
    )


async def seek_and_shot(page, seconds, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    await page.evaluate(
        """(t) => {
        const v = document.querySelector('video');
        v.pause();
        v.currentTime = t;
        }""",
        seconds,
    )
    # wait for seeked
    await page.wait_for_timeout(1500)
    await page.evaluate(
        """() => new Promise((resolve) => {
        const v = document.querySelector('video');
        if (Math.abs(v.currentTime - v._target) < 0.5) return resolve();
        const onSeeked = () => { v.removeEventListener('seeked', onSeeked); resolve(); };
        v.addEventListener('seeked', onSeeked);
        setTimeout(resolve, 2000);
        })"""
    )
    await page.wait_for_timeout(800)
    # screenshot the video element only
    video = page.locator("video").first
    box = await video.bounding_box()
    if box and box["width"] > 10:
        await page.screenshot(path=str(path), clip=box)
    else:
        # fallback: larger player container
        await page.screenshot(path=str(path), full_page=False)
    info = await page.evaluate(
        """() => {
        const v = document.querySelector('video');
        return {t: v.currentTime, paused: v.paused, w: v.videoWidth, h: v.videoHeight};
        }"""
    )
    return info


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "map"
    times = []
    if mode == "map":
        times = CANDIDATES["map"]
        out_dir = SHOTS / "_timeline"
    elif mode == "times":
        # custom: capture_video.py times 127,300,600 outdir
        times = [float(x) for x in sys.argv[2].split(",")]
        out_dir = Path(sys.argv[3]) if len(sys.argv) > 3 else SHOTS / "custom"
    else:
        print("usage: map | times t1,t2,t3 [outdir]")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required", "--disable-web-security"],
        )
        context = await browser.new_context(
            viewport={"width": 1600, "height": 1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = await context.new_page()
        # capture media requests
        media_urls = []

        def on_response(resp):
            u = resp.url
            if any(x in u for x in [".m3u8", ".mp4", "vod-", "aliyunvod", "media"]):
                if u not in media_urls:
                    media_urls.append(u)

        page.on("response", on_response)

        print("Opening page...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(5000)
        # try click play if needed
        try:
            play = page.locator("text=播放").first
            if await play.count():
                await play.click(timeout=3000)
        except Exception:
            pass
        try:
            await page.click("video", timeout=5000)
        except Exception:
            pass

        dur = await wait_video(page)
        print(f"Duration: {dur}s ({dur/3600:.2f}h)")
        src = await get_src(page)
        print("SRC:", json.dumps(src, ensure_ascii=False))
        (OUT / "notes" / "stream.json").write_text(
            json.dumps({"src": src, "media_urls": media_urls[:50]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # unmute / play briefly to force stream
        await page.evaluate("""() => { const v=document.querySelector('video'); v.muted=true; return v.play(); }""")
        await page.wait_for_timeout(3000)
        src = await get_src(page)
        print("SRC after play:", json.dumps(src, ensure_ascii=False))
        print("Media URLs sample:", media_urls[:10])

        results = []
        for t in times:
            if t >= dur:
                continue
            hh = int(t // 3600)
            mm = int((t % 3600) // 60)
            ss = int(t % 60)
            name = f"t{hh:02d}-{mm:02d}-{ss:02d}.png"
            path = out_dir / name
            print(f"Seek {t} -> {name}")
            try:
                info = await seek_and_shot(page, t, path)
                results.append({"t": t, "path": str(path), "info": info})
                print("  ", info)
            except Exception as e:
                print("  ERR", e)
                results.append({"t": t, "error": str(e)})

        (out_dir / "index.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (OUT / "notes" / "media_urls.json").write_text(
            json.dumps(media_urls, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        await browser.close()
        print("Done. frames:", len(results))


if __name__ == "__main__":
    asyncio.run(main())
