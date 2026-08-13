# Monitor de Imóveis — Paulo Tavares Imóveis

Este projeto verifica **uma vez por dia**, sozinho, se apareceram imóveis
novos nos bairros que você escolheu (Betânia, Cinquentenário, Marajó,
Palmeiras, Salgado Filho, Parque São José, Havaí) e gera uma página com os
links, destacando os novos.

Você **não precisa saber programar**. Siga os passos abaixo, é só copiar,
colar e clicar. Leva uns 10 minutos, só da primeira vez.

---

## Passo 1 — Criar uma conta no GitHub (gratuito)

1. Acesse https://github.com/signup
2. Crie sua conta (e-mail, senha, nome de usuário).

## Passo 2 — Criar um repositório novo

1. Clique no botão **"+"** no canto superior direito → **New repository**.
2. Dê um nome, por exemplo `monitor-imoveis`.
3. Deixe marcado como **Public**.
4. Clique em **Create repository**.

## Passo 3 — Subir os arquivos deste projeto

1. Na página do repositório recém-criado, clique no link
   **"uploading an existing file"**.
2. Arraste **todos os arquivos e pastas** que te enviei (mantendo a
   estrutura de pastas: `scraper.py`, `requirements.txt`, `data/seen.json`,
   `docs/index.html`, `.github/workflows/check.yml`).
   - Dica: se o GitHub não deixar arrastar pastas direto, você pode arrastar
     o arquivo `.zip` inteiro que eu te enviei — o GitHub também aceita, ou
     você pode primeiro descompactar no seu computador e arrastar tudo junto.
3. Escreva qualquer mensagem (ex: "primeira versão") e clique em
   **Commit changes**.

## Passo 4 — Ativar o "painel" (GitHub Pages)

1. No repositório, vá em **Settings** (aba no topo).
2. No menu da esquerda, clique em **Pages**.
3. Em **Source**, escolha **Deploy from a branch**.
4. Em **Branch**, escolha `main` e a pasta `/docs`. Clique em **Save**.
5. Espere 1 ou 2 minutinhos. Vai aparecer um link tipo:
   `https://seu-usuario.github.io/monitor-imoveis/`
   **Esse é o painel que você vai acessar sempre que quiser ver os imóveis.**

## Passo 5 — Ativar a verificação automática diária

1. Vá na aba **Actions** do repositório.
2. Se aparecer um aviso perguntando se você quer habilitar as Actions,
   clique em **"I understand my workflows, go ahead and enable them"**.
3. Clique no workflow **"Monitor de Imóveis"** na lista à esquerda.
4. Clique em **Run workflow** (botão à direita) para rodar a primeira
   verificação agora mesmo, sem esperar o dia seguinte.
5. Aguarde alguns minutos (o robô abre o site, navega pelas páginas de
   resultado, etc.) até o círculo ficar verde ✅.
6. Atualize o link do Passo 4 — os imóveis já devem aparecer lá, todos
   marcados como **NOVO** na primeira vez.

Pronto! A partir de agora, todo dia às 08h (horário de Brasília), o robô
roda sozinho e atualiza o painel. Você só precisa abrir o link salvo nos
favoritos do celular ou computador.

---

## Perguntas comuns

**Preciso deixar o computador ligado?**
Não. Isso roda nos servidores do GitHub, de graça, mesmo com seu computador
desligado.

**Quero mudar os bairros ou os filtros de preço/quartos no futuro.**
Vá no site da Paulo Tavares, aplique os filtros que quiser, copie o link
completo da barra de endereço, abra o arquivo `scraper.py` no GitHub (ícone
de lápis para editar), e troque o conteúdo da variável `SEARCH_URL` pelo
novo link — só trocando a parte final `pagina=1` por `pagina={page}` (isso
é necessário para o robô conseguir passar as páginas sozinho).

**O robô "esquece" um imóvel que saiu do site?**
Não — ele mantém o histórico de tudo que já viu, então mesmo que um imóvel
seja vendido/retirado, ele continua listado (só não aparece mais como
"novo"). Se quiser começar do zero, basta apagar o conteúdo do arquivo
`data/seen.json` e deixar só `{}`.

**Posso rodar isso no meu próprio computador em vez do GitHub?**
Sim. Instale Python, rode `pip install -r requirements.txt`, depois
`playwright install chromium`, e depois `python scraper.py`. Mas aí você
precisaria lembrar de rodar isso todo dia manualmente — por isso a versão
com GitHub Actions é mais prática.
