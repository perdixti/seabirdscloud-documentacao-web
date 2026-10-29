# Excluir uma documentação completa

Disponível a partir da versão 2.9.0, em **Site e repositórios → Lixeira de páginas → Excluir definitivamente**. Funciona também com páginas enviadas à lixeira por versões anteriores.

1. Envie a página indesejada à lixeira, se ela ainda estiver na listagem do site.
2. Abra a lixeira e clique em **Excluir definitivamente** ao lado da página.
3. Confira o HTML, a quantidade de cadastros no catálogo, as imagens exclusivas e as imagens compartilhadas que serão mantidas.
4. Marque a confirmação e clique em **Excluir definitivamente**. Essa ação não tem restauração pela lixeira.
5. Use **Revisar publicação das remoções** para revisar e publicar as alterações no GitHub. Salvar ou excluir localmente não dispara a pipeline do S3.

A exclusão elimina a cópia do HTML na lixeira, todos os cadastros que apontam para essa página no catálogo configurado e as imagens locais referenciadas pelo HTML ou por seus cards que não sejam usadas em outros arquivos do site. A capa é incluída mesmo quando não aparece no corpo da documentação. Arquivos de imagem sem relação com a página e imagens externas não são excluídos. As pastas não são apagadas recursivamente.

São conferidas referências estáticas nos HTML, CSS, JavaScript, JSON, SVG e Markdown, inclusive imagens em srcset, estilos, outros cards e páginas ainda na lixeira. Fragmentos em scripts que possam usar uma imagem fazem a análise conservá-la. Imagens usadas somente por URLs montadas dinamicamente sem nomes identificáveis devem ser conferidas antes da exclusão. A revisão lista exatamente os arquivos que serão excluídos.

O catálogo usa a configuração salva em **Catálogo de documentações → Arquivo e página do catálogo**. O padrão é `js/projetos-conteudo.js`, com URLs relativas a `paginas/projetos.html`. Categorias vazias, comentários, propriedades extras e os demais cards são preservados. Catálogo ausente é permitido; catálogo inválido bloqueia a operação até a correção. O desfazer do catálogo é desativado após essa exclusão, para evitar restaurar cards de páginas inexistentes.

Se algum arquivo mudar depois da revisão, a operação é bloqueada sem apagar os itens. Clique em **Revisar novamente**. Uma página recriada no mesmo caminho também é preservada. Links simbólicos e caminhos fora da raiz não são excluídos. Se a análise não conseguir ler os arquivos, ela bloqueia a exclusão, em vez de presumir que uma imagem não está em uso.

A análise tem limite de 5000 arquivos de texto/50 MB, até 10 MB por arquivo; uma exclusão aceita até 1000 imagens/100 MB. Há cópias temporárias para recuperar uma falha durante a operação, removidas ao concluir. A cópia anterior do catálogo segue a política normal de backups de arquivos da aplicação.

## Atualizar o servidor

Extraia o pacote 2.9.0 numa pasta nova e, como root, na pasta `SeaBirdsCloud` extraída, execute:

```bash
bash deploy/update-app.sh
```

Recarregue o navegador após a atualização. Dados, configurações e sites existentes são preservados pelo atualizador.
