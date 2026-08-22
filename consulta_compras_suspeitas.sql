-- Consulta: compras importadas de XML que, com a lógica corrigida
-- (natOp="Venda a prazo" + tPag=05), NÃO deveriam ter sido fiado.
--
-- Pré-requisito: rode "Ver Produtos" ou "Importar XMLs Agora" pelo menos
-- uma vez ANTES de rodar esta consulta, para que a tabela xml_indexados
-- (esvaziada pela migração da correção) seja reconstruída com a lógica
-- nova. Sem isso, a consulta não encontra nada (índice vazio).
--
-- Como ler o resultado:
--   - forma_pagamento diferente de '05' (ex.: '04' = cartão de débito,
--     '03' = cartão de crédito) => venda no cartão importada por engano
--     como fiado. Candidata a exclusão manual.
--   - forma_pagamento NULL (xi.chave IS NULL) => a chave da compra não
--     foi encontrada no índice atual. Pode ser um arquivo que já não
--     está mais na pasta configurada (movido/apagado) — vale conferir
--     manualmente, mas não é necessariamente um erro do mesmo tipo.

SELECT
    c.id            AS compra_id,
    cl.nome         AS cliente,
    c.valor,
    c.data,
    c.status,
    c.origem_nfe_xml AS chave_nfe,
    xi.forma_pagamento,
    xi.natureza_operacao,
    xi.caminho_arquivo
FROM compras c
JOIN clientes cl ON cl.id = c.cliente_id
LEFT JOIN xml_indexados xi ON xi.chave = c.origem_nfe_xml
WHERE c.origem_nfe_xml IS NOT NULL
  AND (xi.eh_fiado IS DISTINCT FROM TRUE)
ORDER BY cl.nome, c.data;
