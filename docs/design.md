# Decisões da entrevista

## Primeira demo

Escolha delegada pelo usuário em 2026-09-12: a mosca orientará o Codex a corrigir uma função de cálculo de desconto em um pequeno repositório de demonstração com um bug proposital e testes fixos. O objetivo é corrigir a função sem alterar os testes que definem o resultado esperado.

O cenário inicial poderá ser restaurado para repetir o experimento. Uma execução bem-sucedida demonstra que o fluxo consegue resolver essa tarefa; isoladamente, não demonstra que a mosca aprendeu a escolher instruções melhores.

## Sessões do Codex

Decisão aceita em 2026-09-12: o projeto iniciará sessões dedicadas do Codex, visíveis durante a demo. Cada instrução e seu resultado devem poder ser acompanhados. A integração terá como alvo essas sessões, sem depender de terminais pessoais previamente abertos.

## Critério de publicação da primeira versão

Decisão aceita em 2026-09-12: a primeira versão terá treinamento experimental e comparação com escolhas aleatórias e com a rede sem adaptação. A publicação poderá ocorrer mesmo sem melhora demonstrada, apresentando os resultados e distinguindo adaptação da rede, sucesso do Codex na tarefa e evidência de aprendizado. O protocolo de avaliação ainda será definido.

## Base neural

Decisão aceita em 2026-09-12: usar conexões de um conectoma real de mosca como base da rede simulada, seguindo a linha do Stonkfly. A escolha não implica simulação biológica completa nem capacidade de compreender linguagem. Ver [ADR 0002](adr/0002-rede-baseada-em-conectoma.md).

## Entrada da mosca

Decisão aceita em 2026-09-12, com confirmação explícita de "painel": a mosca receberá um painel visual simplificado com o estado do Codex, a disponibilidade de resultado e a quantidade de testes passando ou falhando. O terminal do Codex continuará visível para quem acompanha a demo. A representação visual e sua ligação às entradas da rede ainda precisam ser definidas e verificadas; não se presume compreensão de linguagem ou de código pela mosca.

## Catálogo inicial de instruções

Decisão aceita em 2026-09-12: a mosca escolherá entre três instruções predefinidas:

- **Investigar:** "Analise a falha e explique a provável causa, sem editar."
- **Corrigir:** "Corrija a função de desconto, preservando os testes."
- **Testar:** "Execute os testes e relate o resultado."

A mosca seleciona a instrução e o Codex executa o trabalho correspondente. O mapeamento da atividade neural para essas três escolhas ainda será definido.

## Orçamento do piloto

Escolha delegada pelo usuário em 2026-09-13: o piloto inteiro terá teto de 30 instruções enviadas ao Codex, somando a condição com adaptação e as duas condições de comparação. Cada envio conta, inclusive uma nova tentativa após erro. O contador será persistido para que retomar o piloto não reinicie o orçamento. Ao atingir o limite, o experimento interromperá novos envios e salvará os resultados.

Esse teto limita as interações enviadas pelo experimento, não o número de chamadas internas do Codex nem um valor monetário fixo. O piloto serve para verificar o funcionamento do fluxo; não se presume que 30 instruções bastem para avaliar aprendizado.

## Feedback do treinamento

Após a proposta de feedback pelos testes, o usuário pediu para continuar em 2026-09-13. O desenho seguirá com feedback positivo quando aumentar a quantidade de testes passando, negativo quando diminuir e neutro quando permanecer igual. A avaliação será executada pelo controlador após cada instrução concluída, com testes fixos, sem depender do relato do Codex. Esse feedback simples pode não atribuir benefício a uma investigação que só ajude numa instrução posterior.

## Proposta consolidada

O [desenho do piloto](superpowers/specs/2026-09-13-flycodex-design.md) consolida as decisões da entrevista e apresenta as recomendações técnicas restantes para revisão conjunta. A base neural, a representação do painel, o mapeamento das escolhas e o protocolo têm parâmetros iniciais explícitos; seu funcionamento ainda depende de implementação e verificação.

## Pontos sujeitos à revisão do desenho

- Dataset do conectoma, simulador e mecanismo de adaptação.
- Codificação visual do painel, decodificação das escolhas e feedback.
- Distribuição das 30 instruções, feedback e protocolo de avaliação do aprendizado.

Este documento preserva as decisões da entrevista. A proposta consolidada aguarda confirmação de entendimento compartilhado antes da implementação.
