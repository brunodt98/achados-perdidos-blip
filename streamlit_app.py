"""Achados e perdidos da Fatec com BLIP — versão Streamlit (para o Streamlit Community Cloud).
Uso local:  streamlit run streamlit_app.py
Usa o mesmo motor do app Gradio (motor.py). Os itens ficam na memória do servidor e são
compartilhados por todos que abrirem o link; reiniciar o app volta só para os itens de demonstração.
"""
import os
os.environ.setdefault("BLIP_DTYPE", "bf16")   # metade da RAM na CPU; o Community Cloud tem pouca memória
import streamlit as st

st.set_page_config(page_title="Achados e perdidos · BLIP", page_icon="🔎", layout="wide")
RED, G6, PAPER = "#B20000", "#5F5F5F", "#FBFAF7"

st.markdown("""<style>
.topo{background:#171615;color:#F3F1EC;padding:16px 20px;border-radius:4px;margin-bottom:12px}
.topo h1{margin:0;font-size:24px;color:#F3F1EC} .topo p{margin:4px 0 0;color:#A9A59F;font-size:14px} .topo b{color:#FF6B63}
.cap{font-size:11px;letter-spacing:.14em;font-weight:700;color:#B20000}
.tag{display:inline-block;border:1px solid #CFCBC4;padding:3px 9px;margin:3px 4px 0 0;font-size:13px}
.barra{height:10px;background:#EEEAE4;margin-top:4px} .barra div{height:10px}
</style>
<div class="topo"><h1>Achados e perdidos da Fatec com <b>BLIP</b></h1>
<p>Tire foto de um objeto: a IA cadastra. Descreva o que perdeu: a IA encontra.</p></div>""", unsafe_allow_html=True)


@st.cache_resource(show_spinner="Carregando os 3 checkpoints do BLIP e os itens de demonstração (só na primeira vez)…")
def iniciar():
    import motor
    motor.carregar_seed()
    return motor

m = iniciar()

def ficha(item):
    tags = "".join(f"<span class='tag'><b>{k}:</b> {item[k]}</span>" for k in ("objeto", "cor", "marca", "onde"))
    onde = f" · achado em {item['local']}" if item["local"] else ""
    return (f"<div class='cap'>CADASTRADO · #{item['id']} · {item['hora']}</div>"
            f"<div style='font-size:20px;font-weight:700;margin:6px 0 2px'>{item['legenda_pt']}</div>"
            f"<div style='font-size:13px;color:{G6};font-style:italic'>“{item['legenda_en']}”</div>"
            f"<div style='margin-top:8px'>{tags}</div>"
            f"<div style='font-size:12px;color:{G6};margin-top:8px'>por {item['quem']}{onde} · {item['tempo_s']} s</div>")

aba_cad, aba_busca, aba_mural, aba_vqa, aba_sobre = st.tabs(["📸 Cadastrar", "🔎 Procurar", "🗂️ Mural", "💬 Pergunte à IA", "🧠 Sobre"])

with aba_cad:
    with st.form("cadastro", clear_on_submit=True):
        c1, c2 = st.columns(2)
        foto_arq = c1.file_uploader("Foto do objeto", type=["jpg", "jpeg", "png", "webp"])
        foto_cam = c2.camera_input("…ou tire agora")
        quem = c1.text_input("Seu nome (opcional)")
        local = c2.text_input("Onde achou? (opcional)")
        enviar = st.form_submit_button("Cadastrar objeto", type="primary")
    if enviar:
        foto = foto_cam or foto_arq
        if foto is None:
            st.warning("Tire ou escolha uma foto.")
        else:
            with st.spinner("O BLIP está olhando a foto (legenda + 4 perguntas)…"):
                item, img = m.cadastrar(foto, quem or "", local or "")
                m.salvar_novo(img, item)
            a, b = st.columns([1, 2])
            a.image(img, use_container_width=True)
            b.markdown(ficha(item), unsafe_allow_html=True)

with aba_busca:
    with st.form("busca"):
        consulta = st.text_input("Descreva o que você perdeu (em português)", placeholder="garrafa azul com adesivo")
        procurar = st.form_submit_button("Procurar", type="primary")
    st.caption("Exemplos: garrafa de água · mochila · fone de ouvido · caderno")
    if procurar and consulta.strip():
        with st.spinner("Comparando a frase com cada foto (ITM)…"):
            res, q_en = m.buscar(consulta)
        st.markdown(f"<div class='cap'>BUSCA · P(combina) pelo ITM</div>"
                    f"<div style='font-size:20px;font-weight:700'>“{consulta}”</div>"
                    f"<div style='font-size:13px;color:{G6}'>enviado ao modelo como: “{q_en}”</div>", unsafe_allow_html=True)
        if not res:
            st.info("Nada cadastrado ainda.")
        for i, r in enumerate(res):
            it, p = r["item"], r["p_itm"]
            a, b, c = st.columns([1, 6, 1])
            a.image(it["_img"], width=80)
            cor = RED if i == 0 else "#9A968F"
            b.markdown(f"<div style='font-size:15px;{'font-weight:700' if i == 0 else ''}'>{it['legenda_pt']} "
                       f"<span style='color:{G6};font-size:12px'>· #{it['id']} · {it['quem']}</span></div>"
                       f"<div class='barra'><div style='width:{p*100:.0f}%;background:{cor}'></div></div>", unsafe_allow_html=True)
            c.markdown(f"**{p:.2f}**")

with aba_mural:
    with m.LOCK: base = list(m.ITENS)[::-1]
    st.markdown(f"<div style='font-size:15px'><b style='font-size:28px;color:{RED}'>{len(base)}</b> objeto(s) cadastrado(s) pela turma</div>", unsafe_allow_html=True)
    if st.button("Atualizar mural"):
        st.rerun()
    cols = st.columns(4)
    for i, b in enumerate(base):
        legenda = f"#{b['id']} · {b['legenda_pt']} · {b['quem']}" + (f" · {b['local']}" if b["local"] else "")
        cols[i % 4].image(b["_img"], caption=legenda, use_container_width=True)

with aba_vqa:
    with st.form("vqa"):
        p_img = st.file_uploader("Foto", type=["jpg", "jpeg", "png", "webp"], key="vqa_img")
        p_txt = st.text_input("Pergunta (pode ser em português)", placeholder="De que cor é?")
        perguntar = st.form_submit_button("Perguntar", type="primary")
    if perguntar and p_img is not None and p_txt.strip():
        with st.spinner("Perguntando ao BLIP (VQA)…"):
            r = m.perguntar(m.carregar_imagem(p_img), m.para_en(p_txt))
        st.markdown(f"<div style='border-left:5px solid {RED};padding:10px 16px;background:{PAPER}'>"
                    f"<div style='font-size:12px;color:{G6}'>{p_txt}</div>"
                    f"<div style='font-size:28px;font-weight:700'>{m.para_pt(r)}</div>"
                    f"<div style='font-size:12px;color:{G6}'>modelo respondeu: “{r}”</div></div>", unsafe_allow_html=True)

with aba_sobre:
    st.dataframe(m.RAIO_X, use_container_width=True)
    st.caption(f"Li, Li, Xiong & Hoi. BLIP. ICML 2022 · {m.DEVICE} · {m.GPU} · pesos em {str(m.DTYPE).replace('torch.', '')}. "
               "Fotos de demonstração: Wikimedia Commons (créditos em seed/CREDITOS.md).")
