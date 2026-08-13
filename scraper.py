"""
Monitor de imóveis - Paulo Tavares Imóveis
--------------------------------------------------
Este script:
1. Abre a página de busca (com os bairros já filtrados) usando um navegador
   headless (Playwright), porque o site carrega a lista de imóveis via
   JavaScript e não aparece em um simples "download" da página.
2. Percorre as páginas de resultado (paginação) até não encontrar mais nada
   novo.
3. Compara os links encontrados com o que já foi visto em execuções
   anteriores (guardado em data/seen.json).
4. Gera um painel HTML (docs/index.html) destacando os imóveis novos.

Você não precisa mexer neste arquivo. Se um dia quiser trocar o filtro de
bairros, basta trocar a variável SEARCH_URL abaixo pelo novo link que o
próprio site gera quando você aplica os filtros.
"""

import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

# --------------------------------------------------------------------------
# CONFIGURAÇÃO — pode editar aqui se quiser mudar bairros/filtros no futuro.
# Basta copiar a URL nova da barra de endereço do site depois de aplicar os
# filtros desejados.
# --------------------------------------------------------------------------
SEARCH_URL = (
    "https://www.paulotavaresimoveis.com.br/venda/imoveis/belo-horizonte/"
    "betania--cinquentenario--marajo--palmeiras--salgado-filho--parque-sao-jose--havai/"
    "0-quartos/0-suite-ou-mais/0-vaga/0-banheiro-ou-mais/todos-os-condominios"
    "?valorminimo=0&valormaximo=0&areade=0&areaate=0&pagina={page}"
)
BASE_URL = "https://www.paulotavaresimoveis.com.br"
MAX_PAGES = 25          # trava de segurança para não entrar em loop infinito
WAIT_MS = 2500           # tempo extra de espera após o carregamento da página
NAV_TIMEOUT_MS = 45000

DATA_FILE = Path(__file__).parent / "data" / "seen.json"
OUTPUT_HTML = Path(__file__).parent / "docs" / "index.html"

BR_TZ = timezone(timedelta(hours=-3))


def coletar_links_da_pagina(page):
    """Extrai todos os links de imóveis visíveis na página atual."""
    anchors = page.eval_on_selector_all(
        "a[href*='/imovel/']",
        """els => els.map(el => ({
            href: el.getAttribute('href'),
            text: (el.innerText || el.textContent || '').trim()
        }))""",
    )
    resultados = {}
    for a in anchors:
        href = a.get("href") or ""
        if not href:
            continue
        href_abs = urljoin(BASE_URL, href)
        titulo = a.get("text") or ""
        # fica com o texto mais longo encontrado para aquele link
        if href_abs not in resultados or len(titulo) > len(resultados[href_abs]):
            resultados[href_abs] = titulo
    return resultados


def coletar_todos_os_imoveis():
    todos = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            locale="pt-BR",
        )
        page = context.new_page()
        page.set_default_navigation_timeout(NAV_TIMEOUT_MS)

        pagina_anterior_vazia = False
        links_pagina_anterior = set()

        for numero_pagina in range(1, MAX_PAGES + 1):
            url = SEARCH_URL.format(page=numero_pagina)
            print(f"Verificando página {numero_pagina}: {url}")
            try:
                page.goto(url, wait_until="networkidle")
            except Exception as e:
                print(f"  Falha ao carregar a página {numero_pagina}: {e}")
                break

            # espera extra para o JavaScript terminar de montar a lista
            page.wait_for_timeout(WAIT_MS)
            try:
                page.wait_for_selector("a[href*='/imovel/']", timeout=8000)
            except Exception:
                pass  # pode ser que essa página realmente não tenha imóveis

            encontrados = coletar_links_da_pagina(page)

            if not encontrados:
                print("  Nenhum imóvel encontrado nesta página. Parando.")
                break

            # se a página atual tem exatamente os mesmos links da anterior,
            # provavelmente o site parou de paginar e está repetindo a última página
            if set(encontrados.keys()) == links_pagina_anterior:
                print("  Página repetida (provável fim da lista). Parando.")
                break

            links_pagina_anterior = set(encontrados.keys())
            todos.update(encontrados)
            time.sleep(1.5)  # pausa educada entre as páginas

        browser.close()
    return todos


def carregar_estado_anterior():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def salvar_estado(estado):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def limpar_titulo(titulo, href):
    if not titulo:
        # fallback: monta um título a partir da URL
        slug = href.rstrip("/").split("/")[-1]
        slug = re.sub(r"[-_]+", " ", slug)
        return slug.title()
    # o texto do link às vezes vem com quebras de linha/duplicações
    linhas = [l.strip() for l in titulo.split("\n") if l.strip()]
    return linhas[0] if linhas else titulo.strip()


def gerar_html(estado, novos_hrefs, ultima_verificacao):
    itens = list(estado.items())
    # novos primeiro, depois por data em que foram vistos pela primeira vez (mais recente primeiro)
    itens.sort(key=lambda kv: (kv[0] not in novos_hrefs, kv[1].get("primeira_vez", "")), reverse=False)
    itens.sort(key=lambda kv: (kv[0] not in novos_hrefs), reverse=False)

    linhas_html = []
    for href, info in itens:
        titulo = info.get("titulo", href)
        eh_novo = href in novos_hrefs
        badge = '<span class="badge">NOVO</span>' if eh_novo else ""
        classe = "item novo" if eh_novo else "item"
        primeira_vez = info.get("primeira_vez", "")
        linhas_html.append(f"""
        <div class="{classe}">
          <a href="{href}" target="_blank" rel="noopener">{titulo}</a>
          {badge}
          <div class="meta">visto pela primeira vez em {primeira_vez}</div>
        </div>""")

    total = len(estado)
    total_novos = len(novos_hrefs)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Monitor de Imóveis - Paulo Tavares</title>
<style>
  body {{
    font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    background: #f5f4f1;
    color: #2b2b2b;
    margin: 0;
    padding: 0 0 60px;
  }}
  header {{
    background: #1f2d3d;
    color: white;
    padding: 24px 20px;
  }}
  header h1 {{
    margin: 0 0 6px;
    font-size: 22px;
  }}
  header p {{
    margin: 0;
    opacity: 0.8;
    font-size: 14px;
  }}
  .resumo {{
    max-width: 720px;
    margin: 20px auto 0;
    padding: 0 20px;
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
  }}
  .resumo .card {{
    background: white;
    border-radius: 10px;
    padding: 14px 18px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    flex: 1;
    min-width: 140px;
  }}
  .resumo .card .num {{
    font-size: 26px;
    font-weight: 700;
  }}
  .resumo .card .label {{
    font-size: 13px;
    color: #666;
  }}
  .lista {{
    max-width: 720px;
    margin: 24px auto;
    padding: 0 20px;
  }}
  .item {{
    background: white;
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 10px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    position: relative;
  }}
  .item.novo {{
    border-left: 4px solid #2e9e44;
  }}
  .item a {{
    color: #1f2d3d;
    font-weight: 600;
    text-decoration: none;
    font-size: 15px;
  }}
  .item a:hover {{
    text-decoration: underline;
  }}
  .badge {{
    display: inline-block;
    background: #2e9e44;
    color: white;
    font-size: 11px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 999px;
    margin-left: 8px;
    vertical-align: middle;
  }}
  .meta {{
    font-size: 12px;
    color: #888;
    margin-top: 4px;
  }}
</style>
</head>
<body>
<header>
  <h1>Monitor de Imóveis — Paulo Tavares Imóveis</h1>
  <p>Última verificação: {ultima_verificacao}</p>
</header>

<div class="resumo">
  <div class="card"><div class="num">{total}</div><div class="label">imóveis monitorados no total</div></div>
  <div class="card"><div class="num">{total_novos}</div><div class="label">novos desde a última verificação</div></div>
</div>

<div class="lista">
{"".join(linhas_html) if linhas_html else "<p>Nenhum imóvel encontrado ainda.</p>"}
</div>

</body>
</html>
"""
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html, encoding="utf-8")


def main():
    estado_anterior = carregar_estado_anterior()
    encontrados_agora = coletar_todos_os_imoveis()

    agora = datetime.now(BR_TZ).strftime("%d/%m/%Y %H:%M")

    novos_hrefs = set()
    estado_novo = dict(estado_anterior)  # mantém histórico mesmo se um imóvel sair da lista

    for href, titulo_bruto in encontrados_agora.items():
        titulo = limpar_titulo(titulo_bruto, href)
        if href not in estado_novo:
            novos_hrefs.add(href)
            estado_novo[href] = {"titulo": titulo, "primeira_vez": agora}
        else:
            # atualiza o título caso tenha mudado, mas preserva a data original
            estado_novo[href]["titulo"] = titulo or estado_novo[href].get("titulo", "")

    print(f"Total de imóveis encontrados nesta execução: {len(encontrados_agora)}")
    print(f"Novos imóveis: {len(novos_hrefs)}")
    for href in novos_hrefs:
        print(f"  NOVO: {href}")

    salvar_estado(estado_novo)
    gerar_html(estado_novo, novos_hrefs, agora)
    print(f"Painel gerado em: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
