# Atualização avisada e distribuição — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O app avisa na abertura quando existe versão nova, atualiza quando a pessoa clica sem nunca tocar nos dados dela, e o Bruno publica uma versão com um comando só.

**Architecture:** Um módulo `versao.py` guarda a versão instalada e resolve a URL do manifesto; `atualizador.py` concentra checagem, download, verificação de hash, extração e a troca de arquivos por um script auxiliar externo em PowerShell (o app não consegue sobrescrever o próprio `.exe` em execução). O `app.py` dispara a checagem numa thread no startup e injeta o aviso no template via context processor. A publicação é um script que compila, zipa, calcula o hash, gera o `version.json` e faz `firebase deploy`.

**Tech Stack:** Python 3.14 + Flask 3.1 (já no projeto), `urllib` e `zipfile` da stdlib (sem dependência nova), PyInstaller para o pacote, PowerShell para o auxiliar de troca, Firebase Hosting para a distribuição.

**Spec:** `docs/superpowers/specs/2026-10-22-atualizacao-automatica-design.md`

## Global Constraints

- A atualização só pode tocar nestes itens: `Organizador Financeiro.exe`, `OrganizadorFinanceiro.exe`, `_internal/`, `LEIA-ME.txt`. Lista explícita, nunca substituição de pasta inteira.
- `financas.db` jamais é modificado ou removido. Só é **copiado** para `financas.db.bak-<versao>` antes da troca.
- Qualquer falha de rede, DNS, timeout ou manifesto inválido é silenciosa: sem banner, sem erro na tela, sem atraso na abertura.
- Nenhuma dependência nova no `requirements.txt`. Só stdlib.
- Versão em **uma** fonte de verdade: `versao.py`. O build e o `version.json` leem dela.
- Comparação de versão é semver numérico por campo (`maior.menor.correção`), nunca comparação de string.
- A troca descarta a versão antiga **somente** depois que a nova responder em `localhost:5050`.
- O gatilho de atualização só é aceito de `127.0.0.1`/`::1`. O servidor escuta em `0.0.0.0:5050` e o LEIA-ME ensina acesso por celular.
- Hospedagem: Firebase Hosting, conta pessoal `brunoacarvalho.contato@gmail.com` (CLI já logado nela).
- Testes seguem o padrão do projeto: `testar.py` com os helpers `check`/`check_eq`. Não há pytest instalado.
- Textos de interface em português, no tom do app.

## Review Focus

Classes de entrada que a spec implica e que precisam de teste próprio:

1. **Manifesto inacessível** (sem internet, DNS falhando, timeout, 404, 500) — o app abre no tempo de sempre, sem banner e sem erro. Coberto na Task 3.
2. **`version.json` malformado** (JSON truncado, campo faltando, versão não numérica, tipo errado) — tratado como "sem atualização", nunca exceção. Coberto na Task 3.
3. **Download corrompido ou parcial** (hash não confere, disco cheio, conexão cortada) — aborta antes de encostar na instalação. Coberto na Task 4.
4. **Gatilho vindo de outra máquina na rede** (celular no mesmo WiFi) — recusado com 403. Coberto na Task 3.
5. **Versão publicada igual ou menor que a instalada** (publicação errada, rollback no servidor) — sem banner. Coberto na Task 3.

---

### Task 1: Versão e comparação

**Files:**
- Create: `versao.py`
- Create: `testar_atualizacao.py`

**Interfaces:**
- Consumes: nada.
- Produces: `VERSAO: str`; `comparar_versoes(a: str, b: str) -> int` (−1 se `a<b`, 0 se igual, 1 se `a>b`); `manifest_url() -> str`; `ITENS_DO_PROGRAMA: tuple[str, ...]`.

- [ ] **Step 1: Write the failing tests**

```python
# testar_atualizacao.py
import versao

check_eq('versao igual',        versao.comparar_versoes('1.0.0', '1.0.0'),   0)
check_eq('menor que',           versao.comparar_versoes('1.0.0', '1.0.1'),  -1)
check_eq('maior que',           versao.comparar_versoes('1.2.0', '1.1.9'),   1)
check_eq('10 maior que 9',      versao.comparar_versoes('1.10.0', '1.9.0'),  1)   # string compararia errado
check_eq('campos a menos',      versao.comparar_versoes('1.1', '1.1.0'),     0)
check_eq('lixo vira 0',         versao.comparar_versoes('abc', '1.0.0'),    -1)
check_eq('vazio vira 0',        versao.comparar_versoes('', '0.0.0'),        0)
check_eq('itens do programa',   len(versao.ITENS_DO_PROGRAMA),               4)
check_eq('db fora da lista',    any('financas' in i for i in versao.ITENS_DO_PROGRAMA), False)
```

Reaproveite os helpers `check_eq` no estilo do `testar.py` (lista `results` + impressão final).

- [ ] **Step 2: Run to verify it fails**

Run: `venv\Scripts\python.exe testar_atualizacao.py`
Expected: FAIL com `ModuleNotFoundError: No module named 'versao'`

- [ ] **Step 3: Implement `versao.py`**

`VERSAO = '1.0.0'`. `MANIFEST_URL_PADRAO` fica como string vazia por enquanto — a Task 6 preenche com a URL real depois de criar o projeto Firebase.

`comparar_versoes` divide por `.`, converte cada campo com fallback para `0` em qualquer valor não numérico, iguala o comprimento das listas com zeros e compara campo a campo. Nunca levanta exceção.

`manifest_url()` resolve nesta ordem: variável de ambiente `ORGFIN_MANIFEST_URL`, depois um arquivo `manifest.txt` ao lado do executável (use o `DATA_DIR` do `app.py` como referência de "ao lado do executável"), depois `MANIFEST_URL_PADRAO`.

`ITENS_DO_PROGRAMA = ('Organizador Financeiro.exe', 'OrganizadorFinanceiro.exe', '_internal', 'LEIA-ME.txt')`.

- [ ] **Step 4: Run to verify it passes**

Run: `venv\Scripts\python.exe testar_atualizacao.py`
Expected: PASS em todos

- [ ] **Step 5: Commit**

```bash
git add versao.py testar_atualizacao.py
git commit -m "feat: fonte unica de versao e comparacao semver"
```

---

### Task 2: Assets offline

**Files:**
- Create: `static/vendor/` (bootstrap.min.css, bootstrap.bundle.min.js, bootstrap-icons.min.css, `fonts/`, chart.umd.min.js)
- Create: `baixar_vendor.py`
- Modify: `templates/base.html:7-8,135-136`

**Interfaces:**
- Consumes: nada.
- Produces: nenhuma API; o efeito é o `base.html` sem referência externa.

- [ ] **Step 1: Write `baixar_vendor.py`**

Script de manutenção que baixa para `static/vendor/`: Bootstrap 5.3.2 (CSS e `bundle.min.js`), Bootstrap Icons 1.11.3 (CSS) e Chart.js 4.4.0 (`chart.umd.min.js`), nas mesmas versões que o `base.html` usa hoje.

O CSS do Bootstrap Icons referencia `./fonts/bootstrap-icons.woff2` e `.woff` por caminho relativo: baixe as duas fontes para `static/vendor/fonts/` para os ícones não sumirem. Confira isso lendo o `url(...)` do CSS baixado, não presumindo o nome.

- [ ] **Step 2: Run it and verify the files landed**

Run: `venv\Scripts\python.exe baixar_vendor.py`
Expected: 5 arquivos em `static/vendor/` (3 na raiz + 2 fontes), nenhum com 0 byte.

- [ ] **Step 3: Point `base.html` at the local copies**

Troque as 4 tags de CDN por `url_for('static', filename='vendor/...')`, mantendo a ordem atual (CSS no `<head>`, JS antes do `script.js`).

- [ ] **Step 4: Verify no external reference remains**

Run: `grep -rn "cdn.jsdelivr.net\|cdnjs\|googleapis" templates/ static/*.js static/*.css`
Expected: nenhuma linha.

- [ ] **Step 5: Verify the app renders offline**

Suba o servidor, abra `/` e `/planner` no navegador e confirme que o CSS aplicou, que os ícones `bi-*` aparecem e que o gráfico de categorias desenha — com as requisições a domínios externos bloqueadas.
Expected: visual idêntico ao de antes, zero requisição externa, zero erro de console.

- [ ] **Step 6: Commit**

```bash
git add static/vendor baixar_vendor.py templates/base.html
git commit -m "feat: embute bootstrap, icones e chart.js para funcionar offline"
```

---

### Task 3: Checagem e aviso na interface

**Files:**
- Create: `atualizador.py`
- Modify: `app.py` (imports, startup, context processor, rota)
- Modify: `templates/base.html:119-130` (faixa de aviso)
- Modify: `static/script.js:20-26` (excluir o aviso do auto-dismiss)
- Modify: `testar_atualizacao.py`

**Interfaces:**
- Consumes: `versao.VERSAO`, `versao.comparar_versoes`, `versao.manifest_url` (Task 1).
- Produces: `atualizador.checar_atualizacao(url: str, timeout: float = 3.0) -> dict | None` — devolve o manifesto quando a versão publicada é maior que a instalada, senão `None`; **nunca levanta**. `app.py` passa a expor `atualizacao` no contexto dos templates e a função `_e_local(req) -> bool`.

- [ ] **Step 1: Write the failing tests**

Suba um `http.server` numa thread servindo manifestos de teste e aponte `checar_atualizacao` para ele.

```python
check_eq('versao nova avisa',      checar('{"versao":"9.9.9","url":"x","sha256":"y"}')  is not None, True)
check_eq('versao igual nao avisa', checar('{"versao":"1.0.0","url":"x","sha256":"y"}')  is None,     True)
check_eq('versao menor nao avisa', checar('{"versao":"0.0.1","url":"x","sha256":"y"}')  is None,     True)
check_eq('json truncado',          checar('{"versao":"9.9')                            is None,     True)
check_eq('sem campo versao',       checar('{"url":"x"}')                               is None,     True)
check_eq('versao nao numerica',    checar('{"versao":"banana","url":"x"}')             is None,     True)
check_eq('sem url nao avisa',      checar('{"versao":"9.9.9"}')                        is None,     True)
check_eq('http 404',               checar_status(404)                                  is None,     True)
check_eq('host inexistente',       checar_url('http://127.0.0.1:1/version.json')       is None,     True)
check_eq('url vazia',              checar_url('')                                      is None,     True)
```

E, para o gating de origem, com o `test_client` do Flask. Atenção: `request.remote_addr` não é afetado por header — tem que vir do ambiente WSGI, e o helper `check` do `testar.py` não aceita isso, então use o cliente diretamente:

```python
c = flask_app.app.test_client()
de_fora = c.post('/atualizar', environ_base={'REMOTE_ADDR': '192.168.0.50'})
de_casa = c.post('/atualizar', environ_base={'REMOTE_ADDR': '127.0.0.1'})
check_eq('celular na rede recusado', de_fora.status_code, 403)
check_eq('localhost aceito',         de_casa.status_code != 403, True)
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv\Scripts\python.exe testar_atualizacao.py`
Expected: FAIL com `ImportError` / `AttributeError` em `checar_atualizacao`

- [ ] **Step 3: Implement `checar_atualizacao` in `atualizador.py`**

`urllib.request.urlopen` com o timeout recebido, `json.loads` da resposta, e um `try/except Exception` envolvendo tudo que devolve `None` — a captura ampla é deliberada: nenhuma falha de rede pode chegar à interface. Exige os campos `versao`, `url` e `sha256` presentes e não vazios; só devolve o manifesto se `comparar_versoes(manifesto['versao'], VERSAO) == 1`.

- [ ] **Step 4: Wire the startup check into `app.py`**

Variável de módulo `_atualizacao = None`. No bloco `if __name__ == '__main__'`, antes do `app.run`, dispare uma `threading.Thread(daemon=True)` que chama `checar_atualizacao(versao.manifest_url())` e guarda o resultado em `_atualizacao`. Daemon e em thread para que a abertura do app não espere a rede.

Um `@app.context_processor` injeta `atualizacao=_atualizacao`.

- [ ] **Step 5: Implement `_e_local(req)` and the `/atualizar` route in `app.py`**

`_e_local` devolve `True` só quando `request.remote_addr` está em `('127.0.0.1', '::1')`. A rota `POST /atualizar` responde 403 quando `_e_local` for falso. O corpo da atualização entra na Task 5; por ora a rota só valida a origem e devolve 200.

- [ ] **Step 6: Add the banner to `base.html`**

Acima do bloco de `get_flashed_messages`, dentro do mesmo container. Renderiza só `{% if atualizacao %}`. Use a classe `alerta-atualizacao` **sem** `fade show` juntos, para não cair no auto-dismiss (ver Step 7). Mostra `atualizacao.versao`, o texto de `atualizacao.notas` quando houver, e um botão que faz POST em `/atualizar`. Botão de fechar que some com a faixa só naquela sessão.

- [ ] **Step 7: Exclude the banner from auto-dismiss in `script.js`**

O seletor atual é `.alert.fade.show`. Restrinja para não pegar `.alerta-atualizacao` — o aviso de atualização não pode sumir sozinho em 4 segundos.

- [ ] **Step 8: Run all tests**

Run: `venv\Scripts\python.exe testar_atualizacao.py && venv\Scripts\python.exe testar.py`
Expected: PASS nos dois; o `testar.py` continua em 58/58.

- [ ] **Step 9: Verify the banner by hand**

Com `ORGFIN_MANIFEST_URL` apontando para um manifesto local de versão `9.9.9`, abra o app: a faixa aparece e **não** some sozinha. Com a variável apontando para versão igual, não aparece nada. Com a variável apontando para um host morto, o app abre no mesmo tempo e sem aviso.

- [ ] **Step 10: Commit**

```bash
git add atualizador.py app.py templates/base.html static/script.js testar_atualizacao.py
git commit -m "feat: checagem de versao em segundo plano e aviso na interface"
```

---

### Task 4: Download, hash e extração

**Files:**
- Modify: `atualizador.py`
- Modify: `testar_atualizacao.py`

**Interfaces:**
- Consumes: `checar_atualizacao` (Task 3).
- Produces: `baixar_pacote(manifesto: dict, destino: Path) -> Path`; `conferir_hash(caminho: Path, sha256_esperado: str) -> bool`; `extrair_pacote(zip_path: Path, destino: Path) -> Path` (devolve a pasta que contém os itens do programa).

- [ ] **Step 1: Write the failing tests**

```python
check_eq('hash confere',        conferir_hash(zip_ok,  sha_real),            True)
check_eq('hash nao confere',    conferir_hash(zip_ok,  'f'*64),             False)
check_eq('hash de arquivo cortado', conferir_hash(zip_truncado, sha_real),  False)
check_eq('hash insensivel a caixa', conferir_hash(zip_ok, sha_real.upper()), True)
check_eq('extrai itens',        sorted(p.name for p in extraido.iterdir()) == sorted(ITENS_DO_PROGRAMA), True)
check_eq('zip-slip recusado',   extrair_recusa('../../fora.txt'),            True)
check_eq('zip absoluto recusado', extrair_recusa('C:/Windows/fora.txt'),     True)
check_eq('zip sem os itens recusado', extrair_recusa_conteudo(['leia.txt']), True)
```

`extrair_recusa` monta um ZIP com a entrada maliciosa e espera `ValueError`.

- [ ] **Step 2: Run to verify it fails**

Run: `venv\Scripts\python.exe testar_atualizacao.py`
Expected: FAIL com `AttributeError` em `conferir_hash`

- [ ] **Step 3: Implement the three functions**

`conferir_hash` lê em blocos com `hashlib.sha256` e compara em minúsculas.

`baixar_pacote` grava em arquivo temporário com sufixo `.parcial` e só renomeia para o nome final ao terminar, para que um download cortado nunca pareça completo.

`extrair_pacote` **valida cada entrada antes de escrever**: resolve o caminho de destino e rejeita com `ValueError` qualquer entrada que caia fora da pasta de destino ou que seja absoluta. Depois de extrair, confirma que os 4 itens de `ITENS_DO_PROGRAMA` existem e levanta `ValueError` se faltar algum — um ZIP válido mas com estrutura inesperada não pode virar uma troca de arquivos.

- [ ] **Step 4: Run to verify it passes**

Run: `venv\Scripts\python.exe testar_atualizacao.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add atualizador.py testar_atualizacao.py
git commit -m "feat: download verificado por hash e extracao protegida contra zip-slip"
```

---

### Task 5: Troca dos arquivos com reversão

**Files:**
- Modify: `atualizador.py`
- Modify: `app.py` (corpo da rota `/atualizar`)
- Create: `templates/atualizando.html`
- Modify: `testar_atualizacao.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: `copiar_banco(pasta_app: Path, versao_atual: str) -> Path | None`; `gerar_script_troca(pid: int, pasta_app: Path, pasta_nova: Path) -> Path`; `aplicar_atualizacao(manifesto: dict) -> None`.

- [ ] **Step 1: Write the failing tests**

Testes de filesystem, sem processo real:

```python
check_eq('copia o banco',          copiar_banco(pasta, '1.0.0').name, 'financas.db.bak-1.0.0')
check_eq('original intacto',       hash_antes == hash_depois,          True)
check_eq('sem banco devolve None', copiar_banco(pasta_vazia, '1.0.0') is None, True)
check_eq('nao sobrescreve backup', copiar_banco(pasta, '1.0.0').name.endswith('.bak-1.0.0'), True)
check_eq('script cita o pid',      str(pid) in script.read_text(encoding='utf-8'), True)
check_eq('script so toca a lista', all(i in texto for i in ITENS_DO_PROGRAMA), True)
check_eq('script nao cita o banco','financas.db' not in texto,          True)
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv\Scripts\python.exe testar_atualizacao.py`
Expected: FAIL com `AttributeError` em `copiar_banco`

- [ ] **Step 3: Implement `copiar_banco`**

`shutil.copy2` de `financas.db` para `financas.db.bak-<versao_atual>` na mesma pasta. Devolve `None` quando não existe banco. Se o backup já existir, acrescente um sufixo numérico em vez de sobrescrever — um backup anterior pode ser a única cópia boa que a pessoa tem.

- [ ] **Step 4: Implement `gerar_script_troca`**

Escreve um `.ps1` numa pasta temporária (nunca dentro da pasta do app, que vai ser mexida). O script, em ordem: espera o processo `pid` encerrar com limite de tempo; move cada item de `ITENS_DO_PROGRAMA` para `<nome>.old`; copia os itens novos de `pasta_nova`; reabre `Organizador Financeiro.exe`; aguarda `localhost:5050` responder dentro de um limite; **se responder**, apaga os `.old` e o temporário; **se não responder**, mata o que subiu, devolve os `.old` aos nomes originais e reabre a versão antiga.

Toca exclusivamente os itens de `ITENS_DO_PROGRAMA`. Nunca `Remove-Item` na pasta inteira.

- [ ] **Step 5: Implement `aplicar_atualizacao` and the route body**

Orquestra: baixa, confere hash (aborta sem tocar em nada se não bater), extrai, copia o banco, gera o script, dispara o script destacado do processo do app e agenda o encerramento do servidor logo após responder a requisição.

A rota `POST /atualizar` (já com o gating da Task 3) renderiza `atualizando.html` e só então dispara. A página se explica sozinha, sem depender do backend: o Flask morre em seguida e não haverá ninguém para responder polling.

- [ ] **Step 6: Run all tests**

Run: `venv\Scripts\python.exe testar_atualizacao.py && venv\Scripts\python.exe testar.py`
Expected: PASS nos dois

- [ ] **Step 7: Commit**

```bash
git add atualizador.py app.py templates/atualizando.html testar_atualizacao.py
git commit -m "feat: troca de arquivos com backup do banco e reversao automatica"
```

---

### Task 6: Publicação e hospedagem

**Files:**
- Create: `publicar.py`
- Create: `NOTAS.md`
- Create: `site/index.html`
- Create: `firebase.json`, `.firebaserc`
- Modify: `versao.py` (`MANIFEST_URL_PADRAO`)
- Modify: `build.bat`
- Modify: `comprador_leiame.txt`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `versao.VERSAO`, `versao.ITENS_DO_PROGRAMA`.
- Produces: `site/version.json` e `site/OrganizadorFinanceiro-<versao>.zip` gerados; nenhuma API para outras tasks.

- [ ] **Step 1: Create the Firebase project and fix the URL**

Com o CLI já logado em `brunoacarvalho.contato@gmail.com`, crie um projeto Hosting (plano Spark) e anote o ID. Grave a URL resultante em `versao.MANIFEST_URL_PADRAO` (`https://<id>.web.app/version.json`).

Esta URL fica gravada em toda cópia distribuída e não pode ser corrigida remotamente depois. Confira o ID antes de seguir.

- [ ] **Step 2: Write `NOTAS.md` and the publish script**

`NOTAS.md` guarda as novidades por versão, com um cabeçalho por versão; `publicar.py` lê dele o trecho da versão atual.

`publicar.py` executa, em ordem: confere que a árvore git está limpa; roda `build.bat`; zipa `comprador/OrganizadorFinanceiro` como `site/OrganizadorFinanceiro-<versao>.zip` (sem `financas.db`, sem `__pycache__`); calcula o SHA-256; escreve `site/version.json` com `versao`, `url`, `tamanho`, `sha256` e `notas`; e então `firebase deploy --only hosting`.

Campos extras no `version.json` são opcionais por desenho: instalações antigas vão ler esse arquivo para sempre, então o formato só cresce, nunca muda de forma.

- [ ] **Step 3: Write the download page and hosting config**

`site/index.html`: página simples com o nome do app, a versão atual, o link do ZIP e as instruções curtas de instalação, no mesmo tom do `LEIA-ME.txt`. `firebase.json` publica `site/` como diretório público. `.gitignore` passa a ignorar os ZIPs gerados em `site/`, mas **não** o `index.html` nem o `firebase.json`.

O `comprador_leiame.txt` ganha uma seção curta sobre atualização: que o programa avisa sozinho quando sai versão nova, que a pessoa decide se atualiza, e que os dados dela ficam preservados. É o manual que vai na mão do comprador — a funcionalidade nova precisa estar lá, no mesmo tom das outras seções.

- [ ] **Step 4: Verify the generated manifest**

Run: `venv\Scripts\python.exe publicar.py --apenas-gerar` (sem deploy)
Expected: `site/version.json` com a versão do `versao.py`, e o `sha256` batendo com `certutil -hashfile` no ZIP gerado.

- [ ] **Step 5: Publish and fetch it back**

Run: `publicar.py` completo, depois `curl https://<id>.web.app/version.json`
Expected: o manifesto publicado é idêntico ao arquivo local.

- [ ] **Step 6: Commit**

```bash
git add publicar.py NOTAS.md site/index.html firebase.json .firebaserc versao.py build.bat .gitignore
git commit -m "feat: publicacao em um comando e hospedagem do download no firebase"
```

---

### Task 7: Verificação de ponta a ponta

**Files:**
- Modify: `NOTAS.md`, `versao.py` (bump para `1.0.1`)
- Create: `docs/superpowers/plans/2026-10-22-verificacao.md` (registro do resultado)

**Interfaces:**
- Consumes: todas as anteriores.
- Produces: evidência de que o ciclo fecha.

- [ ] **Step 1: Build and keep a 1.0.0 installation**

Gere o pacote na versão `1.0.0`, extraia numa pasta limpa fora do repositório e rode o app. Cadastre renda, conta e um pagamento, para existir um `financas.db` com dado real. Guarde o hash desse arquivo.

- [ ] **Step 2: Publish 1.0.1**

Suba `versao.VERSAO` para `1.0.1`, escreva a entrada no `NOTAS.md` e rode `publicar.py`.

- [ ] **Step 3: Verify the whole loop on the 1.0.0 installation**

Abra o app da instalação `1.0.0`. Confirme: a faixa aparece com as novidades da `1.0.1`; ao clicar, ele baixa, troca e reabre sozinho; a versão passa a ser `1.0.1`.

Expected, e cada um é critério de aceite da spec:
- O hash do `financas.db` é **idêntico** ao do Step 1.
- Existe `financas.db.bak-1.0.0` na pasta.
- Os dados cadastrados continuam na tela.
- Não sobrou nenhum `.old` na pasta.

- [ ] **Step 4: Verify offline behavior**

Com a rede desligada, abra o app: tempo de abertura igual, visual completo, sem faixa e sem erro de console.

- [ ] **Step 5: Verify tampering and rollback**

Publique um `version.json` com `sha256` errado e confirme que a atualização é recusada com a instalação intacta. Depois, simule versão nova que não sobe (troque o exe novo por um arquivo inválido antes da troca) e confirme que o auxiliar devolve a versão anterior funcionando.

- [ ] **Step 6: Record the results and commit**

Anote em `docs/superpowers/plans/2026-10-22-verificacao.md` o que foi verificado, com os hashes.

```bash
git add versao.py NOTAS.md docs/superpowers/plans/2026-10-22-verificacao.md
git commit -m "test: verificacao de ponta a ponta do ciclo de atualizacao"
```
