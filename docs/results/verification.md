# Verificação da entrega

Verificação local em 13/09/2026, após as correções de `751c3c9`.

- `rtk proxy .venv/bin/python -m pytest`: **77 testes passaram**, em 15,33 s. Os testes são sintéticos e não enviam instruções ao Codex.
- `rtk proxy uv build`: distribuição de fontes e wheel gerados. Recursos neurais, núcleo C++ e assets do painel presentes; dados e sessões não incluídos.
- Wheel extraído numa pasta temporária fora do Git: importação, ajuda e `status` funcionaram. A verificação de origem recusou a instalação não editável com diagnóstico explícito, sem carregar o grafo ou executar Codex.
- Painel real conferido em 1440 px e 390 px, sem erro JavaScript ou transbordamento horizontal. A imagem selecionada corresponde ao hash e à resposta da tentativa histórica exibida.
- Os 18 pares de hashes PNG/RGB do relatório público foram conferidos contra as imagens publicadas.
- A revisão automatizada independente do conjunto encontrou cinco ajustes menores; uma revisão restrita às correções confirmou todos resolvidos, sem pendências.

O piloto real foi executado anteriormente em `a16e1713f340a15a4e87f2d5651536f03aa9fe3a`, com árvore limpa. As correções posteriores de apresentação, exportação e instalação não foram tratadas como uma nova execução. O relatório preserva essa revisão original, seis sucessos e nove envios; nenhuma chamada adicional foi feita para finalizar a entrega.

## Decisão de revisão registrada

Uma revisão intermediária das correções do avaliador foi bloqueada automaticamente duas vezes por possível risco de segurança, inclusive quando solicitada apenas inspeção estática defensiva. O coordenador realizou a inspeção estática local e usou a evidência dos testes existentes. O custo dessa decisão foi perder uma perspectiva independente naquela etapa. A revisão final independente do conjunto e a revisão das últimas correções foram concluídas posteriormente.
