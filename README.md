# Achados e perdidos da Fatec com BLIP

Trabalho da disciplina **Paradigmas e Tecnologias Emergentes em Ciência de Dados** (Fatec Cotia, Entrega 05: Foundation Models).
Autores: Bruno dos Santos Silva e Aparecido.

Tire foto de um objeto achado: o **BLIP** (Salesforce, ICML 2022) escreve a legenda e responde o que é, de que cor e de que marca.
Descreva em português o que você perdeu: o BLIP compara a frase com cada foto e mostra as mais parecidas.

| Checkpoint (Hugging Face) | Uso no app | Parâmetros |
|---|---|---|
| `Salesforce/blip-image-captioning-base` | legenda do cadastro | 224,0 M |
| `Salesforce/blip-vqa-base` | objeto, cor, marca, onde | 361,2 M |
| `Salesforce/blip-itm-base-coco` | busca por texto (P(combina)) | 223,7 M |

Nenhum modelo foi treinado de novo: é tudo zero-shot.

## Rodar no Streamlit

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

No **Streamlit Community Cloud**: *Create app* → escolha este repositório, branch `main`, arquivo `streamlit_app.py`.
Na CPU, os pesos são carregados em bfloat16 (cerca de 1,5 GB de RAM). Se precisar de float32, defina `BLIP_DTYPE=fp32`.
A primeira abertura baixa os três checkpoints (cerca de 3 GB) e pode levar alguns minutos. Na CPU, cada cadastro leva de 1 a 2 minutos.

## Rodar a versão Gradio (apresentação ao vivo)

```bash
pip install -r requirements-local.txt
python app.py              # gera um link público https://….gradio.live e o qrcode_app.png
python app.py --sem-share  # só local
python gravar_demo.py --busca "caneca vermelha"   # grava demo_blip.mp4
```

## Arquivos

- `motor.py`: carrega os 3 checkpoints, traduz (Google → MyMemory → dicionário), cadastra e busca.
- `streamlit_app.py` / `app.py`: interfaces Streamlit e Gradio sobre o mesmo motor.
- `seed/`: 10 fotos de demonstração (Wikimedia Commons, créditos em `seed/CREDITOS.md`). `seed/seed_cache.json` guarda as fichas que o modelo gerou para elas, para não precisar recalcular a cada início.
- `teste/`: foto usada no cadastro "ao vivo" do vídeo.
- `apresentacao.html`: slides. `achados_perdidos_BLIP.ipynb`: versão em notebook.

## Limitações

O BLIP só entende inglês, então a busca depende de tradução. Objetos muito parecidos podem trocar de posição no ranking. O app não substitui a conferência humana do objeto.
