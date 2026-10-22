# Distribuição e atualização do Organizador Financeiro

Data: 2026-10-22
Projeto: `Carvalho-99/Dashboard` (Organizador Financeiro)

## Intenção

O Bruno vende o Organizador Financeiro como um programa que a pessoa baixa e roda na
própria máquina. Hoje, entregar uma correção significa recompilar, zipar e mandar o
arquivo para cada comprador individualmente — o que não escala nem para três pessoas, e
na prática significa que quase ninguém fica na versão corrigida.

O objetivo é fechar esse laço: publicar uma versão nova deve ser um comando só do lado do
Bruno, e quem já tem o app instalado deve ficar sabendo sozinho, na próxima vez que abrir
o programa.

**O que NÃO muda:** o app continua local e soberano. Cada pessoa tem sua cópia e seu
`financas.db` na própria máquina. Nada de login, servidor de aplicação, sincronismo ou
dado financeiro de ninguém trafegando para lugar nenhum. A única coisa que vai à internet
é a pergunta "qual é a versão mais recente?" e, se a pessoa mandar, o download do programa.

## Objetivos

1. A pessoa que abre o app é avisada, dentro da própria interface, quando existe versão nova.
2. A atualização acontece quando ela clica — nunca sozinha, nunca obrigatória.
3. Os dados dela (`financas.db`) sobrevivem a qualquer atualização, sempre.
4. Publicar uma versão nova é um comando só para o Bruno.
5. O app funciona normalmente sem internet, sem lentidão e sem erro na tela.

## Não-objetivos

- Login, contas de usuário, painel administrativo.
- Dados na nuvem, backup remoto, sincronismo entre máquinas.
- Telemetria, analytics, ou qualquer coleta sobre quem usa ou como usa.
- Atualização silenciosa, automática ou forçada.
- Controle de licença, bloqueio de quem não pagou, ativação por chave.
- Suporte a Linux/macOS. O pacote distribuído é Windows (PyInstaller).

## Anti-objetivos

São os cenários que tornariam este projeto um fracasso mesmo funcionando:

- **Uma atualização apagar ou corromper o `financas.db` de alguém.** A pessoa pode ter
  meses de contas lançadas. Perder isso é pior do que nunca ter atualizado.
- **Uma atualização interrompida deixar a instalação inutilizável**, com a pessoa sem app
  e sem saber o que fazer.
- **A checagem de versão atrasar ou travar a abertura do app**, ou mostrar erro de rede
  para quem só quer ver as contas do mês.
- **O aviso de atualização virar propaganda** — algo que reaparece, insiste ou atrapalha
  quem decidiu não atualizar agora.

## Restrições

- **O pacote é PyInstaller `--onedir`.** A pasta entregue contém `Organizador
  Financeiro.exe` (launcher), `OrganizadorFinanceiro.exe` (servidor Flask), `_internal/`
  (runtime Python, templates, static) e `LEIA-ME.txt`. O `financas.db` nasce ao lado
  desses arquivos, na mesma pasta, na primeira execução.
- **No Windows não se sobrescreve um `.exe` em execução.** Trocar o programa exige que o
  processo morra antes, e quem faz a troca não pode ser o próprio programa.
- **A versão instalada hoje não sabe se atualizar.** O ZIP já compilado não tem
  verificador dentro. O Bruno confirmou que **ainda não o enviou a ninguém**, então o
  caminho é regerar o pacote já com o verificador e só então distribuir. Nenhuma
  instalação legada precisa ser resgatada.
- **O app depende de CDN para a aparência.** O `base.html` carrega Bootstrap 5.3.2,
  Bootstrap Icons 1.11.3 e Chart.js 4.4.0 de `cdn.jsdelivr.net`. Hoje, sem internet, o app
  abre sem estilo nenhum e cada página trava esperando a rede. O Bruno decidiu **corrigir
  isso neste mesmo trabalho** (ver Objetivo 5, que não é alcançável sem essa correção).
- **Hospedagem: Firebase Hosting na conta pessoal `brunoacarvalho.contato@gmail.com`.**
  Decisão do Bruno, depois de eu levantar que a URL fica gravada permanentemente em cada
  cópia distribuída e não deveria depender de uma conta ligada ao trabalho. O CLI do
  Firebase nesta máquina já está logado nessa conta. **Não existe projeto para este app
  ainda** — os três visíveis são `meu-tunel`, `portifolio-elaibe` e `vpn-forest`.
- **Plano Spark (gratuito) para começar:** 10 GB de armazenamento e 360 MB de
  transferência por dia, ou seja ~16 downloads diários de um ZIP de 21,8 MB. Acima disso
  os downloads passam a falhar até o dia seguinte. Migrar para Blaze (US$ 0,15/GB) é
  decisão do Bruno e exige conta de faturamento; não é necessário no volume atual.
- **O repositório continua público**, por decisão do Bruno. O desenho não depende do
  GitHub de qualquer forma.
- O app não é assinado digitalmente. O Windows exibe aviso do SmartScreen na primeira
  execução — o `LEIA-ME.txt` já orienta sobre isso, e a atualização não piora o cenário.

## As decisões que o Bruno tomou

- A atualização é **avisada, não aplicada**: aparece uma notificação quando a pessoa abre
  o app, e ela clica se quiser.
- O app segue **local, sem login e sem nuvem**.
- Hospedagem no **Firebase Hosting, conta pessoal `brunoacarvalho.contato@gmail.com`**.
- Os dados da pessoa **não podem ser tocados** pela atualização.
- Os arquivos de CDN passam a ser **embutidos no pacote**, para o app funcionar offline.
- O **repositório segue público**.
- O ZIP atual **ainda não foi distribuído**; será substituído antes de ir para alguém.

## Como funciona

### Do lado de quem usa

Existe um arquivo `version.json` publicado no Firebase Hosting, com a versão mais recente,
o endereço do ZIP, o tamanho, um hash SHA-256 e um texto curto de novidades.

Quando o app abre, ele consulta esse arquivo **em segundo plano**, com timeout curto. Se a
versão publicada for maior que a instalada, uma faixa aparece no topo da interface — no
mesmo estilo dos alertas que o app já usa — dizendo que saiu versão nova, com o resumo das
novidades e um botão para atualizar. Se as versões forem iguais, ou se não houver internet,
ou se o Firebase estiver fora do ar, **a pessoa não vê absolutamente nada** e usa o app
normalmente: a falha é silenciosa por princípio, nunca vira erro na tela.

Quem não quiser atualizar agora fecha o aviso e ele não insiste naquela sessão.

Ao clicar em atualizar, o app baixa o ZIP, confere o hash contra o que o `version.json`
declarou e só então aplica. Hash diferente significa download corrompido ou adulterado: a
atualização é abortada e nada é tocado. Durante a troca, a pessoa vê uma tela informando
que o programa vai reabrir sozinho.

### A troca dos arquivos

Esta é a parte delicada, e a regra que a governa é: **só o programa é substituído, por uma
lista explícita de arquivos.** Nunca uma substituição de pasta inteira, porque é assim que
o `financas.db` morre.

Os itens que a atualização pode tocar são exatamente estes: `Organizador Financeiro.exe`,
`OrganizadorFinanceiro.exe`, `_internal/` e `LEIA-ME.txt`. Qualquer outra coisa na pasta —
o banco de dados, backups que a pessoa tenha feito, atalhos — é deixada em paz.

Como o processo em execução segura os próprios executáveis, a troca é feita por um
auxiliar externo, que o app dispara pouco antes de encerrar. Esse auxiliar espera o
processo morrer, move os arquivos antigos para um nome temporário, põe os novos no lugar e
reabre o app.

**A versão antiga só é descartada depois que a nova provar que funciona.** O auxiliar
reabre o app e espera o servidor responder em `localhost:5050`; só então apaga os arquivos
antigos. Se a versão nova não subir — build ruim, DLL faltando, antivírus colocando o
executável recém-baixado em quarentena —, o auxiliar devolve os arquivos antigos e reabre a
versão que estava funcionando. O pior resultado possível de uma atualização é "continuei na
versão anterior", nunca "fiquei sem programa".

### Do lado do Bruno

Publicar vira um comando só, que: lê a versão nova de uma fonte única de verdade no
código, lê o texto de novidades de um arquivo de notas no repositório, compila com o
`build.bat`, zipa o pacote, calcula o SHA-256, gera o `version.json` e sobe tudo para o
Firebase Hosting. Terminado o comando, quem abrir o app vê o aviso.

A versão fica num lugar só do código, e o build a propaga. Duas fontes de versão divergindo
é um jeito conhecido de publicar um aviso que aponta para o ZIP errado.

Além do `version.json` e do ZIP, o site publica uma **página simples de download**, para o
Bruno ter um link para mandar a quem compra.

## Decisões que eu tomei (confira enquanto lê)

Vieram da revisão do documento. Nenhuma delas muda o que você pediu, mas todas mudam o
que será construído:

1. **A versão antiga fica no disco até a nova responder.** Descrito acima. A alternativa
   era apagar na hora (mais simples, mas é exatamente o anti-objetivo de ficar sem
   programa) ou guardar uma cópia de reserva permanente (~50 MB parados ao lado dos dados
   da pessoa, para sempre).
2. **Uma cópia do `financas.db` é feita antes de atualizar**, com nome tipo
   `financas.db.bak-1.0.0`. É a única exceção à regra "só o programa é substituído": ela
   escreve um arquivo novo e nunca modifica o original. Eu considerei isso barato demais
   para abrir mão, mesmo com a troca sendo segura.
   Sobre voltar para a versão anterior depois de uma atualização: as migrações do
   `init_db()` são só aditivas (`ALTER TABLE ADD COLUMN`), então uma versão antiga roda sem
   quebrar num banco já migrado. Blindar o app contra banco de versão futura ficou **fora
   de escopo** — se um dia houver mudança destrutiva de schema, isso volta à mesa.
3. **O endereço do `version.json` é sobrescrevível para teste** (variável de ambiente ou
   arquivo ao lado do executável). Sem isso não há como testar o ciclo completo sem
   publicar no site de produção, e o teste de ponta a ponta é o que dá confiança aqui.
4. **O `version.json` carrega as novidades só da versão mais recente**, com campos
   opcionais para o formato poder crescer sem quebrar instalações antigas — que vão ler
   esse mesmo arquivo para sempre.
5. **O aviso e o botão de atualizar só valem para quem está no próprio PC.** O servidor
   escuta em `0.0.0.0:5050` e o LEIA-ME ensina a acessar pelo celular; disparar uma troca
   de arquivos e reinício do programa a partir do celular, sem ninguém no computador, é
   ruim o bastante para eu bloquear.
6. **Fico no plano Spark.** No seu volume não chega perto do limite; se chegar, os
   downloads falham até o dia seguinte e aí a gente conversa sobre o Blaze.

## O que fica a cargo de quem construir

- **O mecanismo do auxiliar de troca.** Pode ser um script gerado em tempo de execução
  numa pasta temporária, ou um segundo executável embarcado no pacote. O script evita mais
  um alvo de build e não fica travado junto com o app; o executável é mais limpo, mas
  precisa se manter em sincronia e não consegue atualizar a si mesmo. Avaliar também como
  cada opção se comporta diante de antivírus, já que ambos substituem executáveis.
- **Onde exatamente a faixa de aviso é renderizada** e como ela se integra ao
  `base.html`, que já tem área de alertas com auto-dismiss (o aviso de atualização não deve
  sumir sozinho em 4 segundos como os outros).
- **Se a checagem roda a cada abertura ou com um intervalo mínimo** entre consultas.
- **Se vale um botão "verificar atualizações" nas Configurações**, para quem fechou o aviso
  e mudou de ideia.
- **O formato de comparação de versão.** Sugestão: semver simples (`maior.menor.correção`),
  comparado numericamente por campo, nunca por string.
- **Como a tela de "atualizando" é mostrada**, dado que o servidor Flask vai morrer no meio
  do processo e a página não terá backend para conversar.
- **O nome e a estrutura do arquivo de notas de versão** que o comando de publicação lê.

## Como saber que funcionou

- Uma instalação na versão antiga, ao abrir, mostra o aviso; ao clicar, chega na versão
  nova e reabre sozinha.
- O `financas.db` com lançamentos reais continua idêntico depois da atualização —
  verificado por hash do arquivo antes e depois.
- **Com a internet desligada, o app abre no mesmo tempo de sempre, com o visual completo**,
  e não mostra aviso nem erro.
- Um ZIP com hash adulterado é recusado e a instalação continua intacta e funcionando.
- Uma atualização interrompida no meio (processo morto à força) deixa a instalação
  funcionando, seja na versão nova, seja na antiga.
- Uma versão nova que não sobe é revertida sozinha, e a pessoa volta a ter o app da versão
  anterior funcionando.
