# Notas de viabilidade — 2026-09-13

## Observações verificadas

- A máquina local é ARM64 e tem 16 GiB de memória. A preparação real reteve 166.700 neurônios e 25.582.938 arestas; os 11 hashes dos arrays coincidiram com o upstream. Uma janela congelada de 500 ms reproduziu exatamente os disparos da implementação original. Os dados e resultados medidos estão em [reference-check.json](results/reference-check.json).
- A CLI local oferece `codex exec --json` e `codex exec resume` com ID de sessão explícito. A [documentação oficial de execução não interativa](https://learn.chatgpt.com/docs/non-interactive-mode) descreve eventos estruturados e continuação de sessões. Isso fornece uma possível integração com histórico e saída visível no terminal da demo.
- O [modelo do Stonkfly](https://github.com/nftechie/stonkfly/blob/main/docs/model.md) usa MaleCNS v1.0, uma projeção de pixels RGB em entradas visuais, um simulador de disparos neurais e uma regra experimental de plasticidade. Seu decodificador tem três resultados, mas os rótulos de trading são uma associação feita pelo projeto. A adaptação para instruções do Codex precisará explicitar outra associação e verificar a resposta ao painel.
- O [manifesto do Stonkfly](https://github.com/nftechie/stonkfly/blob/main/pyproject.toml) inclui dependências de trading. Reutilizar o núcleo neural exigirá avaliar seus limites de dependência antes de decidir entre uma dependência do projeto completo e uma adaptação dos módulos necessários.
- O [registro de atribuições](https://github.com/nftechie/stonkfly/blob/main/THIRD_PARTY.md) identifica a origem de componentes neurais no DOOMFLY e distingue o código do dataset baixado separadamente. Os avisos e termos das fontes efetivamente utilizadas precisam acompanhar o projeto.

## Recomendações da investigação

### Feedback

Incorporado ao desenho após o usuário pedir para continuar em 2026-09-13.

Usar a variação dos resultados de uma suíte fixa, executada pelo controlador após cada instrução concluída. Ganho de testes passando fornece feedback positivo; regressão fornece feedback negativo; resultado inalterado fica neutro. Falhas de infraestrutura encerram a tentativa e são registradas separadamente, sem se converter em feedback negativo à rede.

Manter os testes de avaliação fora da área editável pelo Codex e executar essa avaliação igualmente nas três condições. A instrução "Testar" continua permitindo ao Codex obter o diagnóstico para sua conversa; a avaliação externa garante que a pontuação não dependa do relato do Codex. Investigar pode ter valor atrasado, que essa regra simples talvez não consiga atribuir corretamente.

### Distribuição do piloto

Distribuição aprovada no [desenho consolidado](superpowers/specs/2026-09-13-flycodex-design.md).

Reservar até 10 instruções para cada condição: rede com adaptação, rede sem adaptação e escolha aleatória. Em cada condição, fazer duas tentativas de até cinco instruções, restaurando o código e abrindo uma sessão nova entre tentativas; terminar antes se todos os testes passarem. A rede adaptável poderá preservar sua adaptação entre as duas tentativas. Essas seis tentativas verificam o fluxo e os controles, sem constituir avaliação de generalização ou de aprendizado demonstrado.

### Integração inicial

Recomenda-se um controlador local que envie uma instrução por vez via `codex exec`, continue a conversa pelo ID explícito e apresente os eventos no terminal da demo. Os detalhes de permissões, interrupção e retomada precisam ser verificados na implementação. O painel sensorial recebe estado objetivo do controlador; o texto completo da conversa fica disponível para o espectador.

### Verificações do núcleo

O [probe real](results/neural-probe.json), sem chamadas ao Codex, comparou duas imagens a partir do mesmo estado neural inicial. Registrou feedback positivo e negativo em janelas separadas de 200 ms, alteração dos pesos adaptáveis, identidade dos pesos congelados após ambos os estímulos e restauração completa do checkpoint. Isso verifica mecanismos da implementação, sem demonstrar aprendizado da tarefa.

A ajuda da CLI 0.154.0 confirmou `--ignore-user-config` preservando autenticação, `--sandbox workspace-write`, aprovação `never` e retomada por ID. A combinação `codex -a never exec --sandbox workspace-write --ignore-user-config --json resume --help` foi aceita pelo parser sem enviar instruções. O transporte e a execução real ainda serão verificados pelo piloto.
