# Cyber Risk Assessment — projeto DATA MASTER

Aplicação multimodal para **apoiar**, e não substituir, a avaliação humana de controles cibernéticos. Recebe o ID de um controle e uma evidência visual (PNG/JPG), recupera o requisito oficial no **servidor**, pede ao Gemini uma análise estruturada e apresenta achados, desvios e quatro avaliações independentes: desenho, implementação, efetividade e Tier indicativo 1–4 do NIST CSF 2.0 (ou não determinado).

**Tema do edital:** Automação e Extração de Conhecimento. O projeto reduz atividades repetitivas de leitura e estruturação de evidências de controles. Não é ferramenta de certificação nem aprova controles automaticamente.

## 1. Entrega e organização

| Arquivo/pasta | Função |
|---|---|
| `index.html` + `static/app.js` | Interface responsiva preservando o layout vermelho aprovado e separando seleção, upload e parecer. |
| `api3.py` | API FastAPI, validação de upload, requisito autoritativo, inferência e resposta. |
| `catalog.py` | Carregamento de JSON fictício ou planilha XLSX com cabeçalho detectado dinamicamente. |
| `schemas.py` | Contratos Pydantic das quatro dimensões e Tiers indicativos 1–4. |
| `prompts.py` | Prompt versionado e regras de análise conservadora. |
| `inference.py` | Adaptador do Gemini, substituível por mock para testes. |
| `data/controles_demo.json` | Dez controles com requisitos **sintéticos**, sem informações internas. |
| `benchmark/` | Vinte evidências sintéticas cegas, manifesto, gabarito 4D pendente de validação e calculadora de métricas. |
| `tests/` | Testes offline de API, integridade, formato de imagem, catálogo e benchmark. |
| `docs/` | Documentação de arquitetura, critérios, ética, decisões e roteiro de apresentação. |

**Importante:** a planilha corporativa enviada para construir o projeto **não está incluída** neste pacote para evitar distribuição acidental de dados internos. No ambiente autorizado, copie o arquivo original para `data/privado/SBK_Framework_NIST.xlsx` e configure `CONTROLS_SOURCE` no `.env`. Por padrão, o aplicativo usa o catálogo fictício e o identifica claramente na tela. Os dois controles `RC.CO-1` e `RC.CO-2` da planilha fornecida têm requisito marcado `NA`: o sistema os exibe como indisponíveis, sem inventar uma política.

## 2. Pré-requisitos

- Python 3.11 ou 3.12, navegador moderno e acesso à Internet apenas para inferência Gemini;
- uma API key autorizada no Google AI/Gemini para executar a análise real;
- opcionalmente Docker + Docker Compose; opcionalmente planilha XLSX privada.

### Instalação em outra máquina (Windows PowerShell)

Pode usar `scripts/setup.ps1` e `scripts/run.ps1` como atalhos; no Linux/macOS, `bash scripts/setup.sh` e `bash scripts/run.sh`. Os comandos completos estão abaixo.

```powershell
cd DATA_MASTER_Cyber_Risk_AI
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edite o .env e defina GOOGLE_API_KEY (não salve a chave no Git)
python -m uvicorn api3:app --host 127.0.0.1 --port 8000
```

Para Linux/macOS: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && cp .env.example .env`, depois execute o mesmo comando `python -m uvicorn ...`.

Abra **http://127.0.0.1:8000/**; API OpenAPI em **http://127.0.0.1:8000/docs** e diagnóstico em **http://127.0.0.1:8000/health**. O HTML é servido pelo próprio backend: não abra `index.html` diretamente via `file://`.

Para rodar com a planilha original: copie-a localmente em `data/privado/` e altere no `.env`:

```env
CONTROLS_SOURCE=data/privado/SBK_Framework_NIST.xlsx
CONTROLS_SHEET=PT-BR
```

Reinicie a API e confira a fonte/quantidade em `/health`. O catálogo privado não deve ser publicado em um repositório aberto.

### Alternativa Docker

```bash
cp .env.example .env  # preencha a chave localmente
# Opcional: copie a planilha privada para data/privado/ e atualize .env
docker compose up --build
```

O Compose só expõe a API em `127.0.0.1:8000` no host. O diretório `data` é montado em modo somente leitura. Sem API key, catálogo, frontend e testes offline funcionam, mas o endpoint de inferência retorna **503**, nunca uma resposta supostamente gerada por IA.

## 3. Como usar e demonstrar

1. Selecione o controle: o dropdown mostra **ID + nome**; o requisito detalhado fica em seu campo separado e não pode ser alterado no navegador.
2. Envie evidência **PNG ou JPEG de até 8 MB** com dados fictícios ou explicitamente autorizados. Arquivos são verificados, têm metadados removidos e são enviados ao modelo apenas em memória. Isso **não** remove dados pessoais visíveis no print.
3. Clique em **Analisar Evidência**: a API usa o ID para buscar o requisito autoritativo, ignora alterações arbitrárias enviadas pelo cliente, aciona o modelo e valida o JSON com Pydantic.
4. Analise **desenho, implementação, efetividade e Tier indicativo** separadamente, a confiança qualitativa declarada e as ressalvas; abra o JSON apenas se precisar da rastreabilidade técnica. Todo parecer permanece **preliminar e sujeito a validação humana**.

## 4. Testes e benchmark

```bash
python -m pytest
python scripts/smoke_test.py       # API deve estar em execução
```

Com API key válida e servidor funcionando, o benchmark **real** executa as 20 imagens. Há custo/limites de API: confira sua autorização antes de executar o conjunto completo.

```bash
python benchmark/evaluate.py --run --limit 2      # ensaio inicial, 2 chamadas reais
python benchmark/evaluate.py --run                # 20 chamadas reais; requer quota
python benchmark/evaluate.py --predictions benchmark/resultados/predictions_EXEMPLO.csv
```

O script gera previsões reais, mas **não calcula acurácia enquanto o gabarito 4D não for preenchido e validado**. As notas legadas 1/5 foram preservadas em `benchmark_legado_1a5/` e não são Tiers NIST. Veja `docs/AVALIACAO.md`.

## 5. Decisões e limitações relevantes

- **Gemini multimodal**: um único modelo para texto + imagem, sem OCR prévio ou sistema RAG, pois a planilha selecionada já fornece o requisito exato; veja `docs/DECISOES_TRADEOFFS.md`.
- **Schema**: há contrato Pydantic para saída estruturada, além de validação novamente no servidor. A documentação oficial do SDK descreve `response_schema` em: https://googleapis.github.io/python-genai/ .
- **Privacidade**: imagens não são persistidas por este aplicativo; seu conteúdo é transmitido ao provedor de IA quando a chave está configurada. Para uso real, verifique regras da organização, condições de retenção e contratos com o fornecedor.
- **Quatro critérios**: desenho, implementação, efetividade e Tier indicativo 1–4, cada um com justificativa própria. Os Tiers NIST CSF 2.0 caracterizam práticas organizacionais; a avaliação por controle **não** atribui um Tier oficial à organização. Veja `docs/CRITERIOS_4D.md`.
- **Segurança para produção**: faltam autenticação/autorização, limitação de requisições, política de retenção auditável e observabilidade corporativa. O projeto é um protótipo de desafio, não uma aplicação bancária pronta para produção.

## 6. Mapa do edital

Confira `docs/MATRIZ_EDITAL.md` para cada requisito, evidência de implementação e lacunas que só a demonstração real pode comprovar. `docs/APRESENTACAO.md` oferece um roteiro de apresentação e perguntas difíceis da banca.

## 7. Se o seletor ficar em “Carregando controles da planilha…”

**Causa frequente:** abrir o `index.html` diretamente (endereço `file:///...`) sem
iniciar o FastAPI. O HTML corrigido agora **mostra 10 controles fictícios em modo
prévia offline** e explica por que a análise está desativada. Os controles reais
exigem a API em execução.

**No Windows (caminho mais simples):**

1. Extraia o ZIP **inteiro**, mantendo a pasta `static/`, os arquivos `.py` e a pasta `data/`.
2. Se quiser os 98 controles da sua planilha, coloque `SBK_Framework_NIST.xlsx`
   na pasta principal do projeto e execute `USAR_MINHA_PLANILHA.bat`.
3. Execute `INICIAR_WINDOWS.bat` — cria o ambiente e instala dependências na
   primeira utilização; em seguida, abre o navegador no endereço correto.
4. Confira `http://127.0.0.1:8000/health`: `status` deve ser `ok` e a
   propriedade `controles_carregados` deve ser `98` com a planilha original
   (`10` se estiver utilizando apenas a base fictícia de demonstração).
5. No navegador, acesse **http://127.0.0.1:8000/**, **não o arquivo HTML**.
   Se o servidor iniciar depois de abrir a tela, use **Tentar conectar à API novamente**.
6. Para habilitar a análise Gemini, preencha `GOOGLE_API_KEY` no `.env` e reinicie.

**Para quem modifica a interface:** altere `static/app.js` e depois rode
`python scripts/build_frontend.py` para embutir o código atualizado em `index.html`.
Isso mantém a versão de preview offline e a versão servida pela API sincronizadas.

## 8. Coluna `CONTROLES` e solução do aviso PRÉVIA SEM API

- A coluna de ID/nome da sua planilha pode ser **`CONTROLES`** ou `Sub-categoria`.
  O importador detecta o cabeçalho ignorando acentos e maiúsculas, e usa a
  coluna `Definição de controles` ou `Requisito da Política` como requisito.
- Coloque `SBK_Framework_NIST.xlsx` ao lado de `INICIAR_WINDOWS.bat` (ou em
  `data/privado/`) e execute `INICIAR_WINDOWS.bat` para configurar e iniciar.
  `USAR_MINHA_PLANILHA.bat` verifica o arquivo e exibe a coluna efetivamente usada.
- **Importante:** `PRÉVIA SEM API` significa que você abriu `index.html`
  diretamente em `file://` — **não** é um erro de cabeçalho. Com o servidor
  iniciado, use `http://127.0.0.1:8000/`, que acessa os controles na API.
- `http://127.0.0.1:8000/health` informa `controles_carregados`, `fonte` e
  `colunas_planilha` para comprovar o carregamento sem expor a planilha.


### A evidência carrega, mas o parecer não aparece

Apenas carregar uma imagem não chama o modelo: selecione o controle e clique em **Analisar Evidência**.

1. Abra a aplicação em `http://127.0.0.1:8000/`, nunca pelo arquivo `index.html` com dois cliques.
2. Na pasta principal do projeto, abra `.env` e preencha `GOOGLE_API_KEY=...` com a sua própria chave (sem aspas, não a compartilhe); reinicie `INICIAR_WINDOWS.bat`.
3. Confira `http://127.0.0.1:8000/health`: `integracao_ia_configurada` deve aparecer `true`; isto verifica apenas que a chave está **presente**, não que é válida ou possui quota.
4. Se aparecer erro após clicar, leia a mensagem junto ao botão. Erros de chave, cota, modelo e indisponibilidade do Gemini agora são distinguidos.
5. Para um diagnóstico sem revelar sua chave, execute `VERIFICAR_CONFIGURACAO.bat`.

O parecer real depende de uma chave válida, acesso ao serviço, quota disponível e retorno do modelo. A prévia sem API não gera avaliações falsas.

## 9. Se aparecer "O Gemini rejeitou a solicitação" (HTTP 400)

A mensagem 400 não identifica sozinha a causa. Pode ser modelo inacessível para a
chave, schema JSON incompatível, parâmetro não aceito ou outro problema de
requisição. Na versão revisada, a aplicação usa um schema **simples** para o
provedor e valida o parecer completo com Pydantic localmente. Se o HTTP 400
mencionar **explicitamente o schema**, ocorre uma única nova tentativa sem
`response_schema`, mas ainda com resposta obrigatória em JSON e validação
Pydantic; nenhum parecer inválido é tratado como válido.

1. No `.env`, configure `GEMINI_MODEL` com um dos modelos disponíveis para sua
   chave. O exemplo atual usa `gemini-3.5-flash`, mas disponibilidade e quota
   dependem da sua conta.
2. Ao executar `INICIAR_WINDOWS.bat`, o iniciador atualiza automaticamente a
   dependência `google-genai` antiga. Alternativa manual:
   `.venv\Scripts\python.exe -m pip install -U -r requirements.txt`
3. Rode **`VERIFICAR_GEMINI.bat`**. Ele lista os modelos realmente acessíveis
   com sua chave, faz uma chamada curta de texto e outra de JSON; essas duas
   chamadas podem gerar cobrança. Não imprime a chave nem o erro bruto.
4. Se o modelo configurado não aparecer, edite `GEMINI_MODEL=...` no `.env` e
   reinicie `INICIAR_WINDOWS.bat`. Não coloque a chave em capturas de tela.
5. Refaça o teste no navegador em `http://127.0.0.1:8000/`, com um PNG **sintético**.

**Importante:** os testes locais automatizados usam mocks e não garantem acesso
ou quota de sua chave. Uma chamada real à API só pode ser validada no ambiente
autorizado onde o `.env` está configurado.


## Disponibilidade Gemini (HTTP 503 / 504)

O SDK oficial já aplica novas tentativas com backoff em falhas transitórias. Como opção explícita no `.env`, `GEMINI_FALLBACK_MODEL=gemini-3.1-flash-lite` habilita uma única passagem para modelo alternativo quando o principal continuar retornando HTTP 503/504. Valide antes o acesso à chave com `VERIFICAR_GEMINI.bat`. O modelo alternativo tem perfil de custo/qualidade próprio e pode ser cobrado mesmo se o primário tiver falhado. Nenhum erro 400/401/403/429 ativa esse fallback, e o parecer só é exibido se um modelo de fato responder com JSON validado. Se ambos falharem, a interface informa a indisponibilidade sem inventar resultado. O JSON retornado identifica o modelo efetivamente utilizado.

### Resposta do modelo sem formato válido (HTTP 502)

A versão de diagnóstico de formato distingue: `RESPOSTA_VAZIA`, `RESPOSTA_TRUNCADA`,
`RESPOSTA_BLOQUEADA`, `JSON_INVALIDO`, `CAMPOS_AUSENTES`, `CAMPOS_INVALIDOS` e
`SCHEMA_INCOMPATIVEL`. Somente o código da categoria e **nomes de campos** podem
ser incluídos na mensagem e no log; jamais copie a saída bruta do Gemini, a
chave, o prompt ou a evidência para esses canais.

Quando a primeira resposta está incompleta ou malformada, o sistema tenta
**uma única vez** uma nova análise do mesmo documento no mesmo modelo, com
instrução mais concisa e maior orçamento de saída. O resultado só é publicado
se passar pela validação Pydantic; nenhum campo de conteúdo ausente é inventado.
Bloqueios de segurança não geram nova tentativa automática. A tentativa
extra pode incorrer em outra cobrança da API. Para desabilitá-la, configure
`GEMINI_FORMAT_RETRY=false` no `.env` e reinicie o servidor.

Se o erro persistir, anote apenas o `codigo` do erro e os nomes de campos
apontados no log da API; execute `VERIFICAR_GEMINI.bat`, verifique a
compatibilidade do modelo e encaminhe a evidência para revisão humana.
Um teste offline com o SDK simulado não certifica o funcionamento de uma
chave Gemini real ou de modelos disponíveis na conta.

## 12. Modo Demonstração — sem consumo de quota Gemini

A interface agora possui dois botões no cabeçalho: **Análise real** (fluxo original)
e **Demonstração**. O modo de demonstração funciona com a API FastAPI iniciada
mesmo sem `GOOGLE_API_KEY` ou com quota esgotada. Não basta abrir `index.html`
com dois cliques: use `http://127.0.0.1:8000/`.

Passo a passo:

1. Inicie `INICIAR_WINDOWS.bat` e acesse `http://127.0.0.1:8000/`.
2. Clique em **Demonstração** no cabeçalho.
3. Escolha um dos cinco cenários sintéticos de backup PR.IP-4, com avaliações separadas e Tiers indicativos 1, 2, 3, 3 e 4.
4. O requisito fictício e a imagem sintética desse cenário aparecem automaticamente.
5. Clique em **Exibir parecer ilustrativo**. O endpoint `/api/demo/avaliar`
   devolve um JSON local com justificativa, achados, desvios e maturidade;
   não ocorre inferência de IA.
6. Volte para **Análise real** quando a quota estiver disponível. Nesse modo,
   é possível selecionar um controle do catálogo e anexar uma imagem própria;
   somente `/api/auditar` faz chamada ao Gemini.

**Transparência para a banca:** toda imagem de demonstração está marcada como
`EVIDÊNCIA SINTÉTICA`; a tela e o JSON exibem `origem_resultado: DEMONSTRACAO`,
`confianca_ia: NÃO APLICÁVEL`, `versao_prompt: NAO_APLICAVEL` e
`validacao_especialista: PENDENTE`. Os textos de exemplo foram preparados para
explicar a interface e **não representam análises executadas previamente pelo
Gemini nem conclusões validadas por auditor**. O modo de demonstração **não**
deve alimentar resultados do benchmark ou decisões reais.

Arquivos relevantes:

- `data/demo_scenarios/images/DEMO-01.png` a `DEMO-05.png`: screenshots fictícios.
- `data/demo_scenarios/casos.json`: cinco pareceres de referência, escritos para
  demonstração visual dos quatro critérios e não enviados ao Gemini.
- `demo_mode.py`: API fechada dos cenários locais, separada da inferência.
- `tests/test_demo_mode.py`: verifica os cinco endpoints, a ausência de chamada
  ao analisador, a rotulagem e a recusa de imagens arbitrárias no modo demo.

O catálogo fictício distribuído não substitui os controles privados da sua
planilha. Em **Análise real**, a fonte ativa permanece configurada pelo `.env`.
