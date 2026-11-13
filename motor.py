"""Motor do achados e perdidos: os 3 checkpoints do BLIP, tradução, cadastro e busca.
Usado pelo app Gradio (app.py) e pelo app Streamlit (streamlit_app.py).
BLIP_DTYPE=bf16 carrega os pesos em bfloat16 na CPU (metade da RAM; usado no Streamlit Cloud).
"""
import io, json, time, base64, datetime, os, threading, textwrap, uuid, glob, sys, random, argparse
from functools import lru_cache
import numpy as np, pandas as pd, requests, torch
from PIL import Image, ImageOps
from transformers import (BlipProcessor, BlipForConditionalGeneration,
                          BlipForQuestionAnswering, BlipForImageTextRetrieval)

DEVICE = "cuda" if torch.cuda.is_available() else ("mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu")
DTYPE  = torch.float16 if DEVICE == "cuda" else (torch.bfloat16 if os.environ.get("BLIP_DTYPE") == "bf16" else torch.float32)
GPU    = torch.cuda.get_device_name(0) if DEVICE == "cuda" else DEVICE.upper()
BASE   = os.path.dirname(os.path.abspath(__file__))
print(f"Dispositivo: {DEVICE} ({GPU}) · {DTYPE}")

# ---------------------------------------------------------------- modelos
CAP_ID, VQA_ID, ITM_ID = ("Salesforce/blip-image-captioning-base",
                          "Salesforce/blip-vqa-base", "Salesforce/blip-itm-base-coco")
t0 = time.time()
cap_proc = BlipProcessor.from_pretrained(CAP_ID)
cap_model = BlipForConditionalGeneration.from_pretrained(CAP_ID, torch_dtype=DTYPE).to(DEVICE).eval()
vqa_proc = BlipProcessor.from_pretrained(VQA_ID)
vqa_model = BlipForQuestionAnswering.from_pretrained(VQA_ID, torch_dtype=DTYPE).to(DEVICE).eval()
itm_proc = BlipProcessor.from_pretrained(ITM_ID)
itm_model = BlipForImageTextRetrieval.from_pretrained(ITM_ID, torch_dtype=DTYPE).to(DEVICE).eval()
T_CARGA = time.time() - t0
print(f"3 modelos carregados em {T_CARGA:.1f} s")

def raio_x(m):
    partes = {"ViT (imagem)": m.vision_model}
    if hasattr(m, "text_encoder"): partes["encoder de texto"] = m.text_encoder
    if hasattr(m, "text_decoder"): partes["decoder de texto"] = m.text_decoder
    d = {k: round(sum(p.numel() for p in v.parameters()) / 1e6, 1) for k, v in partes.items()}
    d["TOTAL (M)"] = round(sum(p.numel() for p in m.parameters()) / 1e6, 1)
    d["memória (MB)"] = round(sum(p.numel() * p.element_size() for p in m.parameters()) / 1024**2)
    return d
RAIO_X = pd.DataFrame({"captioning-base": raio_x(cap_model), "vqa-base": raio_x(vqa_model), "itm-base-coco": raio_x(itm_model)}).T.fillna("—")
print(RAIO_X)

# ---------------------------------------------------------------- tradução
try:
    from deep_translator import GoogleTranslator, MyMemoryTranslator
    _pt2en = [GoogleTranslator(source="auto", target="en"), MyMemoryTranslator(source="pt-BR", target="en-US")]
    _en2pt = [GoogleTranslator(source="en", target="pt"), MyMemoryTranslator(source="en-US", target="pt-BR")]
except Exception:
    _pt2en = _en2pt = []

def _traduzir(tradutores, t):
    """Tenta cada serviço (Google, depois MyMemory); None se todos falharem."""
    for tr in tradutores:
        try:
            r = tr.translate(t)
            if r: return r.lower() if r.isupper() else r
        except Exception: pass
    return None

DIC = {"garrafa": "bottle", "mochila": "backpack", "bolsa": "bag", "estojo": "pencil case", "caderno": "notebook",
       "água": "water", "agua": "water", "caneca": "mug", "xícara": "cup", "guarda-chuva": "umbrella",
       "guarda-chuvas": "umbrella", "sombrinha": "umbrella", "calculadora": "calculator", "fones": "headphones",
       "ouvido": "ear", "molho": "bunch", "estampado": "patterned", "fechado": "closed",
       "livro": "book", "celular": "cell phone", "fone": "headphones", "chave": "key", "chaves": "keys",
       "carteira": "wallet", "óculos": "glasses", "caneta": "pen", "copo": "cup", "garrafinha": "bottle",
       "carregador": "charger", "notebook": "laptop", "boné": "cap", "blusa": "sweater", "casaco": "jacket",
       "azul": "blue", "preto": "black", "preta": "black", "branco": "white", "branca": "white",
       "vermelho": "red", "vermelha": "red", "verde": "green", "amarelo": "yellow", "amarela": "yellow",
       "rosa": "pink", "roxo": "purple", "roxa": "purple", "cinza": "gray", "marrom": "brown", "laranja": "orange",
       "com": "with", "de": "of", "e": "and"}
DIC_EN = {v: k for k, v in DIC.items() if k not in ("garrafinha", "preta", "branca", "vermelha", "amarela", "roxa",
                                                    "agua", "guarda-chuvas", "sombrinha", "fones")}

@lru_cache(1024)
def para_en(t):
    t = (t or "").strip()
    if not t: return t
    palavras = t.lower().split()
    if all(w in DIC for w in palavras):          # busca curta e conhecida: dicionário não perde a cor
        return " ".join(DIC[w] for w in palavras)
    return _traduzir(_pt2en, t) or " ".join(DIC.get(w, w) for w in palavras)

@lru_cache(1024)
def para_pt(t):
    t = (t or "").strip()
    if not t: return t
    return _traduzir(_en2pt, t) or " ".join(DIC_EN.get(w.lower(), w) for w in t.split())



# ---------------------------------------------------------------- motor
def carregar_imagem(origem, lado_max=1024):
    if isinstance(origem, Image.Image): img = origem
    elif str(origem).startswith("http"):
        r = requests.get(origem, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Fatec Cotia demo)"}); r.raise_for_status()
        img = Image.open(io.BytesIO(r.content))
    else: img = Image.open(origem)
    img = ImageOps.exif_transpose(img).convert("RGB"); img.thumbnail((lado_max, lado_max))
    return img

@torch.no_grad()
def legenda(img, prompt="a photo of"):
    x = (cap_proc(img, prompt, return_tensors="pt") if prompt else cap_proc(img, return_tensors="pt")).to(DEVICE, DTYPE)
    out = cap_model.generate(**x, max_new_tokens=30, num_beams=4, repetition_penalty=1.3)
    return cap_proc.decode(out[0], skip_special_tokens=True).strip()

@torch.no_grad()
def perguntar(img, q):
    x = vqa_proc(img, q, return_tensors="pt").to(DEVICE, DTYPE)
    out = vqa_model.generate(**x, max_new_tokens=10)
    return vqa_proc.decode(out[0], skip_special_tokens=True).strip()

ATRIBUTOS = {"objeto": "What is the main object in this photo?",
             "cor": "What color is it?",
             "marca": "What brand is it?",
             "onde": "Where is it?"}

ITENS, LOCK = [], threading.Lock()

def thumb_b64(img, lado=360):
    t = img.copy(); t.thumbnail((lado, lado)); b = io.BytesIO(); t.save(b, "JPEG", quality=82)
    return base64.b64encode(b.getvalue()).decode()

@torch.no_grad()
def cadastrar(origem, quem="", local="", pre=None):
    """pre = ficha já gerada pelo modelo (cache do seed): pula legenda e VQA."""
    t0 = time.time(); img = carregar_imagem(origem)
    if pre:
        leg, att = pre["legenda_en"], pre["atributos_en"]
        leg_pt, att_pt = pre["legenda_pt"], pre["atributos_pt"]
    else:
        leg = legenda(img)
        att = {k: perguntar(img, q) for k, q in ATRIBUTOS.items()}
        leg_pt, att_pt = para_pt(leg), {k: para_pt(v) for k, v in att.items()}
    pix = itm_proc(images=img, return_tensors="pt")["pixel_values"].cpu()   # guardado para a busca
    item = dict(id=uuid.uuid4().hex[:6].upper(), hora=datetime.datetime.now().strftime("%H:%M:%S"),
                quem=quem.strip() or "anônimo", local=local.strip(), legenda_en=leg, legenda_pt=leg_pt,
                **att_pt, atributos_en=att, atributos_pt=att_pt,
                tempo_s=pre["tempo_s"] if pre else round(time.time() - t0, 2))
    with LOCK: ITENS.append({**item, "_img": img, "_pix": pix})
    return item, img

@torch.no_grad()
def buscar(consulta, k=5, lote=16):
    with LOCK: base = list(ITENS)
    if not base or not consulta.strip(): return [], consulta
    q_en = para_en(consulta)
    tx = itm_proc(text=[q_en], return_tensors="pt")
    ids, am = tx["input_ids"].to(DEVICE), tx["attention_mask"].to(DEVICE)
    itm, itc = [], []
    for i in range(0, len(base), lote):
        pv = torch.cat([b["_pix"] for b in base[i:i+lote]]).to(DEVICE, DTYPE); n = pv.shape[0]
        o = itm_model(input_ids=ids.repeat(n, 1), attention_mask=am.repeat(n, 1), pixel_values=pv, use_itm_head=True)
        itm += torch.softmax(o.itm_score.float(), -1)[:, 1].tolist()
        try:
            o2 = itm_model(input_ids=ids, attention_mask=am, pixel_values=pv, use_itm_head=False)
            itc += o2.itm_score.float().reshape(-1).tolist()
        except Exception:
            itc += [float("nan")] * n
    ordem = np.argsort(itm)[::-1][:k]
    return [dict(item=base[j], p_itm=round(itm[j], 3), cos_itc=round(itc[j], 3)) for j in ordem], q_en


# ---------------------------------------------------------------- itens de demonstração
LOCAIS = ["Sala 12", "Biblioteca", "Cantina", "Laboratório 3", "Auditório", "Corredor do 2º andar", "Secretaria", "Pátio"]
def carregar_seed(pasta=os.path.join(BASE, "seed")):
    """Cadastra as fotos de ./seed/. A ficha gerada pelo modelo fica em seed/seed_cache.json
    (chave = nome + tamanho do arquivo); na próxima vez o modelo não precisa rodar de novo."""
    arqs = sorted(glob.glob(os.path.join(pasta, "*.jp*g")) + glob.glob(os.path.join(pasta, "*.png")) + glob.glob(os.path.join(pasta, "*.webp")))
    if not arqs: print(f"(nenhuma imagem em {pasta} — mural começa vazio)"); return
    caminho = os.path.join(pasta, "seed_cache.json")
    cache = json.load(open(caminho, encoding="utf-8")) if os.path.exists(caminho) else {}
    random.seed(13)
    for a in arqs:
        chave = f"{os.path.basename(a)}:{os.path.getsize(a)}"
        try:
            item, _ = cadastrar(a, quem="item de demonstração", local=random.choice(LOCAIS), pre=cache.get(chave))
            print(f"  seed #{item['id']}: {item['legenda_pt']}  ({item['tempo_s']} s{', do cache' if chave in cache else ''})")
            if chave not in cache:
                cache[chave] = {k: item[k] for k in ("legenda_en", "legenda_pt", "atributos_en", "atributos_pt", "tempo_s")}
                json.dump(cache, open(caminho, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception as e:
            print(f"  falhou {a}: {e}")

PASTA_CAD = os.path.join(BASE, "cadastros")
os.makedirs(PASTA_CAD, exist_ok=True)
def salvar_novo(img, item):
    """Guarda cada cadastro feito pela turma (foto + ficha) em ./cadastros/."""
    try:
        img.save(os.path.join(PASTA_CAD, f"{item['id']}.jpg"), quality=88)
        json.dump(item, open(os.path.join(PASTA_CAD, f"{item['id']}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception as e:
        print("não salvou cadastro:", e)
