# 💰 Organizador Financeiro

> Controle financeiro pessoal e para casais — local, rápido e sem nuvem.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0+-000000?style=flat-square&logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-local-003B57?style=flat-square&logo=sqlite&logoColor=white)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?style=flat-square&logo=bootstrap&logoColor=white)

---

## O que é

Aplicativo web local feito em Python + Flask para organizar finanças pessoais. Roda direto no PC e abre no navegador — sem instalar nada além do Python, sem conta, sem nuvem. Todos os dados ficam em um arquivo SQLite local (`financas.db`).

Pensado para uso individual **ou em casal**, com perfis separados, visão unificada e planejamento inteligente de pagamentos.

---

## Funcionalidades

### Dashboard
- Resumo do mês: renda total, total de contas, quanto sobra e progresso de pagamentos
- Barra de comprometimento da renda (verde / amarelo / vermelho)
- Alertas de contas vencidas e vencendo nos próximos 7 dias
- Gráfico de gastos por categoria (Chart.js)
- Lista de contas com check/uncheck direto na tela

### Contas
- Cadastro de contas fixas com nome, valor, dia de vencimento, categoria e prioridade
- 4 níveis de prioridade: **Crítico**, **Importante**, **Normal**, **Opcional**
- Suporte a contas parceladas com encerramento automático ao fim das parcelas
- Contas com data de término (ex: financiamento que acaba em determinado mês)
- Adiantamento de parcelas futuras

### Rendas
- Cadastro de múltiplas fontes de renda (Salário, Vale, Outro)
- Dia do mês de recebimento para o planejador usar como referência

### Planejador Inteligente
- Distribui automaticamente as contas entre as fontes de renda por **janelas de tempo**
  - Ex: "pague isso com o salário do dia 5, aquilo com o vale do dia 20"
- Respeita prioridades: contas críticas são pagas mesmo que o saldo fique abaixo da reserva
- Reserva configurável (padrão: R$ 300)
- Meta de poupança mensal com feedback visual
- Alertas de:
  - Contas que vencem antes do primeiro recebimento
  - Saldo insuficiente
  - Déficit total (contas > renda)
- Dica personalizada baseada no percentual de poupança

### Modo Casal
- Perfis individuais com cor personalizada
- Visão separada por pessoa e visão unificada do casal
- Contas compartilhadas (atribuídas ao casal, não a um indivíduo)
- Estatísticas por membro: renda, contas, saldo e progresso de pagamentos

### Histórico
- Registro completo de todos os pagamentos
- Agrupado por mês com total gasto

### Acesso pelo celular
- Acesse pelo celular no mesmo WiFi: `http://IP-DO-PC:5050`
- Interface responsiva, funciona bem em telas pequenas

---

## Como instalar e rodar

### Opção 1 — Python direto

```bash
# Clone o repositório
git clone https://github.com/Carvalho-99/Dashboard.git
cd Dashboard

# Crie e ative o ambiente virtual
python -m venv venv
venv\Scripts\activate      # Windows
# ou: source venv/bin/activate  # Linux/Mac

# Instale as dependências
pip install -r requirements.txt

# Rode o servidor
python app.py
```

Acesse em: [http://localhost:5050](http://localhost:5050)

---

### Opção 2 — Windows: duplo clique

Execute `iniciar.bat`. Na primeira vez, ele configura o ambiente automaticamente. Nas próximas, já abre direto.

Para criar um atalho na Área de Trabalho, execute `criar_atalho.bat`.

---

### Opção 3 — Compilar como .exe (distribuição)

```bat
build.bat
```

Gera a pasta `comprador\OrganizadorFinanceiro\` com um `.exe` que roda sem Python instalado. Ideal para distribuir para outras pessoas.

---

## Categorias de contas

| Categoria | Ícone |
|-----------|-------|
| Moradia | 🏠 Aluguel, condomínio, IPTU |
| Alimentação | 🛒 Mercado, delivery |
| Transporte | 🚗 Combustível, seguro, financiamento |
| Saúde | 💊 Plano, farmácia, consultas |
| Educação | 📚 Cursos, mensalidade |
| Lazer | 🎮 Streaming, academia, passeios |
| Serviços | 📡 Internet, celular, assinaturas |
| Financeiro | 💳 Cartão, empréstimos |
| Outros | 📦 |

---

## Estrutura do projeto

```
organizador_financeiro/
├── app.py                  # Backend Flask (rotas, banco, lógica)
├── planner.py              # Algoritmo SmartPlanner
├── launcher.py             # Launcher para o .exe compilado
├── requirements.txt        # Dependências Python
├── iniciar.bat             # Inicializador Windows (cria venv na 1ª vez)
├── criar_atalho.bat        # Cria atalho na Área de Trabalho
├── build.bat               # Compila para .exe com PyInstaller
├── gerar_icone.py          # Gera o ícone para o .exe
├── testar.py               # Suite de testes das rotas
├── comprador_leiame.txt    # Manual do usuário final (versão .exe)
├── static/
│   ├── style.css           # Tema dark-mode completo
│   ├── script.js           # Auto-dismiss de alertas, formatação de valores
│   └── favicon.png
└── templates/
    ├── base.html           # Layout base + navbar + seletor de usuário
    ├── dashboard.html      # Dashboard principal
    ├── bills.html          # Lista de contas
    ├── bill_form.html      # Formulário de conta (add/edit)
    ├── incomes.html        # Lista de rendas
    ├── income_form.html    # Formulário de renda (add/edit)
    ├── planner.html        # Planejador inteligente
    ├── couple.html         # Visão do casal
    ├── couples.html        # Gerenciamento de casais
    ├── users.html          # Gerenciamento de usuários
    ├── history.html        # Histórico de pagamentos
    ├── settings.html       # Configurações
    └── suggestions.html    # Sugestões financeiras
```

---

## Tecnologias

| Tecnologia | Uso |
|------------|-----|
| Python 3.10+ | Backend |
| Flask 3.0 | Framework web |
| SQLite | Banco de dados local |
| Jinja2 | Templates HTML |
| Bootstrap 5.3 | Layout e componentes |
| Bootstrap Icons | Ícones |
| Chart.js 4.4 | Gráfico de categorias |
| PyInstaller | Compilação para .exe |

---

## Rodando os testes

```bash
python testar.py
```

Cria um banco temporário, testa todas as rotas (GET e POST) e exibe o resultado.

---

## Dados e privacidade

Todos os dados ficam em `financas.db` na mesma pasta do projeto. Nenhuma informação é enviada para a internet. O `.gitignore` já exclui o banco de dados para que dados pessoais não sejam commitados acidentalmente.

---

## Licença

Projeto pessoal de uso livre.
