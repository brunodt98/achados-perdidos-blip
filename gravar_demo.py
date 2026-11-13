"""Grava um vídeo do app rodando (Playwright) e converte para demo_blip.mp4.

Pré-requisitos: app.py rodando (python app.py --sem-share) e uma foto em ./teste/.
Uso: python gravar_demo.py [--url http://127.0.0.1:7860] [--busca "garrafa azul"]

Roteiro gravado:
  1. Mural com os itens de demonstração
  2. Cadastro de um objeto novo (foto de ./teste/)
  3. Busca em português pelo objeto recém-cadastrado
  4. Mural de novo, já com o item novo
Os seletores seguem o layout do app.py; se o Gradio mudar algo, ajuste aqui.
As esperas longas do modelo (CPU) são cortadas na conversão: fica só --espera s de "carregando".
"""
import argparse, glob, os, shutil, subprocess, time
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:7860")
ap.add_argument("--foto", default=None, help="foto do objeto novo (padrão: primeira de ./teste/)")
ap.add_argument("--busca", default="garrafa azul", help="frase de busca em português (descreva o objeto da foto)")
ap.add_argument("--nome", default="Bruno")
ap.add_argument("--saida", default="demo_blip.mp4")
ap.add_argument("--espera", type=float, default=2.0, help="segundos de 'carregando' mantidos em cada espera do modelo")
args = ap.parse_args()

foto = args.foto or (sorted(glob.glob("teste/*.jp*g") + glob.glob("teste/*.png")) or [None])[0]
assert foto, "Coloque uma foto em ./teste/ ou passe --foto"
W, H = 1280, 800
shutil.rmtree("_video", ignore_errors=True)

def pausa(s): time.sleep(s)
cortes = []                      # (início, fim) em segundos do vídeo, trechos a remover
def esperar_modelo(locator, timeout):
    t_ini = time.time() - T0
    locator.wait_for(timeout=timeout)
    t_fim = time.time() - T0
    if t_fim - t_ini > args.espera + 0.5:
        cortes.append((t_ini + args.espera, t_fim - 0.3))

with sync_playwright() as p:
    nav = p.chromium.launch(headless=True)
    ctx = nav.new_context(viewport={"width": W, "height": H}, record_video_dir="_video", record_video_size={"width": W, "height": H})
    T0 = time.time()
    pg = ctx.new_page()
    pg.goto(args.url); pg.get_by_text("Achados e perdidos da Fatec").first.wait_for(timeout=60000)
    cortes.append((0.0, time.time() - T0 + 0.3))   # tela branca de abertura
    pausa(2)

    # 1. mural com os itens de demonstração
    pg.get_by_role("tab", name="Mural").click(); pausa(5)

    # 2. cadastro de um objeto novo
    pg.get_by_role("tab", name="Cadastrar").click(); pausa(1)
    painel = pg.locator("[role=tabpanel]:visible")
    painel.locator("input[type=file]").first.set_input_files(foto); pausa(2)
    painel.get_by_label("Seu nome (opcional)").fill(args.nome)
    painel.get_by_label("Onde achou? (opcional)").fill("Sala 12"); pausa(1)
    painel.get_by_role("button", name="Cadastrar objeto").click()
    esperar_modelo(pg.get_by_text("CADASTRADO").first, 400000); pausa(5)

    # 3. busca em português
    pg.get_by_role("tab", name="Procurar").click(); pausa(1)
    painel = pg.locator("[role=tabpanel]:visible")
    caixa = painel.get_by_label("Descreva o que você perdeu (em português)")
    caixa.click(); caixa.type(args.busca, delay=90); pausa(0.6)
    painel.get_by_role("button", name="Procurar").click()
    esperar_modelo(pg.get_by_text("BUSCA ·").first, 400000); pausa(2.5)
    pg.mouse.wheel(0, 350); pausa(4)

    # 4. mural atualizado
    pg.get_by_role("tab", name="Mural").click(); pausa(6)
    T_FIM = time.time() - T0

    caminho_webm = pg.video.path()
    ctx.close(); nav.close()

# trechos mantidos = complemento dos cortes
manter, t = [], 0.0
for a, b in sorted(cortes):
    if a > t: manter.append((t, a))
    t = max(t, b)
manter.append((t, T_FIM))
print("cortes:", [(round(a, 1), round(b, 1)) for a, b in cortes])
print("mantidos:", [(round(a, 1), round(b, 1)) for a, b in manter], f"→ {sum(b - a for a, b in manter):.1f} s")

try:
    import imageio_ffmpeg; ff = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    ff = "ffmpeg"
filtro = "".join(f"[0:v]trim={a:.2f}:{b:.2f},setpts=PTS-STARTPTS[v{i}];" for i, (a, b) in enumerate(manter))
filtro += "".join(f"[v{i}]" for i in range(len(manter))) + f"concat=n={len(manter)}:v=1:a=0[out]"
subprocess.run([ff, "-y", "-i", caminho_webm, "-filter_complex", filtro, "-map", "[out]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", args.saida], check=True)
print(f"vídeo salvo: {args.saida}")
