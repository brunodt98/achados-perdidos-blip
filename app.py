"""Achados e perdidos da Fatec com BLIP — app local (Gradio).
Uso:  python app.py            (link público com --share, padrão ligado)
      python app.py --sem-share
Itens de demonstração: todas as imagens em ./seed/ são cadastradas ao iniciar
(marcadas como "item de demonstração"). Novos cadastros entram pelo app.
"""
import argparse, time
from motor import *
RED, INK, G6, PAPER = "#B20000", "#151515", "#5F5F5F", "#FBFAF7"

def cartao(item, img=None):
    im = img if img is not None else item.get("_img")
    foto = f"<img src='data:image/jpeg;base64,{thumb_b64(im)}' style='width:100%;display:block'>" if im is not None else ""
    tags = "".join(f"<span style='display:inline-block;border:1px solid #CFCBC4;padding:3px 9px;margin:3px 4px 0 0;font-size:13px'><b>{k}:</b> {item[k]}</span>"
                   for k in ("objeto", "cor", "marca", "onde"))
    return f"""<div style='font-family:Verdana;display:grid;grid-template-columns:220px 1fr;gap:18px;background:{PAPER};border:1px solid #E3E0D9;padding:14px;max-width:760px'>
      <div>{foto}</div><div>
      <div style='font-size:11px;letter-spacing:.14em;font-weight:700;color:{RED}'>CADASTRADO · #{item['id']} · {item['hora']}</div>
      <div style='font-size:20px;font-weight:700;margin:6px 0 2px'>{item['legenda_pt']}</div>
      <div style='font-size:13px;color:{G6};font-style:italic'>“{item['legenda_en']}”</div>
      <div style='margin-top:8px'>{tags}</div>
      <div style='font-size:12px;color:{G6};margin-top:8px'>por {item['quem']}{' · achado em ' + item['local'] if item['local'] else ''} · {item['tempo_s']} s</div></div></div>"""

def ranking_html(res, consulta, q_en):
    if not res: return "<p style='font-family:Verdana'>Nada cadastrado ainda.</p>"
    linhas = ""
    for i, r in enumerate(res):
        it, p = r["item"], r["p_itm"]
        cor = RED if i == 0 else "#9A968F"
        linhas += f"""<div style='display:grid;grid-template-columns:70px 1fr 64px;gap:12px;align-items:center;margin:8px 0'>
          <img src='data:image/jpeg;base64,{thumb_b64(it["_img"], 140)}' style='width:70px;height:70px;object-fit:cover'>
          <div><div style='font-size:14px;{'font-weight:700' if i == 0 else ''}'>{it['legenda_pt']} <span style='color:{G6};font-size:12px'>· #{it['id']} · {it['quem']}</span></div>
          <div style='height:12px;background:#EEEAE4;margin-top:5px'><div style='height:12px;width:{p*100:.0f}%;background:{cor}'></div></div></div>
          <div style='font-weight:700;text-align:right'>{p:.2f}</div></div>"""
    return f"""<div style='font-family:Verdana;background:{PAPER};border:1px solid #E3E0D9;padding:14px 18px'>
      <div style='font-size:11px;letter-spacing:.14em;font-weight:700;color:{RED}'>BUSCA · P(combina) pelo ITM</div>
      <div style='font-size:20px;font-weight:700'>“{consulta}”</div><div style='font-size:13px;color:{G6}'>enviado ao modelo como: “{q_en}”</div>{linhas}</div>"""


# ---------------------------------------------------------------- app
import gradio as gr

CSS = """
.gradio-container{font-family:Verdana,sans-serif!important;max-width:1100px!important}
#topo{background:#171615;color:#F3F1EC;padding:16px 20px;border-radius:4px}
#topo h1{margin:0;font-size:22px;color:#F3F1EC} #topo p{margin:4px 0 0;color:#A9A59F;font-size:13px} #topo b{color:#FF6B63}
button.primary{background:#B20000!important;border-color:#B20000!important}
"""

def ui_cadastrar(img, quem, local):
    if img is None: return "<p style='font-family:Verdana'>Tire ou escolha uma foto.</p>", mural()
    item, im = cadastrar(img, quem or "", local or "")
    salvar_novo(im, item)
    return cartao(item, im), mural()

def mural():
    with LOCK: base = list(ITENS)[::-1]
    return [(b["_img"], f"#{b['id']} · {b['legenda_pt']} · {b['quem']}" + (f" · {b['local']}" if b['local'] else "")) for b in base]

def contador():
    with LOCK: n = len(ITENS)
    return f"<div style='font-family:Verdana;font-size:15px'><b style='font-size:28px;color:#B20000'>{n}</b> objeto(s) cadastrado(s) pela turma</div>"

def ui_buscar(q):
    res, q_en = buscar(q or "")
    return ranking_html(res, q or "", q_en), [(r["item"]["_img"], f"{r['p_itm']:.2f} · {r['item']['legenda_pt']}") for r in res]

def ui_perguntar(img, q):
    if img is None or not q: return ""
    r = perguntar(carregar_imagem(img), para_en(q))
    return f"<div style='font-family:Verdana;border-left:5px solid #B20000;padding:10px 16px;background:#FBFAF7'><div style='font-size:12px;color:#5F5F5F'>{q}</div><div style='font-size:28px;font-weight:700'>{para_pt(r)}</div><div style='font-size:12px;color:#5F5F5F'>modelo respondeu: “{r}”</div></div>"

with gr.Blocks(theme=gr.themes.Base(primary_hue="red", neutral_hue="stone"), css=CSS, title="Achados e perdidos · BLIP") as app:
    gr.HTML("<div id='topo'><h1>Achados e perdidos da Fatec com <b>BLIP</b></h1><p>Tire foto de um objeto: a IA cadastra. Descreva o que perdeu: a IA encontra.</p></div>")
    with gr.Tab("📸 Cadastrar"):
        c_img = gr.Image(type="pil", sources=["upload", "webcam"], label="Foto do objeto", height=320)
        with gr.Row():
            c_quem = gr.Textbox(label="Seu nome (opcional)"); c_loc = gr.Textbox(label="Onde achou? (opcional)")
        c_btn = gr.Button("Cadastrar objeto", variant="primary", size="lg"); c_out = gr.HTML()
    with gr.Tab("🔎 Procurar"):
        b_txt = gr.Textbox(label="Descreva o que você perdeu (em português)", placeholder="garrafa azul com adesivo")
        gr.Examples([["garrafa de água"], ["mochila preta"], ["fone de ouvido branco"], ["caderno"]], inputs=[b_txt])
        b_btn = gr.Button("Procurar", variant="primary"); b_out = gr.HTML(); b_gal = gr.Gallery(columns=5, height=220)
    with gr.Tab("🗂️ Mural"):
        m_n = gr.HTML(contador()); m_gal = gr.Gallery(value=mural(), columns=4, height=520)
    with gr.Tab("💬 Pergunte à IA"):
        p_img = gr.Image(type="pil", sources=["upload", "webcam"], label="Foto", height=300)
        p_txt = gr.Textbox(label="Pergunta (pode ser em português)", placeholder="De que cor é?")
        p_btn = gr.Button("Perguntar", variant="primary"); p_out = gr.HTML()
    with gr.Tab("🧠 Sobre"):
        gr.HTML("<div style='font-family:Verdana;font-size:14px'>" + RAIO_X.to_html(border=0) +
                f"<p>Li, Li, Xiong &amp; Hoi. <i>BLIP</i>. ICML 2022 · {DEVICE} · {GPU}</p></div>")
    c_btn.click(ui_cadastrar, [c_img, c_quem, c_loc], [c_out, m_gal])
    b_btn.click(ui_buscar, b_txt, [b_out, b_gal]); b_txt.submit(ui_buscar, b_txt, [b_out, b_gal])
    p_btn.click(ui_perguntar, [p_img, p_txt], p_out)
    app.load(lambda: (contador(), mural()), None, [m_n, m_gal])
    try:
        tm = gr.Timer(3); tm.tick(lambda: (contador(), mural()), None, [m_n, m_gal])
    except Exception:
        gr.Button("Atualizar mural").click(lambda: (contador(), mural()), None, [m_n, m_gal])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--sem-share", action="store_true"); ap.add_argument("--porta", type=int, default=7860)
    args = ap.parse_args()
    carregar_seed()
    print(f"{len(ITENS)} itens no mural")
    app.queue(default_concurrency_limit=1)
    _, local_url, share_url = app.launch(share=not args.sem_share, server_name="0.0.0.0", server_port=args.porta, prevent_thread_lock=True)
    url = share_url or local_url
    print("\n" + "=" * 60 + f"\nLINK LOCAL : {local_url}\nLINK TURMA : {share_url}\n" + "=" * 60)
    try:
        import qrcode; qrcode.make(url).save("qrcode_app.png"); print("QR code salvo em qrcode_app.png")
    except Exception: pass
    open("link_app.txt", "w").write(url or "")
    try:
        while True: time.sleep(3600)
    except KeyboardInterrupt:
        pass
