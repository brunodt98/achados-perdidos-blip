"""Vídeo curto do app rodando: mural com as fichas geradas pelo BLIP e a aba Sobre (sem esperar o modelo)."""
import shutil, subprocess, time
from playwright.sync_api import sync_playwright
shutil.rmtree("_video", ignore_errors=True)
with sync_playwright() as p:
    nav = p.chromium.launch(); ctx = nav.new_context(viewport={"width": 1280, "height": 800}, record_video_dir="_video", record_video_size={"width": 1280, "height": 800})
    t0 = time.time(); pg = ctx.new_page(); pg.goto("http://127.0.0.1:7860"); pg.get_by_text("Achados e perdidos da Fatec").first.wait_for(timeout=60000)
    ini = time.time() - t0; time.sleep(3)
    pg.get_by_role("tab", name="Mural").click(); time.sleep(4)
    pg.mouse.wheel(0, 400); time.sleep(4); pg.mouse.wheel(0, 600); time.sleep(4)
    imgs = pg.locator("[role=tabpanel]:visible button img")
    for i in (0, 4, 6):
        try: imgs.nth(i).click(timeout=3000); time.sleep(4); pg.keyboard.press("Escape"); time.sleep(1)
        except Exception: pass
    pg.mouse.wheel(0, -2000); pg.get_by_role("tab", name="Procurar").click(); time.sleep(3)
    pg.get_by_role("tab", name="Sobre").click(); time.sleep(6)
    fim = time.time() - t0; caminho = pg.video.path(); ctx.close(); nav.close()
import imageio_ffmpeg
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-ss", f"{ini:.1f}", "-i", caminho, "-t", f"{fim-ini:.1f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "demo_blip.mp4"], check=True, capture_output=True)
print("ok", round(fim - ini, 1), "s")
