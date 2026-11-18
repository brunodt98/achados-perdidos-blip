"""Motor do achados e perdidos: BLIP, tradução, cadastro, busca e persistência.

Os três checkpoints somam cerca de 3,4 GB, mais do que cabe no Streamlit Community Cloud.
Por isso só um modelo fica na memória de cada vez, e a busca usa os embeddings de imagem
guardados no cadastro: o ViT não precisa rodar de novo a cada consulta.

torch e transformers só são importados na thread de aquecimento, então o mural abre na hora.
BLIP_DTYPE=bf16 usa metade da RAM na CPU (padrão: float32).
"""
import base64, concurrent.futures as cf, datetime as dt, gc, glob, hashlib, io, json, os, random
import re, threading, time, uuid

from PIL import Image, ImageOps, UnidentifiedImageError

BASE = os.path.dirname(os.path.abspath(__file__))
PASTA_SEED = os.path.join(BASE, "seed")
PASTA_CAD = os.path.join(BASE, "cadastros")
FUSO = dt.timezone(dt.timedelta(hours=-3))
MAX_CADASTROS = 60          # itens da turma mantidos na memória
LADO_IMG, LADO_THUMB = 768, 480

CAP_ID = "Salesforce/blip-image-captioning-base"
VQA_ID = "Salesforce/blip-vqa-base"
ITM_ID = "Salesforce/blip-itm-base-coco"
ATRIBUTOS = {"objeto": "What is the main object in this photo?",
             "cor": "What color is it?",
             "marca": "What brand is it?",
             "onde": "Where is it?"}
LOCAIS = ["Sala 12", "Biblioteca", "Cantina", "Laboratório 3", "Auditório",
          "Corredor do 2º andar", "Secretaria", "Pátio"]

ITENS, LOCK = [], threading.RLock()     # LOCK protege ITENS
IA_LOCK = threading.RLock()             # só uma inferência (e um modelo) por vez
ESTADO = {"fase": "parado", "msg": "", "feitos": 0, "total": 0, "erro": ""}
_inicio_lock = threading.Lock()
_iniciado = False


# ---------------------------------------------------------------- tradução
FRASES_PT = {"garrafa de água": "water bottle", "garrafa de agua": "water bottle",
             "fone de ouvido": "headphones", "fones de ouvido": "headphones",
             "molho de chaves": "bunch of keys", "carregador de celular": "phone charger",
             "guarda chuva": "umbrella", "chave de carro": "car key"}
OBJETOS = {"garrafa": "bottle", "garrafinha": "bottle", "mochila": "backpack", "bolsa": "bag",
           "estojo": "pencil case", "caderno": "notebook", "caneca": "mug", "xícara": "cup",
           "xicara": "cup", "copo": "cup", "guarda-chuva": "umbrella", "sombrinha": "umbrella",
           "calculadora": "calculator", "fone": "headphones", "fones": "headphones",
           "livro": "book", "celular": "cell phone", "chave": "key", "chaves": "keys",
           "carteira": "wallet", "óculos": "glasses", "oculos": "glasses", "caneta": "pen",
           "carregador": "charger", "notebook": "laptop", "boné": "cap", "bone": "cap",
           "chapéu": "hat", "chapeu": "hat", "blusa": "sweater", "casaco": "jacket"}
OBJETOS.update({"adesivo": "sticker", "adesivos": "stickers", "tampa": "lid", "capa": "case", "capinha": "phone case",
                "alça": "strap", "alca": "strap", "zíper": "zipper", "ziper": "zipper", "chaveiro": "keychain",
                "lápis": "pencil", "lapis": "pencil", "borracha": "eraser", "régua": "ruler", "regua": "ruler",
                "pendrive": "usb drive", "mouse": "mouse", "teclado": "keyboard", "tablet": "tablet",
                "relógio": "watch", "relogio": "watch", "pulseira": "bracelet", "anel": "ring", "colar": "necklace",
                "brinco": "earring", "luva": "glove", "cachecol": "scarf", "tênis": "sneakers", "tenis": "sneakers",
                "sapato": "shoe", "camisa": "shirt", "camiseta": "t-shirt", "moletom": "hoodie", "jaqueta": "jacket",
                "lancheira": "lunch box", "marmita": "lunch box", "pasta": "folder", "agenda": "planner",
                "documento": "document", "crachá": "badge", "cracha": "badge", "cartão": "card", "cartao": "card",
                "bicicleta": "bicycle", "água": "water", "agua": "water", "café": "coffee", "cafe": "coffee",
                "logo": "logo", "logotipo": "logo", "desenho": "drawing", "nome": "name", "mesa": "table",
                "pequeno": "small", "pequena": "small", "grande": "large", "velho": "old", "velha": "old",
                "novo": "new", "nova": "new", "rasgado": "torn", "rasgada": "torn", "couro": "leather",
                "plástico": "plastic", "plastico": "plastic", "metal": "metal", "tecido": "fabric",
                "listrado": "striped", "listrada": "striped", "estampado": "patterned", "estampada": "patterned"})
CORES = {"azul": "blue", "preto": "black", "preta": "black", "branco": "white", "branca": "white",
         "vermelho": "red", "vermelha": "red", "verde": "green", "amarelo": "yellow",
         "amarela": "yellow", "rosa": "pink", "roxo": "purple", "roxa": "purple",
         "cinza": "gray", "marrom": "brown", "laranja": "orange", "transparente": "clear",
         "pretos": "black", "pretas": "black", "brancos": "white", "brancas": "white", "azuis": "blue",
         "vermelhos": "red", "vermelhas": "red", "verdes": "green", "amarelos": "yellow", "amarelas": "yellow",
         "prata": "silver", "prateado": "silver", "prateada": "silver", "dourado": "gold", "dourada": "gold",
         "bege": "beige", "colorido": "colorful", "colorida": "colorful"}

PERGUNTAS_PT = {"de que cor é": "what color is it?", "qual é a cor": "what color is it?", "qual a cor": "what color is it?",
                "o que é isso": "what is this?", "o que é": "what is this?", "qual é a marca": "what brand is it?",
                "qual a marca": "what brand is it?", "está sobre uma mesa": "is it on a table?"}

EN_PT = {"water bottle": "garrafa de água", "bottle": "garrafa", "backpack": "mochila", "bag": "bolsa",
         "purse": "bolsa", "handbag": "bolsa", "pencil case": "estojo", "notebook": "caderno",
         "book": "livro", "mug": "caneca", "cup": "copo", "coffee cup": "xícara de café",
         "umbrella": "guarda-chuva", "calculator": "calculadora", "headphones": "fones de ouvido",
         "earphones": "fones de ouvido", "cell phone": "celular", "phone": "celular", "key": "chave",
         "keys": "chaves", "wallet": "carteira", "glasses": "óculos", "sunglasses": "óculos de sol",
         "pen": "caneta", "pencil": "lápis", "charger": "carregador", "laptop": "notebook",
         "cap": "boné", "hat": "boné", "sweater": "blusa", "jacket": "casaco", "shirt": "camisa",
         "shoe": "sapato", "shoes": "sapatos", "watch": "relógio", "bracelet": "pulseira",
         "black": "preto", "white": "branco", "blue": "azul", "red": "vermelho", "green": "verde",
         "yellow": "amarelo", "pink": "rosa", "purple": "roxo", "gray": "cinza", "grey": "cinza",
         "brown": "marrom", "orange": "laranja", "silver": "prata", "gold": "dourado",
         "beige": "bege", "tan": "bege", "clear": "transparente", "multicolored": "colorido",
         "multi": "colorido", "colorful": "colorido",
         "on table": "sobre a mesa", "table": "sobre a mesa", "on desk": "sobre a mesa",
         "desk": "sobre a mesa", "on ground": "no chão", "on floor": "no chão", "floor": "no chão",
         "ground": "no chão", "on wall": "na parede", "on chair": "na cadeira", "on bed": "na cama",
         "on counter": "no balcão", "in hand": "na mão", "keychain": "no chaveiro",
         "on bag": "sobre uma bolsa", "yes": "sim", "no": "não"}
SEM_MARCA = {"", "unknown", "none", "no", "nothing", "brand", "generic", "n/a", "not sure",
             "no brand", "no logo"}


def _com_prazo(fn, *args, prazo=5):
    """Serviços de tradução não têm timeout confiável; nenhum pode travar o app."""
    ex = cf.ThreadPoolExecutor(max_workers=1)
    try:
        return ex.submit(fn, *args).result(timeout=prazo)
    except Exception:
        return None
    finally:
        ex.shutdown(wait=False, cancel_futures=True)


def _google(texto, origem, destino):
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source=origem, target=destino).translate(texto)


def _mymemory(texto, origem, destino):
    from deep_translator import MyMemoryTranslator
    return MyMemoryTranslator(source=origem, target=destino).translate(texto)


_memo_tr, _memo_lock = {}, threading.Lock()
_tradutor_volta = 0.0       # os serviços gratuitos limitam acesso: depois de falhar, espera antes de tentar


def _traduzir(texto, sentido, so_google=False):
    global _tradutor_volta
    chave = (sentido, texto)
    with _memo_lock:
        if chave in _memo_tr:
            return _memo_tr[chave]
    if time.time() < _tradutor_volta:
        return None
    g, m = (("auto", "en"), ("pt-BR", "en-US")) if sentido == "en" else (("en", "pt"), ("en-US", "pt-BR"))
    r = _com_prazo(_google, texto, *g) or (None if so_google else _com_prazo(_mymemory, texto, *m))
    if not r:
        _tradutor_volta = time.time() + 60
        return None
    r = r.strip()
    with _memo_lock:
        _memo_tr[chave] = r
    return r


LIGACOES = {"com": "with", "sem": "without", "e": "and", "de": "", "do": "", "da": "", "um": "", "uma": "",
            "o": "", "a": "", "meu": "", "minha": "", "em": "on", "no": "on", "na": "on", "sobre": "on",
            "algum": "", "alguma": ""}


def _dicionario_pt_en(texto):
    """Tradução local. Devolve (frase, tudo_conhecido); a cor vai antes do objeto, como em inglês."""
    t = re.sub(r"[^\wáàâãéêíóôõúç\s-]", " ", texto.lower())
    t = " ".join(t.split())
    for pt, en in FRASES_PT.items():
        t = t.replace(pt, f"§{en.replace(' ', '_')}")
    cores, resto, conhecido = [], [], True
    for w in t.split():
        if w.startswith("§"):
            resto.append(w[1:].replace("_", " "))
        elif w in CORES:
            cores.append(CORES[w])
        elif w in OBJETOS:
            resto.append(OBJETOS[w])
        elif w in LIGACOES:
            resto.append(LIGACOES[w])
        else:
            resto.append(w)
            conhecido = False
    return " ".join(cores + [r for r in resto if r]), conhecido


def para_en(texto):
    texto = (texto or "").strip()
    if not texto:
        return ""
    local, conhecido = _dicionario_pt_en(texto)
    if conhecido and local:
        return local
    return _traduzir(texto, "en") or local or texto


def pergunta_en(texto):
    """Pergunta para o VQA. Devolve None sem tradução: inglês quebrado gera resposta sem sentido."""
    t = " ".join((texto or "").lower().split()).rstrip(" ?")
    if t in PERGUNTAS_PT:
        return PERGUNTAS_PT[t]
    for padrao, modelo in ((r"(?:tem|possui|há|ha) (.+)", "is there a {} ?"), (r"(?:é|e|está|esta) (.+)", "is it {} ?"),
                           (r"(?:o|a) (.+?) (?:é|está) (.+)", "is the {} {} ?")):
        achou = re.fullmatch(padrao, t)
        if achou:
            partes = [_dicionario_pt_en(g) for g in achou.groups()]
            if all(ok and en for en, ok in partes):
                return modelo.format(*(en for en, _ in partes)).replace(" ?", "?")
    return _traduzir(texto.strip(), "en")


def para_pt(texto):
    texto = (texto or "").strip()
    if not texto:
        return ""
    return EN_PT.get(texto.lower()) or _traduzir(texto, "pt") or texto


def legenda_pt(texto):
    """Só a tradução real; vazio se o serviço falhar (o título usa a ficha, em português)."""
    return _traduzir(texto, "pt") or ""


def atributo_pt(campo, valor, objeto_en="", online=True):
    """Traduz uma resposta curta do VQA. Marca é nome próprio: nunca passa pelo tradutor."""
    v = (valor or "").strip()
    baixo = v.lower()
    if campo == "marca":
        repete_objeto = baixo and (baixo in objeto_en.lower() or objeto_en.lower() in baixo)
        return "não identificada" if baixo in SEM_MARCA or repete_objeto else v.title()
    if campo == "onde" and objeto_en and objeto_en.lower().split()[-1].rstrip("s") in baixo:
        return "não identificado"
    if baixo in EN_PT:
        return EN_PT[baixo]
    return (online and _traduzir(v, "pt", so_google=True)) or v


def sem_prefixo(legenda_pt):
    """'uma foto de uma mochila' vira 'Uma mochila'."""
    t = re.sub(r"^\s*(uma\s+)?(foto|fotografia|imagem)\s+(de|do|da)\s+", "", legenda_pt or "", flags=re.I).strip()
    return t[:1].upper() + t[1:]


# ---------------------------------------------------------------- imagens e itens
def carregar_imagem(origem, lado_max=1024):
    try:
        img = origem if isinstance(origem, Image.Image) else Image.open(origem)
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as e:
        raise ValueError("Não consegui abrir esse arquivo como imagem.") from e
    img.thumbnail((lado_max, lado_max))
    return img


def thumb_b64(img, lado=LADO_THUMB):
    t = img.copy()
    t.thumbnail((lado, lado))
    b = io.BytesIO()
    t.save(b, "JPEG", quality=80, optimize=True)
    return base64.b64encode(b.getvalue()).decode()


def _montar(img, ficha, quem, local, demo, quando=None, id_=None):
    en = ficha["atributos_en"]
    objeto_en = en.get("objeto", "")
    pt = {k: atributo_pt(k, en.get(k, ""), objeto_en, online=not demo and quando is None) for k in ATRIBUTOS}
    quando = quando or dt.datetime.now(FUSO).isoformat(timespec="seconds")
    img = img.copy()
    img.thumbnail((LADO_IMG, LADO_IMG))
    return dict(id=id_ or uuid.uuid4().hex[:6].upper(), quando=quando, quem=quem, local=local, demo=demo,
                legenda_en=ficha["legenda_en"], legenda_pt=ficha["legenda_pt"],
                titulo=sem_prefixo(ficha["legenda_pt"]) or f"{pt['objeto']}, {pt['cor']}".capitalize(), atributos_en=en, atributos_pt=pt,
                tempo_s=ficha.get("tempo_s"), _img=img, _thumb=thumb_b64(img), _emb=None, _vec=None)


def publico(item):
    return {k: v for k, v in item.items() if not k.startswith("_")}


def _guardar(item):
    with LOCK:
        ITENS.append(item)
        turma = [i for i in ITENS if not i["demo"]]
        for velho in turma[:-MAX_CADASTROS]:
            ITENS.remove(velho)


def _ler_seed():
    arqs = sorted(p for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp") for p in glob.glob(os.path.join(PASTA_SEED, ext)))
    caminho = os.path.join(PASTA_SEED, "seed_cache.json")
    with open(caminho, encoding="utf-8") as f:
        cache = json.load(f)
    sorteio = random.Random(13)
    for a in arqs:
        local = sorteio.choice(LOCAIS)
        ficha = cache.get(f"{os.path.basename(a)}:{os.path.getsize(a)}")
        if ficha:
            id_ = hashlib.md5(os.path.basename(a).encode()).hexdigest()[:6].upper()     # estável entre reinícios
            _guardar(_montar(carregar_imagem(a), ficha, "item de demonstração", local, True, id_=id_))


def _ler_cadastros():
    fichas = sorted(glob.glob(os.path.join(PASTA_CAD, "*.json")), key=os.path.getmtime)
    for j in fichas[-MAX_CADASTROS:]:
        try:
            with open(j, encoding="utf-8") as f:
                d = json.load(f)
            quando = d.get("quando") or dt.datetime.fromtimestamp(os.path.getmtime(j), FUSO).isoformat(timespec="seconds")
            img = carregar_imagem(j[:-5] + ".jpg")
            _guardar(_montar(img, d, d.get("quem", "anônimo"), d.get("local", ""), False, quando, d["id"]))
        except Exception as e:
            print(f"cadastro ignorado ({os.path.basename(j)}): {e}")


def _salvar(item):
    """Grava foto e ficha. No Streamlit Cloud o disco é apagado quando o app reinicia."""
    try:
        os.makedirs(PASTA_CAD, exist_ok=True)
        base = os.path.join(PASTA_CAD, item["id"])
        item["_img"].save(base + ".jpg", quality=88)
        with open(base + ".json", "w", encoding="utf-8") as f:
            json.dump(publico(item), f, ensure_ascii=False, indent=1)
    except OSError as e:
        print("não salvou o cadastro:", e)


# ---------------------------------------------------------------- modelos (um por vez)
_ia = {}            # torch, device, dtype, classes
_procs = {}
_atual = (None, None)


def _preparar_ia():
    if _ia:
        return
    import torch
    from transformers import (BlipForConditionalGeneration, BlipForImageTextRetrieval,
                              BlipForQuestionAnswering, BlipProcessor)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    modo = os.environ.get("BLIP_DTYPE", "").lower()
    dtype = torch.float16 if device == "cuda" else (torch.bfloat16 if modo == "bf16" else torch.float32)
    _ia.update(torch=torch, device=device, dtype=dtype, proc=BlipProcessor,
               classes={CAP_ID: BlipForConditionalGeneration, VQA_ID: BlipForQuestionAnswering,
                        ITM_ID: BlipForImageTextRetrieval})


def _modelo(nome):
    """Devolve (processor, modelo), liberando antes o modelo que estava carregado."""
    global _atual
    with IA_LOCK:
        _preparar_ia()
        torch = _ia["torch"]
        if _atual[0] != nome:
            _atual = (None, None)
            gc.collect()
            if _ia["device"] == "cuda":
                torch.cuda.empty_cache()
            m = _ia["classes"][nome].from_pretrained(nome, dtype=_ia["dtype"]).to(_ia["device"]).eval()
            _atual = (nome, m)
        if nome not in _procs:
            _procs[nome] = _ia["proc"].from_pretrained(nome)
        return _procs[nome], _atual[1]


def _gerar(nome, img, texto, **kw):
    with IA_LOCK:
        proc, m = _modelo(nome)
        torch = _ia["torch"]
        x = proc(img, texto, return_tensors="pt").to(_ia["device"], _ia["dtype"])
        with torch.inference_mode():
            out = m.generate(**x, **kw)
        return proc.decode(out[0], skip_special_tokens=True).strip()


def legenda(img):
    return _gerar(CAP_ID, img, "a photo of", max_new_tokens=30, num_beams=4, repetition_penalty=1.3)


def perguntar(img, pergunta_en):
    return _gerar(VQA_ID, img, pergunta_en, max_new_tokens=10)


def _embedding(img):
    with IA_LOCK:
        proc, m = _modelo(ITM_ID)
        torch = _ia["torch"]
        pv = proc(images=img, return_tensors="pt")["pixel_values"].to(_ia["device"], _ia["dtype"])
        with torch.inference_mode():
            emb = m.vision_model(pixel_values=pv)[0]
            vetor = torch.nn.functional.normalize(m.vision_proj(emb[:, 0, :]), dim=-1)
            return emb.float().cpu().half(), vetor.float().cpu()      # embedding em float16: metade da RAM


def buscar(consulta, k=6, lote=8, candidatos=8):
    """Devolve ([{item, p}], consulta_em_inglês), do mais para o menos compatível.
    Como no artigo do BLIP, a similaridade ITC (rápida) escolhe os candidatos e o ITM reordena."""
    q_en = para_en(consulta)
    with LOCK:
        base = [i for i in ITENS if i["_emb"] is not None]
    if not base or not q_en:
        return [], q_en
    notas = []
    with IA_LOCK:
        proc, m = _modelo(ITM_ID)
        torch, dev, dtype = _ia["torch"], _ia["device"], _ia["dtype"]
        tx = proc(text=[q_en], return_tensors="pt")
        ids, am = tx["input_ids"].to(dev), tx["attention_mask"].to(dev)
        with torch.inference_mode():
            if candidatos and len(base) > candidatos:
                t = m.text_encoder(input_ids=ids, attention_mask=am).last_hidden_state[:, 0, :]
                t = torch.nn.functional.normalize(m.text_proj(t), dim=-1).float().cpu()
                sim = (torch.cat([b["_vec"] for b in base]) @ t.T).squeeze(1)
                base = [base[j] for j in sim.topk(candidatos).indices.tolist()]
            for i in range(0, len(base), lote):
                emb = torch.cat([b["_emb"] for b in base[i:i + lote]]).to(dev, dtype)
                n = emb.shape[0]
                saida = m.text_encoder(input_ids=ids.repeat(n, 1), attention_mask=am.repeat(n, 1),
                                       encoder_hidden_states=emb,
                                       encoder_attention_mask=torch.ones(emb.shape[:-1], dtype=torch.long, device=dev))
                logits = m.itm_head(saida.last_hidden_state[:, 0, :])
                notas += torch.softmax(logits.float(), -1)[:, 1].tolist()
    ordem = sorted(range(len(base)), key=notas.__getitem__, reverse=True)[:k]
    return [dict(item=base[j], p=round(notas[j], 3)) for j in ordem], q_en


def cadastrar(origem, quem="", local="", progresso=None):
    """Roda legenda, 4 perguntas e embedding. progresso(texto, fração) acompanha cada etapa."""
    avisa = progresso or (lambda *_: None)
    t0 = time.time()
    img = carregar_imagem(origem)
    with IA_LOCK:
        avisa("Escrevendo a legenda", .05)
        leg = legenda(img)
        att = {}
        for n, (campo, q) in enumerate(ATRIBUTOS.items()):
            avisa(f"Identificando: {campo}", .3 + n * .12)
            att[campo] = perguntar(img, q)
        avisa("Preparando a foto para a busca", .8)
        emb, vetor = _embedding(img)
    avisa("Traduzindo a ficha", .93)
    ficha = dict(legenda_en=leg, legenda_pt=legenda_pt(leg), atributos_en=att, tempo_s=round(time.time() - t0, 1))
    item = _montar(img, ficha, quem.strip()[:40] or "anônimo", local.strip()[:60], False)
    item["_emb"], item["_vec"] = emb, vetor
    _guardar(item)
    _salvar(item)
    avisa("Pronto", 1.0)
    return item


# ---------------------------------------------------------------- inicialização
def _aquecer():
    try:
        ESTADO.update(fase="carregando", msg="Preparando as bibliotecas de IA")
        _preparar_ia()
        import deep_translator  # noqa: F401  (a importação é lenta; não pode gastar o prazo da 1ª tradução)
        ESTADO.update(msg="Carregando o modelo de busca")
        _modelo(ITM_ID)
        with LOCK:
            pendentes = [i for i in ITENS if i["_emb"] is None]
        ESTADO.update(msg="Lendo as fotos do mural", total=len(pendentes), feitos=0)
        for n, item in enumerate(pendentes, 1):
            item["_emb"], item["_vec"] = _embedding(item["_img"])
            ESTADO.update(feitos=n)
        ESTADO.update(fase="pronto", msg="")
        print(f"motor pronto: {len(ITENS)} itens, {_ia['device']}, {_ia['dtype']}")
    except Exception as e:
        ESTADO.update(fase="erro", erro=f"{type(e).__name__}: {e}")
        print("falha ao aquecer:", repr(e))


def iniciar():
    """Lê o mural na hora e aquece a IA em segundo plano. Pode ser chamada a cada execução."""
    global _iniciado
    with _inicio_lock:
        if _iniciado:
            return
        _iniciado = True
        _ler_seed()
        _ler_cadastros()
        threading.Thread(target=_aquecer, name="aquecer-blip", daemon=True).start()


def pronto():
    return ESTADO["fase"] == "pronto"


def itens():
    with LOCK:
        return list(ITENS)[::-1]
