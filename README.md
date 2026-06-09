# Monitor de Vagas ONU – Brasil

Monitora automaticamente vagas de emprego e consultorias publicadas por organismos da ONU para o Brasil.  
Envia um e-mail resumo a cada **2 dias às 09:00 (Brasília)** com as novas oportunidades encontradas.

## Organismos monitorados (padrão)

| Organismo | Sigla |
|---|---|
| Programa das Nações Unidas para o Desenvolvimento | UNDP |
| Secretaria das Nações Unidas | UN Careers |
| Fundo das Nações Unidas para a Infância | UNICEF |
| Organização Internacional do Trabalho | ILO |
| Organização para Agricultura e Alimentação | FAO |
| Organização Pan-Americana da Saúde | PAHO |
| UNESCO | UNESCO |
| Escritório de Serviços de Projetos | UNOPS |
| ONU Mulheres | UN Women |
| Banco Mundial | World Bank |

## Como funciona

1. O GitHub Actions executa `scraper.py` a cada 2 dias.
2. O script acessa cada site listado em `config.json`, filtra vagas relacionadas ao Brasil.
3. Compara com `seen_jobs.json` para enviar **apenas novas vagas**.
4. Envia um e-mail HTML formatado com título, organismo e link direto para cada vaga.
5. Atualiza `seen_jobs.json` com as vagas já vistas (commita automaticamente).

## Configuração inicial

### 1. Fork / clone este repositório no GitHub

```bash
git clone https://github.com/SEU_USUARIO/un-jobs-monitor.git
```

### 2. Configure os Secrets do repositório

Vá em **Settings → Secrets and variables → Actions → New repository secret** e adicione:

| Secret | Descrição | Exemplo |
|---|---|---|
| `SMTP_HOST` | Servidor SMTP | `smtp.gmail.com` |
| `SMTP_PORT` | Porta SMTP | `587` |
| `SMTP_USER` | Seu e-mail remetente | `seu@gmail.com` |
| `SMTP_PASS` | Senha de app do Gmail | `xxxx xxxx xxxx xxxx` |
| `EMAIL_TO` | E-mail destinatário | `destino@email.com` |

> **Gmail:** Ative a verificação em 2 etapas e crie uma [Senha de App](https://myaccount.google.com/apppasswords) em vez de usar sua senha normal.

### 3. Testar manualmente

No GitHub: **Actions → Monitor Vagas ONU Brasil → Run workflow**

## Adicionar um site manualmente

Edite `config.json` e adicione um novo objeto no array `"sources"`:

```json
{
  "name": "Nome do Organismo",
  "url": "https://url-do-site-de-vagas.org",
  "type": "html",
  "enabled": true,
  "notes": "Descrição opcional"
}
```

Para desativar temporariamente uma fonte sem removê-la, mude `"enabled": false`.

## Palavras-chave

As vagas são filtradas pelas keywords em `config.json → keywords`. Adicione ou remova conforme necessário:

```json
"keywords": ["Brazil", "Brasil", "Brasília", "consultant", ...]
```

## Estrutura do projeto

```
un-jobs-monitor/
├── .github/
│   └── workflows/
│       └── monitor.yml      # agendamento GitHub Actions
├── config.json              # fontes e configurações
├── scraper.py               # lógica principal
├── seen_jobs.json           # vagas já vistas (evita duplicatas)
├── requirements.txt
└── README.md
```
