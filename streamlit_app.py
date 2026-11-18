"""Achados: o achados e perdidos da Fatec Cotia com BLIP.  Uso: streamlit run streamlit_app.py"""
import datetime as dt
from html import escape as e
from pathlib import Path

import streamlit as st

import motor

RAIZ = Path(__file__).parent
NOTA_FORTE = .25    # nos testes, os acertos ficaram acima de 0,35 e os demais abaixo de 0,10
NOTA_MINIMA = .02
EXEMPLOS = ["garrafa de água", "mochila", "fone de ouvido", "guarda-chuva preto", "molho de chaves"]
PERGUNTAS = ["De que cor é?", "O que é isso?", "Qual é a marca?", "Está sobre uma mesa?"]
ROTULOS = {"objeto": "Objeto", "cor": "Cor", "marca": "Marca (palpite)", "onde": "Na foto"}

st.set_page_config(page_title="Achados · Fatec Cotia", page_icon=":material/sell:", layout="wide")
st.html(f"<style>{(RAIZ / 'assets' / 'estilo.css').read_text(encoding='utf-8')}</style>")
st.logo(str(RAIZ / "assets" / "logo.svg"), size="large")
motor.iniciar()


# ---------------------------------------------------------------- peças
def data_curta(iso):
    try:
        return dt.datetime.fromisoformat(iso).strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return ""


def por_id(id_):
    return next((i for i in motor.itens() if i["id"] == id_), None)


@st.dialog("Ficha do objeto", width="large")
def ficha(item):
    a, b = st.columns([1, 1.15], gap="medium")
    a.image(item["_img"], width="stretch")
    pt = item["atributos_pt"]
    linhas = "".join(f"<dt>{r}</dt><dd>{e(str(pt.get(k, '')))}</dd>" for k, r in ROTULOS.items())
    linhas += f"<dt>Achado em</dt><dd>{e(item['local'] or 'não informado')}</dd>"
    linhas += f"<dt>Entregue por</dt><dd>{e(item['quem'])}</dd>"
    if not item["demo"]:
        linhas += f"<dt>Cadastro</dt><dd>{data_curta(item['quando'])}</dd>"
    b.html(f"""<p class="ficha-id">#{e(item['id'])}</p><p class="ficha-titulo">{e(item['titulo'])}</p>
        <p class="ficha-en">“{e(item['legenda_en'])}”</p><dl class="dados">{linhas}</dl>
        <p class="nota-ia">Texto gerado pelo BLIP, que pode errar, principalmente na marca.
        Confira o objeto pessoalmente antes de devolver.</p>""")


def cartao(item, prefixo, nota=None):
    selo = ""
    if nota is not None:
        selo = f"<span class='etq-nota{' forte' if nota >= NOTA_FORTE else ''}'>{nota:.0%}</span>"
    origem = "demonstração" if item["demo"] else data_curta(item["quando"])
    with st.container(key=f"cartao_{prefixo}_{item['id']}"):
        st.html(f"""<div class="etq-foto"><img alt="{e(item['titulo'], quote=True)}" loading="lazy"
              src="data:image/jpeg;base64,{item['_thumb']}"><span class="etq-furo"></span>{selo}</div>
            <div class="etq-corpo"><div class="etq-id"><span>#{e(item['id'])}</span><span>{e(origem)}</span></div>
            <h3>{e(item['titulo'])}</h3><p class="etq-local">{e(item['local'] or 'Local não informado')}</p></div>""")
        if st.button("Ver ficha", key=f"ver_{prefixo}_{item['id']}", width="stretch"):
            ficha(item)


def grade(itens, prefixo, notas=None):
    with st.container(key=f"grade_{prefixo}"):
        for item in itens:
            cartao(item, prefixo, (notas or {}).get(item["id"]))


def secao(titulo, detalhe=""):
    st.html(f"<div class='secao'><h2>{e(titulo)}</h2><span>{e(detalhe)}</span></div>")


def cabecalho(sobre, titulo, apoio):
    st.html(f"<p class='sobretitulo'>{e(sobre)}</p><h1 class='heroi'>{titulo}</h1><p class='apoio'>{e(apoio)}</p>")


@st.fragment(run_every=3)
def vigia(acompanhar_mural=False):
    """Mostra o aquecimento da IA e atualiza a tela quando ela fica pronta ou chega item novo."""
    est = motor.ESTADO
    lista = motor.itens()
    marca = (est["fase"], (len(lista), lista[0]["id"] if lista else "") if acompanhar_mural else None)
    anterior = st.session_state.get("_vigia")
    st.session_state["_vigia"] = marca
    if anterior is not None and anterior != marca:
        st.rerun()
    if est["fase"] == "erro":
        st.error("A IA não conseguiu iniciar. O mural continua disponível, mas busca e cadastro estão fora do ar.")
        print("erro do motor:", est["erro"])
    elif not motor.pronto():
        pct = est["feitos"] / est["total"] if est["total"] else 0
        st.html(f"""<div class="aviso" role="status"><b>A IA está aquecendo</b><span>{e(est['msg'] or 'Iniciando')}…</span>
            <div class="barra"><i style="width:{pct:.0%}"></i></div></div>""")


def ia_indisponivel():
    if motor.pronto():
        return False
    st.info("A IA ainda está aquecendo. Assim que terminar, esta função é liberada.", icon=":material/hourglass_top:")
    return True


# ---------------------------------------------------------------- telas
def usar_exemplo():
    if st.session_state.get("exemplo"):
        st.session_state["q"] = st.session_state["exemplo"]
        st.session_state["busca_pendente"] = st.session_state["exemplo"]
        st.session_state["exemplo"] = None


def limpar_busca():
    st.session_state.pop("resultado", None)
    st.session_state.pop("busca_pendente", None)
    st.session_state["q"] = ""


def tela_achados():
    vigia(acompanhar_mural=True)
    cabecalho("Fatec Cotia · achados e perdidos", "Perdeu alguma <em>coisa?</em>",
              "Descreva o objeto em português. A IA compara sua frase com a foto de cada item entregue.")
    with st.container(key="caixa_busca"):
        with st.form("busca", enter_to_submit=True):
            c1, c2 = st.columns([6, 1])
            q = c1.text_input("O que você perdeu?", key="q", max_chars=120, label_visibility="collapsed",
                              placeholder="Ex.: garrafa azul")
            if c2.form_submit_button("Procurar", type="primary", icon=":material/search:") and q.strip():
                st.session_state["busca_pendente"] = q.strip()
    st.pills("Exemplos", EXEMPLOS, key="exemplo", on_change=usar_exemplo, label_visibility="collapsed")
    st.page_link(PG_ENTREGAR, label="Achou um objeto? Entregue aqui", icon=":material/arrow_forward:")

    pendente = st.session_state.get("busca_pendente")
    if pendente and motor.pronto():
        with st.spinner("Comparando sua descrição com as fotos…"):
            res, q_en = motor.buscar(pendente)
        st.session_state["resultado"] = dict(q=pendente, en=q_en, res=[(r["item"]["id"], r["p"]) for r in res])
        del st.session_state["busca_pendente"]
    elif pendente:
        st.html(f"<div class='aviso'>Sua busca por “{e(pendente)}” roda assim que a IA terminar de aquecer.</div>")

    r = st.session_state.get("resultado")
    if r:
        notas = dict(r["res"])
        fortes = {i: p for i, p in notas.items() if p >= NOTA_FORTE}
        proximos = {i: p for i, p in notas.items() if p >= NOTA_MINIMA}
        mostrar = fortes or dict(list(proximos.items())[:3])
        secao(f"Resultados para “{r['q']}”", {0: "nenhum provável", 1: "1 provável"}.get(len(fortes), f"{len(fortes)} prováveis"))
        texto = ("Os objetos mais compatíveis com a sua descrição." if fortes else
                 "Nada bateu com segurança. Estes são os mais próximos." if mostrar else
                 "Nenhum objeto do mural parece com essa descrição.")
        st.html(f"<p class='consulta'>{texto} O modelo leu: <code>{e(r['en'])}</code></p>")
        grade([i for i in map(por_id, mostrar) if i], "r", mostrar)
        st.button("Limpar busca", on_click=limpar_busca, icon=":material/close:")

    lista = motor.itens()
    turma = sum(not i["demo"] for i in lista)
    secao("No mural", f"{len(lista)} objetos · {turma} da turma")
    st.write("")
    grade(lista, "m")


def tela_entregar():
    vigia()
    cabecalho("Entregar um objeto", "Achou? <em>Fotografe.</em>",
              "A IA escreve a descrição, identifica objeto, cor e marca, e coloca o item no mural.")
    novo = por_id(st.session_state.get("ultimo", ""))
    if novo:
        st.success("Objeto cadastrado e já disponível na busca.", icon=":material/check_circle:")
        a, b = st.columns([1, 1.6], gap="large")
        a.image(novo["_img"], width="stretch")
        pt = novo["atributos_pt"]
        linhas = "".join(f"<dt>{r}</dt><dd>{e(str(pt.get(k, '')))}</dd>" for k, r in ROTULOS.items())
        b.html(f"""<p class="ficha-id">#{e(novo['id'])} · {novo['tempo_s']} s</p><p class="ficha-titulo">{e(novo['titulo'])}</p>
            <p class="ficha-en">“{e(novo['legenda_en'])}”</p><dl class="dados">{linhas}</dl>""")
        if b.button("Cadastrar outro objeto", type="primary", icon=":material/add_a_photo:"):
            del st.session_state["ultimo"]
            st.rerun()
        return

    n = st.session_state.setdefault("form_n", 0)
    a, b = st.columns([1.25, 1], gap="large")
    with a:
        fonte = st.segmented_control("Origem da foto", ["Enviar arquivo", "Usar câmera"], default="Enviar arquivo",
                                     key=f"fonte_{n}", label_visibility="collapsed")
        if fonte == "Usar câmera":
            foto = st.camera_input("Foto do objeto", key=f"cam_{n}", label_visibility="collapsed")
        else:
            foto = st.file_uploader("Foto do objeto", type=["jpg", "jpeg", "png", "webp"], key=f"arq_{n}",
                                    label_visibility="collapsed")
            if foto:
                try:
                    st.image(motor.carregar_imagem(foto, motor.LADO_IMG), width="stretch")
                except ValueError as erro:
                    st.error(str(erro))
                    foto = None
    with b:
        local = st.text_input("Onde você achou?", key=f"local_{n}", max_chars=60, placeholder="Ex.: Sala 12")
        quem = st.text_input("Seu nome (opcional)", key=f"quem_{n}", max_chars=40,
                             help="Aparece na ficha, visível para quem abrir o app.")
        enviar = st.button("Cadastrar objeto", type="primary", width="stretch", icon=":material/sell:",
                           disabled=not foto or not motor.pronto())
        if not motor.pronto():
            st.caption("O cadastro é liberado quando a IA terminar de aquecer.")
        elif not foto:
            st.caption("Escolha ou tire uma foto para continuar.")
        if enviar:
            barra = st.progress(0, "Na fila da IA…")
            try:
                foto.seek(0)
                item = motor.cadastrar(foto, quem, local, lambda t, f: barra.progress(f, f"{t}…"))
            except ValueError as erro:
                barra.empty()
                st.error(str(erro))
            except Exception as erro:
                barra.empty()
                print("falha no cadastro:", repr(erro))
                st.error("A IA não conseguiu processar esta foto. Tente novamente.")
            else:
                st.session_state["ultimo"] = item["id"]
                st.session_state["form_n"] = n + 1
                st.rerun()


def usar_pergunta():
    if st.session_state.get("sugestao"):
        st.session_state["pergunta"] = st.session_state["sugestao"]
        st.session_state["sugestao"] = None


def tela_perguntar():
    vigia()
    cabecalho("Tire a dúvida com a IA", "Pergunte <em>à foto.</em>",
              "Escolha um objeto do mural ou envie uma foto e faça uma pergunta curta em português.")
    a, b = st.columns([1, 1.25], gap="large")
    img, chave = None, None
    with a:
        fonte = st.segmented_control("Origem", ["Do mural", "Enviar foto"], default="Do mural", key="p_fonte",
                                     label_visibility="collapsed")
        if fonte == "Enviar foto":
            arq = st.file_uploader("Foto", type=["jpg", "jpeg", "png", "webp"], key="p_arq", label_visibility="collapsed")
            if arq:
                try:
                    img, chave = motor.carregar_imagem(arq, motor.LADO_IMG), arq.file_id
                except ValueError as erro:
                    st.error(str(erro))
        else:
            por_chave = {i["id"]: i for i in motor.itens()}     # opções simples: itens guardam tensores
            id_ = st.selectbox("Objeto", list(por_chave), key="p_item", label_visibility="collapsed",
                               format_func=lambda c: f"{por_chave[c]['titulo']} · #{c}" if c in por_chave else c)
            if id_ in por_chave:
                img, chave = por_chave[id_]["_img"], id_
        if img is not None:
            st.image(img, width="stretch")
    with b:
        st.pills("Sugestões", PERGUNTAS, key="sugestao", on_change=usar_pergunta, label_visibility="collapsed")
        with st.form("form_pergunta", border=False):
            q = st.text_input("Sua pergunta", key="pergunta", max_chars=120, placeholder="Ex.: Tem algum adesivo?")
            ok = st.form_submit_button("Perguntar", type="primary", icon=":material/forum:",
                                       disabled=not motor.pronto())
        if ok and img is None:
            st.warning("Escolha uma foto primeiro.")
        elif ok and q.strip() and not ia_indisponivel():
            with st.spinner("Consultando o BLIP. A primeira pergunta carrega o modelo e demora mais…"):
                try:
                    en = motor.pergunta_en(q)
                    if en:
                        r = motor.perguntar(img, en)
                        st.session_state.setdefault("respostas", []).insert(0, dict(foto=chave, q=q.strip(), en=r, pt=motor.para_pt(r)))
                    else:
                        st.warning("Não consegui traduzir a pergunta agora. Tente uma das sugestões acima.")
                except Exception as erro:
                    print("falha na pergunta:", repr(erro))
                    st.error("A IA não conseguiu responder agora. Tente novamente.")
        for r in [r for r in st.session_state.get("respostas", []) if r["foto"] == chave][:5]:
            st.html(f"""<div class="resposta"><small>{e(r['q'])}</small><strong>{e(r['pt'])}</strong>
                <span>resposta do modelo: {e(r['en'])}</span></div>""")


def tela_sobre():
    vigia()
    cabecalho("Como funciona", "Três modelos, <em>uma etiqueta.</em>",
              "O app usa o BLIP (Salesforce, ICML 2022) sem nenhum treino adicional: tudo é zero-shot.")
    st.html("""<div class="passos">
      <div class="passo"><b>1 · LEGENDA</b><h3>Descreve a foto</h3><p>O modelo de captioning escreve uma frase sobre o objeto.</p></div>
      <div class="passo"><b>2 · PERGUNTAS</b><h3>Preenche a ficha</h3><p>O modelo de VQA responde qual é o objeto, a cor, a marca e onde ele aparece.</p></div>
      <div class="passo"><b>3 · BUSCA</b><h3>Encontra pela frase</h3><p>O modelo ITM mede o quanto sua descrição combina com cada foto.</p></div></div>""")
    secao("Checkpoints")
    st.html("""<div class="tabela"><table><tr><th>Hugging Face</th><th>Uso no app</th><th>Parâmetros</th></tr>
      <tr><td>Salesforce/blip-image-captioning-base</td><td>Legenda</td><td>224,0 M</td></tr>
      <tr><td>Salesforce/blip-vqa-base</td><td>Objeto, cor, marca, perguntas</td><td>361,2 M</td></tr>
      <tr><td>Salesforce/blip-itm-base-coco</td><td>Busca por texto</td><td>223,7 M</td></tr></table></div>""")
    secao("Limitações")
    st.markdown("""- O BLIP entende inglês, então buscas e perguntas passam por tradução.
- A marca é um palpite do modelo e costuma errar quando não há logotipo legível.
- A porcentagem indica compatibilidade estimada, não certeza. Confira sempre o objeto.
- Cadastros feitos na versão online são apagados quando o servidor reinicia.""")
    with st.expander("Créditos das fotos de demonstração"):
        st.markdown((RAIZ / "seed" / "CREDITOS.md").read_text(encoding="utf-8").split("\n", 2)[2])


PG_ENTREGAR = st.Page(tela_entregar, title="Entregar objeto", icon=":material/add_a_photo:", url_path="entregar")
st.navigation([
    st.Page(tela_achados, title="Achados", icon=":material/grid_view:", default=True),
    PG_ENTREGAR,
    st.Page(tela_perguntar, title="Perguntar à foto", icon=":material/forum:", url_path="perguntar"),
    st.Page(tela_sobre, title="Como funciona", icon=":material/info:", url_path="como-funciona"),
], position="top").run()
