"""
Monitor de imóveis - várias imobiliárias
--------------------------------------------------
Este script:
1. Para cada imobiliária configurada em SITES, abre a página de busca (com
   os bairros já filtrados) usando um navegador headless (Playwright),
   porque esses sites carregam a lista de imóveis via JavaScript e não
   aparecem em um simples "download" da página.
2. Percorre as páginas de resultado (paginação) até não encontrar mais nada
   novo — tentando primeiro achar um link/botão de "próxima página" e, se
   não achar, tentando rolar a página (scroll infinito).
3. Compara os links encontrados com o que já foi visto em execuções
   anteriores (guardado em data/seen.json, organizado por imobiliária).
4. Gera um painel HTML (docs/index.html) com uma aba para cada imobiliária,
   destacando os imóveis novos.

Você não precisa mexer neste arquivo no dia a dia. Se quiser adicionar,
remover ou trocar o filtro de alguma imobiliária, edite a lista SITES logo
abaixo.
"""

import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

# --------------------------------------------------------------------------
# CONFIGURAÇÃO — uma entrada para cada imobiliária monitorada.
#   name:  nome que aparece no painel
#   url:   link de busca já com os bairros/filtros aplicados
#   base:  domínio base do site (para resolver links relativos)
#   link_pattern: pedaço do link que identifica a página de UM imóvel
#                 (usado para separar links de imóveis dos outros links do
#                 site, tipo menu, rodapé, etc.)
# --------------------------------------------------------------------------
SITES = [
    {
        "key": "paulo_tavares",
        "name": "Paulo Tavares Imóveis",
        "url": (
            "https://www.paulotavaresimoveis.com.br/venda/imoveis/belo-horizonte/"
            "betania--cinquentenario--marajo--palmeiras--salgado-filho--parque-sao-jose--havai/"
            "0-quartos/0-suite-ou-mais/0-vaga/0-banheiro-ou-mais/todos-os-condominios"
            "?valorminimo=0&valormaximo=0&areade=0&areaate=0&pagina=1"
        ),
        "base": "https://www.paulotavaresimoveis.com.br",
        "link_pattern": r"/imovel/[^/?#]+/\d+(?:[/?#]|$)",
    },
    {
        "key": "inteligencia_bh",
        "name": "Inteligência Imobiliária BH",
        "url": (
            "https://www.inteligenciaimobiliariabh.com.br/venda/imovel/belo-horizonte/"
            "betania+cinquentenario+palmeiras+parque-sao-jose+marajo+estrela-do-oriente+havai+salgado-filho/"
            "?&pagina=1"
        ),
        "base": "https://www.inteligenciaimobiliariabh.com.br",
        "link_pattern": r"/imovel/[^/?#]+/\d+(?:[/?#]|$)",
    },
    {
        "key": "bihain",
        "name": "Bihain Imóveis",
        "url": (
            "https://www.bihainimoveis.com.br/imoveis/a-venda/belo-horizonte/"
            "estrela-dalva+betania+cinquentenario+palmeiras+marajo+estrela-do-oriente+parque-sao-jose"
        ),
        "base": "https://www.bihainimoveis.com.br",
        "link_pattern": r"/imovel/[^/?#]+/[A-Za-z]{2,3}\d+-[A-Za-z]+",
    },
    {
        "key": "palmeiras",
        "name": "Imobiliária Palmeiras",
        "url": (
            "https://www.imobiliariapalmeiras.com.br/imoveis/venda/#/?tipoNegocio=VA,VL"
            "&n=1&ordem=valor-ASC&mb=s&slug=0&page=1"
            "&bairros=18489,1385,3879,6075,6794"
        ),
        "base": "https://www.imobiliariapalmeiras.com.br",
        "link_pattern": r"/imovel/[^/?#]+/IP-\d+",
    },
    {
        "key": "gr_imoveis",
        "name": "GR Imóveis",
        "url": (
            "https://www.grimoveis.com.br/venda/imovel/belo-horizonte/"
            "betania+cinquentenario+estrela-d-alva+estrela-dalva+estrela-do-oriente+havai+marajo"
            "+palmeiras+parque-sao-jose+salgado-filho+salgado-filho-nova-suissa/?&pagina=1"
        ),
        "base": "https://www.grimoveis.com.br",
        "link_pattern": r"/imovel/[^/?#]+/\d+(?:[/?#]|$)",
    },
    {
        "key": "sensale",
        "name": "Sensale Imóveis",
        "url": (
            "https://sensaleimoveis.com.br/busca/?cidade%5B%5D=belo+horizonte"
            "&cidade%5B%5D=Belo+Horizonte&cidade%5B%5D=BELO+HORIZONTE"
            "&bairro%5B%5D=Cinquenten%C3%A1rio&bairro%5B%5D=Estrela+Dalva"
            "&bairro%5B%5D=Hava%C3%AD&bairro%5B%5D=Palmeiras&bairro%5B%5D=Salgado+Filho"
            "&valor%5B0%5D=&valor%5B1%5D="
        ),
        "base": "https://sensaleimoveis.com.br",
        "link_pattern": r"/imovel/[^/?#]+/[^/?#]+",
    },
    {
        "key": "leo_batista",
        "name": "Léo Batista Imóveis",
        "url": (
            "https://www.leobatistaimoveis.com.br/imobiliaria/venda/belo-horizonte-mg/"
            "betania-cinquentenario-estrela-do-oriente/imoveis/4281/1"
        ),
        "base": "https://www.leobatistaimoveis.com.br",
        "link_pattern": r"^/\d+/imoveis/(venda|loca)",
    },
    {
        "key": "genesis",
        "name": "Genesis Imóveis",
        "url": (
            "https://www.genesisimoveis.com.br/venda/imoveis/belo-horizonte/"
            "cinquentenario--betania--cinquentenario--estrela-do-oriente--estrela-dalva--havai"
            "--marajo--palmeiras--parque-sao-jose--salgado-filho/0-quartos/0-suite-ou-mais/0-vaga/"
            "0-banheiro-ou-mais/todos-os-condominios?valorminimo=0&valormaximo=0&pagina=1"
        ),
        "base": "https://www.genesisimoveis.com.br",
        "link_pattern": r"/imovel/[^/?#]+/\d+(?:[/?#]|$)",
    },
    {
        "key": "vpr",
        "name": "VPR Imóveis",
        "url": (
            "https://www.vprimoveis.com.br/venda/belo-horizonte+cinquentenario+palmeiras"
            "+betania+estrela-do-oriente+havai+marajo+estrela-dalva+salgado-filho"
        ),
         "base": "https://www.vprimoveis.com.br",
        # O site mudou o formato: antes era só um número na raiz
        # (vprimoveis.com.br/8586), agora é um texto descritivo seguido do
        # número (vprimoveis.com.br/apartamento-.../8586).
        "link_pattern": r"^/[^/?#]+/\d+$",
    },
    {
        "key": "gade",
        "name": "Gade Imóveis",
        "url": (
            "https://gadeimoveis.com.br/busca?finalidade=Venda&cidade=Belo+Horizonte"
            "&bairro=Bet%C3%A2nia%2CCinquenten%C3%A1rio%2CEstrela+Dalva%2CEstrela+do+Oriente"
            "%2Chavai%2CHavai%2CHava%C3%AD%2CMaraj%C3%B3%2CNova+Suissa%2CNova+Su%C3%ADssa"
            "%2Cpalmeiras%2CPalmeiras%2CPALMEIRAS%2CParque+S%C3%A3o+Jose%2CParque+S%C3%A3o+Jos%C3%A9"
            "%2CSalgado+Filho"
        ),
        "base": "https://gadeimoveis.com.br",
        "link_pattern": r"/imovel/[^/?#]+-\d+(?:[/?#]|$)",
    },
    {
        "key": "malta",
        "name": "Malta Imóveis",
        "url": (
            "https://www.maltaimoveis.com.br/venda/imovel/belo-horizonte/"
            "cinquentenario+havai+marajo+nova-suica+nova-suissa+palmeiras+salgado-filho/?&pagina=1"
        ),
        "base": "https://www.maltaimoveis.com.br",
        "link_pattern": r"/imovel/[^/?#]+/\d+(?:[/?#]|$)",
    },
    {
        "key": "remax",
        "name": "Remax",
        "url": (
            "https://www.remax.com.br/listings?Country=Brasil&Province=9512&City=6578971"
            "&LocalZone=50095%2C50132%2C50133%2C50154%2C50208%2C50248%2C50280&CountryId=55"
            "&CityNM=6578971-Belo+Horizonte&ProvinceNM=9512-Minas+Gerais"
            "&LocalZoneNM=50095-Cinquenten%C3%A1rio%2C50132-Estrela+Dalva%2C50133-Estrela+do+Oriente"
            "%2C50154-Hava%C3%AD%2C50208-Maraj%C3%B3%2C50248-Palmeiras%2C50280-Salgado+Filho"
            "&ListingClass=-1&TransactionTypeUID=-1"
        ),
        "base": "https://www.remax.com.br",
        # A Remax é uma rede: cada corretor tem seu próprio subdomínio
        # (ex: mateusbomfim.remax.com.br), então em vez de exigir o domínio
        # EXATO, aceitamos qualquer subdomínio que termine em remax.com.br.
        "domain_suffix": "remax.com.br",
        "link_pattern": r"(^/pt-br/imoveis/.+/\d{5,}-?\d*$)|(^/\d{5,}-\d+$)",
    },
    {
        "key": "net_imoveis",
        "name": "Net Imóveis",
        "url": (
            "https://www.netimoveis.com/venda/minas-gerais/belo-horizonte/oeste/havai"
            "?transacao=venda&localizacao=BR-MG-belo-horizonte-havai-oeste-%2C"
            "BR-MG-belo-horizonte-palmeiras-oeste-%2CBR-MG-belo-horizonte-estrela-dalva-oeste-%2C"
            "BR-MG-belo-horizonte-betania-oeste-%2CBR-MG-belo-horizonte-cinquentenario-oeste-"
            "&pagina=1"
        ),
        "base": "https://www.netimoveis.com",
        # Site experimental: o link de detalhe é montado via um template
        # (ex.: netimoveis.com/apartamento-venda-havai-bh-1185740) que
        # termina num código numérico. Pode precisar de ajuste depois de
        # ver o resultado real.
        "link_pattern": r"^/[a-z0-9\-]+-\d{5,}$",
    },
]

MAX_PAGES = 20            # trava de segurança para não entrar em loop infinito por site
WAIT_MS = 4000             # tempo extra de espera após o carregamento da página
SCROLL_TRIES = 4           # tentativas de "rolar para carregar mais" por página
NAV_TIMEOUT_MS = 45000

DATA_FILE = Path(__file__).parent / "data" / "seen.json"
OUTPUT_HTML = Path(__file__).parent / "docs" / "index.html"

BR_TZ = timezone(timedelta(hours=-3))


def eh_link_do_proprio_site(href_abs, base_url, domain_suffix=None):
    """
    Só aceita links http(s) que apontem para o MESMO domínio do site sendo
    monitorado. Isso descarta de cara botões de compartilhar (WhatsApp,
    Facebook, LinkedIn, Twitter), links "javascript:...", "mailto:", etc.

    Se domain_suffix for informado (ex.: "remax.com.br"), aceita qualquer
    subdomínio que termine nele — útil para redes onde cada corretor tem
    seu próprio subdomínio.
    """
    p = urlparse(href_abs)
    if p.scheme not in ("http", "https"):
        return False
    href_netloc = p.netloc.lower()
    if domain_suffix:
        return href_netloc == domain_suffix.lower() or href_netloc.endswith("." + domain_suffix.lower())
    base_netloc = urlparse(base_url).netloc.lower().replace("www.", "")
    return href_netloc.replace("www.", "") == base_netloc


def coletar_links_da_pagina(page, base_url, link_pattern, domain_suffix=None):
    """Extrai todos os links de imóveis visíveis na página atual."""
    anchors = page.eval_on_selector_all(
        "a[href]",
        """els => els.map(el => ({
            href: el.getAttribute('href'),
            text: (el.innerText || el.textContent || '').trim()
        }))""",
    )
    regex = re.compile(link_pattern)
    resultados = {}
    for a in anchors:
        href = a.get("href") or ""
        if not href:
            continue
        href_abs = urljoin(base_url, href)
        if not eh_link_do_proprio_site(href_abs, base_url, domain_suffix):
            continue
        caminho = urlparse(href_abs).path  # só o caminho, sem domínio nem query string
        if not regex.search(caminho):
            continue
        titulo = a.get("text") or ""
        if href_abs not in resultados or len(titulo) > len(resultados[href_abs]):
            resultados[href_abs] = titulo
    return resultados


def tentar_ir_para_proxima_pagina(page, pagina_atual):
    """
    Tenta descobrir e navegar para a próxima página de resultados.
    Retorna True se conseguiu navegar, False se não achou como.
    """
    proxima_num = str(pagina_atual + 1)

    tentativas_js = f"""
    () => {{
        // 1) link com rel="next"
        const relNext = document.querySelector('a[rel="next"]');
        if (relNext && relNext.href) return relNext.href;

        // 2) link numerado com o próximo número da página
        const links = Array.from(document.querySelectorAll('a[href]'));
        const porNumero = links.find(a => (a.innerText || '').trim() === '{proxima_num}');
        if (porNumero && porNumero.href) return porNumero.href;

        // 3) link/bot\u00e3o com texto tipo "Pr\u00f3xima", "Seguinte", ">", "»"
        const textoProximo = links.find(a => {{
            const t = (a.innerText || '').trim().toLowerCase();
            return t === '>' || t === '»' || t.includes('próxima') || t.includes('proxima')
                || t.includes('seguinte') || t.includes('next') || t.includes('carregar mais')
                || t.includes('ver mais');
        }});
        if (textoProximo && textoProximo.href) return textoProximo.href;

        return null;
    }}
    """
    try:
        href = page.evaluate(tentativas_js)
    except Exception:
        href = None

     if href:
        try:
            page.goto(href, wait_until="networkidle")
            return True
        except Exception:
            return False

    # 4) Alguns sites (ex: Gade Imóveis) paginam com <button> em vez de
    # <a href> — não há link pra "ir", precisa clicar mesmo, e o conteúdo
    # atualiza via JavaScript/AJAX (sem trocar de URL).
    try:
        botao_numero = page.locator(f"button:text-is('{proxima_num}')").first
        if botao_numero.is_visible(timeout=1500):
            botao_numero.click(timeout=3000)
            page.wait_for_timeout(2000)
            return True
    except Exception:
        pass

    try:
        botao_proximo = page.locator(
            "button:has-text('Próxima'), button:has-text('próxima'), "
            "button:has-text('Seguinte'), button:has-text('seguinte'), "
            "button:has-text('Carregar mais'), button:has-text('carregar mais'), "
            "button:has-text('Ver mais'), button:has-text('ver mais')"
        ).first
        if botao_proximo.is_visible(timeout=1500):
            botao_proximo.click(timeout=3000)
            page.wait_for_timeout(2000)
            return True
    except Exception:
        pass

    return False


def tentar_carregar_mais_via_scroll(page, contagem_antes):
    """
    Para sites com scroll infinito ou botão 'carregar mais' via JS (sem link
    navegável): rola a página algumas vezes e verifica se mais itens
    apareceram.
    """
    for _ in range(SCROLL_TRIES):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1800)
        # tenta clicar em algo como "carregar mais" se existir um botão (não link)
        try:
            botao = page.locator(
                "button:has-text('carregar mais'), button:has-text('ver mais'), "
                "button:has-text('mais imóveis')"
            ).first
            if botao and botao.is_visible():
                botao.click(timeout=2000)
                page.wait_for_timeout(1500)
        except Exception:
            pass
    return True


def tentar_fechar_banner_cookies(page):
    """
    Alguns sites mostram um banner de cookies/LGPD que fica por cima do
    conteúdo. Tenta clicar em botões comuns de aceitar, se existir algum.
    Não é um problema se não encontrar nada.
    """
    try:
        botao = page.locator(
            "button:has-text('aceit'), button:has-text('Aceit'), "
            "button:has-text('concord'), button:has-text('Concord'), "
            "button:has-text('entendi'), button:has-text('Entendi'), "
            "button:has-text('OK'), a:has-text('aceit'), a:has-text('Aceit')"
        ).first
        if botao and botao.is_visible():
            botao.click(timeout=2000)
            page.wait_for_timeout(800)
    except Exception:
        pass


def coletar_site(site):
    encontrados_total = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            locale="pt-BR",
            viewport={"width": 1366, "height": 800},
            timezone_id="America/Sao_Paulo",
        )
        # Disfarça sinais comuns de "navegador automatizado" que alguns sites
        # usam para bloquear ou não renderizar conteúdo para robôs.
        context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            window.chrome = { runtime: {} };
            """
        )
        page = context.new_page()
        page.set_default_navigation_timeout(NAV_TIMEOUT_MS)

        print(f"Abrindo: {site['url']}")
        try:
            page.goto(site["url"], wait_until="networkidle")
        except Exception as e:
            print(f"  Falha ao carregar a página inicial: {e}")
            browser.close()
            return encontrados_total

        page.wait_for_timeout(WAIT_MS)
        tentar_fechar_banner_cookies(page)

        # Espera aparecer algo como "28 Imóveis" na tela — mais confiável do
        # que só esperar a rede ficar quieta, principalmente em sites que
        # carregam a contagem/lista de forma assíncrona (Angular, Vue etc).
        try:
            page.wait_for_function(
                "() => /\\d+\\s*im[oó]ve/i.test(document.body.innerText)",
                timeout=12000,
            )
        except Exception:
            pass

        links_pagina_anterior = set()
        for numero_pagina in range(1, MAX_PAGES + 1):
            try:
                page.wait_for_selector("a[href]", timeout=8000)
            except Exception:
                pass

            encontrados = coletar_links_da_pagina(page, site["base"], site["link_pattern"], site.get("domain_suffix"))

            # Se a primeira página veio vazia, o app pode não ter renderizado a
            # tempo. Tenta rolar e, em último caso, recarregar a página uma vez.
            if numero_pagina == 1 and not encontrados:
                tentar_carregar_mais_via_scroll(page, 0)
                encontrados = coletar_links_da_pagina(page, site["base"], site["link_pattern"], site.get("domain_suffix"))
                if not encontrados:
                    print("  Nada encontrado de primeira, tentando recarregar a página...")
                    try:
                        page.reload(wait_until="networkidle")
                        page.wait_for_timeout(WAIT_MS)
                        tentar_fechar_banner_cookies(page)
                        encontrados = coletar_links_da_pagina(page, site["base"], site["link_pattern"], site.get("domain_suffix"))
                    except Exception as e:
                        print(f"  Falha ao recarregar: {e}")

            print(f"  Página {numero_pagina}: {len(encontrados)} imóveis encontrados")

            novos_nesta_pagina = set(encontrados.keys()) - links_pagina_anterior
            if not encontrados or (numero_pagina > 1 and not novos_nesta_pagina):
                # tenta rolar (scroll infinito) antes de desistir de vez
                tentar_carregar_mais_via_scroll(page, len(encontrados))
                encontrados_apos_scroll = coletar_links_da_pagina(
                    page, site["base"], site["link_pattern"], site.get("domain_suffix")
                )
                if len(encontrados_apos_scroll) > len(encontrados):
                    encontrados = encontrados_apos_scroll
                else:
                    encontrados_total.update(encontrados)
                    print("  Sem novidades nesta página. Parando por aqui.")
                    break

            links_pagina_anterior = set(encontrados.keys())
            encontrados_total.update(encontrados)

            conseguiu_navegar = tentar_ir_para_proxima_pagina(page, numero_pagina)
            if not conseguiu_navegar:
                print("  Não encontrei como ir para a próxima página. Parando por aqui.")
                break

            page.wait_for_timeout(WAIT_MS)
            time.sleep(1.5)  # pausa educada entre as páginas

        if not encontrados_total:
            # Nada encontrado em nenhuma página: salva uma captura de tela
            # para dar pra diagnosticar visualmente o que o robô "viu".
            try:
                debug_dir = Path(__file__).parent / "debug"
                debug_dir.mkdir(exist_ok=True)
                caminho_print = debug_dir / f"{site['key']}.png"
                page.screenshot(path=str(caminho_print), full_page=True)
                print(f"  Nenhum imóvel encontrado. Print salvo em: {caminho_print}")
            except Exception as e:
                print(f"  Não consegui salvar o print de diagnóstico: {e}")

        browser.close()
    return encontrados_total


def carregar_estado_anterior():
    if not DATA_FILE.exists():
        return {}
    try:
        estado = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    # Migração automática: versões antigas deste script guardavam o estado
    # no formato {href: {...}} (uma imobiliária só). Se detectarmos esse
    # formato antigo, movemos tudo para dentro da primeira imobiliária da
    # lista SITES, para não perder o histórico já coletado.
    if estado and all(
        isinstance(v, dict) and "titulo" in v for v in estado.values()
    ) and not any(k in estado for k in [s["key"] for s in SITES]):
        primeiro_site = SITES[0]["key"]
        return {primeiro_site: estado}

    return estado


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


def gerar_html(estado_por_site, novos_por_site, ultima_verificacao):
    abas_botoes = []
    abas_conteudo = []

    total_geral = sum(len(v) for v in estado_por_site.values())
    total_novos_geral = sum(len(v) for v in novos_por_site.values())

    site_por_key = {s["key"]: s for s in SITES}

    for indice, site in enumerate(SITES):
        key = site["key"]
        nome = site["name"]
        estado = estado_por_site.get(key, {})
        novos_hrefs = novos_por_site.get(key, set())

        itens = list(estado.items())
        itens.sort(key=lambda kv: (kv[0] not in novos_hrefs))

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

        qtd_novos = len(novos_hrefs)
        badge_aba = f'<span class="badge-aba">{qtd_novos}</span>' if qtd_novos else ""
        ativa = "active" if indice == 0 else ""

        abas_botoes.append(
            f'<button class="tab-btn {ativa}" data-tab="{key}">{nome}{badge_aba}</button>'
        )
        abas_conteudo.append(f"""
        <div class="tab-content {ativa}" id="tab-{key}">
          <div class="resumo">
            <div class="card"><div class="num">{len(estado)}</div><div class="label">imóveis monitorados</div></div>
            <div class="card"><div class="num">{qtd_novos}</div><div class="label">novos agora</div></div>
          </div>
          <div class="lista">
            {"".join(linhas_html) if linhas_html else "<p>Nenhum imóvel encontrado ainda nesta imobiliária.</p>"}
          </div>
        </div>""")

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Monitor de Imóveis</title>
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
  .resumo-geral {{
    max-width: 900px;
    margin: 20px auto 0;
    padding: 0 20px;
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
  }}
  .resumo-geral .card, .resumo .card {{
    background: white;
    border-radius: 10px;
    padding: 14px 18px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    flex: 1;
    min-width: 140px;
  }}
  .resumo {{
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 18px;
  }}
  .card .num {{
    font-size: 26px;
    font-weight: 700;
  }}
  .card .label {{
    font-size: 13px;
    color: #666;
  }}
  .tabs {{
    max-width: 900px;
    margin: 24px auto 0;
    padding: 0 20px;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }}
  .tab-btn {{
    background: white;
    border: 1px solid #ddd;
    border-radius: 999px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    color: #444;
    position: relative;
  }}
  .tab-btn.active {{
    background: #1f2d3d;
    color: white;
    border-color: #1f2d3d;
  }}
  .badge-aba {{
    display: inline-block;
    background: #2e9e44;
    color: white;
    font-size: 10px;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: 999px;
    margin-left: 6px;
  }}
  .tab-content {{
    display: none;
    max-width: 900px;
    margin: 20px auto;
    padding: 0 20px;
  }}
  .tab-content.active {{
    display: block;
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
  <h1>Monitor de Imóveis</h1>
  <p>Última verificação: {ultima_verificacao}</p>
</header>

<div class="resumo-geral">
  <div class="card"><div class="num">{total_geral}</div><div class="label">imóveis monitorados no total</div></div>
  <div class="card"><div class="num">{total_novos_geral}</div><div class="label">novos em todas as imobiliárias</div></div>
</div>

<div class="tabs">
  {"".join(abas_botoes)}
</div>

{"".join(abas_conteudo)}

<script>
  document.querySelectorAll('.tab-btn').forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      var key = btn.getAttribute('data-tab');
      document.querySelectorAll('.tab-btn').forEach(function(b) {{ b.classList.remove('active'); }});
      document.querySelectorAll('.tab-content').forEach(function(c) {{ c.classList.remove('active'); }});
      btn.classList.add('active');
      document.getElementById('tab-' + key).classList.add('active');
    }});
  }});
</script>

</body>
</html>
"""
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html, encoding="utf-8")


def main():
    estado_anterior = carregar_estado_anterior()
    agora = datetime.now(BR_TZ).strftime("%d/%m/%Y %H:%M")

    estado_novo = {}
    novos_por_site = {}

    for site in SITES:
        key = site["key"]
        print(f"\n=== {site['name']} ===")
        try:
            encontrados_agora = coletar_site(site)
        except Exception as e:
            print(f"  ERRO ao coletar {site['name']}: {e}")
            encontrados_agora = {}

        estado_site_anterior = estado_anterior.get(key, {})
        estado_site_novo = dict(estado_site_anterior)
        novos_hrefs = set()

        for href, titulo_bruto in encontrados_agora.items():
            titulo = limpar_titulo(titulo_bruto, href)
            if href not in estado_site_novo:
                novos_hrefs.add(href)
                estado_site_novo[href] = {"titulo": titulo, "primeira_vez": agora}
            else:
                estado_site_novo[href]["titulo"] = titulo or estado_site_novo[href].get("titulo", "")

        print(f"  Total encontrado: {len(encontrados_agora)} | Novos: {len(novos_hrefs)}")
        for href in novos_hrefs:
            print(f"    NOVO: {href}")

        estado_novo[key] = estado_site_novo
        novos_por_site[key] = novos_hrefs

    salvar_estado(estado_novo)
    gerar_html(estado_novo, novos_por_site, agora)
    print(f"\nPainel gerado em: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
