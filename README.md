# Achados: achados e perdidos da Fatec com BLIP

Trabalho da disciplina **Paradigmas e Tecnologias Emergentes em Ciência de Dados** (Fatec Cotia, Entrega 05: Foundation Models).
Autores: Bruno dos Santos Silva e Aparecido.

Fotografe um objeto achado: o **BLIP** (Salesforce, ICML 2022) escreve a legenda e responde o que é, de que cor e de que marca.
Descreva em português o que você perdeu: o BLIP compara a frase com cada foto e mostra as mais parecidas.

| Checkpoint (Hugging Face) | Uso no app | Parâmetros |
|---|---|---|
| `Salesforce/blip-image-captioning-base` | legenda do cadastro | 224,0 M |
| `Salesforce/blip-vqa-base` | objeto, cor, marca, perguntas | 361,2 M |
| `Salesforce/blip-itm-base-coco` | busca por texto | 223,7 M |

Nenhum modelo foi treinado de novo: é tudo zero-shot.

## Rodar

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Publicar no Streamlit Community Cloud

Em [share.streamlit.io](https://share.streamlit.io): *Create app* → repositório `brunodt98/achados-perdidos-blip`, branch `main`, arquivo `streamlit_app.py`, Python 3.13.

O mural abre na hora. Na primeira execução o servidor baixa cerca de 3,4 GB de modelos, e busca e cadastro ficam liberados quando a IA termina de aquecer.
Só um modelo fica na memória de cada vez. Os cadastros feitos online são apagados quando o servidor reinicia.

## Arquivos

- `streamlit_app.py`: interface. `assets/` e `.streamlit/`: visual e tema.
- `motor.py`: modelos, tradução, cadastro e busca.
- `seed/`: 10 fotos de demonstração (Wikimedia Commons, créditos em `seed/CREDITOS.md`) e as fichas já geradas em `seed_cache.json`.
- `teste/`: foto para testar o cadastro.
- `apresentacao.html`: slides. `achados_perdidos_BLIP.ipynb`: versão em notebook.

## Limitações

O BLIP só entende inglês, então a busca depende de tradução. A marca é um palpite do modelo. Objetos parecidos podem trocar de posição no ranking, e o app não substitui a conferência humana.
