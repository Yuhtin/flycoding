# Mosca que orienta o Codex

Experimento open source em que uma mosca simulada escolhe instruções para orientar o Codex em tarefas de programação. Flycodex é o nome provisório da pasta de trabalho.

## Linguagem

**Mosca**:
Agente com rede simulada baseada em um conectoma real de mosca, cuja atividade neural determina a escolha da próxima instrução para o Codex.
_Evitar_: mosquito, gerador de texto

**Conectoma**:
Mapa de conexões neurais reconstruídas que fornece a base anatômica da rede da mosca. Não estabelece por si só a dinâmica ou as capacidades da simulação.
_Evitar_: cérebro completo emulado

**Instrução**:
Uma das opções de orientação disponíveis à mosca, expressa em um texto predefinido que pode ser enviado ao Codex.
_Evitar_: texto inventado pela mosca

**Investigar**:
Instrução para analisar a falha e explicar sua provável causa sem editar o código.

**Corrigir**:
Instrução para corrigir a função de desconto preservando os testes.

**Testar**:
Instrução para executar os testes e relatar o resultado.

**Escolha**:
Seleção de uma instrução a partir da atividade neural da mosca.
_Evitar_: geração de prompt

**Painel de observação**:
Representação visual simplificada do estado da tarefa apresentada à mosca, incluindo a atividade do Codex e os resultados dos testes.
_Evitar_: captura do terminal, leitura de código pela mosca

**Sessão da demo**:
Conversa dedicada com o Codex, iniciada pelo experimento e visível ao usuário, na qual são enviadas as instruções escolhidas pela mosca.
_Evitar_: terminal pessoal existente

**Treinamento experimental**:
Processo que adapta a rede a partir do feedback das tentativas. A existência dessa adaptação não implica melhora nas escolhas.
_Evitar_: aprendizado comprovado

**Aprendizado demonstrado**:
Melhora nas escolhas sustentada por avaliação comparativa, incluindo escolhas aleatórias e a rede sem adaptação.
_Evitar_: sucesso isolado, mudança de pesos

**Feedback**:
Sinal positivo, negativo ou neutro definido pela variação na quantidade de testes passando após uma instrução.
_Evitar_: opinião do Codex sobre o próprio resultado
