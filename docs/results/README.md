# Resultados medidos

Estes arquivos registram verificações reais feitas em 13 de setembro de 2026,
num Mac ARM64 com 16 GiB de RAM. Não contêm chamadas ao Codex nem resultados
do piloto de programação.

## Origem e referência numérica

[reference-check.json](reference-check.json) contém os hashes dos três arquivos
de origem e dos 11 arrays compilados. O grafo retido tem 166.700 neurônios e
25.582.938 arestas, representando 124.177.617 contatos sinápticos.

Com uma imagem uniforme RGB 240, pesos congelados e 500 ms simulados, a
adaptação reproduziu exatamente os 388.867 disparos da implementação original
fixada. O hash dos disparos foi
`776c33e872595a635845b0c3719c8343e425ee47ea968a242f2ba0cb79230704`.
Essa comparação verifica uma trajetória numérica; não valida a fisiologia
modelada nem todas as trajetórias possíveis.

## Entrada, feedback e memória

[neural-probe.json](neural-probe.json) compara imagens uniformes a partir do
mesmo estado inicial. Cada observação dura 500 ms simulados.

| Entrada | Esquerda | Direita | Habilitação | Escolha |
| --- | ---: | ---: | ---: | --- |
| RGB 0 | 14 Hz | 22 Hz | 13 disparos | Corrigir |
| RGB 255 | 30 Hz | 32 Hz | 17 disparos | Corrigir |

A entrada alterou a atividade, mas ambas produziram a mesma instrução. O probe
também registrou janelas separadas de feedback positivo e negativo de 200 ms,
alteração dos pesos adaptáveis, pesos congelados idênticos após ambos os
estímulos e restauração completa do estado salvo.

A regra do upstream pode alterar pesos durante a própria observação, antes
do estímulo externo. Portanto, alteração de pesos isoladamente não demonstra
que o feedback ensinou a tarefa. Estes testes não estabelecem aprendizado,
compreensão de linguagem ou capacidade de programar.
