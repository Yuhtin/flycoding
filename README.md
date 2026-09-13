# Flycodex

Um piloto local em que uma rede simulada baseada no conectoma MaleCNS observa
uma imagem, escolhe uma de três instruções e acompanha uma sessão dedicada do
Codex. O observatório mostra os pixels exatos usados pela rede, escolhas,
feedback, testes externos e eventos reais da sessão.

O experimento tem seis tentativas: adaptável, congelada e aleatória; depois
repete essa ordem. Cada tentativa começa com o mesmo bug e uma sessão nova.
Há no máximo 5 instruções por tentativa, 10 por condição e 30 no piloto inteiro.
Sucesso antecipado encerra a tentativa sem transferir a sobra de orçamento.

## Piloto real

Em 13/09/2026, o piloto completou as seis tentativas com **9 envios ao Codex**.
Todas começaram com 1/5 testes passando e terminaram com 5/5, sem violações.

| Condição | Sucessos | Envios |
| --- | ---: | ---: |
| Rede adaptável | 2/2 | 2 |
| Pesos congelados | 2/2 | 2 |
| Aleatória uniforme | 2/2 | 5 |

As duas condições neurais escolheram Corrigir de primeira. A memória adaptável
mudou e foi preservada, mas teve o mesmo desempenho da rede congelada: este
piloto **não demonstrou vantagem de aprendizado**. Quem escreve o código é o
Codex; a rede seleciona uma das três instruções fixas.

![Painel com uma escolha neural e a resposta real do Codex](docs/results/dashboard.png)

[Relatório e evidências](docs/results/README.md) ·
[Resultados por tentativa](docs/results/pilot.md) ·
[Traces completos sem eventos brutos](docs/results/pilot.json).

## Instalação

Requisitos: macOS ou Linux, Python 3.11+, `uv`, Git, `curl`, compilador C++17
(`c++`, por exemplo Xcode Command Line Tools no macOS ou GCC/Clang no Linux),
[RTK](https://github.com/rtk-ai/rtk) no PATH e Codex CLI autenticada localmente.
O armazenamento usa locks POSIX e o transporte usa grupos de processos; Windows
não foi validado. Nenhuma credencial pertence aos arquivos do projeto.

```sh
rtk proxy uv sync --group dev
rtk proxy uv run flycodex --help
rtk proxy .venv/bin/python -m pytest
```

Os testes usam somente executáveis controlados e políticas determinísticas,
identificados como **sintéticos**. Não baixam dados, não executam a CLI real do
Codex e não produzem evidência do piloto real. A CI executa apenas esses testes.

## Preparar e verificar a rede

```sh
rtk proxy uv run flycodex prepare --data-dir data
rtk proxy uv run flycodex probe --data-dir data --output-dir runs/probe
```

`prepare` baixa e verifica os hashes fixados dos arquivos de origem, normaliza
os neurônios e compila o grafo integral retido. Reutiliza dados existentes que
passam na verificação. `probe` é uma verificação neural sem envios ao Codex;
a primeira carga compila o núcleo C++ local.

Na preparação medida em Mac ARM64 com 16 GiB em 13/09/2026:

| Artefato | Tamanho |
| --- | ---: |
| Anotações de origem | 14.483.314 bytes |
| Neurotransmissores de origem | 43.282.834 bytes |
| Arestas de origem | 1.051.241.946 bytes |
| Diretório preparado em disco | 1.647.152 KiB (aprox. 1,57 GiB) |
| `graph.npz` em disco | 244.296 KiB |
| Ambiente Python em disco | 225.624 KiB |

A preparação precisa de espaço temporário adicional e faz sua própria
verificação de espaço. O grafo tem 166.700 neurônios e 25.582.938 arestas.
O piloto mantém apenas um grafo carregado por vez; checkpoints comprimidos
medidos têm aproximadamente 6,5 MB cada. As verificações reais da preparação
e do mecanismo estão em [docs/results](docs/results/README.md).

## Executar e observar

Execute o servidor em um terminal e o piloto em outro, na raiz do projeto.
`uv run` coloca o Python do projeto no PATH também para os testes do workspace.

```sh
rtk proxy uv run flycodex serve --run-dir runs/pilot --port 8765
rtk proxy uv run flycodex run --data-dir data --run-dir runs/pilot --model gpt-6-astra
```

Abra <http://127.0.0.1:8765>. O servidor é somente leitura: não inicia ações,
não envia prompts e serve apenas os assets da interface, o snapshot público
e as imagens explicitamente registradas. O seletor de histórico permite
inspecionar escolhas neurais anteriores após a condição aleatória terminar.
A mosca desenhada é uma ilustração, sem simulação de locomoção.

`run` recusa dados ausentes ou com hashes incompatíveis antes de reservar um
envio. Registra modelo, versão da CLI, revisão do código, estado de alterações
locais, hashes, parâmetros e flags. Essas configurações ficam fixadas para a
retomada. O transporte usa aprovação `never`, sandbox `workspace-write`,
`--ignore-user-config`, eventos JSON, ID de sessão explícito e 300 segundos por
turno. O avaliador externo tem prazo de 30 segundos. Não há bypass de permissões
ou envio separado para inicializar a sessão; o contexto acompanha a primeira
instrução selecionada.

```sh
rtk proxy uv run flycodex status --run-dir runs/pilot
rtk proxy uv run flycodex report --run-dir runs/pilot --output-dir docs/results
```

O relatório exporta `pilot.json` e `pilot.md`, identificados como reais ou
sintéticos. Omite eventos brutos e IDs de sessão e substitui caminhos locais
conhecidos em diagnósticos. Revise os artefatos antes de qualquer publicação;
os comandos não criam repositórios remotos nem publicam resultados.

## Parada, orçamento e retomada

Toda tentativa de envio consome uma reserva **antes** de iniciar o Codex.
Reservas pendentes continuam consumidas, inclusive após falha ou interrupção.
Todos os envios reais, inclusive qualquer integração exploratória, devem usar
o mesmo `runs/pilot`; criar outro diretório não reinicia o orçamento autorizado.

Ctrl-C encerra o processo ativo e preserva os registros. Execute o mesmo comando
com o mesmo diretório para retomar. Uma interrupção tratada, com limpeza de
processos confirmada pelo transporte, aborta aquela tentativa e permite as
restantes. Não reenvia a instrução nem repete feedback. Após um crash sem prova
de que o processo antigo terminou, o piloto recusa a retomada com
`recovery_error`; é preciso inspecionar os journals e reconciliar manualmente.
Não apague reservas para contornar essa recusa.

Para parar em um ponto seguro, use `--stop-after-attempts 1`; o próximo `run`
continua a partir da tentativa seguinte. A rede adaptável restaura apenas o
último checkpoint confirmado e reinicia o estado dinâmico, retendo memória e
pesos. Um checkpoint confirmado ausente ou incompatível impede continuar.
A condição congelada começa novamente do estado original e verifica identidade
dos pesos a cada janela; a aleatória usa as sementes registradas 1729 e 1730.

## Contrato do experimento

A entrada exclusiva da política neural é RGB uint8 de 320 × 180. Cada decisão
avança 500 ms simulados. A diferença média direita menos esquerda em DNp20,
com disparos de habilitação DNpe017, seleciona Corrigir em ≥ +2 Hz, Testar em
≤ −2 Hz ou Investigar nos demais casos. O log registra o motivo e os neurônios.
Enquanto o Codex trabalha, o relógio neural pausa; o observatório indica a
atividade e preserva a imagem exata da escolha, sem substituí-la por uma
representação diferente.

| Ação | Instrução |
| --- | --- |
| Investigar | Analise a falha e explique a provável causa, sem editar. |
| Corrigir | Corrija a função de desconto, preservando os testes. |
| Testar | Execute os testes e relate o resultado. |

A tarefa corrige `discounted_total` para calcular
`subtotal_cents * (100 - discount_percent) // 100`. A avaliação aceita
intencionalmente uma função sem decoradores e com uma única expressão de
retorno de aritmética inteira; rejeita imports, chamadas, atributos e outras
operações com efeitos colaterais. Esse contrato é específico deste benchmark,
**não é um sandbox geral para Python arbitrário**. Os cinco testes confiáveis
ficam fora do workspace editável. Modificações de arquivos fixos encerram a
tentativa como violação, mesmo que todos os testes passem.

O feedback é o sinal da variação na contagem de testes passando. Cada avaliação
válida gera exatamente uma janela de feedback de 200 ms, inclusive a última
instrução: pulso positivo/negativo de 20 mV-equivalente, ou intervalo neutro sem
pulso externo. Uma violação não inventa um sinal negativo adicional. Falha de
infraestrutura não é regressão da tarefa e não gera feedback. A condição
aleatória registra o sinal sem fingir estímulo ou atividade neural.

## Artefatos e limites

- `data/`: fontes separadas, metadados normalizados, grafo e núcleo compilado.
- `runs/pilot/manifest.json`, `state.json`: configurações e reservas duráveis.
- `runs/pilot/controller.json`, `journal.jsonl`: estados, escolhas e limites de efeitos.
- `runs/pilot/attempts/<tentativa>/`: workspace dedicado, avaliador, eventos JSONL e checkpoints.
- `runs/pilot/public/`: snapshot atômico e PNGs exatos de observação/feedback.
- `docs/results/pilot.{json,md}`: relatório exportado; os checks neurais existentes permanecem separados.

Alteração sináptica e melhora na tarefa são medidas distintas. A regra de
plasticidade experimental do upstream pode alterar pesos durante a observação,
antes de qualquer recompensa. O feedback imediato pode não reconhecer uma
contribuição tardia de Investigar. Seis tentativas não estabelecem aprendizado,
generalização, significância estatística, compreensão de linguagem ou
experiência subjetiva. Resultados negativos e falhas de execução são resultados
válidos e permanecem registrados.

Código novo sob MIT, ao lado dos avisos preservados de Stonkfly/DOOMFLY. A rede
foi adaptada do [Stonkfly na revisão fixada](https://github.com/nftechie/stonkfly/commit/78ef3e05ab0fa086032098558d893667068944a0).
Os dados MaleCNS têm atribuição e licença separadas. Consulte
[THIRD_PARTY.md](THIRD_PARTY.md), a [proveniência neural](src/flycodex/neural/PROVENANCE.md)
e o [protocolo aprovado](docs/superpowers/specs/2026-09-13-flycodex-design.md).
